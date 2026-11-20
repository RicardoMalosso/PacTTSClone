import threading
from types import SimpleNamespace
from unittest.mock import Mock

from pacttsclone.studio import Studio
from pacttsclone.twitch_directory import TwitchDirectory, directory_messages
from pacttsclone.twitch_oauth import TwitchAPIError


def test_directory_format_and_engine_tags():
    assert directory_messages(["!rag", "!pac"], [], "kittentts2") == [
        "Available voices: !pac, !rag | Available SFX: none"
    ]
    for engine, tag in (("omnivoice", "[sigh]"), ("ming-3", "[Sigh]")):
        line, = directory_messages([], [], engine)
        assert line.startswith("Available voices: none | Available SFX: ")
        assert tag in line.split()


def test_directory_split_preserves_whole_entries_once():
    commands = [f"!voice_{i:02}" for i in range(50)]
    triggers = [f"[a long sound {i:02}]" for i in range(80)]
    lines = directory_messages(commands, [{"triggers": triggers}], "kittentts2")
    assert len(lines) >= 3 and all(len(line) <= 500 for line in lines)
    voices, effects = [], []
    for line in lines:
        for part in line.split(" | "):
            if part.startswith("Available voices: "):
                voices.extend(part.removeprefix("Available voices: ").split(", "))
            else:
                assert part.startswith("Available SFX: ")
                effects.extend(part.removeprefix("Available SFX: ")[1:-1].split("] ["))
    assert voices == commands
    assert effects == [t[1:-1] for t in triggers]


def test_channel_intake_coalesces_and_retries_without_generating():
    accounts = Mock()
    accounts.snapshot.return_value = {"scopes": ["user:write:chat"]}
    accounts.account.return_value = {"user_id": "123"}
    configs = {
        channel: {"enabled": True, "transport": "oauth", "commands": commands}
        for channel, commands in (("one", {"!pac": "v", "!alias": "v", "!old": "removed"}),
                                  ("two", {"!rag": "v"}))
    }
    store = Mock()
    store.get.side_effect = lambda kind, key: configs[key] if kind == "channel" else key == "v"
    tags = [f"[long sound {i:02}]" for i in range(90)]
    effects = [{"triggers": tags}, {"triggers": ["[off]"], "enabled": False}]
    store.all.side_effect = lambda kind, *args: effects if kind == "sfx" else [{"id": "v"}]
    studio = SimpleNamespace(store=store, accounts=accounts, chat_lock=threading.RLock(),
                             service=SimpleNamespace(settings=SimpleNamespace(engine_id="unknown")))
    directory = studio.directory = TwitchDirectory(studio)
    sent = []
    started, resume = threading.Event(), threading.Event()

    def send(channel, method, path, body):
        assert (method, path) == ("POST", "/chat/messages")
        assert body["sender_id"] == body["broadcaster_id"] == "123"
        if not started.is_set():
            started.set()
            assert resume.wait(3)
            raise TwitchAPIError(429, retry_after=11)
        sent.append(body["message"])
        return {"data": [{"is_sent": True}]}

    accounts.api.side_effect = send
    directory.stop.wait = Mock(return_value=False)
    try:
        Studio.receive(studio, "one", "viewer", " !PacTTS ")
        assert started.wait(3)
        worker = directory.workers["one"]
        Studio.receive(studio, "one", "other", "!pactts")
        resume.set()
        worker.join(3)
        expected = directory_messages(["!alias", "!pac"], effects, "unknown")
        assert sent == expected
        assert [c.args[0] for c in directory.stop.wait.call_args_list] == [11] + [2] * len(sent)
        configs["two"]["sfx_enabled"] = False
        directory._reply("two")
        assert sent[-1] == "Available voices: !rag | Available SFX: none"
        accounts.snapshot.return_value = {"scopes": []}
        directory._reply("two")
        assert len(sent) == len(expected) + 1
    finally:
        resume.set()
        directory.close()
