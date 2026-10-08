"""Kertaluonteinen jonon purku: sulkee avoimet lähdemuutosissuet, joiden kaikki diffit ovat kohinaa.

Käyttö:
  python scripts/triage_backlog.py           # vain raportti, ei muutoksia
  python scripts/triage_backlog.py --apply   # sulkee kohinaissuet kommentin kera

Issue jätetään auki, jos yksikin sen diffeistä (runko + seurannan lisäkommentit)
on sisällöllinen tai katkaistu, tai jos siihen on jo liitetty patch.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter

import noise
from common import gh

LABEL = "lahdemuutos"
DIFF_START = "Muutos (unified diff poimitusta tekstistä):"
TRUNCATED = "diff katkaistu"
# An actual patch (JSON right after the marker), not the instructions that mention the markers.
PATCH_RE = re.compile(r"BEGIN-PATCH\s*(?:[`~]{3,}\w*\s*)?\{")
CLOSE_NOTE = ("Suljettu automaattisesti: kaikki tämän issuen muutokset ovat kohinaa "
              "(päivämääriä, välilyöntejä, kirjainkokoa tai rivien järjestystä). "
              "Snapshot on jo ajan tasalla, joten mitään ei jäänyt käsittelemättä.")


def diffs(text: str) -> list[str]:
    """Bundlen diff alkaa otsikkorivistä ja päättyy ensimmäiseen tyhjään riviin."""
    return [part.lstrip("\n").split("\n\n", 1)[0] for part in (text or "").split(DIFF_START)[1:]]


def verdict(issue: dict) -> tuple[bool, str]:
    comments = [c.get("body", "") for c in issue.get("comments", [])]
    if any(PATCH_RE.search(t) for t in comments):
        return False, "patch jo liitetty"
    texts = [issue.get("body", "")] + comments
    blocks = [d for t in texts for d in diffs(t)]
    if not blocks:
        return False, "diffiä ei löytynyt"
    if any(noise.diff_blocked(d) for d in blocks):
        return False, "esto- tai kirjautumissivu (korjaa lähde)"
    if any(TRUNCATED in d for d in blocks):
        return False, "diff katkaistu"
    real = sum(not noise.diff_is_noise(d) for d in blocks)
    if real:
        return False, f"sisällöllinen muutos ({real}/{len(blocks)})"
    return True, f"kohinaa ({len(blocks)}/{len(blocks)})"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="sulje kohinaissuet (oletuksena vain raportti)")
    args = ap.parse_args()

    listing = json.loads(gh("issue", "list", "--state", "open", "--label", LABEL, "--limit", "300",
                            "--json", "number,title") or "[]")
    closed, kept = [], Counter()
    for it in listing:
        issue = json.loads(gh("issue", "view", str(it["number"]), "--json", "body,comments") or "{}")
        is_noise, why = verdict(issue)
        print(f"#{it['number']:<5} {'SULJE' if is_noise else 'pidä '}  {it['title']}  ({why})")
        if is_noise:
            closed.append(it["number"])
            if args.apply:
                gh("issue", "close", str(it["number"]), "--reason", "not planned", "--comment", CLOSE_NOTE)
        else:
            kept[why.split(" (")[0]] += 1

    action = "Suljettu" if args.apply else "Suljettaisiin"
    print(f"\n{action} {len(closed)}/{len(listing)}. Auki jäävät: {dict(kept) or '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
