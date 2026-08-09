# fega-schmitt-client

[![Tests](https://github.com/the78mole/fega-schmitt-client/actions/workflows/test.yml/badge.svg)](https://github.com/the78mole/fega-schmitt-client/actions/workflows/test.yml)
[![Release](https://github.com/the78mole/fega-schmitt-client/actions/workflows/pypi-publish.yml/badge.svg)](https://github.com/the78mole/fega-schmitt-client/actions/workflows/pypi-publish.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Renovate](https://img.shields.io/badge/renovate-enabled-brightgreen.svg)](https://renovatebot.com)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

> **Status: v1 implementiert (SOAP-Preis-/Verfügbarkeitsservice) + erste IDS-Erweiterung (Warenkorb senden/empfangen), noch nicht auf PyPI veröffentlicht.** UGL4 sowie IDS-Artikeldeeplink/-suche/Heatinglabel sind bewusst noch nicht umgesetzt, siehe [Architektur](docs/architecture.md#7-bewusst-nicht-in-v1-abgedeckt). Der SOAP-Preis-/Verfügbarkeitsservice ist sowohl gegen die Spezifikation/einen Mock-Server (automatisierte Tests) als auch **live gegen den echten FEGA & Schmitt-Server** verifiziert (siehe "Offene Punkte" für Details zum manuellen Testaufruf).

Eine reine Python-Library für den Zugriff auf die B2B-Schnittstellen von **FEGA & Schmitt Elektrogroßhandel** — allen voran den Preis-/Verfügbarkeitsservice. Kein MCP-, kein KI-spezifischer Code: diese Library ist eigenständig nutzbar (Skripte, andere Services, Warenwirtschaftssysteme) und wird zusätzlich vom Schwester-Projekt `fega-schmitt-mcp` (separates Repository unter `GIT/MCP/`) als MCP-Interface verpackt.

> **Suchst du das MCP-Interface für KI-Assistenten?**
> Siehe das Repository `fega-schmitt-mcp` — der dünne MCP-Wrapper um diese Library.

## Über FEGA & Schmitt

FEGA & Schmitt ist ein deutscher Elektrogroßhändler. Kunden erhalten Zugriff auf mehrere, technisch sehr unterschiedliche B2B-Schnittstellen zum Datenaustausch mit ihrer Warenwirtschaft/Handwerkersoftware. Details siehe [docs/architecture.md](docs/architecture.md).

## Schnittstellen im Überblick

| Schnittstelle | Typ | Zweck | Eignung für Library v1 |
|---|---|---|---|
| **SOAP Preis-/Verfügbarkeitsservice** | Synchrones SOAP/XML über HTTPS | Preis & Verfügbarkeit für bis zu 1000 Artikel je Anfrage | ✅ Basis für v1 — einzige echte Request/Response-API |
| **IDS-Schnittstelle** (BVBS/ITEK-Branchenstandard, v2.5) | Browser-Redirect + Hook-URL, halbautomatisch | Warenkorb-Austausch, Artikelsuche, Artikel-Deeplinks, Heizungslabel (ErP) | ⚠️ Später — passt nicht zu einer reinen Funktionsaufruf-API, siehe [Architektur](docs/architecture.md#7-bewusst-nicht-in-v1-abgedeckt) |
| **UGL Version 4** (SHK-Branchenstandard) | Datei-basiert (FTP/Portal), ASCII Fixed-Length | Anfragen, Abrufaufträge, Auftragsbestätigungen als Batch-Dateien | ⚠️ Später — Batch/Polling statt Live-Antwort |

Die Original-Spezifikationen sind **nicht Teil dieses Repositories** (`docs/specs/` steht in `.gitignore` — die PDFs gehören FEGA & Schmitt bzw. den jeweiligen Branchenverbänden und werden hier nicht weiterverbreitet). Als Kunde erhältst du sie direkt von FEGA & Schmitt:

- **Preis-/Verfügbarkeits-Webservice**: `Schnittstellenbeschreibung_SOAP.pdf` (Stand März 2016)
- **IDS-Schnittstelle**: `IDS_Schnittstelle_2_5_final_NEU.pdf` (BVBS/ITEK, Version 2.5, Stand 02.11.2020)
- **UGL Version 4**: `ugl4neutral.pdf` (GC-Gruppe, Stand 16.06.2006)

Zum lokalen Entwickeln legst du die jeweilige PDF unter dem oben genannten Dateinamen in `docs/specs/` ab — der Code referenziert sie unter diesem Pfad.

## Öffentliche API (v1)

```python
from fega_schmitt_client import FegaSchmittClient, PriceAvailRequestItem

client = FegaSchmittClient(
    partner_purchaser="9920",       # Kundennummer bei FEGA & Schmitt
    legitimation_id="...",          # Shop-Kennwort
)

results = client.get_price_availability([
    PriceAvailRequestItem(material_number="0815", quantity=200, unit="MTR"),
    PriceAvailRequestItem(material_number="4711", quantity=1),
])

for r in results:
    print(r.material_number, r.availability_status, r.net_amount)
```

Details zu Datenmodell, Fehlerbehandlung und Architektur: siehe [docs/architecture.md](docs/architecture.md).

## IDS-Erweiterung: Warenkorb senden/empfangen

`fega_schmitt_client.ids` implementiert den "Warenkorb senden"-Teil der IDS-Schnittstelle (BVBS/ITEK v2.5, halbautomatisch — Browserfenster + manuelle Nutzerinteraktion im FEGA-Shop, siehe `IDS_Schnittstelle_2_5_final_NEU.pdf` — s.o., nicht im Repo enthalten —, Abschnitt 5.2). Die Library baut nur die Daten — **kein** Browser-Handling, **kein** Webhook-Server; das übernimmt der Aufrufer (z. B. `fega-schmitt-mcp`):

```python
from decimal import Decimal
from fega_schmitt_client.ids import Cart, CartItem, build_cart_request, parse_cart_callback

cart = Cart(items=[
    CartItem(article_number="0815", quantity=Decimal(200), unit="MTR"),
])

request = build_cart_request(
    cart,
    shop_url="https://shop.fega.de/...",   # noch nicht bekannt, siehe "Offene Punkte"
    customer_number="9920",
    hook_url="https://mein-server.example/fega-hook",  # optional
)
# request.fields als multipart/form-data-POST an request.shop_url schicken
# (bzw. als auto-submitting HTML-Formular im Browser des Nutzers öffnen)

# Später, wenn der Shop das Ergebnis an die hook_url zurückschickt:
updated_cart = parse_cart_callback(received_xml)
```

Ohne `hook_url` funktioniert das Senden weiterhin — der Nutzer schließt den Vorgang dann manuell im Browser ab, es gibt nur keinen automatischen Rücklauf.

## CLI

Als Kommandozeilen-Tool `fega` installierbar, ohne dass ein eigenes venv angelegt werden muss:

```bash
uv tool install fega-schmitt-client
fega --customer-number 9920 --shop-password "..." price-avail 0815:200:MTR 4711
```

Alternativ per Umgebungsvariablen (`FEGA_CUSTOMER_NUMBER`, `FEGA_SHOP_PASSWORD`) statt Optionen. `-j`/`--json` liefert JSON statt Tabellenausgabe. `fega --help` bzw. `fega price-avail --help` zeigen alle Optionen.

## Installation

```bash
pip install fega-schmitt-client
# oder
uv add fega-schmitt-client
```

(Noch nicht auf [PyPI](https://pypi.org/) veröffentlicht — bis dahin lokal installierbar via `uv pip install .` bzw. `uv tool install .` aus dem geklonten Repo.)

## Entwicklung

```bash
uv sync --all-groups        # Dependencies + Dev-Tools installieren
uv run pytest                # Tests (gegen einen respx-Mock-Server, kein echter FEGA-Zugang nötig)
uv run pre-commit install    # Linting/Formatting-Hooks aktivieren
uv run pre-commit run --all-files
```

## Offene Punkte

- ~~Test-/Produktivzugangsdaten für den SOAP-Service~~ — **erledigt**: `get_price_availability` wurde live gegen `https://soap.fega.de/priceavail.php` verifiziert (echte Kundennummer/Shop-Kennwort, Artikel 121350 → `I720`, korrekte Preis-, Verfügbarkeits- und Kupferzuschlag-Daten). Zugangsdaten liegen als Secret in OpenBao, nicht im Repo.
- Wie FEGA & Schmitt eine komplett abgelehnte Anmeldung tatsächlich signalisiert (HTTP-Status, Fault oder ein bestimmter Returncode), bleibt weiterhin offen — der Live-Test lief mit gültigen Zugangsdaten, absichtlich falsche wurden nicht getestet. Beobachtet wurde allerdings: eine unbekannte Artikelnummer liefert `E999`/Fehler 216 mit dem missverständlichen Text "Bitte pruefen Sie Ihre Anmeldedaten" (HTTP 200) — nicht mit einem Auth-spezifischen HTTP-Status. `FegaAuthError` (aktuell nur bei HTTP 401/403) ist also weiterhin eine ungetestete Annahme, könnte in der Praxis aber nie greifen, wenn FEGA Ablehnungen generell per Item-Returncode statt HTTP-Status meldet
- Die tatsächliche IDS-Shop-URL von FEGA & Schmitt (`shop_url` in `build_cart_request`) sowie die referenzierten XSD-Schemas (`Warenkorb_senden.xsd`, `Warenkorb_empfangen_2-5.xsd` — in der vorliegenden PDF nicht enthalten, nur die tabellarische Feldbeschreibung); die Implementierung von `fega_schmitt_client.ids` ist entsprechend nur gegen die Spezifikation getestet, nicht gegen den echten Shop
- Das exakte Formularfeld, unter dem der Shop den Warenkorb an die Hook-URL zurückschickt — die Spec dokumentiert nur den Feldnamen `warenkorb` für die ausgehende Richtung, für den Rücklauf wird das per Analogieschluss angenommen
- Artikeldeeplink, Artikelsuche, Login-Informationen, Schnittstellenversion und Heatinglabel (restliche IDS-Aktionen) sind noch nicht umgesetzt
- **DATANORM v5 + Offline-Zugang (FTP)**: bei FEGA & Schmitt beantragt, aber Zugangsdaten und Format-Spezifikation liegen noch nicht vor — siehe [docs/architecture.md](docs/architecture.md#73-datanorm-v5-artikel-stammdatenpreislisten). DATANORM ist die von der SOAP-Spec selbst referenzierte Quelle der Artikelnummern für `get_price_availability`, daher relevanter als "nur" ein weiteres Zusatzformat
- Ob UGL4 für dieses Projekt relevant ist, und falls ja: FTP-Zugangsdaten/Verzeichnis
- Endgültiger PyPI-/Modulname (`fega-schmitt-client` ist ein Arbeitstitel)
- PyPI Trusted Publishing muss einmalig manuell auf pypi.org eingerichtet werden (Workflow-Datei `pypi-publish.yml`, Environment `pypi`), bevor der Release-Workflow tatsächlich veröffentlichen kann

## Lizenz

MIT, siehe [LICENSE](LICENSE).
