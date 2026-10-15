"""Reference solution for ai-engineering/beginner/m01/l01 (used by self-tests, not shown to learners)."""
import json
import re

ALLOWED_INTENTS = ("refund", "question", "complaint")
KEYS = {"intent", "priority", "summary"}


def parse_reply(text: str) -> dict:
    fence = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.S)
    if fence:
        raw = fence.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("no JSON object found in reply")
        raw = text[start:end + 1]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON: {e}") from None
    if not isinstance(data, dict):
        raise ValueError("reply must be a JSON object")
    if missing := KEYS - data.keys():
        raise ValueError(f"missing key(s): {', '.join(sorted(missing))}")
    if extra := data.keys() - KEYS:
        raise ValueError(f"unexpected key(s): {', '.join(sorted(extra))}")
    if data["intent"] not in ALLOWED_INTENTS:
        raise ValueError(f"intent must be one of {ALLOWED_INTENTS}, got {data['intent']!r}")
    p = data["priority"]
    if type(p) is not int or not 1 <= p <= 5:
        raise ValueError(f"priority must be an integer 1-5, got {p!r}")
    s = data["summary"]
    if not isinstance(s, str) or not s.strip() or len(s.strip()) > 120:
        raise ValueError("summary must be a non-empty string of at most 120 characters")
    return {"intent": data["intent"], "priority": p, "summary": s.strip()}


def build_prompt(ticket: str, error: str | None = None) -> str:
    prompt = ("Classify the support ticket. Reply with only a JSON object with keys "
              f"intent (one of {', '.join(ALLOWED_INTENTS)}), priority (integer 1-5) and summary "
              f"(at most 120 characters).\n\nTicket:\n{ticket}")
    if error:
        prompt += f"\n\nYour previous reply was invalid: {error}. Reply again with corrected JSON only."
    return prompt


def classify(ticket: str, model, max_attempts: int = 3) -> dict:
    error = None
    for _ in range(max_attempts):
        try:
            return parse_reply(model(build_prompt(ticket, error)))
        except ValueError as e:
            error = str(e)
    raise RuntimeError(f"model gave no valid reply after {max_attempts} attempts; last error: {error}")
