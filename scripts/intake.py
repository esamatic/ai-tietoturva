"""Convert an issue-form submission into a patch (+ research bundle).

Usage: intake.py --event $GITHUB_EVENT_PATH
Writes out/patch.json and, for rows/columns, out/bundle.md.
Step output kind=row|column|source|none.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

import bundles
from common import ID_RE, load_all, out_path, set_output

KINDS = {"uusi-ominaisuus": "row", "uusi-lisenssi": "column", "uusi-lahde": "source"}


def parse_form(body: str) -> dict[str, str]:
    """GitHub issue forms render as '### Label\\n\\nvalue' sections."""
    fields: dict[str, str] = {}
    for part in re.split(r"^### ", body or "", flags=re.M)[1:]:
        label, _, value = part.partition("\n")
        value = value.strip()
        fields[label.strip()] = "" if value == "_No response_" else value
    return fields


def slug(text: str) -> str:
    t = text.lower().translate(str.maketrans("äöå", "aoa"))
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")[:60]


def checked(value: str) -> bool:
    return bool(re.search(r"- \[[xX]\]", value or ""))


def match(value: str, items: list[dict], name_key: str) -> dict | None:
    v = value.strip().lower()
    for it in items:
        if v in (it["id"].lower(), it[name_key].lower()):
            return it
    return None


def build(kind: str, f: dict[str, str], data: dict) -> tuple[dict, str]:
    st = data["structure"]
    if kind == "row":
        label = f.get("Nimi", "")
        rid = f.get("Tunniste") or slug(label)
        group_in = f.get("Ryhmä", "")
        g = match(group_in, st["groups"], "label")
        row = {"id": rid, "label": label, "hint": f.get("Selite", ""), "group": g["id"] if g else slug(group_in)}
        if not g:
            row["group_label"] = group_in
        if checked(f.get("Asetukset", "")):
            row["span"] = True
        patch = {"summary": f"Uusi seurattava ominaisuus: {label}", "rows": [row]}
        return patch, bundles.new_row(row, data)
    if kind == "column":
        plan = f.get("Lisenssin nimi", "")
        vendor_in = f.get("Tarjoaja", "")
        v = match(vendor_in, st["vendors"], "name")
        vendor_id = v["id"] if v else slug(vendor_in)[:12]
        vendor_name = v["name"] if v else vendor_in
        plan_slug = slug(plan)
        prefix = slug(vendor_name) + "_"
        if plan_slug.startswith(prefix):
            plan_slug = plan_slug[len(prefix):]
        col = {"id": f.get("Tunniste") or f"{vendor_id}_{plan_slug}", "plan": plan,
               "meta": f.get("Lisätieto", ""), "vendor": vendor_id}
        if not v:
            col["vendor_name"] = vendor_in
        full = plan if plan.lower().startswith(vendor_name.lower()) else f"{vendor_name} {plan}"
        patch = {"summary": f"Uusi lisenssi: {full}", "columns": [col]}
        return patch, bundles.new_column(col, data)
    if kind == "source":
        vendor_in = f.get("Tarjoaja", "")
        v = match(vendor_in, st["vendors"], "name") if vendor_in else None
        src = {"url": f.get("URL", ""), "title": f.get("Otsikko", ""),
               "type": (f.get("Tyyppi") or "primary").split()[0].lower(),
               "selector": f.get("CSS-valitsin", ""), "vendor": v["id"] if v else "", "monitor": True}
        if f.get("Tunniste"):
            src["id"] = f["Tunniste"]
        return {"summary": f"Uusi seurattava lähde: {src['title'] or src['url']}", "sources": [src]}, ""
    raise ValueError(kind)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--event", required=True)
    args = ap.parse_args()
    event = json.load(open(args.event, encoding="utf-8"))
    issue = event["issue"]
    labels = {l["name"] for l in issue.get("labels", [])}
    kind = next((KINDS[l] for l in labels if l in KINDS), None)
    if kind is None:
        set_output("kind", "none")
        return 0
    fields = parse_form(issue.get("body", ""))
    data = load_all()
    patch, bundle = build(kind, fields, data)
    for item in patch.get("rows", []) + patch.get("columns", []):
        if not ID_RE.match(item["id"]):
            out_path("error.md").write_text(f"Tunniste {item['id']!r} ei kelpaa (a-z, 0-9, _ tai -).", encoding="utf-8")
            set_output("kind", "error")
            return 0
    out_path("patch.json").write_text(json.dumps(patch, ensure_ascii=False, indent=2), encoding="utf-8")
    if bundle:
        note = ("Kun tämän issuen pull request on yhdistetty, tutki uusi kohde alla olevalla paketilla. "
                "Siihen asti uudet solut näkyvät sivulla tilassa *Ei vielä tutkittu*.\n\n")
        out_path("bundle.md").write_text(note + bundle, encoding="utf-8")
    set_output("kind", kind)
    return 0


if __name__ == "__main__":
    sys.exit(main())
