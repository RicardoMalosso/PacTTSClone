"""Viewer-facing voice and sound directory, sent through broadcaster OAuth."""

import logging
import threading

from .domain import UserError
from .twitch_oauth import FEATURE_SCOPES, TwitchAPIError

VOCAL_TAGS = {
    "omnivoice": (
        "[laughter] [sigh] [confirmation-en] [question-en] [question-ah] [question-oh] "
        "[question-ei] [question-yi] [surprise-ah] [surprise-oh] [surprise-wa] [surprise-yo] "
        "[dissatisfaction-hnn] [sniff]"
    ).split(),
    "ming-3": (
        "[Breathing] [Cough] [Sigh] [Laughter] [Surprise-ah] [Surprise-oh] "
        "[Dissatisfaction-hnn] [Uhm] [Confirmation-en] [Question-ei] [Question-ah] "
        "[Question-en] [Question-oh] [Question-huh]"
    ).split(),
}


def directory_messages(commands, effects, engine):
    sounds = {tag.casefold(): tag for tag in VOCAL_TAGS.get(engine, ())}
    for effect in effects:
        if effect.get("enabled", True):
            sounds.update((tag.casefold(), tag) for tag in effect["triggers"])
    messages = []
    line = ""
    for heading, items, separator in (
        ("Available voices: ", sorted(commands), ", "),
        ("Available SFX: ", [sounds[k] for k in sorted(sounds)], " "),
    ):
        for index, item in enumerate(items or ["none"]):
            prefix = ((" | " if line else "") + heading) if index == 0 else separator
            if len(line + prefix + item) > 500:
                messages.append(line)
                line = heading + item
            else:
                line += prefix + item
    return [*messages, line]


class TwitchDirectory:
    def __init__(self, studio):
        self.studio = studio
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.workers = {}

    def request(self, channel):
        with self.lock:
            if self.stop.is_set() or channel in self.workers:
                return
            thread = threading.Thread(target=self._reply, args=(channel,), daemon=True)
            self.workers[channel] = thread
            thread.start()

    def _reply(self, channel):
        store = self.studio.store
        try:
            config = store.get("channel", channel) or {}
            if not config.get("enabled") or config.get("transport") != "oauth":
                return
            accounts = self.studio.accounts
            scope = FEATURE_SCOPES["directory"]
            if scope not in accounts.snapshot(channel)["scopes"]:
                return
            uid = accounts.account(channel)["user_id"]
            voices = {v for v in set(config["commands"].values()) if store.get("voice", v)}
            commands = [key for key, voice in config["commands"].items() if voice in voices]
            effects = (
                store.all("sfx")
                if config.get("sfx_enabled", True) and config.get("max_sfx", 8) else []
            )
            engine = self.studio.service.settings.engine_id
            for message in directory_messages(commands, effects, engine):
                while not self.stop.is_set():
                    current = store.get("channel", channel) or {}
                    if not current.get("enabled") or current.get("transport") != "oauth":
                        return
                    try:
                        response = accounts.api(channel, "POST", "/chat/messages", body={
                            "broadcaster_id": uid, "sender_id": uid, "message": message,
                        })
                    except TwitchAPIError as exc:
                        if exc.status != 429:
                            raise
                        self.stop.wait(exc.retry_after)
                        continue
                    if not any(row.get("is_sent") for row in response.get("data", [])):
                        raise UserError("Twitch declined the !pactts chat reply.")
                    break
                if self.stop.wait(2):
                    return
        except UserError as exc:
            logging.getLogger(__name__).warning("Directory reply for %s: %s", channel, exc)
        finally:
            with self.lock:
                self.workers.pop(channel, None)

    def close(self):
        with self.lock:
            self.stop.set()
            workers = list(self.workers.values())
        for thread in workers:
            thread.join()
