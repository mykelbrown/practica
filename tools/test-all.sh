#!/usr/bin/env bash
# Practica quality gate: run every check before publishing course material.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
results=()
gate() { local name="$1"; shift; echo "── $name"; if "$@" >"$TMP/log" 2>&1; then results+=("PASS $name"); tail -1 "$TMP/log";
         else results+=("FAIL $name"); cat "$TMP/log"; fi; }

export PRACTICA_LEGACY="$TMP/no-legacy.json"
gate "catalogue doctor"            env PRACTICA_PROGRESS="$TMP/doctor.json" python3 "$ROOT/bin/practica.py" doctor
gate "progression test suite"      python3 -m unittest discover -s "$ROOT/tests"
gate "checker self-test devops b1" "$ROOT/tools/selftest-m1d1.sh"
gate "checker self-test ai b1"     "$ROOT/tools/selftest-ai-eng-b-m01-l01.sh"

# Real progress file for the catalogue overlay test: pass both ready lessons on a copy.
cp -a "$ROOT" "$TMP/p"; rm -f "$TMP/p"/progress.json*
P=(env PRACTICA_ROOT="$TMP/p" PRACTICA_PROGRESS="$TMP/progress.json" python3 "$TMP/p/bin/practica.py")
"${P[@]}" enrol ai-engineering >/dev/null
cp "$ROOT/tools/reference/ai-eng-b-m01-l01.py" "$TMP/p/courses/ai-engineering/beginner/m01-l01-structured-output/workspace/extract.py"
"${P[@]}" verify >/dev/null
"${P[@]}" enrol devops >/dev/null
bash -c 'source <(sed -n "/^build() {/,/^}/p" "$1"); VERIFY="$2" build "$3" && cp -a "$3/workspace/app" "$4/"' _ \
  "$ROOT/tools/selftest-m1d1.sh" "$ROOT/courses/devops/module-01/day-01/verify.sh" "$TMP/ref" "$TMP/p/courses/devops/module-01/day-01/workspace"
"${P[@]}" verify >/dev/null

gate "page: devops b1 lesson"      node "$ROOT/tools/test-lesson-page.mjs" "$ROOT/courses/devops/module-01/day-01/lesson.html"
gate "page: ai b1 lesson"          node "$ROOT/tools/test-ai-lesson-page.mjs" "$ROOT/courses/ai-engineering/beginner/m01-l01-structured-output/lesson.html"
python3 "$ROOT/tools/build-web.py" >/dev/null
gate "page: course catalogue"      node "$ROOT/tools/test-catalog-page.mjs" "$ROOT/web/catalog.html" "$TMP/progress.json"

echo; printf '%s\n' "${results[@]}"
! printf '%s\n' "${results[@]}" | grep -q '^FAIL'
