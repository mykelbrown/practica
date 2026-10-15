#!/usr/bin/env bash
# Verifier for Module 1 Day 1. Read-only against the learner's workspace.
set -uo pipefail

APP="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/workspace/app"
pass=0; fail=0

ok()  { printf '  \033[32mPASS\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; [ -n "${2:-}" ] && printf '       hint: %s\n' "$2"; fail=$((fail+1)); }
mode() { stat -c '%a' "$1" 2>/dev/null; }

echo "Structure"
for d in bin config logs; do
  [ -d "$APP/$d" ] && ok "app/$d exists" || bad "app/$d missing" "mkdir -p app/{bin,config,logs}"
done
[ -f "$APP/logs/app.log" ] && [ ! -s "$APP/logs/app.log" ] && ok "logs/app.log exists and is empty" \
  || bad "logs/app.log missing or not empty" "touch app/logs/app.log"

echo "Config"
if [ -f "$APP/config/app.env" ]; then
  expected=$'APP_ENV=development\nAPP_PORT=8080'
  [ "$(cat "$APP/config/app.env")" = "$expected" ] && ok "app.env content correct" \
    || bad "app.env content differs" "exactly two lines: APP_ENV=development / APP_PORT=8080"
else
  bad "config/app.env missing"
fi

echo "Permissions"
[ "$(mode "$APP/bin/healthcheck.sh")" = 750 ] && ok "healthcheck.sh is 750" || bad "healthcheck.sh mode is $(mode "$APP/bin/healthcheck.sh" || echo none), want 750" "chmod 750 ..."
[ "$(mode "$APP/config/app.env")" = 600 ]     && ok "app.env is 600"        || bad "app.env mode is $(mode "$APP/config/app.env" || echo none), want 600"
[ "$(mode "$APP/logs")" = 750 ]               && ok "logs/ is 750"          || bad "logs/ mode is $(mode "$APP/logs" || echo none), want 750"

echo "Symlink"
if [ -L "$APP/current-config" ]; then
  tgt="$(readlink "$APP/current-config")"
  [ "$tgt" = "config/app.env" ] && ok "current-config -> config/app.env" \
    || bad "current-config points to '$tgt'" "use a relative target: cd app && ln -s config/app.env current-config"
else
  bad "current-config is not a symlink"
fi

echo "Script behaviour"
HC="$APP/bin/healthcheck.sh"
if [ -f "$HC" ]; then
  head -1 "$HC" | grep -qx '#!/usr/bin/env bash' && ok "shebang correct" || bad "first line must be #!/usr/bin/env bash"
  grep -q 'set -euo pipefail' "$HC" && ok "uses set -euo pipefail" || bad "missing set -euo pipefail"

  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
  cp -a "$APP" "$tmp/app"

  # Happy path, run from an unrelated directory to prove path independence.
  out="$(cd / && "$tmp/app/bin/healthcheck.sh" 2>/dev/null)"; rc=$?
  [ $rc -eq 0 ] && [ "$out" = "OK env=development port=8080" ] && ok "healthy: prints OK line, exit 0 (run from /)" \
    || bad "healthy run gave exit=$rc output='$out'" "resolve app.env relative to the script, not \$PWD"

  # Values must come from the file.
  printf 'APP_ENV=staging\nAPP_PORT=9090\n' > "$tmp/app/config/app.env"
  out="$("$tmp/app/bin/healthcheck.sh" 2>/dev/null)"
  [ "$out" = "OK env=staging port=9090" ] && ok "values read from file (not hard-coded)" || bad "with staging/9090 got '$out'"

  # Non-numeric port -> 3, error on stderr.
  printf 'APP_ENV=staging\nAPP_PORT=abc\n' > "$tmp/app/config/app.env"
  so="$("$tmp/app/bin/healthcheck.sh" 2>"$tmp/err")"; rc=$?
  [ $rc -eq 3 ] && grep -q '^ERROR' "$tmp/err" && [ -z "$so" ] && ok "bad port: ERROR on stderr, exit 3" \
    || bad "bad port gave exit=$rc stdout='$so' stderr='$(cat "$tmp/err")'"

  # Missing file -> 2, error on stderr.
  rm -f "$tmp/app/config/app.env"
  so="$("$tmp/app/bin/healthcheck.sh" 2>"$tmp/err")"; rc=$?
  [ $rc -eq 2 ] && grep -q '^ERROR' "$tmp/err" && [ -z "$so" ] && ok "missing config: ERROR on stderr, exit 2" \
    || bad "missing config gave exit=$rc stdout='$so' stderr='$(cat "$tmp/err")'"
else
  bad "bin/healthcheck.sh missing"
fi

echo
echo "Result: $pass passed, $fail failed"
[ $fail -eq 0 ]
