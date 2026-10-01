# AI-avustajien tietoturvamatriisi

Julkinen, itseään seuraava vertailu yrityskäyttöön tarkoitettujen AI-avustajien (Microsoft Copilot, Google Gemini, Anthropic Claude, OpenAI ChatGPT) lisensseistä tietoturvan ja tietosuojan näkökulmasta. Jokaisella solulla on omat lähteensä ja muutoshistoriansa.

Automaatio hoitaa seurannan, julkaisun ja kirjanpidon. Tulkinta tehdään käsin claude.ai-chatissa, ja jokainen muutos hyväksytään pull requestina ennen julkaisua.

```
Seuranta (päivittäin) ──► lähde muuttui ──► issue + tutkimuspaketti
                                                   │
                         kopioi paketti Claude-projektiin, liitä vastaus kommentiksi
                                                   │
Patch kommentista ──► validointi ──► pull request ──► sinä yhdistät ──► Julkaise sivu
```

## Käyttöönotto

1. Luo **julkinen** GitHub-repo ja vie nämä tiedostot sinne.
2. **Settings → Pages → Build and deployment → Source:** GitHub Actions.
3. **Settings → Actions → General → Workflow permissions:** Read and write permissions, ja rastita *Allow GitHub Actions to create and approve pull requests*.
4. Aja **Actions → Seuranta → Run workflow**. Ensimmäinen ajo tallentaa lähtötilanteen eikä avaa issueita, ja se luo myös lomakkeiden tarvitsemat labelit. Julkaisu käynnistyy perään automaattisesti.
5. Luo claude.ai:ssa Project (esim. "Tietoturvamatriisi") ja liitä sen ohjeiksi `prompts/project_instructions.md`.

Sivu löytyy osoitteesta https://esamatic.github.io/ai-tietoturva/

## Rakenne

Rivit on jaettu kahteen tasoon. **Kynnysehdot** ovat vaatimuksia, joiden puute sulkee vaihtoehdon pois (koulutuskielto, DPA, sertifikaatit, poikkeamailmoitukset, AI Act -valmius). **Erottelevat tekijät** ovat asioita, joissa tarjoajat ja lisenssitasot eroavat ja joita painotetaan oman käyttötapauksen mukaan. Taso määritellään ryhmälle (`tier` tiedostossa `data/structure.json`). Lomakkeella luotu uusi ryhmä menee erottelevien tekijöiden alle.

Tarjoajien värit ovat datassa (`color`, `color_dark`). Uusi tarjoaja saa värin automaattisesti varapaletista, ja sen voi vaihtaa muokkaamalla tiedostoa.

## Käyttö

**Lähde muuttui.** Seuranta avaa issuen *Lähdemuutos: &lt;lähde&gt;*, jossa on diff ja kopioitava paketti. Liitä paketti Claude-projektin keskusteluun, ja liitä Clauden koko vastaus issueen kommentiksi. Workflow poimii `BEGIN-PATCH … END-PATCH`-lohkon, validoi sen ja avaa pull requestin, jonka taulukko näyttää jokaisen muutoksen. Yhdistä PR, niin sivu päivittyy. Jos validointi epäonnistuu, virheet tulevat kommenttina ja voit pyytää Claudelta korjatun version. Saman issuen myöhemmät patch-kommentit (korjaukset tai pitkän patchin jatko-osat) lisätään samaan avoimeen PR:ään.

**Uusi seurattava ominaisuus (rivi), lisenssi (sarake) tai lähde.** Avaa issue vastaavalla lomakkeella. Workflow avaa PR:n, joka lisää kohteen, ja kommentoi issueen tutkimuspaketin. Tutki kohde paketilla ja liitä vastaus samaan issueen: patch lisätään samaan PR:ään, joten sitä ei tarvitse yhdistää välissä. Jos yhdistät PR:n ennen tutkimusta, uudet solut näkyvät sivulla tilassa *Ei vielä tutkittu* ja rivillä lukee, mistä päivästä alkaen sitä on seurattu.

**Lähde- tai korjausehdotus.** Sivun jokaisessa solussa on ✎-linkki, joka avaa lomakkeen valmiiksi täytettynä kyseiselle solulle. Voit myös avata issuen suoraan lomakkeella *Lähde- tai korjausehdotus* ja anna yksi tai useampi URL, halutessasi rajauksella (esim. "ChatGPT Enterprise, Tallennus EU:ssa"). Automaatio kommentoi tutkimuspaketin, jolla Claude selvittää, mitä soluja lähde tukee, ja palauttaa patchin tavalliseen tapaan.

**Täysi tarkistus.** Neljännesvuosittain (tai käsin: *Actions → Täysi tarkistus*) avautuu issue per tarjoaja. Se etsii uudet lisenssit ja dokumentit, joita seuranta ei näe, ja lähteettömien solujen lähteet.

