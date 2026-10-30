"""Local webhook credential, kept outside SQLite, imports, API snapshots and logs."""

import base64
import json
import os

from .domain import UserError
from .twitch_oauth import _protect


class DiscordWebhookCredential:
    def __init__(self, data_dir):
        self.path = data_dir / "credentials" / "discord-webhook.json"
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
            self.error = "Saved Discord webhook could not be read. Save it again."

    def save(self, token):
        import re

        # Restrict the authority/path; credentials must never reach arbitrary hosts.
        if not isinstance(token, str) or not re.fullmatch(
            r"https://discord\.com/api/webhooks/[0-9]{1,20}/[A-Za-z0-9_-]{20,200}", token.strip()
        ):
            raise UserError("Paste a Discord webhook URL copied from Server Settings.")
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
            raise UserError("Could not save the Discord webhook locally.") from None
        finally:
            temporary.unlink(missing_ok=True)
        self.token, self.error = token, None

    def forget(self):
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            raise UserError("Could not remove the saved Discord webhook.") from None
        self.token, self.error = "", None
