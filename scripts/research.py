"""Open full-research issues: one per vendor, split per license if too large.

Usage: research.py --vendor all|ms|go|an|oa
"""
from __future__ import annotations

import argparse
import sys

import bundles
from common import gh, load_all, out_path, today
from monitor import ensure_labels

MAX_BODY = 60000  # GitHub limit is 65536 characters


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vendor", default="all")
    args = ap.parse_args()
    data = load_all()
    vendors = data["structure"]["vendors"]
    chosen = vendors if args.vendor == "all" else [v for v in vendors if v["id"] == args.vendor]
    if not chosen:
        print(f"Tuntematon tarjoaja: {args.vendor}", file=sys.stderr)
        return 1
    ensure_labels()
    intro = ("Säännöllinen täysi tarkistus. Seuranta näkee vain seuratut sivut, joten tämä ajo etsii myös "
             "uudet lisenssit, dokumentit ja lähteettömien solujen lähteet.\n\n")
    for v in chosen:
        bodies = [(v["name"], bundles.full_research(v["id"], data))]
        if len(bodies[0][1]) > MAX_BODY:
            cols = [c for c in data["structure"]["columns"] if c["vendor"] == v["id"]]
            bodies = [(f'{v["name"]} – {c["plan"]}', bundles.full_research(v["id"], data, [c["id"]])) for c in cols]
        for title, body in bodies:
            path = out_path("research_body.md")
            path.write_text(intro + body[: MAX_BODY], encoding="utf-8")
            gh("issue", "create", "--title", f"Täysi tarkistus: {title} ({today()})",
               "--label", "tutkimus", "--body-file", str(path))
            print(f"Luotu: {title} ({len(body)} merkkiä)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
