#!/usr/bin/env bash
# Self-test for ai-engineering/beginner/m01/l01: reference passes, each broken variant is caught.
set -uo pipefail
TOOLS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LESSON="$TOOLS/../courses/ai-engineering/beginner/m01-l01-structured-output"
REF="$TOOLS/reference/ai-eng-b-m01-l01.py"
root="$(mktemp -d)"; trap 'rm -rf "$root"' EXIT
ok=0; bad=0

expect() { # name want regex python-mutation
  local c="$root/$1"; mkdir -p "$c/workspace"; cp "$LESSON/verify.sh" "$LESSON/checks.py" "$c/"
  cp "$REF" "$c/workspace/extract.py"
  python3 - "$c/workspace/extract.py" "$4" <<'PY'
import sys; p, mut = sys.argv[1], sys.argv[2]
if mut:
    old, new = mut.split("|||")
    s = open(p).read(); assert s.count(old) == 1, old; open(p, "w").write(s.replace(old, new))
PY
  out="$("$c/verify.sh" 2>&1)"; rc=$?
  if [ "$2" = pass ] && [ $rc -eq 0 ]; then echo "PASS $1"; ok=$((ok+1))
  elif [ "$2" = fail ] && [ $rc -ne 0 ] && grep -E "FAIL.*$3" <<<"$out" >/dev/null; then echo "PASS $1 (caught: $3)"; ok=$((ok+1))
  else echo "FAIL $1 (rc=$rc)"; grep -E "FAIL|Result" <<<"$out"; bad=$((bad+1)); fi
}

expect reference           pass ""                         ""
expect no-fence-support    fail "fence"                    'fence = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.S)|||fence = None'
expect bool-priority       fail "priority true"            'if type(p) is not int or|||if not isinstance(p, int) or'
expect allows-extra-keys   fail "extra key"                'if extra := data.keys() - KEYS:|||if False:'
expect unbounded-retries   fail "stops after 3"            'for _ in range(max_attempts):|||while True:'
expect no-feedback         fail "retries once with feedback" 'prompt += f"\n\nYour previous reply was invalid|||prompt += f"\n\nTry again'
expect swallows-outages    fail "TimeoutError"             'except ValueError as e:|||except Exception as e:'
expect accepts-float-prio  fail "priority 4.5"             'if type(p) is not int or|||if not isinstance(p, (int, float)) or'
echo "Result: $ok passed, $bad failed"; [ $bad -eq 0 ]
