#!/usr/bin/env python3
# Usage: python3 tools/demo-journey.py web/demo/journey.json  (then rebuild web/demo/demo-film.html)
"""Drive the real practica CLI through a learner journey on a throwaway copy; record real output."""
import json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path
REPO = Path("/home/user/practica")
tmp = Path(tempfile.mkdtemp(prefix="practica-demo-"))
root = tmp / "practica"
shutil.copytree(REPO, root, ignore=shutil.ignore_patterns(".git", "progress.json*", "media", "*.mp4", "*.webm"))
lesson = root / "courses/ai-engineering/beginner/m01-l01-structured-output"
ref = (REPO / "tools/reference/ai-eng-b-m01-l01.py").read_text()
steps = []

def run(cmd, note, now="2026-10-17T10:00:00", show=None):
    env = dict(os.environ, PRACTICA_ROOT=str(root), PRACTICA_PROGRESS=str(tmp / "progress.json"),
               PRACTICA_LEGACY=str(tmp / "none.json"), PRACTICA_NOW=now, HOME=str(tmp))
    p = subprocess.run(["python3", str(root / "bin/practica.py"), *cmd.split()[1:]], env=env, text=True,
                       capture_output=True, timeout=300)
    out = re.sub(r"\x1b\[[0-9;]*m", "", p.stdout + p.stderr).replace(str(root), "~/practica")
    if show:
        out = show(out)
    steps.append({"cmd": cmd, "out": out.rstrip(), "rc": p.returncode, "note": note, "now": now})
    print(f"$ {cmd}   [exit {p.returncode}]\n{out.rstrip()}\n")

def head(n): return lambda o: "\n".join(o.splitlines()[:n]) + ("\n…" if len(o.splitlines()) > n else "")
def fails_and_result(o): return "\n".join(l for l in o.splitlines() if "FAIL" in l or "hint" in l or l.startswith("Result") or l.startswith(("PASSED", "Not yet", "Unlocked", "First review", "Checking", "Review", "practica:")))[:2500]

run("practica catalog", "Browse every course, grouped by field", show=head(22))
run("practica paths", "Career paths chain courses towards a role", show=head(9))
run("practica enrol ai-engineering --level beginner", "Enrol at the level that suits you")
run("practica next", "Your current lesson, with its video, page and workspace")
run("practica verify", "Day 1: the blank starter fails, and the attempt is recorded", show=fails_and_result)
buggy = ref.replace("if type(p) is not int or", "if not isinstance(p, int) or")
(lesson / "workspace/extract.py").write_text(buggy)
run("practica verify", "Attempt 2: one bug left, a boolean priority slips through", show=fails_and_result)
(lesson / "workspace/extract.py").write_text(ref)
run("practica verify", "Attempt 3: fixed, passed, next lesson unlocked", show=fails_and_result)
run("practica verify ai-engineering/beginner/m01/l03", "Lessons unlock in order: skipping ahead is refused")
chk = lesson / "checks.py"; orig = chk.read_text(); chk.write_text(orig + "\n# sneaky edit\n")
run("practica verify ai-engineering/beginner/m01/l01", "Editing the checker to cheat is detected")
chk.write_text(orig)
run("practica status", "Progress, streak and reviews across courses", now="2026-10-19T09:00:00")
run("practica verify ai-engineering/beginner/m01/l01", "Two days later: the spaced review is re-run and recorded", now="2026-10-19T09:00:00", show=fails_and_result)
run("practica transcript", "A transcript of everything you have passed", now="2026-10-19T09:05:00")
data = json.loads((tmp / "progress.json").read_text())
lesson_rec = data["enrolments"]["ai-engineering"]["lessons"]["ai-engineering/beginner/m01/l01"]
print("RECORDED:", json.dumps(lesson_rec, indent=1))
print("HISTORY:", [ (h["at"], h["event"]) for h in data["history"]])
json.dump(steps, open(sys.argv[1], "w"), indent=1)
shutil.rmtree(tmp)
