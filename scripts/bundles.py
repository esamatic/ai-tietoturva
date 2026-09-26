"""Copy-paste bundles for the chat step.

Each bundle is self-contained: task, relevant current data, and the expected
answer format. The standing rules live in prompts/project_instructions.md
(Claude Project); the short recap here keeps a bundle usable without it.
"""
from __future__ import annotations

import json

from common import SPAN_COL, key

MAX_DIFF_CHARS = 20000
FENCE = "~~~~"  # tilde fence so that ``` inside the payload cannot break it

RECAP = """Vastaa noudattaen projektin ohjeita (prompts/project_instructions.md). Lyhyesti:
- Palauta VAIN muuttuneet tai uudet solut patchina merkkien BEGIN-PATCH ja END-PATCH väliin.
- Tila on arvio, ei kyllä/ei-vastaus: y = hyvä (vahva tietoturvan kannalta), p = osittain/ehdoin, n = heikko tai puuttuu, u = ei tiedossa. Rivin status_labels voi määritellä oman asteikon.
- Jokaisella solulla (paitsi tila u) vähintään yksi lähde; merkitse lähdetyyppi primary/secondary.
- Muuta tekstiä vain, jos tila tai lähteen sisältö muuttui. Perustele muutos kentässä reason.
- Solut, jotka tarkistit ja jotka pitävät yhä paikkansa, listaa kenttään unchanged.
- Jos et pysty varmistamaan asiaa, käytä tilaa u tai merkitse verify: true. Älä arvaa.
- Rivin hint kertoo, mitä rivillä arvioidaan; pysy sen rajauksessa."""


def _resolve_sources(cell: dict, sources_by_id: dict) -> list[dict]:
    out = []
    for s in cell.get("sources", []):
        src = sources_by_id.get(s["id"], {})
        out.append({"id": s["id"], "url": src.get("url", ""), "type": src.get("type", ""),
                    "accessed": s.get("accessed", "")})
    return out


def _cell_view(k: str, cell: dict | None, sources_by_id: dict) -> dict:
    row, col = k.split("|", 1)
    if cell is None:
        return {"row": row, "col": col, "status": None, "text": "(ei vielä tutkittu)"}
    view = {"row": row, "col": col, "status": cell["status"], "text": cell["text"],
            "sources": _resolve_sources(cell, sources_by_id)}
    if cell.get("verify"):
        view["verify"] = True
    return view


def _columns_view(columns: list[dict], vendors: dict) -> list[dict]:
    return [{"col": c["id"], "tuote": f'{vendors[c["vendor"]]} – {c["plan"]}', "meta": c.get("meta", "")}
            for c in columns]


def _known_sources(sources: list[dict], vendor_ids: set[str] | None = None) -> list[dict]:
    return [{"id": s["id"], "url": s["url"], "type": s["type"]}
            for s in sources if vendor_ids is None or s.get("vendor") in vendor_ids]


def _wrap(title: str, body_parts: list[str]) -> str:
    inner = "\n\n".join(body_parts)
    return (f"## Kopioi tämä Claudelle\n\n{FENCE}text\n# {title}\n\n{inner}\n\n{RECAP}\n{FENCE}\n\n"
            "Liitä Clauden vastaus tämän issuen kommentiksi sellaisenaan. "
            "Automaatio poimii BEGIN-PATCH/END-PATCH-lohkon, validoi sen ja avaa pull requestin.")


def _json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1)


