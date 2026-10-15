"""Checker for AI Engineering beginner lesson 1. Run via verify.sh (python3 -I)."""
import importlib.util
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGET = HERE / "workspace" / "extract.py"
passed = failed = 0


class RunawayRetries(BaseException):
    """Raised by the fake model when it is called far too often (BaseException so it is not swallowed)."""


class Scripted:
    LIMIT = 50

    def __init__(self, *replies):
        self.replies, self.prompts = list(replies), []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        if len(self.prompts) > self.LIMIT:
            raise RunawayRetries(f"model called more than {self.LIMIT} times")
        r = self.replies.pop(0) if self.replies else "still not JSON"
        if isinstance(r, BaseException):
            raise r
        return r



def report(ok, name, hint=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  \033[32mPASS\033[0m {name}")
    else:
        failed += 1
        print(f"  \033[31mFAIL\033[0m {name}")
        if hint:
            print(f"       hint: {hint}")


def check(name, fn, hint=""):
    try:
        ok = fn()
    except NotImplementedError as e:
        ok, hint = False, f"{e} is not implemented yet"
    except RunawayRetries as e:
        ok, hint = False, f"{e}: your retry loop is not bounded by max_attempts"
    except Exception as e:  # learner code may raise anything
        ok, hint = False, f"{hint} (raised {type(e).__name__}: {e})".strip()
    report(bool(ok), name, hint)


def raises(exc, fn):
    try:
        fn()
    except exc:
        return True
    except NotImplementedError:
        raise
    except Exception as e:
        raise AssertionError(f"expected {exc.__name__}, got {type(e).__name__}: {e}")
    return False


def _msg_contains(fn, word):
    try:
        fn()
    except ValueError as e:
        return word in str(e)
    return False


try:
    spec = importlib.util.spec_from_file_location("learner_extract", TARGET)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
except Exception:
    print("Could not import workspace/extract.py:\n" + traceback.format_exc())
    print("\nResult: 0 passed, 1 failed")
    sys.exit(1)

parse, build, classify = mod.parse_reply, mod.build_prompt, mod.classify
GOOD = '{"intent": "refund", "priority": 4, "summary": "Charged twice for March"}'
WANT = {"intent": "refund", "priority": 4, "summary": "Charged twice for March"}

print("parse_reply: extraction")
check("plain JSON object", lambda: parse(GOOD) == WANT)
check("JSON inside ```json fence with prose around it",
      lambda: parse("Sure! Here you go:\n```json\n" + GOOD + "\n```\nAnything else?") == WANT,
      "use the content of the first fenced block")
check("JSON inside a bare ``` fence", lambda: parse("```\n" + GOOD + "\n```") == WANT)
check("fence wins over braces in surrounding prose",
      lambda: parse("Format: {intent, priority, summary}\n```json\n" + GOOD + "\n```\nDone {ok}") == WANT,
      "when a fence exists, parse only the fenced block")
check("JSON embedded in a sentence", lambda: parse("The answer is " + GOOD + " as requested.") == WANT,
      "fall back to first '{' .. last '}'")
check("no JSON at all raises ValueError", lambda: raises(ValueError, lambda: parse("I cannot help with that.")))
check("truncated JSON raises ValueError", lambda: raises(ValueError, lambda: parse('{"intent": "refund", "prio')))

print("parse_reply: validation")
check("missing key raises ValueError naming it",
      lambda: _msg_contains(lambda: parse('{"intent": "refund", "priority": 4}'), "summary"))
check("extra key raises ValueError naming it",
      lambda: _msg_contains(lambda: parse(GOOD[:-1] + ', "confidence": 0.9}'), "confidence"))
check("unknown intent rejected", lambda: raises(ValueError, lambda: parse(GOOD.replace("refund", "billing"))))
for bad in ("true", "4.5", '"4"', "0", "6"):
    check(f"priority {bad} rejected", lambda b=bad: raises(ValueError, lambda: parse(GOOD.replace(": 4,", f": {b},"))),
          "priority must be an int 1-5; note bool is a subclass of int in Python")
check("priority 1 and 5 accepted", lambda: parse(GOOD.replace(": 4,", ": 1,"))["priority"] == 1
      and parse(GOOD.replace(": 4,", ": 5,"))["priority"] == 5)
check("summary is trimmed", lambda: parse(GOOD.replace('"Charged', '"   Charged').replace('March"', 'March  "'))
      ["summary"] == "Charged twice for March")
check("empty summary rejected", lambda: raises(ValueError, lambda: parse(GOOD.replace("Charged twice for March", "   "))))
check("summary over 120 chars rejected",
      lambda: raises(ValueError, lambda: parse(GOOD.replace("Charged twice for March", "x" * 121))))

print("build_prompt")
check("contains ticket and allowed intents",
      lambda: all(s in build("My card was charged twice") for s in ("My card was charged twice", "refund", "question", "complaint")))
check("feedback included on retry",
      lambda: "previous reply was invalid" in build("t", error="priority must be 1-5").lower()
      and "priority must be 1-5" in build("t", error="priority must be 1-5"))
check("no feedback on first attempt", lambda: "previous reply was invalid" not in build("t").lower())




def first_try():
    m = Scripted(GOOD)
    return classify("ticket", m) == WANT and len(m.prompts) == 1


def fixed_on_retry():
    m = Scripted("Sorry, here it is: {bad json", GOOD)
    out = classify("ticket", m)
    return out == WANT and len(m.prompts) == 2 and "previous reply was invalid" in m.prompts[1].lower()


def gives_up():
    m = Scripted()
    try:
        classify("ticket", m, max_attempts=3)
    except RuntimeError as e:
        return len(m.prompts) == 3 and "after 3 attempts" in str(e)
    return False


def custom_limit():
    m = Scripted()
    try:
        classify("ticket", m, max_attempts=5)
    except RuntimeError as e:
        return len(m.prompts) == 5 and "after 5 attempts" in str(e)
    return False


def outage_propagates():
    m = Scripted(TimeoutError("model timed out"), GOOD)
    try:
        classify("ticket", m)
    except TimeoutError:
        return len(m.prompts) == 1
    return False


def feedback_is_specific():
    m = Scripted(GOOD.replace(": 4,", ": 9,"), GOOD)
    classify("ticket", m)
    return "9" in m.prompts[1] or "priority" in m.prompts[1].lower()


print("classify: retry behaviour with fake models")
check("valid first reply: one model call", first_try)
check("invalid then valid: retries once with feedback", fixed_on_retry)
check("always invalid: stops after 3 calls with RuntimeError", gives_up, "count calls, do not loop forever")
check("respects max_attempts=5", custom_limit)
check("TimeoutError propagates without retry", outage_propagates, "only retry on ValueError")
check("retry prompt contains the actual validation error", feedback_is_specific)

print(f"\nResult: {passed} passed, {failed} failed")
sys.exit(0 if failed == 0 else 1)
