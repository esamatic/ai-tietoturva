"""Kohinasuodatin seurannalle: onko lähdemuutos issuen arvoinen?

Vertailu tehdään normalisoidusta tekstistä, joten vanhoja snapshotteja ei
tarvitse muuntaa. Kokoon perustuvaa kynnystä ei ole tarkoituksella:
hinnastotaulukossa yhden sanan muutos (No -> Yes) voi olla koko päivityksen
tärkein tieto.

Kohinaa ovat:
  1. vain päivämäärät, suhteelliset ajat, ©-vuodet, linkkimerkinnät ("opens in a new
     window"), kirjainkoko tai välilyönnit ja rivitys (myös HTML-merkinnän muutoksista
     syntyvät, esim. "(firstName ,lastName )" vs. "(firstName, lastName)"),
  2. vain rivien järjestys,
  3. sivu vuorottelee versioiden välillä (A/B-testit, CDN-variantit).

looks_blocked() tunnistaa esto- ja kirjautumissivut, jotta niitä ei tallenneta
snapshotiksi eikä raportoida sisällön muutoksena.
"""
from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from collections import Counter

FLAP_MIN = 2         # versio on "vuorotteleva", kun siihen on palattu näin monta kertaa aiemmin
MAX_VERSIONS = 12    # montako versiotunnistetta pidetään tilassa lähdettä kohden

_MONTHS = ("january|february|march|april|may|june|july|august|september|october|november|december"
           "|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec")
_DATE = (rf"(?:\d{{4}}-\d{{1,2}}-\d{{1,2}}|\d{{1,2}}\.\d{{1,2}}\.\d{{4}}"
         rf"|(?:{_MONTHS})\.? \d{{1,2}}(?:st|nd|rd|th)?,? \d{{4}}|\d{{1,2}} (?:{_MONTHS})\.? \d{{4}})")
_STAMP = r"(?:last )?(?:updated|modified|reviewed|published|effective|revised|edited)(?: on| date)?"

_SUBS = [
    (re.compile(r"\b(?:about |over |almost |less than |more than )?(?:a|an|one|\d+) "
                r"(?:second|minute|hour|day|week|month|year)s? ago\b"), "‹aika›"),
    (re.compile(r"©\s*\d{4}(?:\s*[-–]\s*\d{4})?"), "©"),
    (re.compile(r"\(opens in a new (?:window|tab)\)|↗"), ""),
]
_DROP = [
    re.compile(rf"^(?:{_STAMP}\s*:?\s*)?{_DATE}\.?$"),          # pelkkä päiväys tai "Effective: July 27, 2026"
    re.compile(rf"^{_STAMP}\s*:?\s*(?:‹aika›|today|yesterday)\.?$"),  # "Updated over 3 weeks ago"
    re.compile(r"^changes can take up to 24 hours but typically happen more quickly\.?(?: learn more)?$"),  # Google Admin -ohjeiden vakiohuomautus
]
# Esto-, kirjautumis- ja bottitarkistussivujen tunnisteet (pienillä kirjaimilla).
_BLOCKED = re.compile(r"access to this page requires authorization|access denied|verify you are (?:a )?human"
                      r"|checking your browser|enable javascript and cookies to continue|just a moment\.\.\."
                      r"|sign in to continue|you don't have permission to access")
_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"))
_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"})


def normalize(text: str, ignore: list[str] | tuple = ()) -> list[str]:
    """Vertailuun käytettävät rivit. ignore = lähdekohtaiset regexit, joihin osuvat rivit ohitetaan."""
    extra = [re.compile(p, re.I) for p in ignore]
    out = []
    for line in unicodedata.normalize("NFKC", html.unescape(text)).translate(_ZERO_WIDTH).splitlines():
        line = re.sub(r"\s+", " ", line.translate(_QUOTES)).strip().casefold()
        for rx, repl in _SUBS:
            line = rx.sub(repl, line)
        if not line or any(rx.match(line) for rx in _DROP) or any(rx.search(line) for rx in extra):
            continue
        out.append(line)
    return out


def _squash(lines: list[str]) -> str:
    """Koko teksti ilman välilyöntejä ja rivinvaihtoja: rivitys ja välit eivät vaikuta."""
    return re.sub(r"\s+", "", "".join(lines))


def _same(a: list[str], b: list[str]) -> str | None:
    if _squash(a) == _squash(b):
        return "vain muotoilua, päivämääriä tai ohitettavia rivejä"
    if Counter(re.sub(r"\s+", "", l) for l in a) == Counter(re.sub(r"\s+", "", l) for l in b):
        return "vain rivien järjestys"
    return None


def digest(lines: list[str]) -> str:
    return hashlib.sha1(_squash(lines).encode()).hexdigest()[:12]


def looks_blocked(new: str, old: str = "") -> str | None:
    """Palauttaa osuman, jos uusi teksti näyttää esto- tai kirjautumissivulta eikä vanha näyttänyt."""
    m = _BLOCKED.search(new.casefold())
    if m and not _BLOCKED.search(old.casefold()):
        return m.group(0)
    return None


def classify(old: str, new: str, state: dict, ignore: list[str] | tuple = ()) -> str | None:
    """Palauttaa syyn, jos muutos on kohinaa, muuten None (= avaa issue).

    state on lähteen tila (_status.json); funktio pitää siellä versiolaskuria.
    Aito palautus aiempaan versioon raportoidaan aina ensimmäisellä kerralla,
    koska vuorotteluksi tulkitaan vasta FLAP_MIN aiempaa paluuta.
    """
    a, b = normalize(old, ignore), normalize(new, ignore)
    same = _same(a, b)
    if same:
        return same

    versions: dict = state.setdefault("versions", {})
    versions.setdefault(digest(a), 1)
    h = digest(b)
    seen = versions.pop(h, 0)
    versions[h] = seen + 1                       # siirtyy sanakirjan loppuun = tuorein
    for k in list(versions)[:-MAX_VERSIONS]:
        del versions[k]
    if seen >= FLAP_MIN:
        return f"sivu vuorottelee versioiden välillä (versioon palattu {seen} kertaa aiemmin)"
    return None


def diff_is_noise(diff: str, ignore: list[str] | tuple = ()) -> bool:
    """Unified diffin poistetut ja lisätyt rivit ovat normalisoituina samat (rivityksestä tai järjestyksestä riippumatta)."""
    minus, plus = [], []
    for line in diff.splitlines():
        if line.startswith(("---", "+++", "@@")):
            continue
        if line.startswith("-"):
            minus.append(line[1:])
        elif line.startswith("+"):
            plus.append(line[1:])
    return _same(normalize("\n".join(minus), ignore), normalize("\n".join(plus), ignore)) is not None


def diff_blocked(diff: str) -> str | None:
    """Diffin lisätyt rivit näyttävät esto- tai kirjautumissivulta."""
    plus = "\n".join(l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))
    minus = "\n".join(l[1:] for l in diff.splitlines() if l.startswith("-") and not l.startswith("---"))
    return looks_blocked(plus, minus)