**Historian nollaus.** *Actions → Nollaa historia* (kirjoita vahvistukseksi NOLLAA) tyhjentää muutoslokin ja solujen aiemmat arvot ja asettaa kaikille riveille, sarakkeille ja soluille lähtöpäivän. Solujen sisältö, lähteet ja git-historia säilyvät. Muutos tulee pull requestina.

**Käsin muokkaus.** Tiedostoja voi muokata myös suoraan. `python scripts/validate.py` tarkistaa eheyden, ja sama tarkistus ajetaan ennen jokaista julkaisua.

## Datamalli

| Tiedosto | Sisältö |
|---|---|
| `data/structure.json` | tarjoajat (värit), ryhmät (taso), rivit ja sarakkeet (`added`-päivä kertoo, mistä asti kohdetta on seurattu) |
| `data/cells.json` | solut avaimella `rivi\|sarake`: tila, teksti, lähteet, `verified`, `changed`, `history` |
| `data/sources.json` | kaikki lähteet; `monitor: true` = päivittäisessä seurannassa, `selector` = CSS-rajaus |
| `data/changelog.json` | muutosloki |
| `data/meta.json` | otsikko, huomiot, muutosikkunan pituus |
| `status/monitor.json` | seurannan tila (tarkistuspäivät, muutokset, virheet); julkinen |
| *(yksityinen repo)* | seurattujen sivujen poimittu teksti; git-historia toimii todisteena muutoksista |

Koko leveyden rivin solun sarake on `*` (tuettu, mutta tällä hetkellä sellaisia rivejä ei ole).

## Snapshotit yksityisessä repossa

Seurattujen sivujen koko teksti tallennetaan erilliseen yksityiseen repoon, koska kolmansien osapuolten tekstiä ei kannata julkaista. Seuranta tarvitsee:

- **Repository variable** `SNAPSHOTS_REPO`, esim. `käyttäjä/ai-tietoturva-snapshots` (Settings → Secrets and variables → Actions → Variables).
- **Repository secret** `SNAPSHOTS_TOKEN`: fine-grained token, jolla on vain tähän yksityiseen repoon *Contents: Read and write* -oikeus. Tokenilla on vanhenemispäivä; uusi se ajoissa, muuten seuranta pysähtyy virheeseen.

Issueihin tulee vain lyhyt ote muutoksesta (enintään 4 000 merkkiä).

## Paikallinen kehitys

```bash
pip install -r requirements.txt
python scripts/validate.py
python scripts/build_site.py          # → site/index.html
SNAPSHOT_DIR=/tmp/snap DRY_RUN=1 python scripts/monitor.py   # gh-komennot vain tulostetaan
```

## Tiedossa olevat rajoitukset

- **Bottiesto ja JavaScript-sivut.** Osa sivuista palauttaa esto- tai tyhjän sivun. Tällainen haku ei koskaan ylikirjoita snapshotia, ja kolmen peräkkäisen epäonnistumisen jälkeen avautuu issue *Seurantavirhe*. Korjaus on yleensä `selector`, toinen URL tai `monitor: false`.
- **Kosmeettiset muutokset.** Ilman valitsinta myös navigaation tai päivämäärien muutokset näkyvät. Lisää lähteelle `selector` (esim. `main`, `article`).
- **Seuranta näkee vain seuratut sivut.** Uudet dokumentit ja lisenssit löytyvät täysissä tarkistuksissa.
- **Ylläpito patcheilla.** Patch voi myös korjata olemassa olevia lähteitä (`source_ops`: update, merge, remove) sekä sarakkeiden ja rivien tekstejä (`column_updates`, `row_updates`). Lähde, johon mikään solu ei patchin jälkeen viittaa, poistuu automaattisesti, ja seuranta siivoaa poistettujen lähteiden snapshotit. Täyden tarkistuksen paketti näyttää, montako solua kuhunkin lähteeseen viittaa, joten siivous tapahtuu tarkistusten yhteydessä.
- **Automaattinen yhdistäminen (valinnainen).** Repository variable `AUTO_MERGE=true` (*Settings → Secrets and variables → Actions → Variables*) yhdistää validoidun patchin PR:n heti ja julkaisee sivun. Silloin ihmisen tekemä PR-tarkastus jää pois; muutosloki ja git-historia säilyvät, ja virheellisen muutoksen voi perua uudella patchilla tai revertillä.
- **Tietoturva.** Patch hyväksytään vain repon omistajan kommenteista, ja kommentti käsitellään pelkkänä JSON-datana. PR-tarkastus on toinen suojakerros.

Tämä on hankinnan apuväline, ei oikeudellinen arvio.
