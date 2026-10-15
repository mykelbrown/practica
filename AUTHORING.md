# Practica lesson standard

A lesson is **ready** only when every item below exists and `tools/test-all.sh`
passes. Planned lessons stay `"status": "planned"` until then.

## 1. Files in the lesson folder

| File | Requirement |
|---|---|
| `LESSON.md` | Goal, concepts table (why each matters in practice), precise challenge spec, verify command, stretch tasks |
| `lesson.html` | Interactive page: video, at least one diagram and one interactive simulator of the core mechanism, checklist, copyable verify command. Light and dark themes, phone width, reduced-motion support |
| `media/film.html` + `media/record.mjs` | Animated, captioned film source. `node media/record.mjs` renders `lesson.mp4`; also encode `lesson.webm` and `poster.jpg` |
| `workspace/` | Where the learner works. May contain a starter file that fails every check |
| `verify.sh` (+ helpers) | Checker. Prints `PASS`/`FAIL` lines with hints and ends with `Result: N passed, M failed`; exit 0 only when all pass. Never modifies the learner's work; tests failure paths on a copy. Bounded runtime |

## 2. Checker quality

- A reference solution lives in `tools/reference/` and must pass.
- A self-test in `tools/selftest-<lesson>.sh` applies at least five realistic
  mistakes to the reference; every one must be caught by a named check.
- The blank starter must fail.
- Hints say what to change, not just what failed.
- Runaway learner code (infinite loops, hangs) must fail fast with a hint.

## 3. Manifest entry

```json
{"id": "l01", "title": "...", "status": "ready", "minutes": 60,
 "path": "relative/folder", "skills": ["..."], "checker": ["verify.sh"],
 "checker_sha256": "<run: practica doctor --fix-hashes>", "page_url": "<published page>"}
```

## 4. Content principles

- Teach by building: every concept appears in the challenge.
- Local and free by default. Any paid service or account is flagged as
  optional before it is needed.
- Use real tools and real output. Never show invented terminal output.
- British English, plain sentences, professional terminology.
- One concept per diagram; the animation shows the mechanism, not decoration.
