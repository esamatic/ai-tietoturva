"""Render site/index.html (and site/data.json) from data/ and snapshots/_status.json."""
from __future__ import annotations

import html
import json
import os
import sys

from common import ROOT, SNAPSHOTS, load_all, today


def main() -> int:
    data = load_all()
    status_path = SNAPSHOTS / "_status.json"
    data["monitor"] = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    data["generated"] = today()
    data["repo"] = os.environ.get("GITHUB_REPOSITORY", "")

    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    template = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    page = (template.replace("__TITLE__", html.escape(data["meta"]["title"]))
                    .replace("__DATA_JSON__", payload))
    site = ROOT / "site"
    site.mkdir(exist_ok=True)
    (site / "index.html").write_text(page, encoding="utf-8")
    (site / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"site/index.html ({len(page) // 1024} kt)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
