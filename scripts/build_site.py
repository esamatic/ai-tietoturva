"""Render site/index.html (and site/data.json) from data/ and snapshots/_status.json."""
from __future__ import annotations

import html
import json
import os
import shutil
import sys

from common import LEGACY_STATUS, ROOT, STATUS_FILE, load_all, today


OG_IMAGE = ROOT / "templates" / "og-image.png"


def site_url(meta: dict, repo: str) -> str:
    """Public address of the page: meta.site_url, else the GitHub Pages address of the repository."""
    if meta.get("site_url"):
        return meta["site_url"].rstrip("/") + "/"
    if "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner.lower()}.github.io/{name}/"
    return ""


def share_meta(meta: dict, url: str) -> str:
    """Open Graph and Twitter tags for link previews (LinkedIn, Teams, Slack). Needs an absolute URL."""
    if not url:
        return ""
    title, desc = html.escape(meta["title"]), html.escape(meta["description"])
    tags = [
        f'<link rel="canonical" href="{url}">',
        '<meta property="og:type" content="website">',
        '<meta property="og:locale" content="fi_FI">',
        f'<meta property="og:url" content="{url}">',
        f'<meta property="og:title" content="{title}">',
        f'<meta property="og:description" content="{desc}">',
        '<meta name="twitter:card" content="summary_large_image">',
    ]
    if OG_IMAGE.exists():
        img = url + OG_IMAGE.name
        alt = html.escape(meta.get("og_image_alt", meta["title"]))
        tags += [
            f'<meta property="og:image" content="{img}">',
            '<meta property="og:image:type" content="image/png">',
            '<meta property="og:image:width" content="1200">',
            '<meta property="og:image:height" content="627">',
            f'<meta property="og:image:alt" content="{alt}">',
        ]
    return "".join(t + "\n" for t in tags)


def main() -> int:
    data = load_all()
    status_path = STATUS_FILE if STATUS_FILE.exists() else LEGACY_STATUS
    data["monitor"] = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    data["generated"] = today()
    data["repo"] = os.environ.get("GITHUB_REPOSITORY", "")

    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    meta = data["meta"]
    url = site_url(meta, data["repo"])
    template = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    page = (template.replace("__TITLE__", html.escape(meta["title"]))
                    .replace("__DESCRIPTION__", html.escape(meta["description"]))
                    .replace("__SHARE_META__", share_meta(meta, url))
                    .replace("__DATA_JSON__", payload))
    site = ROOT / "site"
    site.mkdir(exist_ok=True)
    if OG_IMAGE.exists():
        shutil.copyfile(OG_IMAGE, site / OG_IMAGE.name)
    (site / "index.html").write_text(page, encoding="utf-8")
    (site / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"site/index.html ({len(page) // 1024} kt)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
