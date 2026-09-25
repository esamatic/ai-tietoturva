"""Integrity check for data/*.json. Exit code 1 on errors; warnings are informational."""
from __future__ import annotations

import sys
from collections import Counter

from common import DATE_RE, ID_RE, SOURCE_TYPES, SPAN_COL, STATUS_LABELS, load_all


def main() -> int:
    d = load_all()
    st, cells, sources = d["structure"], d["cells"], d["sources"]
    errors, warnings = [], []

    for kind, items in (("vendor", st["vendors"]), ("group", st["groups"]), ("row", st["rows"]),
                        ("column", st["columns"]), ("source", sources)):
        dup = [i for i, n in Counter(x["id"] for x in items).items() if n > 1]
        errors += [f"{kind}: kaksoistunniste {i}" for i in dup]
        errors += [f"{kind}: virheellinen tunniste {x['id']!r}" for x in items if not ID_RE.match(x["id"])]

    vendors = {v["id"] for v in st["vendors"]}
    groups = {g["id"] for g in st["groups"]}
    errors += [f"sarake {c['id']}: tuntematon vendor {c['vendor']}" for c in st["columns"] if c["vendor"] not in vendors]
    errors += [f"rivi {r['id']}: tuntematon group {r['group']}" for r in st["rows"] if r["group"] not in groups]
    errors += [f"lähde {s['id']}: tyyppi {s.get('type')!r}" for s in sources if s.get("type") not in SOURCE_TYPES]

    rows = {r["id"]: r for r in st["rows"]}
    cols = {c["id"] for c in st["columns"]}
    src_ids = {s["id"] for s in sources}
    for k, c in cells.items():
        row, _, col = k.partition("|")
        if row not in rows:
            errors.append(f"solu {k}: tuntematon rivi")
            continue
        if bool(rows[row].get("span")) != (col == SPAN_COL) or (col != SPAN_COL and col not in cols):
            errors.append(f"solu {k}: sarake ei sovi riviin")
        if c.get("status") not in STATUS_LABELS:
            errors.append(f"solu {k}: virheellinen tila")
        for s in c.get("sources", []):
            if s["id"] not in src_ids:
                errors.append(f"solu {k}: tuntematon lähde {s['id']}")
            if not DATE_RE.match(s.get("accessed", "")):
                errors.append(f"solu {k}: virheellinen accessed-päivä lähteelle {s['id']}")
        if c.get("status") != "u" and not c.get("sources"):
            warnings.append(f"solu {k}: lähde puuttuu")

    missing = sum(1 for r in st["rows"] for col in ([SPAN_COL] if r.get("span") else cols) if f"{r['id']}|{col}" not in cells)
    if missing:
        warnings.append(f"{missing} solua ei ole vielä tutkittu")

    for e in errors:
        print("VIRHE:", e)
    print(f"{len(errors)} virhettä, {len(warnings)} varoitusta "
          f"({sum(1 for w in warnings if 'lähde puuttuu' in w)} lähteetöntä solua).")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
