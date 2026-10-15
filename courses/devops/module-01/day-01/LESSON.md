# Module 1 · Day 1 — Filesystem, Permissions and Exit Codes

**Goal:** build a small "application" directory by hand, lock its permissions
down properly, and write a health-check script that reports success or failure
through its **exit code**, which is how every CI pipeline, container
orchestrator and monitoring system decides whether something worked.

## 0. Watch and explore first

- **Interactive lesson** (video, diagrams, permission calculator, exit-code simulator):
  https://claude.ai/artifact/PKNsaDxmRFk48Qq88CgjX1 (local copy: `lesson.html`)
- **Animated video** (no audio, captioned): `media/lesson.mp4`, or `media/lesson.webm`
  if your player cannot open MP4. Rebuild it with `node media/record.mjs`.

## 1. Concepts you need (about 10 minutes)

| Concept | Why it matters in DevOps |
|---|---|
| `pwd`, `cd`, `ls -la`, `tree`, `find` | You will be dropped into unfamiliar servers and containers constantly. |
| `mkdir -p a/{b,c}` | Brace expansion creates whole layouts in one idempotent command. |
| Permission bits `rwx` / octal `750`, `600` | Secrets must not be world-readable. Scripts must be executable. |
| `chmod`, `stat -c '%a %n'` | Set permissions and inspect them. |
| Symlinks `ln -s target link` | Used for "current release" switching and zero-downtime deploys. |
| Exit codes `$?` | `0` = success, anything else = failure. Pipelines rely on this. |
| stdout vs stderr (`>&2`) | Errors go to stderr so they are not mixed into parsable output. |
| `set -euo pipefail` | Makes bash fail fast instead of silently continuing after errors. |

Octal permissions: `r=4 w=2 x=1`, summed per **owner / group / others**.
`750` = owner `rwx`, group `r-x`, others nothing. `600` = owner `rw-` only.

Try these first:

```bash
cd ~/devops-lab/module-01/day-01/workspace
mkdir -p demo/{one,two} && ls -la demo
touch demo/secret && chmod 600 demo/secret && stat -c '%a %n' demo/secret
true;  echo "exit code: $?"
false; echo "exit code: $?"
ls /does-not-exist 2>/dev/null; echo "exit code: $?"
rm -rf demo
```

## 2. Challenge

Work inside `~/devops-lab/module-01/day-01/workspace/`. Create:

```
app/
├── bin/
│   └── healthcheck.sh      # mode 750
├── config/
│   └── app.env             # mode 600
├── logs/                   # mode 750
│   └── app.log             # empty file
└── current-config -> config/app.env   (symbolic link, relative target)
```

1. `app/config/app.env` contains exactly these two lines:
   ```
   APP_ENV=development
   APP_PORT=8080
   ```
2. `app/bin/healthcheck.sh` must:
   - start with `#!/usr/bin/env bash` and use `set -euo pipefail`;
   - locate `app.env` **relative to the script's own location**, not your
     current directory (hint: `"$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"`);
   - if the file exists: load it and print `OK env=development port=8080`
     (values read from the file, not hard-coded), then exit `0`;
   - if the file is missing: print a message beginning `ERROR` to **stderr**
     and exit `2`;
   - if `APP_PORT` is not a number: print `ERROR` to stderr and exit `3`.
3. Permissions: `bin/healthcheck.sh` → `750`, `config/app.env` → `600`,
   `logs/` → `750`.

Do it by typing the commands yourself; that's the point of the exercise.

## 3. Verify

```bash
practica verify
```

(or run the checker directly: `~/devops-lab/module-01/day-01/verify.sh`;
only `practica verify` records your progress).

The checker copies your `app/` into a throwaway directory to test the failure
paths, so it never modifies your work. When every check passes, tell me and
I'll record the lesson and unlock Day 2 (processes, signals, pipes and
redirection).

## 4. Stretch (optional)

- Make `healthcheck.sh` pass `shellcheck` (we'll install it in a later lesson).
- Add a `--quiet` flag that prints nothing and relies only on the exit code.
