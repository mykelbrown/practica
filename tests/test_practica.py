"""End-to-end tests for the practica CLI: progression, persistence, recovery and integrity.

Run: python3 -m unittest discover -s tests -v   (from the practica directory)
Each test drives the real CLI in a subprocess against an isolated catalogue and progress file.
"""
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLI = REPO / "bin" / "practica.py"
sys.path.insert(0, str(REPO / "bin"))
import practica  # noqa: E402  (for hashing helpers only)

VERIFY = """#!/usr/bin/env bash
# passes when workspace/done exists
if [ -f "$(dirname "$0")/workspace/done" ]; then echo "  PASS done"; echo "Result: 1 passed, 0 failed"; exit 0
else echo "  FAIL done missing"; echo "Result: 0 passed, 1 failed"; exit 1; fi
"""


def lesson(lid, status="ready", **extra):
    d = {"id": lid, "title": f"Lesson {lid}", "status": status, "minutes": 10}
    d.update(extra)
    return d


def make_course(cid, levels):
    return {"id": cid, "title": f"{cid.title()} Course", "track": "t", "summary": "s", "why_now": "w",
            "careers": ["c"], "outcomes": ["o"], "levels": levels}


class Fixture:
    """A throwaway Practica root with two small courses."""

    def __init__(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="practica-test-"))
        self.root = self.tmp / "practica"
        (self.root / "catalog").mkdir(parents=True)
        (self.root / "catalog" / "catalog.json").write_text(json.dumps({
            "name": "T", "tracks": [{"id": "t", "title": "T", "summary": "s"}],
            "courses": ["devops", "alpha"], "paths": [{"id": "p", "title": "P", "summary": "s", "courses": ["alpha"]}]}))
        # devops: beginner m01 l01,l02 ready ; intermediate m02 l01 ready, l02 planned
        self.add_course("devops", [
            {"id": "beginner", "title": "Foundations", "hours": 1, "capstone": "c", "modules": [
                {"id": "m01", "title": "M1", "outcome": "o", "lessons": [lesson("l01", legacy_id="m1d1"), lesson("l02")]}]},
            {"id": "intermediate", "title": "Practitioner", "hours": 1, "capstone": "c", "modules": [
                {"id": "m02", "title": "M2", "outcome": "o", "lessons": [lesson("l01"), lesson("l02", "planned")]}]}])
        self.add_course("alpha", [
            {"id": "beginner", "title": "Foundations", "hours": 1, "capstone": "c", "modules": [
                {"id": "m01", "title": "M1", "outcome": "o", "lessons": [lesson("l01")]}]}])
        self.progress = self.tmp / "progress.json"
        self.legacy = self.tmp / ".devops_progress.json"
        self.now = "2026-10-15T10:00:00"

    def add_course(self, cid, levels):
        cdir = self.root / "courses" / cid
        for lv in levels:
            for m in lv["modules"]:
                for l in m["lessons"]:
                    if l["status"] == "ready":
                        l["path"] = f"{lv['id']}/{m['id']}-{l['id']}"
                        d = cdir / l["path"]
                        (d / "workspace").mkdir(parents=True)
                        (d / "verify.sh").write_text(VERIFY)
                        (d / "verify.sh").chmod(0o755)
                        (d / "LESSON.md").write_text("# lesson\n")
                        l["checker"] = ["verify.sh"]
        course = make_course(cid, levels)
        cdir.mkdir(parents=True, exist_ok=True)
        (cdir / "course.json").write_text(json.dumps(course))
        # fill hashes (Catalog.checker_hash only reads lesson["dir"] and lesson["checker"])
        for lv in course["levels"]:
            for m in lv["modules"]:
                for l in m["lessons"]:
                    if l["status"] == "ready":
                        l["checker_sha256"] = practica.Catalog.checker_hash(None, dict(l, dir=cdir / l["path"]))
        (cdir / "course.json").write_text(json.dumps(course))

    def env(self, now=None):
        e = dict(os.environ, PRACTICA_ROOT=str(self.root), PRACTICA_PROGRESS=str(self.progress),
                 PRACTICA_LEGACY=str(self.legacy), PRACTICA_NOW=now or self.now, HOME=str(self.tmp))
        return e

    def run(self, *args, now=None):
        p = subprocess.run([sys.executable, str(CLI), *args], env=self.env(now), text=True,
                           capture_output=True, timeout=120)
        return p.returncode, p.stdout + p.stderr

    def complete(self, cid, path):
        (self.root / "courses" / cid / path / "workspace" / "done").write_text("x")

    def uncomplete(self, cid, path):
        (self.root / "courses" / cid / path / "workspace" / "done").unlink()

    def data(self):
        return json.loads(self.progress.read_text())

    def cleanup(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class ProgressionTests(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()

    def tearDown(self):
        self.f.cleanup()

    def test_no_enrolment(self):
        rc, out = self.f.run("status")
        self.assertEqual(rc, 0)
        self.assertIn("No enrolments", out)
        rc, out = self.f.run("next")
        self.assertEqual(rc, 2)
        self.assertFalse(self.f.progress.exists(), "read-only commands must not create a progress file")

    def test_enrol_creates_valid_progress(self):
        rc, out = self.f.run("enrol", "devops")
        self.assertEqual(rc, 0, out)
        d = self.f.data()
        self.assertEqual(practica.validate_progress(d), [])
        self.assertEqual(d["active_course"], "devops")
        self.assertEqual(d["enrolments"]["devops"]["start_level"], "beginner")
        self.assertEqual(d["history"][-1]["event"], "enrolled")

    def test_failed_attempt_is_recorded_without_advancing(self):
        self.f.run("enrol", "devops")
        rc, out = self.f.run("verify")
        self.assertEqual(rc, 1)
        s = self.f.data()["enrolments"]["devops"]["lessons"]["devops/beginner/m01/l01"]
        self.assertEqual((s["status"], s["attempts"]), ("in_progress", 1))
        self.assertEqual(s["last_result"]["checks"], {"passed": 0, "failed": 1})
        rc, out = self.f.run("next")
        self.assertIn("devops/beginner/m01/l01", out)

    def test_pass_unlocks_next_and_schedules_review(self):
        self.f.run("enrol", "devops")
        self.f.run("verify")  # fail first
        self.f.complete("devops", "beginner/m01-l01")
        rc, out = self.f.run("verify")
        self.assertEqual(rc, 0, out)
        self.assertIn("Unlocked: devops/beginner/m01/l02", out)
        s = self.f.data()["enrolments"]["devops"]["lessons"]["devops/beginner/m01/l01"]
        self.assertEqual((s["status"], s["attempts"]), ("passed", 2))
        self.assertEqual(s["review_due"], "2026-10-16T10:00:00")
        rc, out = self.f.run("next")
        self.assertIn("devops/beginner/m01/l02", out)

    def test_locked_lesson_cannot_be_verified(self):
        self.f.run("enrol", "devops")
        self.f.complete("devops", "beginner/m01-l02")
        rc, out = self.f.run("verify", "devops/beginner/m01/l02")
        self.assertEqual(rc, 4, out)
        self.assertIn("locked", out)
        self.assertNotIn("devops/beginner/m01/l02", self.f.data()["enrolments"]["devops"]["lessons"])

    def test_level_certificate_and_transcript(self):
        self.f.run("enrol", "devops")
        for p in ("beginner/m01-l01", "beginner/m01-l02"):
            self.f.complete("devops", p)
            self.assertEqual(self.f.run("verify")[0], 0)
        d = self.f.data()["enrolments"]["devops"]
        self.assertIn("beginner", d["certificates"])
        rc, out = self.f.run("transcript")
        self.assertIn("Certificate: Devops Course, Beginner level", out)
        self.assertIn("2/4 lessons passed", out)

    def test_planned_lesson_reports_not_ready(self):
        self.f.run("enrol", "devops", "--level", "intermediate")
        self.f.complete("devops", "intermediate/m02-l01")
        self.assertEqual(self.f.run("verify")[0], 0)
        rc, out = self.f.run("next")
        self.assertEqual(rc, 3)
        self.assertIn("not built yet", out)
        rc, out = self.f.run("verify")
        self.assertEqual(rc, 3)

    def test_start_level_skips_lower_levels(self):
        self.f.run("enrol", "devops", "--level", "intermediate")
        rc, out = self.f.run("next")
        self.assertIn("devops/intermediate/m02/l01", out)
        rc, out = self.f.run("course", "devops")
        self.assertIn("[–] l01", out)
        self.assertIn("[▶] l01", out)
        rc, out = self.f.run("status")
        self.assertIn("0/2 lessons", out)

    def test_changing_level_keeps_passes(self):
        self.f.run("enrol", "devops")
        self.f.complete("devops", "beginner/m01-l01")
        self.f.run("verify")
        self.f.run("enrol", "devops", "--level", "intermediate")
        d = self.f.data()["enrolments"]["devops"]
        self.assertEqual(d["start_level"], "intermediate")
        self.assertEqual(d["lessons"]["devops/beginner/m01/l01"]["status"], "passed")

    def test_tampered_checker_is_refused(self):
        self.f.run("enrol", "devops")
        v = self.f.root / "courses/devops/beginner/m01-l01/verify.sh"
        v.write_text("#!/usr/bin/env bash\necho 'Result: 1 passed, 0 failed'; exit 0\n")
        rc, out = self.f.run("verify")
        self.assertEqual(rc, 5, out)
        d = self.f.data()
        self.assertNotIn("devops/beginner/m01/l01", d["enrolments"]["devops"]["lessons"])
        self.assertEqual(d["history"][-1]["event"], "tamper")

    def test_transcript_counts_attempts_to_pass_not_reviews(self):
        self.f.run("enrol", "devops")
        self.f.run("verify")
        self.f.complete("devops", "beginner/m01-l01")
        self.f.run("verify")
        self.f.run("verify", "devops/beginner/m01/l01", now="2026-10-17T10:00:00")  # a review
        s = self.f.data()["enrolments"]["devops"]["lessons"]["devops/beginner/m01/l01"]
        self.assertEqual((s["attempts"], s["attempts_to_pass"]), (3, 2))
        rc, out = self.f.run("transcript")
        self.assertIn("| Lesson l01 | 2026-10-15 | 2 |", out)

    def test_spaced_review_cycle(self):
        self.f.run("enrol", "devops")
        self.f.complete("devops", "beginner/m01-l01")
        self.f.run("verify")
        uid = "devops/beginner/m01/l01"
        rc, out = self.f.run("status", now="2026-10-15T18:00:00")
        self.assertNotIn("Reviews due", out)
        rc, out = self.f.run("status", now="2026-10-16T09:00:00")  # due 16th 10:00, not yet
        self.assertNotIn("Reviews due", out)
        rc, out = self.f.run("status", now="2026-10-17T09:00:00")
        self.assertIn("Reviews due: 1", out)
        rc, out = self.f.run("verify", uid, now="2026-10-17T09:00:00")
        self.assertEqual(rc, 0, out)
        s = self.f.data()["enrolments"]["devops"]["lessons"][uid]
        self.assertEqual(s["review_step"], 1)
        self.assertEqual(s["review_due"], "2026-10-20T09:00:00")  # 3-day interval
        self.assertEqual(self.f.data()["history"][-1]["event"], "reviewed")

    def test_regression_puts_lesson_back_on_review(self):
        self.f.run("enrol", "devops")
        self.f.complete("devops", "beginner/m01-l01")
        self.f.run("verify")
        self.f.uncomplete("devops", "beginner/m01-l01")
        rc, out = self.f.run("verify", "devops/beginner/m01/l01", now="2026-10-15T12:00:00")
        self.assertEqual(rc, 1)
        s = self.f.data()["enrolments"]["devops"]["lessons"]["devops/beginner/m01/l01"]
        self.assertEqual(s["status"], "passed")
        self.assertEqual(s["review_due"], "2026-10-15T12:00:00")
        self.assertEqual(self.f.data()["history"][-1]["event"], "regressed")

    def test_streak_counts_consecutive_days(self):
        self.f.run("enrol", "devops")
        self.f.complete("devops", "beginner/m01-l01")
        self.f.run("verify", now="2026-10-15T10:00:00")
        self.f.run("verify", "devops/beginner/m01/l01", now="2026-10-16T10:00:00")
        rc, out = self.f.run("status", now="2026-10-17T08:00:00")
        self.assertIn("Streak: 2 day(s)", out)
        rc, out = self.f.run("status", now="2026-10-19T08:00:00")
        self.assertIn("Streak: 0 day(s)", out)

    def test_courses_progress_independently(self):
        self.f.run("enrol", "devops")
        self.f.run("enrol", "alpha")
        self.f.complete("alpha", "beginner/m01-l01")
        self.assertEqual(self.f.run("verify")[0], 0)  # active course is alpha
        d = self.f.data()
        self.assertIn("beginner", d["enrolments"]["alpha"]["certificates"])
        self.assertEqual(d["enrolments"]["devops"]["lessons"], {})
        self.f.run("switch", "devops")
        rc, out = self.f.run("next")
        self.assertIn("devops/beginner/m01/l01", out)
        rc, out = self.f.run("status")
        self.assertIn("1/1 lessons  100%", out)

    def test_backups_rotate(self):
        self.f.run("enrol", "devops")
        for _ in range(5):
            self.f.run("verify")
        for i in (1, 2, 3):
            self.assertTrue(self.f.progress.with_name(f"progress.json.bak{i}").exists())
        self.assertFalse(self.f.progress.with_name("progress.json.bak4").exists())

    def test_corrupt_progress_recovers_from_backup(self):
        self.f.run("enrol", "devops")
        self.f.run("verify")
        self.f.run("verify")  # bak1 now holds the state after the first attempt
        self.f.progress.write_text("{ not json")
        rc, out = self.f.run("status")
        self.assertEqual(rc, 0, out)
        self.assertIn("damaged", out)
        quarantined = list(self.f.tmp.glob("progress.json.corrupt-*"))
        self.assertEqual(len(quarantined), 1)
        self.assertEqual(quarantined[0].read_text(), "{ not json")
        rc, out = self.f.run("verify")  # a write persists the recovered state
        self.assertEqual(practica.validate_progress(self.f.data()), [])
        self.assertGreaterEqual(self.f.data()["enrolments"]["devops"]["lessons"]["devops/beginner/m01/l01"]["attempts"], 2)

    def test_corrupt_without_backup_fails_loudly(self):
        self.f.progress.write_text('{"schema_version": 99}')
        rc, out = self.f.run("status")
        self.assertEqual(rc, 1)
        self.assertIn("no valid backup", out)
        self.assertEqual(self.f.progress.read_text(), '{"schema_version": 99}', "original must be preserved")

    def test_legacy_progress_is_migrated_and_mirrored(self):
        legacy = {"current_module": 1, "current_day": 1, "topic": "DevOps", "baseline_experience": "Beginner",
                  "completed_steps": ["m1d1:lesson_scaffolded"], "completed_lessons": ["m1d1"],
                  "last_verification": None, "preferences": {"diagrams": True}}
        self.f.legacy.write_text(json.dumps(legacy))
        rc, out = self.f.run("next")
        self.assertIn("Imported your existing progress", out)
        self.assertIn("devops/beginner/m01/l02", out, "m1d1 should count as passed")
        self.f.run("verify")  # first write: persist migration + mirror
        d = self.f.data()
        self.assertEqual(d["learner"]["preferences"], {"diagrams": True})
        self.assertEqual(d["enrolments"]["devops"]["legacy"]["completed_steps"], ["m1d1:lesson_scaffolded"])
        mirror = json.loads(self.f.legacy.read_text())
        self.assertEqual((mirror["current_module"], mirror["current_day"]), (1, 2))
        self.assertEqual(mirror["completed_lessons"], ["m1d1"])
        self.assertEqual(mirror["completed_steps"], ["m1d1:lesson_scaffolded"])
        self.assertEqual(mirror["last_verification"]["result"], "failed")
        self.assertTrue(self.f.tmp.joinpath(".devops_progress.json.pre-practica").exists())

    def test_no_legacy_file_is_created_when_absent(self):
        self.f.run("enrol", "devops")
        self.f.run("verify")
        self.assertFalse(self.f.legacy.exists(), "the legacy mirror must only update an existing file")

    def test_concurrent_writes_do_not_lose_attempts(self):
        self.f.run("enrol", "devops")
        with concurrent.futures.ThreadPoolExecutor(8) as ex:
            codes = list(ex.map(lambda _: self.f.run("verify")[0], range(12)))
        self.assertEqual(codes, [1] * 12)
        s = self.f.data()["enrolments"]["devops"]["lessons"]["devops/beginner/m01/l01"]
        self.assertEqual(s["attempts"], 12)

    def test_doctor_detects_problems(self):
        self.assertEqual(self.f.run("doctor")[0], 0)
        (self.f.root / "courses/devops/beginner/m01-l02/verify.sh").write_text("#!/bin/sh\nexit 0\n")
        shutil.rmtree(self.f.root / "courses/alpha/beginner/m01-l01")
        rc, out = self.f.run("doctor")
        self.assertEqual(rc, 1)
        self.assertIn("checker hash differs", out)
        self.assertIn("lesson directory missing", out)


class RealCatalogueTests(unittest.TestCase):
    """Run the real lessons end to end on a copy of the repository."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="practica-real-"))
        cls.root = cls.tmp / "practica"
        shutil.copytree(REPO, cls.root, ignore=shutil.ignore_patterns("progress.json*", "media", "*.mp4", "*.webm"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_cli(self, *args):
        env = dict(os.environ, PRACTICA_ROOT=str(self.root), PRACTICA_PROGRESS=str(self.tmp / "p.json"),
                   PRACTICA_LEGACY=str(self.tmp / "none.json"), HOME=str(self.tmp))
        p = subprocess.run([sys.executable, str(self.root / "bin/practica.py"), *args], env=env, text=True,
                           capture_output=True, timeout=300)
        return p.returncode, p.stdout + p.stderr

    def test_1_catalogue_is_healthy(self):
        rc, out = self.run_cli("doctor")
        self.assertEqual(rc, 0, out)
        rc, out = self.run_cli("catalog")
        for cid in ("devops", "ai-engineering", "mlops", "data-engineering", "cloud", "kubernetes",
                    "security", "python", "ai-assisted-dev"):
            self.assertIn(cid, out)
        rc, out = self.run_cli("paths")
        self.assertIn("AI Engineer", out)

    def test_2_devops_lesson_progression(self):
        self.run_cli("enrol", "devops")
        rc, out = self.run_cli("verify")
        self.assertEqual(rc, 1, out)
        self.assertIn("Result: 0 passed", out)
        ws = self.root / "courses/devops/module-01/day-01/workspace"
        script = (self.root / "tools/selftest-m1d1.sh").read_text()
        body = script.split("build() {", 1)[1].split("\n}\n", 1)[0]
        build = "build() {" + body + "\n}\n"
        subprocess.run(["bash", "-c", build + 'build "$1"; cp -a "$1/workspace/app" "$2/"',
                        "_", str(self.tmp / "ref"), str(ws)], check=True,
                       env=dict(os.environ, VERIFY=str(ws.parent / "verify.sh")))
        rc, out = self.run_cli("verify")
        self.assertEqual(rc, 0, out)
        self.assertIn("Result: 15 passed, 0 failed", out)
        self.assertIn("Unlocked: devops/beginner/m01/l02", out)
        rc, out = self.run_cli("next")
        self.assertEqual(rc, 3, out)

    def test_3_ai_lesson_progression(self):
        self.run_cli("enrol", "ai-engineering")
        rc, out = self.run_cli("verify")
        self.assertEqual(rc, 1)
        ws = self.root / "courses/ai-engineering/beginner/m01-l01-structured-output/workspace/extract.py"
        shutil.copy(self.root / "tools/reference/ai-eng-b-m01-l01.py", ws)
        rc, out = self.run_cli("verify")
        self.assertEqual(rc, 0, out)
        rc, out = self.run_cli("status")
        self.assertIn("1/36 lessons", out)
        self.assertIn("Streak: 1 day(s)", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
