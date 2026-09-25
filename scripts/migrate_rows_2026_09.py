"""Rivistön uudistus 9/2026 (kertaluonteinen, idempotentti).

- Rivit jaetaan kahteen tasoon: kynnysehdot ja erottelevat tekijät (tier ryhmätasolla).
- Poistetaan: salaus siirrossa ja levossa, prompt injection -suojaus.
- Yhdistetään SSO + SCIM -> identity.
- Uudelleen rajataan: human_review -> provider_access, subprocessors -> data_egress,
  connectors -> agents (solut säilyvät, merkitään varmistettaviksi, koska rajaus laajeni).
- Lainkäyttöalue muutetaan koko leveyden rivistä sarakekohtaiseksi.
- Uudet rivit (tila "Ei vielä tutkittu"): dlp, incident_notification, ai_act, pricing, exit.
- Tarjoajille lisätään värit datamalliin.

Aja: python scripts/migrate_rows_2026_09.py
"""
from __future__ import annotations

import sys

from common import SPAN_COL, key, load_all, save, today

BASE_DATE = "2026-09-25"  # alkuperäisen datan päivä; tätä myöhemmin muutetut solut raportoidaan

GROUPS = [
    {"id": "baseline", "label": "Kynnysehdot", "tier": "threshold"},
    {"id": "data_access", "label": "Datan käyttö ja pääsy", "tier": "differentiator"},
    {"id": "location", "label": "Sijainti ja lainkäyttöalue", "tier": "differentiator"},
    {"id": "access", "label": "Pääsynhallinta ja valvonta", "tier": "differentiator"},
    {"id": "encryption", "label": "Salaus ja avainten hallinta", "tier": "differentiator"},
    {"id": "llm", "label": "Agentit ja integraatiot", "tier": "differentiator"},
    {"id": "commercial", "label": "Kaupalliset ehdot", "tier": "differentiator"},
]

# (id, group, label, hint, vanha rivi josta solut ja added-päivä periytyvät)
ROWS = [
    ("training", "baseline", "Koulutus asiakasdatalla",
     "Käytetäänkö yrityksen syötteitä mallien koulutukseen. Kyllä-vastaus sulkee vaihtoehdon pois.", "training"),
    ("dpa", "baseline", "DPA ja GDPR-rooli",
     "Onko tarjoaja sopimuksella henkilötietojen käsittelijä. Ilman tätä palvelua ei voi käyttää henkilötiedoille.", "dpa"),
    ("certifications", "baseline", "Sertifikaatit",
     "Riippumaton varmennus tietoturvasta. Tarkista, kattaako sertifikaatti juuri tämän lisenssin.", "certifications"),
    ("incident_notification", "baseline", "Tietoturvapoikkeamista ilmoittaminen",
     "Sopimukseen kirjattu ilmoitusaika ja -tapa. Tarvitaan omien GDPR- ja NIS2-velvoitteiden täyttämiseen.", None),
    ("ai_act", "baseline", "EU AI Act -valmius",
     "Tarjoajan GPAI-velvoitteet ja käyttäjälle annettava dokumentaatio, jota tarvitaan omien velvoitteiden arviointiin.", None),

    ("provider_access", "data_access", "Palveluntarjoajan pääsy dataan",
     "Voiko tarjoajan henkilöstö lukea sisältöä, ja voiko asiakas hyväksyä tai estää pääsyn (esim. Customer Lockbox).", "human_review"),
    ("retention", "data_access", "Säilytys ja poistaminen",
     "Kauanko data säilyy ja voiko sen sovittaa omiin säilytys- ja eDiscovery-vaatimuksiin.", "retention"),
    ("data_egress", "data_access", "Datan kulku palvelun ulkopuolelle",
     "Lähteekö dataa web-hakuun, kolmansien osapuolten malleille tai konnektoreille eri ehdoilla kuin itse palvelussa.", "subprocessors"),

    ("storage_eu", "location", "Tallennus EU:ssa", "Pysyykö levossa oleva data EU:ssa.", "storage_eu"),
    ("inference_eu", "location", "Käsittely EU:ssa",
     "Ajetaanko malli EU:ssa. Usein eri asia kuin tallennus.", "inference_eu"),
    ("jurisdiction", "location", "Lainkäyttöalue",
     "Minkä maan lainsäädäntö voi velvoittaa tarjoajan luovuttamaan dataa (esim. US CLOUD Act).", "jurisdiction"),

    ("identity", "access", "Identiteetin- ja käyttäjähallinta",
     "Kirjautuminen yrityksen tunnuksilla (SSO) ja automaattinen käyttäjähallinta (SCIM): poistuneen työntekijän pääsy katkeaa automaattisesti.", "sso"),
    ("rbac", "access", "Roolit ja ominaisuusrajaukset",
     "Voiko ominaisuuksia ja pääsyä rajata ryhmittäin, esim. sallia konnektorit vain osalle käyttäjistä.", "rbac"),
    ("dlp", "access", "DLP ja tietoluokitus",
     "Kunnioittaako avustaja luottamuksellisuusluokituksia ja voiko syötteisiin ja vastauksiin soveltaa tietovuodon estosääntöjä.", None),
    ("audit", "access", "Audit-lokit ja eDiscovery",
     "Voidaanko käyttö selvittää jälkikäteen tietoturvapoikkeamassa tai oikeudellisessa selvityksessä.", "audit"),
    ("visibility", "access", "Mitä avustaja näkee",
     "Integroitu avustaja näkee kaiken, mihin käyttäjällä on oikeus. Liian laajat jako-oikeudet on siivottava ennen käyttöönottoa.", "visibility"),
    ("personal_accounts", "access", "Henkilökohtaisten tilien hallinta",
     "Voiko työntekijöiden omat tilit tuoda organisaation hallintaan (shadow AI).", "personal_accounts"),

    ("cmk", "encryption", "Asiakkaan hallinnoimat avaimet",
     "Voiko yritys hallita salausavaimia itse ja siten estää pääsyn dataansa. Tarpeen lähinnä säännellyillä aloilla.", "cmk"),

    ("agents", "llm", "Agenttiominaisuudet ja niiden hallinta",
     "Mihin järjestelmiin avustaja pääsee ja mitä se voi tehdä (konnektorit, koodin suoritus, selain- ja tietokoneagentit), ja voiko näitä rajata.", "connectors"),

    ("pricing", "commercial", "Hinta ja vähimmäissitoumus",
     "Listahinta per käyttäjä, vähimmäismäärät ja sitoumus. Tietoturvaominaisuudet ovat usein vain kalliimmissa tasoissa.", None),
    ("ip_indemnity", "commercial", "Tekijänoikeusvastuu",
     "Puolustaako tarjoaja asiakasta, jos tuotettu sisältö loukkaa tekijänoikeuksia.", "ip_indemnity"),
    ("sla", "commercial", "SLA ja tuki", "Sopimukseen kirjattu saatavuus ja tuen taso.", "sla"),
    ("exit", "commercial", "Datan vienti ja irtautuminen",
     "Saako datan ulos ja mitä sille tapahtuu sopimuksen päättyessä (lock-in-riski).", None),
]

