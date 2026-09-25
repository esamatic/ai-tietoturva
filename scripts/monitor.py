"""Fetch monitored sources, compare with snapshots, open issues for changes.

The first successful fetch of a source only stores a baseline.
A fetch that fails or returns suspiciously little text never overwrites a
snapshot; after 3 consecutive failures an issue is opened, so silent
breakage does not look like "no changes".
"""
from __future__ import annotations

import difflib
import json
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

import bundles
from common import SNAPSHOTS, gh, load_all, out_path, today

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36 ai-security-matrix-monitor")
MIN_CHARS = 300
FAIL_ISSUE_AFTER = 3
LABELS = {
    "lahdemuutos": ("0e8a16", "Seurattu lähde muuttui"),
    "seurantavirhe": ("d93f0b", "Lähteen haku epäonnistuu toistuvasti"),
    "tutkimus": ("1d76db", "Tutkimuspaketti Claudelle"),
}


def fetch(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "en;q=0.9"}, timeout=30)
    r.raise_for_status()
    return r.text


def extract(html: str, selector: str = "") -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
        tag.decompose()
    text = ""
    if selector:
        nodes = soup.select(selector)
        text = "\n".join(n.get_text("\n") for n in nodes)
    if not text.strip():
        try:
            import trafilatura
            text = trafilatura.extract(html, include_tables=True, include_comments=False) or ""
        except ImportError:
            text = ""
    if not text.strip():
        body = soup.body or soup
        text = body.get_text("\n")
    return normalize(text)


def normalize(text: str) -> str:
    lines = (re.sub(r"\s+", " ", l).strip() for l in text.splitlines())
    return "\n".join(l for l in lines if l) + "\n"


def unified(old: str, new: str, name: str) -> str:
    return "\n".join(difflib.unified_diff(old.splitlines(), new.splitlines(),
                                          fromfile=f"{name} (edellinen)", tofile=f"{name} (uusi)",
                                          lineterm="", n=2))


def ensure_labels() -> None:
    for name, (color, desc) in LABELS.items():
        try:
            gh("label", "create", name, "--color", color, "--description", desc, "--force")
        except Exception as e:  # label creation is best effort
            print(f"label {name}: {e}", file=sys.stderr)


def open_or_comment(title: str, label: str, body: str) -> None:
    listing = gh("issue", "list", "--state", "open", "--label", label, "--limit", "100",
                 "--json", "number,title")
    existing = [i for i in json.loads(listing or "[]") if i["title"] == title]
    path = out_path("issue_body.md")
    path.write_text(body, encoding="utf-8")
    if existing:
        gh("issue", "comment", str(existing[0]["number"]), "--body-file", str(path))
    else:
        gh("issue", "create", "--title", title, "--label", label, "--body-file", str(path))


def main() -> int:
    data = load_all()
    SNAPSHOTS.mkdir(exist_ok=True)
    status_path = SNAPSHOTS / "_status.json"
    status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    now = today()
    monitored = [s for s in data["sources"] if s.get("monitor")]
    ensure_labels()
    changed = failed = 0

    for src in monitored:
        st = status.setdefault(src["id"], {})
        st["last_checked"] = now
        snap = SNAPSHOTS / f"{src['id']}.txt"
        try:
            text = extract(fetch(src["url"]), src.get("selector", ""))
            if len(text) < MIN_CHARS:
                raise ValueError(f"liian vähän tekstiä ({len(text)} merkkiä); todennäköisesti esto tai JS-sivu")
        except Exception as e:
            failed += 1
            st["error"] = str(e)[:300]
            st["failures"] = st.get("failures", 0) + 1
            print(f"FAIL {src['id']}: {e}", file=sys.stderr)
            if st["failures"] == FAIL_ISSUE_AFTER:
                open_or_comment(f"Seurantavirhe: {src['id']}", "seurantavirhe",
                                f"Lähteen **{src['title']}** haku on epäonnistunut {FAIL_ISSUE_AFTER} kertaa peräkkäin.\n\n"
                                f"- URL: {src['url']}\n- Virhe: `{st['error']}`\n\n"
                                "Vaihtoehdot: lisää CSS-valitsin (`selector` data/sources.json:ssa), vaihda URL "
                                "tai aseta `monitor: false` ja tarkista lähde täysissä tutkimusajoissa.")
            continue
        finally:
            time.sleep(1)

        st.update({"last_ok": now, "failures": 0})
        st.pop("error", None)
        if not snap.exists():
            snap.write_text(text, encoding="utf-8")
            st["baseline"] = now
            print(f"BASELINE {src['id']}")
            continue
        old = snap.read_text(encoding="utf-8")
        if old == text:
            continue
        changed += 1
        diff = unified(old, text, src["id"])
        snap.write_text(text, encoding="utf-8")
        st["last_change"] = now
        n_cells = sum(1 for c in data["cells"].values() if any(s["id"] == src["id"] for s in c.get("sources", [])))
        body = (f"Seurattu lähde **[{src['title']}]({src['url']})** muuttui ({now}).\n"
                f"Lähteeseen viittaa {n_cells} solua. Snapshotin muutos näkyy tämän päivän seurantacommitissa.\n\n"
                + bundles.source_change(src, diff, data))
        open_or_comment(f"Lähdemuutos: {src['id']}", "lahdemuutos", body)
        print(f"CHANGED {src['id']}")

    status["_run"] = {"date": now, "monitored": len(monitored), "changed": changed, "failed": failed}
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Valmis: {len(monitored)} lähdettä, {changed} muuttui, {failed} epäonnistui.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
