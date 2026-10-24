"""Read-only anonymous Twitch IRC client. Never sends a chat PRIVMSG."""

import contextlib
import random
import threading
from collections import deque


def parse_irc(line):
    tags = {}
    prefix = ""
    if line.startswith("@"):
        raw, _, line = line.partition(" ")
        for field in raw[1:].split(";"):
            key, _, value = field.partition("=")
            for old, new in [("\\s", " "), ("\\:", ";"), ("\\r", "\r"), ("\\n", "\n")]:
                value = value.replace(old, new)
            tags[key] = value.replace("\\\\", "\\")
    if line.startswith(":"):
        prefix, _, line = line[1:].partition(" ")
    head, separator, trailing = line.partition(" :")
    fields = head.split()
    return {
        "tags": tags,
        "prefix": prefix,
        "command": fields[0] if fields else "",
        "params": fields[1:],
        "text": trailing if separator else "",
    }


class TwitchClient:
    def __init__(self, channel, callback, connector=None):
        self.channel, self.callback = channel, callback
        self.connector = connector
        self.stop = threading.Event()
        self.thread = None
        self.socket = None
        self.status = "disconnected"
        self.error = None
        self.seen = set()
        self.order = deque()

    def start(self):
        self.thread = threading.Thread(target=self._run, name="twitch-" + self.channel, daemon=True)
        self.thread.start()

    def handle(self, line, send):
        message = parse_irc(line)
        command = message["command"]
        if command == "PING":
            send("PONG :" + message["text"] + "\r\n")
        elif command == "RECONNECT":
            raise ConnectionError("Twitch requested reconnection")
        elif command in {"001", "ROOMSTATE"}:
            self.status = "connected"
        elif command == "NOTICE":
            self.error = message["text"][:300]
        elif command == "PRIVMSG" and message["params"]:
            if message["params"][0].lower() != "#" + self.channel:
                return
            key = message["tags"].get("id")
            if key:
                if key in self.seen:
                    return
                self.seen.add(key)
                self.order.append(key)
                if len(self.order) > 1000:
                    self.seen.discard(self.order.popleft())
            username = message["prefix"].split("!", 1)[0]
            self.callback(self.channel, username, message["text"], key)

    def _run(self):
        delay = 1
        while not self.stop.is_set():
            try:
                self.status = "connecting"
                if self.connector is None:
                    from websockets.sync.client import connect

                    connector = connect
                else:
                    connector = self.connector
                with connector(
                    "wss://irc-ws.chat.twitch.tv:443",
                    open_timeout=10,
                    close_timeout=1,
                    max_size=1024 * 1024,
                ) as ws:
                    self.socket = ws
                    ws.send("CAP REQ :twitch.tv/tags twitch.tv/commands\r\n")
                    ws.send("PASS SCHMOOPIIE\r\n")
                    ws.send(f"NICK justinfan{random.randint(10000, 999999)}\r\n")
                    ws.send(f"JOIN #{self.channel}\r\n")
                    delay = 1
                    self.error = None
                    buffer = ""
                    while not self.stop.is_set():
                        try:
                            data = ws.recv(timeout=1)
                        except TimeoutError:
                            continue
                        if not isinstance(data, str):
                            continue
                        buffer += data
                        if len(buffer) > 1024 * 1024:
                            raise ConnectionError("Oversized IRC buffer")
                        while "\r\n" in buffer:
                            line, buffer = buffer.split("\r\n", 1)
                            self.handle(line, ws.send)
            except Exception as exc:
                self.status = "reconnecting" if not self.stop.is_set() else "disconnected"
                self.error = str(exc)[:300]
            finally:
                self.socket = None
            self.stop.wait(delay)
            delay = min(30, delay * 2)
        self.status = "disconnected"

    def close(self):
        self.stop.set()
        if self.socket:
            with contextlib.suppress(Exception):
                self.socket.close()
        if self.thread:
            self.thread.join(3)
