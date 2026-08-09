# fega-schmitt-client

> **Status: Konzeptphase.** Dieses Repository enthält aktuell nur Dokumentation (README + Architekturbeschreibung + Original-Spezifikationen). Es ist noch kein Code implementiert.

Eine geplante, reine Python-Library für den Zugriff auf die B2B-Schnittstellen von **FEGA & Schmitt Elektrogroßhandel** — allen voran den Preis-/Verfügbarkeitsservice. Kein MCP-, kein KI-spezifischer Code: diese Library ist eigenständig nutzbar (Skripte, andere Services, Warenwirtschaftssysteme) und wird zusätzlich vom Schwester-Projekt `fega-schmitt-mcp` (separates Repository unter `GIT/MCP/`) als MCP-Interface verpackt.

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

Die vollständigen Original-Spezifikationen liegen als PDF in [docs/specs/](docs/specs/):

- `Schnittstellenbeschreibung_SOAP.pdf` — Preis-/Verfügbarkeits-Webservice (FEGA & Schmitt, Stand März 2016)
- `IDS_Schnittstelle_2_5_final_NEU.pdf` — IDS-Schnittstelle für Warenkorb/Artikelsuche/Heizlabel (BVBS/ITEK, Version 2.5, Stand 02.11.2020)
- `ugl4neutral.pdf` — UGL Version 4, Datenaustausch Handwerk ↔ SHK-Großhandel (GC-Gruppe, Stand 16.06.2006)

## Geplante öffentliche API (v1, Entwurf)

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

## Geplante Installation

```bash
pip install fega-schmitt-client
```

(Noch nicht veröffentlicht — Ziel ist eine Veröffentlichung auf [PyPI](https://pypi.org/).)

## Offene Punkte

- Test-/Produktivzugangsdaten für den SOAP-Service (Kundennummer, Shop-Kennwort, ggf. abweichende Firmennummer)
- Ob und in welcher Form FEGA & Schmitt die IDS-Schnittstelle über den eigenen Webshop anbietet, inkl. der referenzierten XSD-Schemas (`Warenkorb_senden.xsd`, `Warenkorb_empfangen_2-5.xsd`, `heatinglabel_*.xsd` — in der vorliegenden PDF nicht enthalten)
- Ob UGL4 für dieses Projekt relevant ist, und falls ja: FTP-Zugangsdaten/Verzeichnis
- Endgültiger PyPI-/Modulname (`fega-schmitt-client` ist ein Arbeitstitel)

## Lizenz

MIT, siehe [LICENSE](LICENSE).