RENAMED = {"human_review": "provider_access", "subprocessors": "data_egress", "connectors": "agents"}
REMOVED = {"encryption_basic", "prompt_injection", "scim"}

IDENTITY = {  # SSO + SCIM yhdistettynä: (tila, teksti)
    "ms_copilot_chat": ("y", "Entra ID: SSO, Conditional Access, MFA ja SCIM-provisiointi."),
    "ms_copilot": ("y", "Entra ID: SSO ja SCIM; Copilotille voi tehdä omat, tiukemmat Conditional Access -politiikat."),
    "g_workspace_business": ("y", "Google-identiteetti tai SAML-federointi, 2SV; käyttäjien synkronointi hakemistosta."),
    "g_workspace_enterprise": ("y", "Google-identiteetti tai SAML-federointi, kontekstitietoinen pääsy; hakemistosynkronointi."),
    "g_gemini_enterprise": ("p", "Useita IdP:itä, myös Entra ID. Käyttäjähallinnan integraatiot Std/Plus-editioissa; Business rajallisempi."),
    "a_claude_team": ("p", "SSO ja domain-vahvistus, mutta ei SCIM:iä: poistuneet käyttäjät poistetaan käsin."),
    "a_claude_enterprise": ("y", "SSO, domain capture ja SCIM."),
    "o_chatgpt_business": ("p", "SAML SSO, MFA ja domain-vahvistus, mutta ei SCIM:iä."),
    "o_chatgpt_enterprise": ("y", "SAML SSO, SCIM ja globaali admin-konsoli."),
}
JURISDICTION_TEXT = ("Yhdysvaltalainen yhtiö: CLOUD Act voi velvoittaa luovuttamaan dataa sijainnista riippumatta. "
                     "Siirrot nojaavat EU–US Data Privacy Frameworkiin ja/tai SCC:ihin.")
US_VENDORS = {"ms", "go", "an", "oa"}

COLORS = {"ms": ("#2B67A8", "#6FA3DC"), "go": ("#2F7D5B", "#6CC29A"),
          "an": ("#8A5A2B", "#D3A06E"), "oa": ("#5A4A9C", "#A796E0")}

NOTES_ADD = [
    "Salaus siirrossa ja levossa on kaikilla vakiona, eikä sitä siksi vertailla erikseen.",
    "Matriisi vertaa tietoturvaa ja tietosuojaa. Sopivuus organisaation nykyiseen ympäristöön (esim. M365 vai Google Workspace) ratkaisee käytännössä usein, mutta se ei ole mukana tässä vertailussa.",
]


