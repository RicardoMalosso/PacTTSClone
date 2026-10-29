"""Local bot credential, kept outside SQLite, imports, API snapshots and logs."""

import base64
import json
import os

from .domain import UserError
from .twitch_oauth import _protect


class DiscordCredential:
    def __init__(self, data_dir):
        self.path = data_dir / "credentials" / "discord.json"
        self.path.parent.mkdir(mode=0o700, exist_ok=True)
        self.token = ""
        self.error = None
        try:
            envelope = json.loads(self.path.read_text())
            data = base64.b64decode(envelope["data"], validate=True)
            if envelope["protection"] == "dpapi":
                data = _protect(data, decrypt=True)
            elif envelope["protection"] != "permissions":
                raise ValueError("Unknown credential protection")
            self.token = data.decode()
        except FileNotFoundError:
            pass
        except (OSError, ValueError, KeyError, TypeError):
            self.error = "Saved Discord token could not be read. Save it again."

    def save(self, token):
        # Never reflect even malformed credentials through validation errors.
        if (
            not isinstance(token, str)
            or not 20 <= len(token.strip()) <= 256
            or any(c.isspace() for c in token.strip())
        ):
            raise UserError("Enter a Discord bot token, without the Bot prefix.")
        token = token.strip()
        data = token.encode()
        mode = "dpapi" if os.name == "nt" else "permissions"
        temporary = self.path.with_suffix(".tmp")
        try:
            if mode == "dpapi":
                data = _protect(data)
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as stream:
                json.dump({"protection": mode, "data": base64.b64encode(data).decode()}, stream)
            if os.name != "nt":
                temporary.chmod(0o600)
            temporary.replace(self.path)
        except OSError:
            raise UserError("Could not save the Discord token locally.") from None
        finally:
            temporary.unlink(missing_ok=True)
        self.token, self.error = token, None

    def forget(self):
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            raise UserError("Could not remove the saved Discord token.") from None
        self.token, self.error = "", None
