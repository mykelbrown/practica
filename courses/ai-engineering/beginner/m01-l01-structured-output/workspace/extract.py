"""Structured output for a ticket classifier. Implement the three functions below.

Run `practica verify` (or ../verify.sh) to check your work.
"""

ALLOWED_INTENTS = ("refund", "question", "complaint")


def parse_reply(text: str) -> dict:
    """Extract and validate {"intent", "priority", "summary"} from a model reply.

    Raise ValueError with a helpful message when the reply is unusable.
    """
    raise NotImplementedError("parse_reply")


def build_prompt(ticket: str, error: str | None = None) -> str:
    """Return the prompt to send to the model, with feedback when `error` is set."""
    raise NotImplementedError("build_prompt")


def classify(ticket: str, model, max_attempts: int = 3) -> dict:
    """Call `model(prompt)` until it returns a valid reply, at most `max_attempts` times."""
    raise NotImplementedError("classify")
