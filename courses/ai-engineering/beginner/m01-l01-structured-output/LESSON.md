# AI Engineering · Beginner · Lesson 1 — Structured Output

**Goal:** turn a language model's free-text reply into data your program can
trust. You will write the code that sits between every LLM call and the rest
of your system: it finds the JSON, checks it against a schema, and asks the
model to try again with a precise error message when the reply is wrong.

Everything runs offline. The checker uses fake models that misbehave in the
ways real ones do, so you need no API key and spend nothing.

## 0. Watch and explore first

- Interactive lesson with an animated retry loop and a reply inspector: open
  `lesson.html` (or the online copy linked from `practica next`).
- Video: `media/lesson.mp4` (captioned, no audio).

## 1. Concepts (about 15 minutes)

| Concept | Why it matters |
|---|---|
| Models return **text**, never objects | Even when asked for JSON they add prose, code fences or extra fields. |
| **Extract** before you parse | Pull the JSON out of fences or surrounding text first. |
| **Validate** against a schema | Wrong types and invented values are the most common silent bugs in AI features. |
| **Retry with feedback** | Telling the model exactly what was wrong fixes most bad replies on the next attempt. |
| **Bounded retries** | Unlimited retries burn money and hide outages. Stop and raise a clear error. |
| **Fakes in tests** | Real models are slow, costly and non-deterministic. Test your logic with scripted fakes. |

## 2. Challenge

Edit `workspace/extract.py`. A support desk wants every ticket classified as:

```json
{"intent": "refund", "priority": 4, "summary": "Charged twice for March"}
```

Implement three functions:

1. **`parse_reply(text) -> dict`**
   - If the text contains a fenced block (three backticks, optionally `json`),
     use the content of the first block; otherwise use everything from the
     first `{` to the last `}`. If there is no object, raise `ValueError`.
   - Invalid JSON raises `ValueError`.
   - The object must have **exactly** the keys `intent`, `priority`, `summary`.
     Missing or extra keys raise `ValueError` naming the key.
   - `intent` must be one of `refund`, `question`, `complaint`.
   - `priority` must be an **integer** from 1 to 5 (`true`, `4.5` and `"4"` are invalid).
   - `summary` must be a non-empty string of at most 120 characters after
     trimming spaces. Return it trimmed.
2. **`build_prompt(ticket, error=None) -> str`**
   - Includes the ticket text and the three allowed intents.
   - When `error` is given, includes the phrase `previous reply was invalid`
     and the error message, so the model can correct itself.
3. **`classify(ticket, model, max_attempts=3) -> dict`**
   - `model` is any callable taking a prompt string and returning a string.
   - Parse each reply. On `ValueError`, call the model again with
     `build_prompt(ticket, error=str(err))`.
   - Never call the model more than `max_attempts` times. If every attempt
     fails, raise `RuntimeError` whose message contains
     `after <max_attempts> attempts`.
   - Do **not** retry or hide other exceptions such as `TimeoutError`; let them
     propagate so callers can see outages.

## 3. Verify

```bash
practica verify
```

or run the checker directly with `./verify.sh`. It imports your file and runs
it against ten fake models plus a set of tricky replies.

## 4. Stretch

- Replace the hand-written checks with a Pydantic model and compare the code.
- Add jittered exponential back-off between attempts (the checker passes a fake
  clock-free model, so keep the delay injectable).
