"""Host-only public-client Device OAuth and Helix. Never expose tokens to the UI."""

import base64
import contextlib
import ctypes
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .domain import UserError

FEATURE_SCOPES = {
    "chat": "user:read:chat",
    "rewards": "channel:manage:redemptions",
    "bits": "bits:read",
    "subscriptions": "channel:read:subscriptions",
    "follows": "moderator:read:followers",
}


class TwitchAPIError(UserError):
    def __init__(self, status, code=""):
        self.status, self.code = status, code
        super().__init__(f"Twitch request failed ({status}). Reconnect or check permissions.")


def http_json(method, url, *, headers=None, form=None, body=None):
    headers = dict(headers or {})
    data = None
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read(2 * 1024 * 1024)) if response.status != 204 else {}
    except urllib.error.HTTPError as exc:
        # Never propagate URLs, request headers, tokens or arbitrary remote text.
        with contextlib.suppress(ValueError, OSError):
            payload = json.loads(exc.read(4096))
            code = payload.get("error", "") or payload.get("message", "")
            if code in {"authorization_pending", "slow_down", "access_denied", "expired_token"}:
                raise TwitchAPIError(exc.code, code) from None
        raise TwitchAPIError(exc.code) from None
    except (OSError, ValueError) as exc:
        raise UserError("Cannot reach Twitch. Check the connection and retry.") from exc


