#!/usr/bin/env bash
# Self-test for module-01/day-01/verify.sh: a reference solution must pass,
# and each deliberately broken variant must fail on the expected check.
set -uo pipefail
LAB="$(cd "$(dirname "${BASH_SOURCE[0]}")/../courses/devops" && pwd)"
VERIFY="$LAB/module-01/day-01/verify.sh"
root="$(mktemp -d)"; trap 'rm -rf "$root"' EXIT
ok=0; bad=0

build() { # $1 = case dir; builds the reference solution
  local d="$1/workspace"; mkdir -p "$d" && cp "$VERIFY" "$1/" && cd "$d" || return
  mkdir -p app/{bin,config,logs} && touch app/logs/app.log
  printf 'APP_ENV=development\nAPP_PORT=8080\n' > app/config/app.env
  cat > app/bin/healthcheck.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
env_file="$here/../config/app.env"
[ -f "$env_file" ] || { echo "ERROR: missing $env_file" >&2; exit 2; }
source "$env_file"
[[ "${APP_PORT:-}" =~ ^[0-9]+$ ]] || { echo "ERROR: APP_PORT not numeric" >&2; exit 3; }
echo "OK env=${APP_ENV} port=${APP_PORT}"
SH
  chmod 750 app/bin/healthcheck.sh app/logs; chmod 600 app/config/app.env
  (cd app && ln -s config/app.env current-config)
}

expect() { # $1 name, $2 want (pass|fail), $3 regex that must appear as FAIL (for fail cases), $4 mutation
  local c="$root/$1"; build "$c"; (cd "$c/workspace" && eval "$4")
  out="$("$c/verify.sh" 2>&1)"; rc=$?
  if [ "$2" = pass ] && [ $rc -eq 0 ]; then echo "PASS $1"; ok=$((ok+1))
  elif [ "$2" = fail ] && [ $rc -ne 0 ] && grep -E "FAIL.*$3" <<<"$out" >/dev/null; then echo "PASS $1 (caught: $3)"; ok=$((ok+1))
  else echo "FAIL $1 (rc=$rc)"; echo "$out" | grep FAIL; bad=$((bad+1)); fi
}

expect reference         pass ""                    ":"
expect absolute-symlink  fail "current-config"      "rm app/current-config; ln -s \"\$PWD/app/config/app.env\" app/current-config"
expect world-readable    fail "app.env mode"        "chmod 644 app/config/app.env"
expect hardcoded-output  fail "staging/9090"        "sed -i 's/echo \"OK env=\${APP_ENV} port=\${APP_PORT}\"/echo \"OK env=development port=8080\"/' app/bin/healthcheck.sh"
expect error-on-stdout   fail "missing config"      "sed -i 's/missing \$env_file\" >&2/missing \$env_file\"/' app/bin/healthcheck.sh"
expect pwd-relative      fail "healthy run"         "sed -i 's|env_file=\"\$here/../config/app.env\"|env_file=\"config/app.env\"|' app/bin/healthcheck.sh"
expect no-port-check     fail "bad port"            "sed -i '/APP_PORT:-/d' app/bin/healthcheck.sh"
echo "Result: $ok passed, $bad failed"; [ $bad -eq 0 ]
