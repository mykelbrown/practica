#!/usr/bin/env python3
"""Build web/catalog.html by embedding the catalogue manifests into the template."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))
import practica  # noqa: E402

cat = practica.Catalog(ROOT)
data = {k: cat.meta[k] for k in ("name", "levels", "tracks", "paths")}
data["courses"] = [{k: v for k, v in c.items() if not k.startswith("_")} for c in cat.courses.values()]
for c in data["courses"]:  # drop author-only fields from the public page
    for lv in c["levels"]:
        for m in lv["modules"]:
            for l in m["lessons"]:
                for key in ("checker", "checker_sha256", "path", "legacy_id"):
                    l.pop(key, None)
payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
tpl = (ROOT / "web" / "catalog.template.html").read_text()
assert tpl.count("/*CATALOG_DATA*/null") == 1
out = ROOT / "web" / "catalog.html"
out.write_text(tpl.replace("/*CATALOG_DATA*/null", payload))
print(f"Wrote {out} ({out.stat().st_size // 1024} KB, {len(data['courses'])} courses)")
