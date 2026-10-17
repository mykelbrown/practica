#!/usr/bin/env python3
"""Practica: a terminal-first, verify-to-progress learning platform.

Courses live in courses/<id>/course.json. Learner progress lives in
progress.json (or $PRACTICA_PROGRESS). Lessons unlock in order, and a lesson
only counts as passed when its checker exits 0. Standard library only.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("PRACTICA_ROOT", Path(__file__).resolve().parent.parent))
PROGRESS = Path(os.environ.get("PRACTICA_PROGRESS", ROOT / "progress.json"))
LEGACY = Path(os.environ.get("PRACTICA_LEGACY", ROOT.parent / ".devops_progress.json"))
SCHEMA_VERSION = 2
LEVELS = ["beginner", "intermediate", "advanced", "expert"]
REVIEW_INTERVALS = [1, 3, 7, 21, 60]  # days between spaced reviews
BACKUPS = 3
VERIFY_TIMEOUT = 600

EXIT_OK, EXIT_FAIL, EXIT_USAGE, EXIT_NOT_READY, EXIT_LOCKED, EXIT_TAMPER = 0, 1, 2, 3, 4, 5


class PracticaError(Exception):
    def __init__(self, msg: str, code: int = EXIT_USAGE):
        super().__init__(msg)
        self.code = code


# --------------------------------------------------------------------------- time

def now() -> dt.datetime:
    fixed = os.environ.get("PRACTICA_NOW")
    if fixed:
        return dt.datetime.fromisoformat(fixed).replace(tzinfo=None)
    return dt.datetime.now().replace(microsecond=0)


def iso(t: dt.datetime) -> str:
    return t.isoformat(timespec="seconds")


# ------------------------------------------------------------------------ catalog

class Catalog:
    def __init__(self, root: Path = ROOT):
        self.root = root
        meta_path = root / "catalog" / "catalog.json"
        self.meta = json.loads(meta_path.read_text())
        self.courses: dict[str, dict] = {}
        for cid in self.meta["courses"]:
            path = root / "courses" / cid / "course.json"
            course = json.loads(path.read_text())
            course["_dir"] = path.parent
            self.courses[cid] = course

    def course(self, cid: str) -> dict:
        if cid not in self.courses:
            known = ", ".join(self.courses)
            raise PracticaError(f"Unknown course '{cid}'. Available: {known}")
        return self.courses[cid]

    def lessons(self, cid: str) -> list[dict]:
        """Flattened, ordered lesson list for a course."""
        course = self.course(cid)
        out = []
        for level in course["levels"]:
            for module in level["modules"]:
                for lesson in module["lessons"]:
                    rec = dict(lesson)
                    rec.update(
                        uid=f"{cid}/{level['id']}/{module['id']}/{lesson['id']}",
                        course=cid, level=level["id"], level_title=level["title"],
                        module=module["id"], module_title=module["title"],
                    )
                    rec["dir"] = course["_dir"] / lesson["path"] if lesson.get("path") else None
                    out.append(rec)
        return out

    def lesson(self, uid: str) -> dict:
        cid = uid.split("/", 1)[0]
        for rec in self.lessons(cid):
            if rec["uid"] == uid:
                return rec
        raise PracticaError(f"Unknown lesson '{uid}'. Use 'practica course {cid}' to list lesson ids.")

    def checker_hash(self, lesson: dict) -> str:
        h = hashlib.sha256()
        for name in lesson.get("checker", ["verify.sh"]):
            p = lesson["dir"] / name
            h.update(name.encode() + b"\0" + p.read_bytes() + b"\0")
        return h.hexdigest()

    def problems(self) -> list[str]:
        """Static validation of the whole catalogue."""
        issues = []
        for cid, course in self.courses.items():
            if course.get("id") != cid:
                issues.append(f"{cid}: course.json id is '{course.get('id')}'")
            ids = [lv["id"] for lv in course["levels"]]
            if ids != [lv for lv in LEVELS if lv in ids]:
                issues.append(f"{cid}: levels out of order {ids}")
            seen = set()
            for rec in self.lessons(cid):
                if rec["uid"] in seen:
                    issues.append(f"{rec['uid']}: duplicate id")
                seen.add(rec["uid"])
                if rec["status"] not in ("ready", "planned"):
                    issues.append(f"{rec['uid']}: bad status {rec['status']}")
                if rec["status"] == "ready":
                    if not rec["dir"] or not rec["dir"].is_dir():
                        issues.append(f"{rec['uid']}: lesson directory missing ({rec.get('path')})")
                        continue
                    for name in rec.get("checker", ["verify.sh"]):
                        if not (rec["dir"] / name).is_file():
                            issues.append(f"{rec['uid']}: checker file {name} missing")
                    v = rec["dir"] / "verify.sh"
                    if v.is_file() and not os.access(v, os.X_OK):
                        issues.append(f"{rec['uid']}: verify.sh not executable")
                    if not (rec["dir"] / "LESSON.md").is_file():
                        issues.append(f"{rec['uid']}: LESSON.md missing")
                    try:
                        if self.checker_hash(rec) != rec.get("checker_sha256"):
                            issues.append(f"{rec['uid']}: checker hash differs from manifest")
                    except FileNotFoundError:
                        pass
        for path in self.meta.get("paths", []):
            for cid in path["courses"]:
                if cid not in self.courses:
                    issues.append(f"career path '{path['title']}' references unknown course {cid}")
        return issues


# ----------------------------------------------------------------------- progress

def blank_progress() -> dict:
    return {"schema_version": SCHEMA_VERSION, "created_at": iso(now()), "learner": {},
            "active_course": None, "enrolments": {}, "history": []}


def validate_progress(p: dict) -> list[str]:
    errs = []
    if not isinstance(p, dict):
        return ["top level is not an object"]
    if p.get("schema_version") != SCHEMA_VERSION:
        errs.append(f"schema_version {p.get('schema_version')!r} != {SCHEMA_VERSION}")
    for key, typ in (("enrolments", dict), ("history", list), ("learner", dict)):
        if not isinstance(p.get(key), typ):
            errs.append(f"'{key}' missing or wrong type")
    for cid, enr in (p.get("enrolments") or {}).items():
        if not isinstance(enr, dict) or enr.get("start_level") not in LEVELS:
            errs.append(f"enrolment '{cid}' invalid")
        elif not isinstance(enr.get("lessons"), dict):
            errs.append(f"enrolment '{cid}' lessons missing")
    if p.get("active_course") is not None and p.get("active_course") not in (p.get("enrolments") or {}):
        errs.append("active_course is not an enrolled course")
    return errs


def migrate_legacy(legacy: dict, cat: Catalog) -> dict:
    """Convert a v1 .devops_progress.json into the v2 structure without losing data."""
    p = blank_progress()
    base = (legacy.get("baseline_experience") or "").lower()
    p["learner"] = {"baseline_experience": legacy.get("baseline_experience"),
                    "preferences": legacy.get("preferences", {})}
    level = "intermediate" if base == "intermediate" else "beginner"
    enr = new_enrolment(level)
    enr["legacy"] = {k: legacy.get(k) for k in ("completed_steps", "lesson_assets", "current_module", "current_day")
                     if k in legacy}
    by_legacy = {r.get("legacy_id"): r for r in cat.lessons("devops") if r.get("legacy_id")}
    for lid in legacy.get("completed_lessons", []):
        rec = by_legacy.get(lid)
        if rec:
            enr["lessons"][rec["uid"]] = {"status": "passed", "attempts": 1, "passed_at": iso(now()),
                                          "review_step": 0, "review_due": iso(now() + dt.timedelta(days=1)),
                                          "migrated": True}
    p["enrolments"]["devops"] = enr
    p["active_course"] = "devops"
    p["history"].append({"at": iso(now()), "event": "migrated", "detail": "imported .devops_progress.json (v1)"})
    return p


def new_enrolment(level: str) -> dict:
    return {"enrolled_at": iso(now()), "start_level": level, "lessons": {}, "certificates": {}}


class Store:
    """Locked, atomic, backed-up progress storage."""

    def __init__(self, path: Path = PROGRESS, legacy: Path = LEGACY):
        self.path, self.legacy = path, legacy
        self.notices: list[str] = []

    @contextlib.contextmanager
    def transaction(self, cat: Catalog, write: bool = True):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = open(self.path.with_name(self.path.name + ".lock"), "w")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX)
            data = self._load(cat)
            yield data
            if write:
                errs = validate_progress(data)
                if errs:
                    raise PracticaError("Refusing to save invalid progress: " + "; ".join(errs), EXIT_FAIL)
                self._save(data)
                self._mirror_legacy(data, cat)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()

    def _backup(self, i: int) -> Path:
        return self.path.with_name(f"{self.path.name}.bak{i}")

    def _read(self, path: Path) -> dict | None:
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            return None
        return data if not validate_progress(data) else None

    def _load(self, cat: Catalog) -> dict:
        if not self.path.exists():
            if self.legacy.exists():
                try:
                    data = migrate_legacy(json.loads(self.legacy.read_text()), cat)
                    shutil.copy2(self.legacy, self.legacy.with_name(self.legacy.name + ".pre-practica"))
                    self.notices.append(f"Imported your existing progress from {self.legacy} "
                                        f"(original kept as {self.legacy.name}.pre-practica).")
                    return data
                except (OSError, ValueError) as e:
                    self.notices.append(f"Could not import {self.legacy}: {e}. It was left untouched.")
            return blank_progress()
        data = self._read(self.path)
        if data is not None:
            return data
        stamp = now().strftime("%Y%m%dT%H%M%S")
        quarantine = self.path.with_name(f"{self.path.name}.corrupt-{stamp}")
        shutil.copy2(self.path, quarantine)
        for i in range(1, BACKUPS + 1):
            data = self._read(self._backup(i))
            if data is not None:
                self.notices.append(f"progress.json was damaged; saved it as {quarantine.name} and restored "
                                    f"backup {i} (last saved {data.get('history', [{}])[-1].get('at', '?')}).")
                data["history"].append({"at": iso(now()), "event": "recovered", "detail": f"from bak{i}"})
                return data
        raise PracticaError(f"progress.json is damaged and no valid backup exists. The damaged file is kept "
                            f"at {quarantine}. Fix it by hand or move it aside to start fresh.", EXIT_FAIL)

    def _save(self, data: dict) -> None:
        tmp = self.path.with_name(self.path.name + ".tmp")
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2, sort_keys=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        if self.path.exists() and self._read(self.path) is not None:
            for i in range(BACKUPS, 1, -1):
                if self._backup(i - 1).exists():
                    os.replace(self._backup(i - 1), self._backup(i))
            shutil.copy2(self.path, self._backup(1))
        os.replace(tmp, self.path)

    def _mirror_legacy(self, data: dict, cat: Catalog) -> None:
        """Keep the original .devops_progress.json format current for older tooling."""
        enr = data["enrolments"].get("devops")
        if not enr or not self.legacy.exists():  # only maintain a legacy file that already exists
            return
        try:
            legacy = json.loads(self.legacy.read_text())
        except ValueError:
            legacy = {}
        lessons = cat.lessons("devops")
        cur = current_lesson(enr, lessons)
        passed = [r.get("legacy_id") or r["uid"] for r in lessons
                  if enr["lessons"].get(r["uid"], {}).get("status") == "passed"]
        last = next((h for h in reversed(data["history"]) if h.get("course") == "devops"
                     and h["event"] in ("passed", "failed", "reviewed")), None)
        legacy.update({
            "current_module": int(cur["module"].lstrip("m")) if cur else legacy.get("current_module"),
            "current_day": int(cur["id"].lstrip("l")) if cur else legacy.get("current_day"),
            "topic": "DevOps",
            "baseline_experience": data["learner"].get("baseline_experience") or enr["start_level"].title(),
            "completed_lessons": passed,
            "last_verification": ({"lesson": last["lesson"], "at": last["at"], "result": last["event"]}
                                  if last else legacy.get("last_verification")),
            "managed_by": "practica (see practica/progress.json)",
        })
        legacy.setdefault("completed_steps", [])
        tmp = self.legacy.with_name(self.legacy.name + ".tmp")
        tmp.write_text(json.dumps(legacy, indent=2) + "\n")
        os.replace(tmp, self.legacy)


# --------------------------------------------------------------------- progression

def required(enr: dict, lessons: list[dict]) -> list[dict]:
    start = LEVELS.index(enr["start_level"])
    return [r for r in lessons if LEVELS.index(r["level"]) >= start]


def is_passed(enr: dict, uid: str) -> bool:
    return enr["lessons"].get(uid, {}).get("status") == "passed"


def current_lesson(enr: dict, lessons: list[dict]) -> dict | None:
    for r in required(enr, lessons):
        if not is_passed(enr, r["uid"]):
            return r
    return None


def lesson_state(enr: dict, lessons: list[dict], rec: dict) -> str:
    """passed | current | locked | skipped (below start level)."""
    if is_passed(enr, rec["uid"]):
        return "passed"
    if LEVELS.index(rec["level"]) < LEVELS.index(enr["start_level"]):
        return "skipped"
    cur = current_lesson(enr, lessons)
    return "current" if cur and cur["uid"] == rec["uid"] else "locked"


def reviews_due(enr: dict, when: dt.datetime) -> list[str]:
    return sorted(uid for uid, s in enr["lessons"].items()
                  if s.get("status") == "passed" and s.get("review_due")
                  and dt.datetime.fromisoformat(s["review_due"]) <= when)


def streak(history: list[dict], when: dt.datetime) -> int:
    days = {dt.datetime.fromisoformat(h["at"]).date() for h in history if h["event"] in ("passed", "reviewed")}
    day, n = when.date(), 0
    if day not in days:
        day -= dt.timedelta(days=1)  # today not yet practised does not break the streak
    while day in days:
        n += 1
        day -= dt.timedelta(days=1)
    return n


def bar(done: int, total: int, width: int = 24) -> str:
    fill = round(width * done / total) if total else 0
    return "█" * fill + "░" * (width - fill)


# ------------------------------------------------------------------------ commands

def need_enrolment(data: dict, cid: str | None) -> tuple[str, dict]:
    cid = cid or data.get("active_course")
    if not cid:
        raise PracticaError("You are not enrolled in any course. Run 'practica catalog' then 'practica enrol <course>'.")
    if cid not in data["enrolments"]:
        raise PracticaError(f"You are not enrolled in '{cid}'. Run 'practica enrol {cid}'.")
    return cid, data["enrolments"][cid]


def cmd_catalog(cat: Catalog, args) -> int:
    tracks = {t["id"]: t for t in cat.meta["tracks"]}
    for tid, track in tracks.items():
        rows = [c for c in cat.courses.values() if c["track"] == tid]
        if args.track and args.track != tid:
            continue
        if not rows:
            continue
        print(f"\n{track['title'].upper()}  ·  {track['summary']}")
        for c in rows:
            ls = cat.lessons(c["id"])
            if args.level and not any(lv["id"] == args.level for lv in c["levels"]):
                continue
            ready = sum(r["status"] == "ready" for r in ls)
            hours = sum(lv["hours"] for lv in c["levels"])
            print(f"  {c['id']:<18} {c['title']}")
            print(f"  {'':<18} {len(ls)} lessons · {hours} h · Beginner→Expert · {ready} ready now")
    print("\nDetails: practica course <id>    Career paths: practica paths    Enrol: practica enrol <id> --level beginner")
    return EXIT_OK


def cmd_paths(cat: Catalog, args) -> int:
    for p in cat.meta["paths"]:
        seq = " → ".join(cat.course(c)["title"] for c in p["courses"])
        print(f"\n{p['title']}\n  {p['summary']}\n  {seq}")
    return EXIT_OK


def cmd_course(cat: Catalog, store: Store, args) -> int:
    course = cat.course(args.course)
    with store.transaction(cat, write=False) as data:
        enr = data["enrolments"].get(course["id"])
    lessons = cat.lessons(course["id"])
    print(f"{course['title']}\n{course['summary']}\n")
    print("Why now: " + course["why_now"])
    print("Roles: " + ", ".join(course["careers"]))
    marks = {"passed": "[✓]", "current": "[▶]", "locked": "[ ]", "skipped": "[–]"}
    for level in course["levels"]:
        if args.level and level["id"] != args.level:
            continue
        lv_lessons = [r for r in lessons if r["level"] == level["id"]]
        done = sum(1 for r in lv_lessons if enr and is_passed(enr, r["uid"]))
        print(f"\n{level['id'].upper()} · {level['title']} · {level['hours']} h"
              + (f" · {done}/{len(lv_lessons)} passed" if enr else ""))
        for module in level["modules"]:
            print(f"  {module['id']}  {module['title']}")
            for r in (x for x in lv_lessons if x["module"] == module["id"]):
                state = lesson_state(enr, lessons, r) if enr else "locked"
                tag = "" if r["status"] == "ready" else "  (to be built)"
                print(f"      {marks[state] if enr else '   '} {r['id']}  {r['title']}{tag}")
        print(f"  Capstone: {level['capstone']}")
    if not enr:
        print(f"\nEnrol: practica enrol {course['id']} --level beginner|intermediate|advanced|expert")
    return EXIT_OK


def cmd_enrol(cat: Catalog, store: Store, args) -> int:
    course = cat.course(args.course)
    level = args.level
    if level not in [lv["id"] for lv in course["levels"]]:
        raise PracticaError(f"{course['title']} has no '{level}' level.")
    with store.transaction(cat) as data:
        enr = data["enrolments"].get(course["id"])
        if enr and enr["start_level"] == level:
            print(f"Already enrolled in {course['title']} from {level}. Now active.")
        elif enr:
            old = enr["start_level"]
            enr["start_level"] = level
            print(f"Changed your starting level in {course['title']} from {old} to {level}. "
                  "Lessons you passed stay passed.")
            data["history"].append({"at": iso(now()), "event": "level_changed", "course": course["id"],
                                    "detail": f"{old}->{level}"})
        else:
            data["enrolments"][course["id"]] = new_enrolment(level)
            data["history"].append({"at": iso(now()), "event": "enrolled", "course": course["id"], "detail": level})
            print(f"Enrolled in {course['title']} starting at {level}.")
        data["active_course"] = course["id"]
        cur = current_lesson(data["enrolments"][course["id"]], cat.lessons(course["id"]))
    if cur:
        print(f"First lesson: {cur['uid']}  {cur['title']}\nRun 'practica next' to begin.")
    return EXIT_OK


def cmd_switch(cat: Catalog, store: Store, args) -> int:
    with store.transaction(cat) as data:
        need_enrolment(data, args.course)
        data["active_course"] = args.course
    print(f"Active course: {cat.course(args.course)['title']}")
    return EXIT_OK


def cmd_status(cat: Catalog, store: Store, args) -> int:
    with store.transaction(cat, write=False) as data:
        pass
    if not data["enrolments"]:
        print("No enrolments yet. Browse with 'practica catalog'.")
        return EXIT_OK
    t = now()
    print(f"Streak: {streak(data['history'], t)} day(s)   Active course: {data['active_course']}\n")
    for cid, enr in data["enrolments"].items():
        lessons = cat.lessons(cid)
        req = required(enr, lessons)
        done = sum(is_passed(enr, r["uid"]) for r in req)
        cur = current_lesson(enr, lessons)
        due = reviews_due(enr, t)
        star = "*" if cid == data["active_course"] else " "
        print(f"{star} {cat.course(cid)['title']}  (from {enr['start_level']})")
        print(f"   {bar(done, len(req))} {done}/{len(req)} lessons  {round(100 * done / len(req)) if req else 0}%")
        print(f"   Next: {cur['uid'] + '  ' + cur['title'] if cur else 'course complete'}")
        if enr["certificates"]:
            print("   Certificates: " + ", ".join(f"{k} ({v[:10]})" for k, v in enr["certificates"].items()))
        if due:
            print(f"   Reviews due: {len(due)} → " + ", ".join(due))
    return EXIT_OK


def lesson_files(rec: dict) -> list[str]:
    out = []
    if rec["dir"]:
        for name, label in (("LESSON.md", "Read"), ("lesson.html", "Interactive page"),
                            ("media/lesson.mp4", "Video"), ("workspace", "Your workspace")):
            if (rec["dir"] / name).exists():
                out.append(f"  {label:<17} {rec['dir'] / name}")
    if rec.get("page_url"):
        out.append(f"  {'Online lesson':<17} {rec['page_url']}")
    return out


def cmd_next(cat: Catalog, store: Store, args) -> int:
    with store.transaction(cat, write=False) as data:
        cid, enr = need_enrolment(data, args.course)
    rec = current_lesson(enr, cat.lessons(cid))
    if not rec:
        print(f"You have finished every lesson in {cat.course(cid)['title']}. Run 'practica transcript'.")
        return EXIT_OK
    print(f"{rec['uid']}\n{rec['title']}\n{rec['level_title']} › {rec['module_title']} · ~{rec.get('minutes', 60)} min")
    if rec.get("skills"):
        print("Skills: " + ", ".join(rec["skills"]))
    if rec["status"] != "ready":
        print("\nThis lesson is in the syllabus but its materials are not built yet.\n"
              f"Ask Claude: \"build Practica lesson {rec['uid']}\"")
        return EXIT_NOT_READY
    print("\n".join(lesson_files(rec)))
    print("\nWhen you are done: practica verify")
    return EXIT_OK


def cmd_verify(cat: Catalog, store: Store, args) -> int:
    with store.transaction(cat, write=False) as data:
        cid, enr = need_enrolment(data, args.lesson.split("/")[0] if args.lesson else None)
    lessons = cat.lessons(cid)
    rec = cat.lesson(args.lesson) if args.lesson else current_lesson(enr, lessons)
    if rec is None:
        print("Nothing left to verify in this course.")
        return EXIT_OK
    state = lesson_state(enr, lessons, rec)
    if state == "locked":
        cur = current_lesson(enr, lessons)
        raise PracticaError(f"{rec['uid']} is locked. Finish {cur['uid']} first.", EXIT_LOCKED)
    if rec["status"] != "ready":
        raise PracticaError(f"{rec['uid']} is not built yet. Ask Claude: \"build Practica lesson {rec['uid']}\"",
                            EXIT_NOT_READY)
    if cat.checker_hash(rec) != rec["checker_sha256"]:
        with store.transaction(cat) as data:
            data["history"].append({"at": iso(now()), "event": "tamper", "course": cid, "lesson": rec["uid"]})
        raise PracticaError("The lesson checker has been modified, so this attempt cannot be recorded. "
                            f"Restore the original files in {rec['dir']} and try again.", EXIT_TAMPER)

    print(f"Checking {rec['uid']}  {rec['title']}\n")
    try:
        proc = subprocess.run(["bash", str(rec["dir"] / "verify.sh")], cwd=rec["dir"], text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=VERIFY_TIMEOUT)
        output, rc = proc.stdout, proc.returncode
    except subprocess.TimeoutExpired as e:
        output, rc = (e.stdout or "") + f"\nChecker timed out after {VERIFY_TIMEOUT}s", 124
    sys.stdout.write(output)
    m = re.search(r"Result: (\d+) passed, (\d+) failed", output)
    counts = {"passed": int(m[1]), "failed": int(m[2])} if m else None
    ok = rc == 0

    t = now()
    with store.transaction(cat) as data:
        enr = data["enrolments"][cid]
        entry = enr["lessons"].setdefault(rec["uid"], {"status": "in_progress", "attempts": 0,
                                                       "first_attempt_at": iso(t)})
        entry["attempts"] += 1
        entry["last_attempt_at"] = iso(t)
        entry["last_result"] = {"ok": ok, "exit_code": rc, "checks": counts}
        was_passed = entry["status"] == "passed"
        if ok and not was_passed:
            entry.update(status="passed", passed_at=iso(t), attempts_to_pass=entry["attempts"], review_step=0,
                         review_due=iso(t + dt.timedelta(days=REVIEW_INTERVALS[0])))
            event = "passed"
        elif ok and was_passed:
            due = dt.datetime.fromisoformat(entry["review_due"])
            if due <= t:
                entry["review_step"] = min(entry["review_step"] + 1, len(REVIEW_INTERVALS) - 1)
            entry["review_due"] = iso(t + dt.timedelta(days=REVIEW_INTERVALS[entry["review_step"]]))
            event = "reviewed"
        elif was_passed:
            entry["review_step"] = 0
            entry["review_due"] = iso(t)
            event = "regressed"
        else:
            event = "failed"
        data["history"].append({"at": iso(t), "event": event, "course": cid, "lesson": rec["uid"],
                                "checks": counts})
        newly = []
        for level in cat.course(cid)["levels"]:
            ids = [r["uid"] for r in lessons if r["level"] == level["id"]]
            if (level["id"] not in enr["certificates"] and LEVELS.index(level["id"]) >= LEVELS.index(enr["start_level"])
                    and all(is_passed(enr, u) for u in ids)):
                enr["certificates"][level["id"]] = iso(t)
                data["history"].append({"at": iso(t), "event": "certificate", "course": cid, "detail": level["id"]})
                newly.append(level["title"])
        nxt = current_lesson(enr, lessons)

    print()
    if event == "passed":
        print(f"PASSED. {rec['uid']} recorded as complete (attempt {entry['attempts']}).")
        print(f"First review due {entry['review_due'][:10]}: re-run 'practica verify {rec['uid']}' then.")
    elif event == "reviewed":
        print(f"Review recorded. Next review {entry['review_due'][:10]}.")
    elif event == "regressed":
        print("This lesson passed before but fails now. It is back on your review list for today.")
    else:
        print(f"Not yet. Attempt {entry['attempts']} recorded. Fix the FAIL lines above and run 'practica verify' again.")
    for title in newly:
        print(f"Level complete: {title}. Your certificate is in 'practica transcript'.")
    if ok and nxt and event == "passed":
        print(f"Unlocked: {nxt['uid']}  {nxt['title']}" + ("" if nxt["status"] == "ready" else "  (to be built)"))
    return EXIT_OK if ok else EXIT_FAIL


def cmd_transcript(cat: Catalog, store: Store, args) -> int:
    with store.transaction(cat, write=False) as data:
        pass
    t = now()
    lines = ["# Practica transcript", "", f"Generated {iso(t)}", ""]
    for cid, enr in data["enrolments"].items():
        course, lessons = cat.course(cid), cat.lessons(cid)
        req = required(enr, lessons)
        done = [r for r in req if is_passed(enr, r["uid"])]
        lines += [f"## {course['title']}", "",
                  f"Enrolled {enr['enrolled_at'][:10]} at {enr['start_level']} level · "
                  f"{len(done)}/{len(req)} lessons passed", ""]
        for lv, at in enr["certificates"].items():
            lines.append(f"- **Certificate: {cat.course(cid)['title']}, {lv.title()} level**, awarded {at[:10]}")
        if done:
            lines += (["", ] if enr["certificates"] else []) + ["| Lesson | Passed | Attempts to pass | Skills |",
                                                                 "|---|---|---|---|"]
            for r in done:
                s = enr["lessons"][r["uid"]]
                lines.append(f"| {r['title']} | {s['passed_at'][:10]} | {s.get('attempts_to_pass', s['attempts'])} "
                             f"| {', '.join(r.get('skills', []))} |")
        lines.append("")
    text = "\n".join(lines)
    if args.out:
        Path(args.out).write_text(text)
        print(f"Wrote {args.out}")
    else:
        print(text)
    return EXIT_OK


def cmd_doctor(cat: Catalog, store: Store, args) -> int:
    issues = cat.problems()
    if args.fix_hashes:
        for cid, course in cat.courses.items():
            changed = False
            for level in course["levels"]:
                for module in level["modules"]:
                    for lesson in module["lessons"]:
                        if lesson["status"] != "ready":
                            continue
                        rec = cat.lesson(f"{cid}/{level['id']}/{module['id']}/{lesson['id']}")
                        h = cat.checker_hash(rec)
                        if lesson.get("checker_sha256") != h:
                            lesson["checker_sha256"] = h
                            changed = True
            if changed:
                path = course["_dir"] / "course.json"
                clean = {k: v for k, v in course.items() if not k.startswith("_")}
                path.write_text(json.dumps(clean, indent=2, ensure_ascii=False) + "\n")
                print(f"Updated checker hashes in {path}")
        issues = Catalog(cat.root).problems()
    with store.transaction(cat, write=False) as data:
        errs = validate_progress(data)
    for cid in data["enrolments"]:
        if cid not in cat.courses:
            errs.append(f"progress references unknown course {cid}")
    for msg in issues + errs:
        print("PROBLEM " + msg)
    n = sum(len(cat.lessons(c)) for c in cat.courses)
    print(f"Catalogue: {len(cat.courses)} courses, {n} lessons. Progress file: {store.path}")
    print("Healthy." if not issues + errs else f"{len(issues + errs)} problem(s).")
    return EXIT_OK if not issues + errs else EXIT_FAIL


def cmd_setup(cat: Catalog, store: Store, args) -> int:
    """Create convenience links so lesson paths like ~/devops-lab work in any container."""
    home = Path.home()
    links = {home / "practica": ROOT, home / "devops-lab": ROOT / "courses" / "devops"}
    for link, target in links.items():
        if link.resolve() == target.resolve():
            print(f"ok      {link} -> {target}")
        elif link.exists() or link.is_symlink():
            print(f"skipped {link} exists and points elsewhere; left untouched")
        else:
            link.symlink_to(target)
            print(f"linked  {link} -> {target}")
    bin_dir = home / ".local" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    exe = bin_dir / "practica"
    if not exe.exists():
        exe.symlink_to(ROOT / "bin" / "practica")
        print(f"linked  {exe}")
    if str(bin_dir) not in os.environ.get("PATH", "").split(":"):
        print(f"Add to PATH: export PATH=\"{bin_dir}:$PATH\"")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)  # behave like other CLIs when piped into head
    ap = argparse.ArgumentParser(prog="practica", description="Terminal-first courses with verified progress.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("catalog", help="list courses")
    s.add_argument("--track"); s.add_argument("--level", choices=LEVELS)
    sub.add_parser("paths", help="career paths that chain courses")
    s = sub.add_parser("course", help="show a course roadmap"); s.add_argument("course")
    s.add_argument("--level", choices=LEVELS)
    s = sub.add_parser("enrol", aliases=["enroll"], help="enrol in a course at a level")
    s.add_argument("course"); s.add_argument("--level", choices=LEVELS, default="beginner")
    s = sub.add_parser("switch", help="change the active course"); s.add_argument("course")
    sub.add_parser("status", help="progress across all courses")
    s = sub.add_parser("next", help="show your current lesson"); s.add_argument("--course")
    s = sub.add_parser("verify", help="check your work and record the result"); s.add_argument("lesson", nargs="?")
    s = sub.add_parser("transcript", help="export completed lessons and certificates")
    s.add_argument("--out")
    s = sub.add_parser("doctor", help="validate catalogue and progress"); s.add_argument("--fix-hashes", action="store_true")
    sub.add_parser("setup", help="create ~/practica and ~/devops-lab links")
    args = ap.parse_args(argv)

    try:
        cat = Catalog()
        store = Store()
        handlers = {"catalog": lambda: cmd_catalog(cat, args), "paths": lambda: cmd_paths(cat, args),
                    "course": lambda: cmd_course(cat, store, args), "enrol": lambda: cmd_enrol(cat, store, args),
                    "enroll": lambda: cmd_enrol(cat, store, args), "switch": lambda: cmd_switch(cat, store, args),
                    "status": lambda: cmd_status(cat, store, args), "next": lambda: cmd_next(cat, store, args),
                    "verify": lambda: cmd_verify(cat, store, args),
                    "transcript": lambda: cmd_transcript(cat, store, args),
                    "doctor": lambda: cmd_doctor(cat, store, args), "setup": lambda: cmd_setup(cat, store, args)}
        code = handlers[args.cmd]()
        for n in store.notices:
            print("NOTE " + n, file=sys.stderr)
        return code
    except PracticaError as e:
        print(f"practica: {e}", file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