def main() -> int:
    d = load_all()
    st, cells = d["structure"], d["cells"]
    if any("tier" in g for g in st["groups"]):
        print("Migraatio on jo tehty; ei muutoksia.")
        return 0
    now = today()
    warnings = []
    old_rows = {r["id"]: r for r in st["rows"]}
    col_ids = [c["id"] for c in st["columns"]]
    col_vendor = {c["id"]: c["vendor"] for c in st["columns"]}

    def late(c):
        return c and c.get("changed", BASE_DATE) > BASE_DATE

    # --- solut ---------------------------------------------------------
    new_cells = {}
    for k, c in cells.items():
        row, col = k.split("|", 1)
        if row in REMOVED or row in {"sso", "jurisdiction"}:
            continue
        if row in RENAMED:
            c = dict(c, verify=True)
            row = RENAMED[row]
        new_cells[key(row, col)] = c

    for col in col_ids:
        sso, scim = cells.get(key("sso", col)), cells.get(key("scim", col))
        if not (sso or scim):
            continue
        if late(sso) or late(scim):
            warnings.append(f"identity|{col}: SSO- tai SCIM-solua on muutettu {BASE_DATE} jälkeen; tarkista yhdistetty teksti.")
        status, text = IDENTITY.get(col, ((sso or scim)["status"], " ".join(x["text"] for x in (sso, scim) if x)))
        srcs = {s["id"]: s for x in (sso, scim) if x for s in x.get("sources", [])}
        merged = {"status": status, "text": text, "sources": list(srcs.values()),
                  "verified": min(x["verified"] for x in (sso, scim) if x),
                  "changed": max(x["changed"] for x in (sso, scim) if x), "history": []}
        if any(x and x.get("verify") for x in (sso, scim)) or col not in IDENTITY:
            merged["verify"] = True
        new_cells[key("identity", col)] = merged

    span = cells.get(key("jurisdiction", SPAN_COL))
    for col in col_ids:
        if span and col_vendor[col] in US_VENDORS:
            new_cells[key("jurisdiction", col)] = {
                "status": span["status"], "text": JURISDICTION_TEXT, "sources": span.get("sources", []),
                "verified": span.get("verified", now), "changed": span.get("changed", now), "history": []}

    # --- rakenne -------------------------------------------------------
    rows = []
    for rid, group, label, hint, src in ROWS:
        added = old_rows[src]["added"] if src in old_rows else now
        rows.append({"id": rid, "group": group, "label": label, "hint": hint, "added": added})
    known = {r[0] for r in ROWS}
    handled = known | REMOVED | set(RENAMED) | {"sso"}
    extra = [r for r in st["rows"] if r["id"] not in handled]  # käyttäjän lisäämät rivit säilyvät
    group_ids = {g["id"] for g in GROUPS}
    extra_groups = []
    for r in extra:
        if r["group"] not in group_ids:
            g = next(g for g in st["groups"] if g["id"] == r["group"])
            extra_groups.append(dict(g, tier="differentiator"))
            group_ids.add(g["id"])
        warnings.append(f"Käyttäjän lisäämä rivi {r['id']} säilytettiin ryhmässä {r['group']}.")
    st["groups"] = GROUPS + extra_groups
    st["rows"] = rows + extra
    for v in st["vendors"]:
        if v["id"] in COLORS and "color" not in v:
            v["color"], v["color_dark"] = COLORS[v["id"]]

    d["cells"] = dict(sorted(new_cells.items()))
    meta = d["meta"]
    meta["notes"] = [n.replace("Kaikki neljä ovat", "Kaikki nykyiset tarjoajat ovat") for n in meta.get("notes", [])]
    meta["notes"] += [n for n in NOTES_ADD if n not in meta["notes"]]
    meta["tiers"] = {
        "threshold": {"label": "Kynnysehdot",
                      "description": "Näiden pitää täyttyä. Puute sulkee vaihtoehdon pois tai vaatii erillisen riskiarvion."},
        "differentiator": {"label": "Erottelevat tekijät",
                           "description": "Näissä tarjoajat ja lisenssitasot eroavat. Painota oman käyttötapauksen mukaan."},
    }
    d["changelog"].insert(0, {
        "date": now, "ref": "",
        "summary": "Rivistön uudistus: kynnysehdot ja erottelevat tekijät erotettu; SSO ja SCIM yhdistetty; "
                   "kolme riviä rajattu uudelleen (varmistettava); salaus- ja prompt injection -rivit poistettu; "
                   "lainkäyttöalue sarakekohtaiseksi; viisi uutta riviä.",
        "changes": [{"kind": "row", "key": r[0], "text": r[2]} for r in ROWS if r[4] is None]})

    for name in ("structure", "cells", "changelog", "meta"):
        save(f"{name}.json", d[name])
    for w in warnings:
        print("HUOM:", w)
    print(f"Valmis: {len(rows) + len(extra)} riviä, {len(new_cells)} solua.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
