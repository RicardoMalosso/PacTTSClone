"""Durable Twitch event intake, moderation, reward management and settlement."""

import threading
import time
from datetime import datetime

from .domain import GenerationRequest, UserError
from .moderation import blocked_reason
from .twitch_events import CHAT, EVENT_TYPES, REWARD_UPDATE
from .twitch_oauth import TwitchAPIError


class TwitchActions:
    def __init__(self, studio):
        self.studio, self.store = studio, studio.store
        self.accounts = studio.accounts
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True, name="twitch-rewards")
        self.thread.start()

    def rewards(self, channel):
        uid = self.accounts.account(channel)["user_id"]
        all_rewards = self.accounts.api(
            channel, "GET", "/channel_points/custom_rewards", query={"broadcaster_id": uid}
        )["data"]
        managed = self.accounts.api(
            channel,
            "GET",
            "/channel_points/custom_rewards",
            query={"broadcaster_id": uid, "only_manageable_rewards": "true"},
        )["data"]
        ids = {r["id"] for r in managed}
        result = [
            {
                "id": r["id"],
                "title": r["title"],
                "cost": r["cost"],
                "is_enabled": r["is_enabled"],
                "manageable": r["id"] in ids,
                **{
                    key: r.get(setting, {}).get(key, 0)
                    if r.get(setting, {}).get("is_enabled") else 0
                    for key, setting in (
                        ("global_cooldown_seconds", "global_cooldown_setting"),
                        ("max_per_stream", "max_per_stream_setting"),
                        ("max_per_user_per_stream", "max_per_user_per_stream_setting"),
                    )
                },
            }
            for r in all_rewards
        ]
        self.store.put("twitch_rewards", channel, {"rewards": result})
        return result

    @staticmethod
    def reward_limits(values):
        body = {}
        for key, flag, maximum in (
            ("global_cooldown_seconds", "is_global_cooldown_enabled", 604800),
            ("max_per_stream", "is_max_per_stream_enabled", 2147483647),
            ("max_per_user_per_stream", "is_max_per_user_per_stream_enabled", 2147483647),
        ):
            value = values.get(key, 0)
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
                raise UserError(f"{key} must be an integer between 0 and {maximum}.")
            body[flag] = value > 0
            if value:
                body[key] = value
        return body

    def update_reward_limits(self, channel, reward_id, values):
        body = self.reward_limits(values)
        reward = next((r for r in self.rewards(channel) if r["id"] == reward_id), None)
        if not reward or not reward["manageable"]:
            raise UserError("Only rewards created by this Twitch application can be edited here.")
        uid = self.accounts.account(channel)["user_id"]
        self.accounts.api(
            channel, "PATCH", "/channel_points/custom_rewards",
            query={"broadcaster_id": uid, "id": reward_id}, body=body,
        )
        return self.rewards(channel)

    def create_reward(self, channel, title, cost, limits=None):
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 45:
            raise UserError("Reward title must contain 1–45 characters.")
        if isinstance(cost, bool) or not isinstance(cost, int) or not 1 <= cost <= 1000000000:
            raise UserError("Reward cost must be a positive integer.")
        limit_body = self.reward_limits(limits or {})
        uid = self.accounts.account(channel)["user_id"]
        result = self.accounts.api(
            channel,
            "POST",
            "/channel_points/custom_rewards",
            query={"broadcaster_id": uid},
            body={
                **limit_body,
                "title": title.strip(),
                "cost": cost,
                "is_user_input_required": True,
                "should_redemptions_skip_request_queue": False,
                "prompt": "Enter the text for local TTS.",
            },
        )["data"][0]
        self.rewards(channel)
        return {"id": result["id"], "title": result["title"], "cost": result["cost"]}

    def reconcile(self, channel):
        """Refund missed managed redemptions, never replay old speech on reconnect."""
        config = self.store.get("channel", channel) or {}
        reward_ids = {
            r["reward_id"] for r in config.get("event_rules", []) if r["kind"] == "reward"
        }
        if not reward_ids:
            return
        cutoff = time.time() - 2
        try:
            rewards = self.rewards(channel)
            uid = self.accounts.account(channel)["user_id"]
            for reward in rewards:
                if not reward["manageable"] or reward["id"] not in reward_ids:
                    continue
                cursor = None
                for _ in range(20):
                    query = {
                        "broadcaster_id": uid,
                        "reward_id": reward["id"],
                        "status": "UNFULFILLED",
                        "first": 50,
                    }
                    if cursor:
                        query["after"] = cursor
                    page = self.accounts.api(
                        channel, "GET", "/channel_points/custom_rewards/redemptions", query=query
                    )
                    for redemption in page.get("data", []):
                        claimed = channel + ":" + redemption["id"]
                        redeemed_at = datetime.fromisoformat(
                            redemption["redeemed_at"].replace("Z", "+00:00")
                        ).timestamp()
                        if redeemed_at >= cutoff:
                            continue
                        with self.studio.chat_lock:
                            if self.store.get("twitch_redemption", claimed):
                                continue
                            self.store.put("twitch_redemption", claimed, {"id": claimed})
                            key = channel + ":recovered:" + redemption["id"]
                            self.store.put(
                                "twitch_event",
                                key,
                                {
                                    "id": key,
                                    "channel": channel,
                                    "kind": "reward",
                                    "username": redemption.get("user_name", "Viewer"),
                                    "created_at": time.time(),
                                    "text": "",
                                    "job_id": None,
                                    "status": "blocked",
                                    "reward_id": reward["id"],
                                    "redemption_id": redemption["id"],
                                    "settlement": "pending",
                                    "settlement_error": None,
                                    "reason": "Missed while disconnected; refund without replay.",
                                },
                            )
                    cursor = page.get("pagination", {}).get("cursor")
                    if not cursor:
                        break
        except UserError as exc:
            self.store.put("twitch_recovery", channel, {"error": str(exc)})
            return
        self.store.delete("twitch_recovery", channel)

    def receive(self, channel, event_type, event, metadata):
        config = self.store.get("channel", channel)
        if not config or not config["enabled"] or config.get("transport", "irc") != "oauth":
            return
        message_id = metadata.get("message_id", "")
        if not isinstance(message_id, str) or not 1 <= len(message_id) <= 200:
            return
        try:
            stamp = datetime.fromisoformat(
                metadata["message_timestamp"].replace("Z", "+00:00")
            ).timestamp()
        except (KeyError, TypeError, ValueError):
            return
        if not -60 <= time.time() - stamp <= 600:
            return
        key = channel + ":" + message_id
        with self.studio.chat_lock:
            # Claim before allocating generation. Restart never replays stale paid events.
            if self.store.get("twitch_seen", key):
                return
            self.store.put("twitch_seen", key, {"id": key, "created_at": time.time()})
            if event_type == CHAT:
                self.studio.receive(
                    channel,
                    event.get("chatter_user_name", "Viewer"),
                    event.get("message", {}).get("text", ""),
                    message_id,
                )
                return
            if event_type == REWARD_UPDATE:
                if event.get("status") in {"canceled", "fulfilled"}:
                    for previous in self.store.all("twitch_event", 10000):
                        if (
                            previous.get("redemption_id") == event.get("id")
                            and previous["channel"] == channel
                        ):
                            if previous.get("job_id") and event["status"] == "canceled":
                                self.studio.cancel_job(previous["job_id"])
                            self.store.patch(
                                "twitch_event",
                                previous["id"],
                                settlement="CANCELED"
                                if event["status"] == "canceled"
                                else "FULFILLED",
                                settlement_error=None,
                            )
                return
            kind = next((k for k, v in EVENT_TYPES.items() if v == event_type), None)
            if not kind:
                return
            reward_id = event.get("reward", {}).get("id", "")
            # Gift purchases are handled once by gift, not again for each recipient.
            if kind == "subscribe" and event.get("is_gift"):
                return
            rule = next(
                (
                    r
                    for r in config.get("event_rules", [])
                    if r["kind"] == kind and (kind != "reward" or r["reward_id"] == reward_id)
                ),
                None,
            )
            if not rule or (kind == "bits" and event.get("bits", 0) < rule["min_bits"]):
                return
            if kind == "reward" and self.store.get(
                "twitch_redemption", channel + ":" + event["id"]
            ):
                return
            if kind == "reward":
                self.store.put(
                    "twitch_redemption",
                    channel + ":" + event["id"],
                    {"id": channel + ":" + event["id"]},
                )
            username = (
                event.get("user_name") or event.get("from_broadcaster_user_name") or "Anonymous"
            )
            raw_text = event.get("user_input", "") if kind == "reward" else event.get("message", "")
            raw_text = raw_text or ""
            if isinstance(raw_text, dict):
                raw_text = raw_text.get("text", "")
                # Cheermotes are payment markers, not words to synthesize.
                if kind == "bits":
                    fragments = event.get("message", {}).get("fragments", [])
                    if fragments:
                        raw_text = "".join(
                            f.get("text", "") for f in fragments if f.get("type") != "cheermote"
                        )
            values = {
                "username": username,
                "text": raw_text.strip(),
                "bits": event.get("bits", 0),
                "total": event.get("total", 1),
                "tier": event.get("tier", ""),
                "months": event.get("cumulative_months", 0),
                "viewers": event.get("viewers", 0),
                "reward": event.get("reward", {}).get("title", ""),
            }
            text = rule["template"].format_map(values).strip()
            known_rewards = (self.store.get("twitch_rewards", channel) or {}).get("rewards", [])
            manageable = (
                kind == "reward"
                and event.get("status") == "unfulfilled"
                and any(r["id"] == reward_id and r["manageable"] for r in known_rewards)
            )
            record = {
                "id": key,
                "channel": channel,
                "kind": kind,
                "username": username,
                "created_at": time.time(),
                "text": text[:2000],
                "status": "received",
                "job_id": None,
                "reason": None,
                "reward_id": reward_id,
                "redemption_id": event.get("id") if kind == "reward" else None,
                "settlement": "pending" if manageable else "external",
                "settlement_error": None,
            }
            self.store.put("twitch_event", key, record)
            reason = None
            if not text or len(text) > config["max_message_chars"]:
                reason = "empty or overlong message"
            reason = reason or blocked_reason(
                text, config["filter_level"], config["custom_filters"]
            )
            cooldown = (channel, username.casefold())
            if (
                not reason
                and time.time() - self.studio.cooldowns.get(cooldown, 0)
                < config["user_cooldown_seconds"]
            ):
                reason = "user cooldown"
            job = None
            if not reason:
                try:
                    job = self.studio.voices.generate(
                        rule["voice_id"], GenerationRequest(text=text), channel, username
                    )
                    self.studio.cooldowns[cooldown] = time.time()
                except (UserError, OSError) as exc:
                    reason = str(exc)
            if reason:
                self.studio.service.reject_request(
                    text, reason, channel=channel, username=username, voice_id=rule["voice_id"]
                )
            self.store.patch(
                "twitch_event",
                key,
                status="accepted" if job else "blocked",
                reason=reason,
                job_id=job["id"] if job else None,
            )

    def settle(self):
        with self.studio.chat_lock:
            events = self.store.all("twitch_event", 10000)
        for event in events:
            if event["status"] == "received" and time.time() - event["created_at"] < 30:
                continue
            if event["settlement"] != "pending" or time.time() < event.get("retry_at", 0):
                continue
            job = self.studio.service.get(event["job_id"]) if event.get("job_id") else None
            status = None
            if event["status"] in {"blocked", "received"} or not job:
                status = "CANCELED"
            elif job["status"] in {"failed", "cancelled"} or job.get("playback_error"):
                status = "CANCELED"
            elif job["status"] == "succeeded":
                items = [
                    i
                    for i in self.store.channel_records("playback", event["channel"])
                    if i["job_id"] == job["id"] and not i.get("replay")
                ]
                if any(i["status"] == "played" for i in items):
                    status = "FULFILLED"
                elif items and all(
                    i["status"] not in {"queued", "countdown", "ready", "playing"} for i in items
                ):
                    status = "CANCELED"
            if not status:
                continue
            try:
                uid = self.accounts.account(event["channel"])["user_id"]
                self.accounts.api(
                    event["channel"],
                    "PATCH",
                    "/channel_points/custom_rewards/redemptions",
                    query={
                        "broadcaster_id": uid,
                        "reward_id": event["reward_id"],
                        "id": event["redemption_id"],
                    },
                    body={"status": status},
                )
                self.store.patch(
                    "twitch_event", event["id"], settlement=status, settlement_error=None
                )
            except UserError as exc:
                # A successful PATCH with a lost response may return 404 on retry.
                # Reconcile terminal state instead of refunding or retrying forever.
                if isinstance(exc, TwitchAPIError) and exc.status == 404:
                    try:
                        result = self.accounts.api(
                            event["channel"],
                            "GET",
                            "/channel_points/custom_rewards/redemptions",
                            query={
                                "broadcaster_id": uid,
                                "reward_id": event["reward_id"],
                                "id": event["redemption_id"],
                            },
                        )
                        remote = next(
                            (
                                r
                                for r in result.get("data", [])
                                if r["id"] == event["redemption_id"]
                            ),
                            None,
                        )
                        if remote and remote["status"] in {"FULFILLED", "CANCELED"}:
                            self.store.patch(
                                "twitch_event",
                                event["id"],
                                settlement=remote["status"],
                                settlement_error=None,
                            )
                            continue
                    except UserError:
                        pass
                self.store.patch(
                    "twitch_event",
                    event["id"],
                    settlement_error=str(exc),
                    retry_at=time.time() + 60,
                )

    def _run(self):
        while not self.stop.wait(1):
            try:
                self.settle()
                with self.studio.chat_lock:
                    for kind, limit in (
                        ("twitch_seen", 10000),
                        ("twitch_redemption", 10000),
                        ("twitch_event", 1000),
                    ):
                        for old in self.store.all(kind, 100000)[limit:]:
                            if old.get("settlement") != "pending":
                                self.store.delete(kind, old["id"])
            except Exception:
                # Individual network errors are persisted above. Shutdown remains bounded.
                continue

    def close(self):
        self.stop.set()
        self.thread.join(3)
