"""EventSub WebSocket receiver. Chat and paid events share no IRC connection."""

import contextlib
import json
import threading
import time
from urllib.parse import urlsplit

from .domain import UserError

EVENT_TYPES = {
    "reward": "channel.channel_points_custom_reward_redemption.add",
    "bits": "channel.bits.use",
    "subscribe": "channel.subscribe",
    "gift": "channel.subscription.gift",
    "resub": "channel.subscription.message",
    "subscription_end": "channel.subscription.end",
    "follow": "channel.follow",
    "raid": "channel.raid",
    "online": "stream.online",
    "offline": "stream.offline",
}
REWARD_UPDATE = "channel.channel_points_custom_reward_redemption.update"
CHAT = "channel.chat.message"
SOCKET_URL = "wss://eventsub.wss.twitch.tv/ws?keepalive_timeout_seconds=30"


class EventSubClient:
    def __init__(self, channel, accounts, store, callback, connector=None, on_connected=None):
        self.channel, self.accounts, self.store, self.callback = channel, accounts, store, callback
        self.connector = connector
        self.on_connected = on_connected or (lambda channel: None)
        self.stop = threading.Event()
        self.thread = None
        self.socket = None
        self.status, self.error = "disconnected", None
        self.subscriptions, self.subscription_errors = [], {}
        self.gap_since = None

    def start(self):
        self.thread = threading.Thread(
            target=self._run, daemon=True, name="eventsub-" + self.channel
        )
        self.thread.start()

    def subscribe(self, session_id):
        config = self.store.get("channel", self.channel)
        account = self.accounts.account(self.channel)
        uid = account["user_id"]
        types = {EVENT_TYPES[r["kind"]] for r in config.get("event_rules", [])}
        if config.get("commands"):
            types.add(CHAT)
        if EVENT_TYPES["reward"] in types:
            types.add(REWARD_UPDATE)
        # Always maintain a useful connection even before configuring actions.
        if not types:
            types.add("stream.online")
        self.subscriptions, self.subscription_errors = [], {}
        for event_type in sorted(types):
            condition = {"broadcaster_user_id": uid}
            if event_type == CHAT:
                condition["user_id"] = uid
            elif event_type == "channel.follow":
                condition["moderator_user_id"] = uid
            elif event_type == "channel.raid":
                condition = {"to_broadcaster_user_id": uid}
            try:
                self.accounts.api(
                    self.channel,
                    "POST",
                    "/eventsub/subscriptions",
                    body={
                        "type": event_type,
                        "version": "2" if event_type == "channel.follow" else "1",
                        "condition": condition,
                        "transport": {"method": "websocket", "session_id": session_id},
                    },
                )
                self.subscriptions.append(event_type)
            except UserError as exc:
                self.subscription_errors[event_type] = str(exc)
        if not self.subscriptions:
            raise UserError("No Twitch event subscriptions succeeded. Check authorization scopes.")
        self.status = "connected" if not self.subscription_errors else "partial"
        self.error = (
            "Some event subscriptions failed. Check permissions."
            if self.subscription_errors
            else None
        )

    def handle(self, message):
        metadata, payload = message["metadata"], message.get("payload", {})
        kind = metadata["message_type"]
        if kind == "notification":
            event_type = metadata.get("subscription_type")
            if event_type not in self.subscriptions:
                return
            account = self.accounts.account(self.channel)
            event = payload.get("event", {})
            uid = (
                event.get("to_broadcaster_user_id")
                if event_type == "channel.raid"
                else event.get("broadcaster_user_id")
            )
            if uid != account["user_id"]:
                return
            self.callback(self.channel, event_type, event, metadata)
        elif kind == "revocation":
            event_type = payload.get("subscription", {}).get("type", "unknown")
            if event_type in self.subscriptions:
                self.subscriptions.remove(event_type)
            self.subscription_errors[event_type] = "Subscription revoked. Authorize again."
            self.error, self.status = (
                "Twitch revoked an event subscription. Authorize again.",
                "partial",
            )
        elif kind == "session_reconnect":
            url = payload["session"]["reconnect_url"]
            parsed = urlsplit(url)
            if (
                parsed.scheme != "wss"
                or parsed.hostname != "eventsub.wss.twitch.tv"
                or parsed.username
                or parsed.port not in {None, 443}
            ):
                raise UserError("Unexpected Twitch reconnect address.")
            return url

    def _open(self, connector, url):
        return connector(url, open_timeout=10, close_timeout=1, max_size=1024 * 1024)

    def _welcome(self, ws):
        message = json.loads(ws.recv(timeout=10))
        if message.get("metadata", {}).get("message_type") != "session_welcome":
            raise ConnectionError("Missing EventSub welcome")
        return message["payload"]["session"]

    def _run(self):
        delay = 1
        while not self.stop.is_set():
            ws = None
            try:
                self.status = "connecting"
                self.accounts.account(self.channel)
                if self.connector is None:
                    from websockets.sync.client import connect

                    connector = connect
                else:
                    connector = self.connector
                ws = self._open(connector, SOCKET_URL)
                self.socket = ws
                session = self._welcome(ws)
                self.subscribe(session["id"])
                self.on_connected(self.channel)
                silence = session.get("keepalive_timeout_seconds") or 30
                last = time.monotonic()
                delay = 1
                while not self.stop.is_set():
                    try:
                        message = json.loads(ws.recv(timeout=1))
                    except TimeoutError:
                        if time.monotonic() - last > silence + 2:
                            raise ConnectionError("EventSub heartbeat expired") from None
                        self.accounts.account(
                            self.channel
                        )  # hourly validation, including idle streams
                        continue
                    last = time.monotonic()
                    reconnect = self.handle(message)
                    if reconnect:
                        # Keep the old socket open until the replacement welcomes us.
                        replacement = self._open(connector, reconnect)
                        try:
                            session = self._welcome(replacement)
                        except Exception:
                            replacement.close()
                            raise
                        ws.close()
                        ws = replacement
                        self.socket = ws
                        silence = session.get("keepalive_timeout_seconds") or silence
                        last = time.monotonic()
                        # Twitch transfers subscriptions; do not create duplicates.
            except Exception as exc:
                self.status = "reconnecting" if not self.stop.is_set() else "disconnected"
                self.gap_since = time.time()
                self.error = (
                    str(exc)
                    if isinstance(exc, UserError)
                    else "Twitch connection lost; events during the gap may be missed."
                )
            finally:
                self.socket = None
                if ws:
                    with contextlib.suppress(Exception):
                        ws.close()
            self.stop.wait(delay)
            delay = min(60, delay * 2)
        self.status = "disconnected"

    def close(self):
        self.stop.set()
        if self.socket:
            with contextlib.suppress(Exception):
                self.socket.close()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(3)
