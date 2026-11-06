"""Parse voice switches and literal SFX triggers without consuming model tags."""

import re

from .domain import UserError

# Reserved model syntax must never be replaced by uploaded audio.
RESERVED = {
    "[happy]",
    "[sad]",
    "[angry]",
    "[nervous]",
    "[whisper]",
    "[calm]",
    "[excited]",
    "[shy]",
    "[crying]",
    "[emotion]",
    "<sigh>",
    "<laughter>",
}


def parse_script(message, commands, effects, *, max_sections=4, max_effects=8):
    triggers = {
        t.casefold(): e["id"] for e in effects if e.get("enabled", True) for t in e["triggers"]
    }
    tokens = sorted(triggers, key=len, reverse=True)
    pattern = re.compile(
        r"\\[\\!\[\]*]|(?<!\S)![a-zA-Z0-9_]+(?=\s|$)"
        + ("|" + "|".join(re.escape(t) for t in tokens) if tokens else ""),
        re.I,
    )
    sections = []
    current = None
    buffer = ""
    count = 0

    def flush():
        nonlocal buffer
        if buffer.strip():
            if current is None:
                raise UserError("Start the message with a configured voice command.")
            current["parts"].append({"text": buffer.strip()})
        buffer = ""

    cursor = 0
    for match in pattern.finditer(message):
        buffer += message[cursor : match.start()]
        token = match.group()
        cursor = match.end()
        if token.startswith("\\"):
            buffer += token[1:]
            continue
        flush()
        if token.startswith("!"):
            voice_id = commands.get(token.casefold())
            if voice_id is None:
                raise UserError(f"Unknown voice command: {token}")
            current = {"voice_id": voice_id, "parts": []}
            sections.append(current)
            if len(sections) > max_sections:
                raise UserError(f"Maximum {max_sections} voice sections per message.")
        else:
            if current is None:
                raise UserError("Start the message with a configured voice command.")
            count += 1
            if count > max_effects:
                raise UserError(f"Maximum {max_effects} sound effects per message.")
            current["parts"].append({"sfx_id": triggers[token.casefold()]})
    buffer += message[cursor:]
    flush()
    if not sections or any(not section["parts"] for section in sections):
        raise UserError("Each voice command needs speech or a sound effect.")
    return sections