def _protect(data, decrypt=False):
    """Windows user-bound DPAPI; no portable encryption key shipped with the app."""
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_char))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    target = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if decrypt:
        fn = crypt.CryptUnprotectData
        fn.argtypes = [
            ctypes.POINTER(Blob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(Blob),
        ]
        args = (ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
    else:
        fn = crypt.CryptProtectData
        fn.argtypes = [
            ctypes.POINTER(Blob),
            wintypes.LPCWSTR,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(Blob),
        ]
        args = (
            ctypes.byref(source),
            "PacTTSClone Twitch",
            None,
            None,
            None,
            1,
            ctypes.byref(target),
        )
    fn.restype = wintypes.BOOL
    if not fn(*args):
        raise OSError("Windows credential protection failed.")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(target.data)


class TwitchAccounts:
    def __init__(self, data_dir: Path, on_change, http=http_json):
        self.path = data_dir / "credentials" / "twitch.json"
        self.path.parent.mkdir(mode=0o700, exist_ok=True)
        self.http, self.on_change = http, on_change
        self.lock = threading.RLock()
        self.pending, self.threads, self.errors = {}, [], {}
        self.closed = False
        self.accounts = {}
        try:
            envelope = json.loads(self.path.read_text())
            data = base64.b64decode(envelope["data"])
            if envelope["protection"] == "dpapi":
                data = _protect(data, decrypt=True)
            self.accounts = json.loads(data)
            for value in self.accounts.values():
                value["validated_at"] = 0
        except FileNotFoundError:
            pass
        except (OSError, ValueError, KeyError):
            self.errors["storage"] = (
                "Saved Twitch authorization could not be read. Authorize again."
            )

    def _save(self):
        data = json.dumps(self.accounts).encode()
        mode = "dpapi" if os.name == "nt" else "permissions"
        if mode == "dpapi":
            data = _protect(data)
        temporary = self.path.with_suffix(".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump({"protection": mode, "data": base64.b64encode(data).decode()}, stream)
        temporary.replace(self.path)
        if os.name != "nt":
            self.path.chmod(0o600)

    def snapshot(self, channel):
        with self.lock:
            account = self.accounts.get(channel)
            pending = self.pending.get(channel, {})
            return {
                "authorized": bool(account),
                "login": account.get("login") if account else None,
                "client_id": account.get("client_id", "")
                if account
                else os.environ.get("PACTTS_TWITCH_CLIENT_ID", ""),
                "scopes": account.get("scopes", []) if account else [],
                "features": list(FEATURE_SCOPES),
                "pending": bool(pending),
                "user_code": pending.get("user_code"),
                "verification_uri": pending.get("verification_uri"),
                "expires_at": pending.get("expires_at"),
                "error": self.errors.get(channel) or self.errors.get("storage"),
            }

    def start(self, channel, client_id, features):
        if not isinstance(client_id, str) or not re.fullmatch(r"[a-zA-Z0-9]{10,100}", client_id):
            raise UserError("Enter the Client ID of a public Twitch application.")
        if (
            not isinstance(features, list)
            or not features
            or any(not isinstance(f, str) or f not in FEATURE_SCOPES for f in features)
        ):
            raise UserError("Select at least one Twitch permission group.")
        scopes = sorted({FEATURE_SCOPES[f] for f in features})
        with self.lock:
            if self.closed:
                raise UserError("Application is closing.")
            self._cancel(channel)
            response = self.http(
                "POST",
                "https://id.twitch.tv/oauth2/device",
                form={"client_id": client_id, "scopes": " ".join(scopes)},
            )
            uri = response["verification_uri"]
            parsed = urllib.parse.urlsplit(uri)
            if parsed.scheme != "https" or parsed.hostname not in {"www.twitch.tv", "twitch.tv"}:
                raise UserError("Twitch returned an unexpected authorization address.")
            pending = {
                **response,
                "client_id": client_id,
                "scopes": scopes,
                "expires_at": time.time() + response["expires_in"],
                "stop": threading.Event(),
            }
            self.pending[channel] = pending
            self.errors.pop(channel, None)
            thread = threading.Thread(target=self._poll, args=(channel, pending), daemon=True)
            self.threads = [t for t in self.threads if t.is_alive()]
            self.threads.append(thread)
            thread.start()
            return self.snapshot(channel)

    def _poll(self, channel, pending):
        interval = max(1, pending.get("interval", 5))
        try:
            while not pending["stop"].wait(interval):
                if time.time() >= pending["expires_at"]:
                    raise UserError("Twitch authorization expired. Start again.")
                try:
                    tokens = self.http(
                        "POST",
                        "https://id.twitch.tv/oauth2/token",
                        form={
                            "client_id": pending["client_id"],
                            "scopes": " ".join(pending["scopes"]),
                            "device_code": pending["device_code"],
                            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                        },
                    )
                except TwitchAPIError as exc:
                    if exc.code == "authorization_pending":
                        continue
                    if exc.code == "slow_down":
                        interval += 5
                        continue
                    raise
                validated = self.http(
                    "GET",
                    "https://id.twitch.tv/oauth2/validate",
                    headers={"Authorization": "OAuth " + tokens["access_token"]},
                )
                if (
                    validated["login"].lower() != channel
                    or validated["client_id"] != pending["client_id"]
                ):
                    raise UserError("Authorize the broadcaster account matching the saved channel.")
                with self.lock:
                    if self.pending.get(channel) is not pending or pending["stop"].is_set():
                        return
                    self.accounts[channel] = {
                        **tokens,
                        "client_id": pending["client_id"],
                        "login": validated["login"],
                        "user_id": validated["user_id"],
                        "scopes": validated["scopes"],
                        "validated_at": time.time(),
                    }
                    self._save()
                    self.pending.pop(channel, None)
                self.on_change(channel)
                return
        except Exception as exc:
            with self.lock:
                if self.pending.get(channel) is pending:
                    self.errors[channel] = (
                        str(exc)
                        if isinstance(exc, UserError)
                        else "Twitch authorization failed. Retry."
                    )
        finally:
            with self.lock:
                if self.pending.get(channel) is pending:
                    self.pending.pop(channel, None)

    def _cancel(self, channel):
        pending = self.pending.pop(channel, None)
        if pending:
            pending["stop"].set()

    def forget(self, channel):
        with self.lock:
            self._cancel(channel)
            self.accounts.pop(channel, None)
            self.errors.pop(channel, None)
            self._save()
        self.on_change(channel)
        return self.snapshot(channel)

    def account(self, channel):
        with self.lock:
            value = self.accounts.get(channel)
            if not value:
                raise UserError("Authorize this broadcaster in the Twitch tab first.")
            if time.time() - value.get("validated_at", 0) >= 3600:
                try:
                    checked = self.http(
                        "GET",
                        "https://id.twitch.tv/oauth2/validate",
                        headers={"Authorization": "OAuth " + value["access_token"]},
                    )
                except TwitchAPIError as exc:
                    if exc.status != 401:
                        raise
                    self._refresh(channel)
                    checked = self.http(
                        "GET",
                        "https://id.twitch.tv/oauth2/validate",
                        headers={"Authorization": "OAuth " + value["access_token"]},
                    )
                if (
                    checked["user_id"] != value["user_id"]
                    or checked["client_id"] != value["client_id"]
                ):
                    raise UserError("Twitch authorization identity changed. Authorize again.")
                value.update(scopes=checked["scopes"], validated_at=time.time())
                self._save()
            return dict(value)

    def _refresh(self, channel):
        value = self.accounts[channel]
        try:
            updated = self.http(
                "POST",
                "https://id.twitch.tv/oauth2/token",
                form={
                    "client_id": value["client_id"],
                    "grant_type": "refresh_token",
                    "refresh_token": value["refresh_token"],
                },
            )
        except TwitchAPIError as exc:
            if exc.status in {400, 401}:
                self.errors[channel] = "Twitch authorization expired or revoked. Authorize again."
            raise
        value.update(updated, validated_at=0)
        self._save()  # Rotating refresh tokens must be durable before reuse.

    def api(self, channel, method, path, *, query=None, body=None):
        if not path.startswith("/") or ".." in path:
            raise ValueError("Invalid Helix path")
        url = "https://api.twitch.tv/helix" + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        with self.lock:
            value = self.account(channel)
            for attempt in range(2):
                try:
                    return self.http(
                        method,
                        url,
                        headers={
                            "Client-Id": value["client_id"],
                            "Authorization": "Bearer " + value["access_token"],
                        },
                        body=body,
                    )
                except TwitchAPIError as exc:
                    if exc.status != 401 or attempt:
                        raise
                    self._refresh(channel)
                    value = self.account(channel)

    def close(self):
        with self.lock:
            self.closed = True
            for channel in list(self.pending):
                self._cancel(channel)
        for thread in self.threads:
            thread.join(0.1)
