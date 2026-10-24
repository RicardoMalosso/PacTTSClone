"""Basic PT/EN lexical filtering, deliberately not a Twitch policy classifier."""

import re
import unicodedata

# Always applied. Plain data, never shown on the OBS source.
SLURS = {
    "nigger",
    "nigga",
    "faggot",
    "kike",
    "chink",
    "tranny",
    "spic",
    "negrada",
    "crioulo",
    "macaco",
    "bicha",
    "viado",
    "traveco",
    "sapatão",
}
PROFANITY = {
    "fuck",
    "fucking",
    "shit",
    "bitch",
    "asshole",
    "cunt",
    "caralho",
    "porra",
    "merda",
    "puta",
    "foder",
    "fodase",
    "foda-se",
}
STRICT = {"dick", "cock", "pussy", "porn", "pornografia", "pinto", "buceta", "cu"}


def normalize(text: str) -> str:
    text = "".join(
        c
        for c in unicodedata.normalize("NFKD", text.casefold())
        if unicodedata.category(c) not in {"Mn", "Cf"}
    )
    return " ".join(re.findall(r"\w+", text, re.UNICODE))


def blocked_reason(text: str, level: str, custom: list[str]) -> str | None:
    words = set(SLURS)
    if level in {"profanity", "strict"}:
        words |= PROFANITY
    if level == "strict":
        words |= STRICT
    candidates = [normalize(text), normalize(text.translate(str.maketrans("013457", "oieast")))]
    for terms, reason in [
        (words, "mandatory/profanity word filter"),
        (custom, "custom word filter"),
    ]:
        for term in terms:
            value = normalize(term)
            if value and any(
                re.search(r"(?<!\w)" + re.escape(value) + r"(?!\w)", c) for c in candidates
            ):
                return reason
    return None