def source_change(src: dict, diff: str, data: dict) -> str:
    st, cells = data["structure"], data["cells"]
    sources_by_id = {s["id"]: s for s in data["sources"]}
    affected = sorted(k for k, c in cells.items() if any(s["id"] == src["id"] for s in c.get("sources", [])))
    views = [_cell_view(k, cells[k], sources_by_id) for k in affected]
    truncated = len(diff) > MAX_DIFF_CHARS
    diff_txt = diff[:MAX_DIFF_CHARS] + ("\n[... diff katkaistu, hae sivu itse ...]" if truncated else "")
    parts = [
        f"Tehtävä: seurattu lähde on muuttunut. Hae sivu ({src['url']}) ja arvioi, muuttaako muutos "
        "alla lueteltuja soluja. Jos muutos on kosmeettinen, palauta patch, jossa on vain summary ja unchanged-lista.",
        f"Lähde: {src['id']} – {src['title']} ({src['type']})",
        f"Solut, jotka viittaavat tähän lähteeseen ({len(views)} kpl):\n{_json(views)}",
        f"Muutos (unified diff poimitusta tekstistä):\n{diff_txt}",
    ]
    if not views:
        parts.insert(1, "Mikään solu ei vielä viittaa tähän lähteeseen. Arvioi, pitäisikö jonkin solun viitata siihen.")
        parts.append("Rivit ja sarakkeet:\n" + _json({
            "rows": [r["id"] for r in st["rows"]], "cols": [c["id"] for c in st["columns"]]}))
    return _wrap(f"Lähdemuutos: {src['id']}", parts)


def new_row(row: dict, data: dict) -> str:
    st = data["structure"]
    vendors = {v["id"]: v["name"] for v in st["vendors"]}
    cols = [SPAN_COL] if row.get("span") else [c["id"] for c in st["columns"]]
    parts = [
        "Tehtävä: matriisiin on lisätty uusi seurattava ominaisuus. Tutki se jokaiselle sarakkeelle "
        "ja palauta solut patchina." + (" Rivi on koko leveyden rivi: käytä col-arvoa \"*\"." if row.get("span") else ""),
        f"Uusi rivi:\n{_json({k: row[k] for k in ('id', 'label', 'hint', 'group') if k in row})}",
        f"Sarakkeet:\n{_json(_columns_view(st['columns'], vendors)) if not row.get('span') else _json(cols)}",
        f"Tunnetut lähteet (voit käyttää id:tä tai lisätä uusia url:lla):\n{_json(_known_sources(data['sources']))}",
    ]
    return _wrap(f"Uusi rivi: {row['id']}", parts)


def new_column(col: dict, data: dict) -> str:
    st = data["structure"]
    vendors = {v["id"]: v["name"] for v in st["vendors"]}
    rows = [{"row": r["id"], "label": r["label"], "hint": r.get("hint", "")}
            for r in st["rows"] if not r.get("span")]
    siblings = [c for c in st["columns"] if c["vendor"] == col["vendor"] and c["id"] != col["id"]]
    sources_by_id = {s["id"]: s for s in data["sources"]}
    sibling_cells = {c["id"]: [_cell_view(key(r["row"], c["id"]), data["cells"].get(key(r["row"], c["id"])), sources_by_id)
                               for r in rows] for c in siblings}
    parts = [
        "Tehtävä: matriisiin on lisätty uusi lisenssi (sarake). Tutki jokainen rivi tälle lisenssille "
        "ja palauta solut patchina.",
        f"Uusi sarake:\n{_json(_columns_view([col], vendors))}",
        f"Rivit:\n{_json(rows)}",
        f"Saman tarjoajan muiden lisenssien nykyiset solut vertailukohdaksi:\n{_json(sibling_cells)}" if siblings else "",
        f"Tarjoajan tunnetut lähteet:\n{_json(_known_sources(data['sources'], {col['vendor']}))}",
    ]
    return _wrap(f"Uusi sarake: {col['id']}", [p for p in parts if p])


