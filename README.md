# Practica

Terminal-first courses where progress is earned by working code. Every lesson
ends in real files on your machine and an automated checker; a lesson counts as
complete only when its checker passes.

## Quick start

```bash
practica/bin/practica setup          # creates ~/practica, ~/devops-lab and ~/.local/bin/practica
export PATH="$HOME/.local/bin:$PATH"

practica catalog                     # every course, grouped by field
practica paths                       # career paths that chain courses
practica course ai-engineering       # full Beginner → Expert roadmap
practica enrol ai-engineering --level beginner
practica next                        # your current lesson, its video, page and workspace
practica verify                      # run the checker; the result is recorded
practica status                      # progress, streak and reviews due across courses
practica transcript --out me.md      # completed lessons and level certificates
practica save                        # commit and push progress and lesson work
```

The visual course selector is `web/catalog.html` (built by `tools/build-web.py`).
Load your `progress.json` into it to see your progress on every course.

## Use it any time on claude.ai

Open a new session at https://claude.ai/code with the `practica` repository
selected. The start-up hook in `.claude/` creates the shortcuts, puts
`practica` on the PATH and shows Claude your status and current lesson, and
`CLAUDE.md` tells Claude to act as your instructor. After each lesson,
`practica save` commits and pushes your progress and work to GitHub.

## Catalogue

| Field | Course | Levels |
|---|---|---|
| AI & Machine Learning | AI Engineering: LLM Apps, RAG & Agents | Beginner → Expert |
| AI & Machine Learning | MLOps & ML Systems | Beginner → Expert |
| Infrastructure & Platforms | DevOps & Platform Engineering | Beginner → Expert |
| Infrastructure & Platforms | Cloud Architecture | Beginner → Expert |
| Infrastructure & Platforms | Kubernetes & Cloud-Native | Beginner → Expert |
| Data | Data Engineering | Beginner → Expert |
| Security | Cybersecurity & DevSecOps | Beginner → Expert |
| Foundations | Python for Automation & AI | Beginner → Expert |
| Foundations | AI-Assisted Software Engineering | Beginner → Expert |

Each course has 4 levels × 3 modules × 3 lessons plus a capstone per level
(324 lessons, 36 capstones). Lessons marked **ready** have full materials;
the rest are in the syllabus and are built, to the standard in
`AUTHORING.md`, when a learner reaches them.

## How progress works

- **Unlocking:** lessons unlock in order from the level you enrol at. Lower
  levels are skipped, not required.
- **Passing:** `practica verify` runs the lesson checker. Exit 0 records a
  pass with the date and attempt count; failures are recorded too.
- **Integrity:** each checker's SHA-256 is stored in the course manifest. A
  modified checker is refused and the attempt is not recorded.
- **Retention:** a passed lesson is due for review after 1, 3, 7, 21 and 60
  days. Re-running its checker when due advances the schedule; a lesson that
  passed before but fails now goes back on today's review list.
- **Certificates:** passing every lesson in a level records a certificate in
  the transcript.
- **Safety:** writes are locked (safe with parallel terminals), atomic, and
  keep three rolling backups. A damaged progress file is quarantined and the
  newest valid backup restored; nothing is ever silently reset.
- **Compatibility:** an existing `.devops_progress.json` is imported once and
  then kept up to date in its original format.

Progress lives in `progress.json` next to this README. Commit it with your
work so it survives a new machine or container.

## Exit codes

`0` ok · `1` checker failed or error · `2` usage · `3` lesson not built yet ·
`4` lesson locked · `5` checker modified

## Quality gate

`tools/test-all.sh` runs everything below and must pass before any lesson ships:

| Gate | What it proves |
|---|---|
| `practica doctor` | Manifests valid, lesson folders present, checker hashes match |
| `tests/test_practica.py` | 27 end-to-end tests of progression, reviews, certificates, locking, recovery, migration, tamper detection and both real lessons |
| `tools/selftest-*.sh` | Each checker passes a reference solution and catches deliberate mistakes |
| `tools/test-*-page.mjs` | Every control on each lesson page and the catalogue works at desktop and phone widths, light and dark |