def full_research(vendor_id: str, data: dict, col_ids: list[str] | None = None) -> str:
    st, cells = data["structure"], data["cells"]
    vendors = {v["id"]: v["name"] for v in st["vendors"]}
    cols = [c for c in st["columns"] if c["vendor"] == vendor_id and (col_ids is None or c["id"] in col_ids)]
    sources_by_id = {s["id"]: s for s in data["sources"]}
    views = [_cell_view(key(r["id"], c["id"]), cells.get(key(r["id"], c["id"])), sources_by_id)
             for r in st["rows"] if not r.get("span") for c in cols]
    unsourced = sum(1 for v in views if v.get("status") and v["status"] != "u" and not v.get("sources"))
    unresearched = sum(1 for v in views if v.get("status") is None)
    parts = [
        f"Tehtävä: täysi tarkistus tarjoajalle {vendors[vendor_id]}. (1) Selvitä, onko tarjoajalla uusia, "
        "poistuneita tai uudelleennimettyjä yrityslisenssejä; ehdota uudet sarakkeet patchin columns-kentässä. "
        "(2) Tarkista jokainen solu ensisijaisista lähteistä. Erityisesti tutkimattomat solut "
        f"({unresearched} kpl), lähteettömät solut ({unsourced} kpl) ja verify-merkityt. (3) Ehdota seurattaviksi lähteiksi keskeiset ensisijaiset sivut.",
        f"Sarakkeet:\n{_json(_columns_view(cols, vendors))}",
        f"Rivit:\n{_json([{'row': r['id'], 'label': r['label'], 'hint': r.get('hint', '')} for r in st['rows'] if not r.get('span')])}",
        f"Nykyiset solut:\n{_json(views)}",
        f"Tarjoajan tunnetut lähteet:\n{_json(_known_sources(data['sources'], {vendor_id}))}",
    ]
    return _wrap(f"Täysi tarkistus: {vendors[vendor_id]}", parts)


def _match_columns(scope: str, st: dict) -> list[dict]:
    """Columns whose vendor name, plan or id appears in the free-text scope."""
    s = scope.lower()
    if not s.strip():
        return []
    vendors = {v["id"]: v["name"].lower() for v in st["vendors"]}
    plan_hits = [c for c in st["columns"] if c["plan"].lower() in s or c["id"] in s]
    if plan_hits:
        return plan_hits
    return [c for c in st["columns"] if vendors.get(c["vendor"], "") in s]


def _match_rows(scope: str, st: dict) -> list[dict]:
    s = scope.lower()
    return [r for r in st["rows"] if r["id"] in s or r["label"].lower() in s]


def correction(urls: list[str], scope: str, note: str, data: dict) -> str:
    """Bundle for a user-submitted source or correction: find which cells the URLs support."""
    st, cells = data["structure"], data["cells"]
    vendors = {v["id"]: v["name"] for v in st["vendors"]}
    sources_by_id = {s["id"]: s for s in data["sources"]}
    cols, rows = _match_columns(scope, st), _match_rows(scope, st)
    col_ids = [c["id"] for c in (cols or st["columns"])]
    row_list = rows or [r for r in st["rows"] if not r.get("span")]
    keys = [key(r["id"], c) for r in row_list for c in col_ids]
    if not (cols or rows):
        # no scope given: show only the cells that most need a source
        keys = [k for k, c in cells.items() if (c["status"] != "u" and not c.get("sources")) or c.get("verify")]
    views = [_cell_view(k, cells.get(k), sources_by_id) for k in sorted(keys)][:120]
    parts = [
        "Tehtävä: käyttäjä ehdottaa alla olevia lähteitä. Hae jokainen URL ja selvitä, mitä matriisin soluja "
        "se tukee, kumoaa tai tarkentaa. Päivitä solut ja lisää URL lähteeksi (id, title, type). "
        "Jos lähde ei tue mitään solua, kerro se ja palauta patch, jossa on vain summary.",
        "Ehdotetut lähteet:\n" + "\n".join(f"- {u}" for u in urls),
        f"Käyttäjän rajaus: {scope or '(ei annettu)'}",
        f"Käyttäjän huomio: {note or '(ei annettu)'}",
        f"Sarakkeet:\n{_json(_columns_view(cols or st['columns'], vendors))}",
        ("Asiaan liittyvät solut" if (cols or rows) else
         "Rajausta ei annettu; alla solut, joilta puuttuu lähde tai jotka on merkitty varmistettaviksi") +
        f" ({len(views)} kpl):\n{_json(views)}",
    ]
    return _wrap("Lähde-ehdotus", parts)
