# Architektur

> Entwurfsstand — es existiert noch keine Implementierung. Dieses Dokument beschreibt die geplante Architektur auf Basis der drei vorliegenden FEGA & Schmitt/Branchen-Spezifikationen in [`specs/`](specs/).

## 1. Kontext & Abgrenzung

`fega-schmitt-client` ist die **einzige Stelle**, an der Wissen über die konkreten FEGA & Schmitt-Protokolle (Wire-Format, Auth, Fehlercodes) existiert. Alles, was HTTP/SOAP/XML im Detail versteht, gehört hierher — nicht in den MCP-Wrapper.

```mermaid
graph LR
    MCP["fega-schmitt-mcp<br/>(separates PyPI-Paket,<br/>separates Repo unter GIT/MCP/)"] -->|nutzt| LIB(("fega-schmitt-client<br/>(dieses Repo)"))
    Scripts["Eigene Skripte /<br/>Warenwirtschaftsanbindungen"] -->|nutzt| LIB
    CLI["CLI<br/>(später, optional, nicht v1)"] -.->|nutzt| LIB
    LIB -->|SOAP/HTTPS| API["FEGA & Schmitt<br/>Preis-/Verfügbarkeitsservice"]

    style LIB fill:#2b6cb0,color:#fff
```

`fega-schmitt-mcp` verpackt die Funktionen dieser Library als MCP-Tools für KI-Assistenten.

Diese Trennung ist bewusst: Die Library ist testbar, versionierbar und auf PyPI installierbar, ohne dass ein MCP-Host beteiligt sein muss. Der MCP-Server bleibt dadurch dünn (siehe Architektur von `fega-schmitt-mcp`) und die Protokoll-Logik ist wiederverwendbar für andere Integrationen (z. B. eine direkte Anbindung an ein Warenwirtschaftssystem ohne KI-Assistenten).

FEGA & Schmitt stellt Kunden drei technisch unabhängige Schnittstellen zur Verfügung. Sie unterscheiden sich stark in Protokoll, Interaktionsmuster und Automatisierbarkeit:

| | SOAP Preis-/Verfügbarkeit | IDS-Schnittstelle | UGL Version 4 |
|---|---|---|---|
| Quelle | FEGA & Schmitt-eigene Doku | BVBS/ITEK-Branchenstandard, v2.5 | GC-Gruppe-Branchenstandard (SHK) |
| Protokoll | SOAP 1.1 / XML über HTTPS POST | HTTP-Formular-POST (`multipart/form-data`) an eine Shop-URL, Rückkanal über "Hook-URL" | Flatfile (ASCII, feste Satzlänge 200 Byte) über FTP oder Webportal-Verzeichnis |
| Interaktionsmuster | Synchron, zustandslos, Server-zu-Server | Öffnet ein Browserfenster im GH-Shop; Nutzer agiert dort manuell; Shop schickt Ergebnis per Formular-POST an die Hook-URL zurück ("halbautomatisch") | Asynchron/Batch: Datei ablegen, später Antwortdatei abholen |
| Auth | Kundennummer + Shop-Kennwort im XML-Body je Anfrage | Kundennummer/Benutzername/Passwort als POST-Parameter beim Öffnen des Shops | Vermutlich FTP-Zugangsdaten (nicht in den ersten Seiten der Spec spezifiziert) |
| Als Funktionsaufruf abbildbar? | **Ja** — klassischer Request/Response-API-Aufruf | **Nein, nicht direkt** — benötigt Browser-Kontext bzw. Nachbau der Shop-Formularlogik | **Nein, nicht direkt** — benötigt Scheduler/Polling |

**Konsequenz für den Zuschnitt:** v1 der Library deckt ausschließlich den SOAP-Preis-/Verfügbarkeitsservice als reine Python-Funktionsaufrufe ab. IDS und UGL4 werden in Abschnitt 7 als mögliche spätere Erweiterungen *derselben Library* skizziert (nicht als eigene Repos), da beide letztlich auch "FEGA & Schmitt ansprechen" — nur mit anderer Transportlogik dahinter.

## 2. Paketaufbau (v1, Vorschlag)

```
fega_schmitt_client/
    __init__.py        # Public API: FegaSchmittClient, Modelle, Exceptions
    price_avail.py      # SOAP-Client für den Preis-/Verfügbarkeitsservice
    models.py             # PriceAvailRequestItem, PriceAvailResultItem, Surcharge, ...
    exceptions.py          # FegaApiError, FegaAuthError, FegaTransportError, ...
    _soap.py                 # Low-Level: SOAP-Envelope bauen/parsen (intern, kein Public API)

    # spätere Erweiterungen (siehe Abschnitt 7), nicht Teil von v1:
    # ids/                  # IDS-Schnittstelle (Warenkorb, Artikelsuche, Heizlabel)
    # ugl4/                 # UGL4 Flatfile-Ex-/Import
```

`FegaSchmittClient` ist der einzige öffentliche Einstiegspunkt in v1; interne Transportdetails (`_soap.py`) sind nicht Teil der Public API und können sich ändern, ohne SemVer-Major auszulösen.

## 3. Ablauf `get_price_availability`

```mermaid
sequenceDiagram
    participant App as Aufrufer<br/>(fega-schmitt-mcp / Skript)
    participant Client as FegaSchmittClient
    participant Soap as _soap.py
    participant API as FEGA & Schmitt<br/>priceavail.php

    App->>Client: get_price_availability(items)
    Client->>Soap: build_request(items, prefix, header)
    Soap-->>Client: PRICE_AVAIL_REQUEST (XML)
    Client->>API: HTTPS POST (SOAP-Envelope)
    API-->>Client: PRICE_AVAIL_RESPONSE (XML)
    Client->>Soap: parse_response(xml)
    Soap-->>Client: Liste von ITEM-Ergebnissen
    Client-->>App: list[PriceAvailResultItem]
```

1. Aufrufer (z. B. `fega-schmitt-mcp` oder ein eigenes Skript) ruft `client.get_price_availability(items, ...)` mit einer Liste von `PriceAvailRequestItem` auf (max. 1000 Positionen laut Spezifikation, siehe [`specs/Schnittstellenbeschreibung_SOAP.pdf`](specs/Schnittstellenbeschreibung_SOAP.pdf), Abschnitt "Allgemeiner Ablauf").
2. `price_avail.py` baut über `_soap.py` eine `PRICE_AVAIL_REQUEST`-Nachricht:
   - `PREFIX`: Firmennummer ("50"), Kundennummer, Shop-Kennwort, eine pro Aufruf generierte `TRANSACTION_ID`
   - `HEADER`: Versandart (Lieferung/Abholung), Zielwährung ("EUR"), optional PLZ/Länderkennzeichen für lieferabhängige Verfügbarkeit
   - `ITEM_LIST`: eine `ITEM`-Position je angefragtem Artikel, mit fortlaufender `LINE_ITEM_NUMBER` zur Zuordnung der Antwort
3. HTTPS-POST des SOAP-Envelopes an `https://soap.fega.de/priceavail.php`.
4. `_soap.py` parst `PRICE_AVAIL_RESPONSE` und mappt jede `ITEM`-Position zurück auf die ursprüngliche Anfrageposition (über `LINE_ITEM_NUMBER`).
5. `get_price_availability` gibt eine Liste von `PriceAvailResultItem` zurück (siehe Abschnitt 5) — Fehler auf einzelnen Positionen führen nicht zum Abbruch des gesamten Aufrufs, sondern werden je Position im Ergebnis abgebildet (entspricht dem Verhalten der Schnittstelle selbst: Returncode ist je Position, nicht global).
6. Reine Transportfehler (Timeout, HTTP-Statuscode ≠ 200, ungültiges SOAP-Envelope, Auth komplett abgelehnt) lösen eine Exception aus (`FegaTransportError` / `FegaAuthError`), da hier keine sinnvolle Teilantwort existiert.

## 4. Fehler- und Hinweisbehandlung (Returncodes)

Aus [`specs/Schnittstellenbeschreibung_SOAP.pdf`](specs/Schnittstellenbeschreibung_SOAP.pdf), Abschnitt 4:

| Prefix | Bedeutung | Abbildung im Ergebnis |
|---|---|---|
| `I…` (z. B. `I720`) | Erfolgreiche Ermittlung | `PriceAvailResultItem.status = "ok"` |
| `H…` (z. B. `H014`, Abholverzögerung) | Erfolgreich, aber mit Hinweis | `status = "hint"`, `return_code_text` gesetzt |
| `E…` (z. B. `E999`: unbekannte Artikelnummer, unbekannter ISO-Mengeneinheitscode, Mengenüberlauf) | Fehler bei dieser Position | `status = "error"`, `return_code_text` gesetzt, restliche Werte `None` |

Der `RETURNCODE_TEXT` wird unverändert durchgereicht, da er laut Spezifikation für die Anzeige beim Endnutzer vorgesehen ist.

## 5. Datenmodell (geplant)

```python
@dataclass
class PriceAvailRequestItem:
    material_number: str        # FEGA & Schmitt-Artikelnummer, Pflicht
    quantity: Decimal            # Pflicht
    unit: str | None = None      # ISO-Code, z. B. "PCE", "MTR"; optional

@dataclass
class Surcharge:
    code: str
    text: str
    amount: Decimal

@dataclass
class PriceAvailResultItem:
    line_item_number: int
    material_number: str
    status: Literal["ok", "hint", "error"]
    return_code: str
    return_code_text: str
    availability_status: Literal["V", "T", "N", "B", "0"] | None   # voll/teilw./nicht verfügbar/Beschaffung/keine Aussage
    warehouse_number: str | None
    warehouse_name: str | None
    price_amount: Decimal | None      # Nettowert vor Zu-/Abschlägen
    net_amount: Decimal | None        # Nettowert inkl. Zu-/Abschläge, vor Steuer
    list_amount: Decimal | None       # Listenpreis
    surcharges: list[Surcharge]       # z. B. Kupfer-/Metallzuschlag
```

Die Felder orientieren sich 1:1 an der XML-Struktur aus der Spezifikation (Abschnitt 3.3 "Nachrichtenaufbau Antwort"), um verlustfrei zu bleiben.

## 6. Sicherheit & Credential-Handling

- Kundennummer und Shop-Kennwort werden dem `FegaSchmittClient`-Konstruktor explizit übergeben (kein implizites Lesen von Umgebungsvariablen in der Library selbst — das ist Aufgabe des jeweiligen Aufrufers, z. B. des MCP-Wrappers).
- Die Schnittstelle verlangt HTTPS (`https://soap.fega.de/...`); Klartext-HTTP wird nicht unterstützt und nicht implementiert.
- Da jede Anfrage Kundennummer + Kennwort im Klartext-XML-Body enthält, maskiert das Logging der Library das Kennwort standardmäßig (nie im Klartext loggen).
- Keine Persistierung von Preisdaten in v1 — jeder Aufruf ist eine Live-Abfrage. Ein optionaler kurzlebiger In-Memory-Cache (TTL im Minutenbereich) ist als spätere Optimierung denkbar, aber wegen tagesaktueller Preise (siehe `SURCHARGE_REBATE_AMOUNT`-Hinweis "wertmäßig akt. Tagespreisen") mit Vorsicht zu dosieren.

## 7. Bewusst nicht in v1 abgedeckt

### 7.1 IDS-Schnittstelle (BVBS/ITEK, v2.5)

Beschrieben in [`specs/IDS_Schnittstelle_2_5_final_NEU.pdf`](specs/IDS_Schnittstelle_2_5_final_NEU.pdf). Diese Schnittstelle ist ein **Branchenstandard**, kein FEGA & Schmitt-spezifisches Protokoll — ob und wie FEGA & Schmitt ihn im eigenen Webshop implementiert, ist ungeklärt (offener Punkt, siehe README).

Warum nicht v1:

- Das Muster ist "Browserfenster öffnen → Nutzer agiert im Shop (Blackbox) → Shop postet Ergebnis an Hook-URL". Das lässt sich nicht als einfacher, synchroner Python-Funktionsaufruf abbilden, ohne entweder (a) einen echten Nutzer im Loop zu haben oder (b) eine Headless-Browser-Automatisierung zu bauen, die die individuelle FEGA & Schmitt-Shopoberfläche nachbildet.
- Referenzierte XSD-Schemas (`Warenkorb_senden.xsd`, `Warenkorb_empfangen_2-5.xsd`, `heatinglabel_senden.xsd`, `heatinglabel_empfangen.xsd`) liegen der vorliegenden PDF nicht bei.
- Falls später umgesetzt: eigenes Untermodul `fega_schmitt_client.ids`, das die Browser-Automatisierung kapselt (z. B. Playwright) und nach außen trotzdem eine funktionsartige API anbietet (`send_cart(...)`, `search_articles(...)`), damit `fega-schmitt-mcp` weiterhin nur einfache Funktionsaufrufe tätigen muss.

### 7.2 UGL Version 4

Beschrieben in [`specs/ugl4neutral.pdf`](specs/ugl4neutral.pdf). Ebenfalls ein **Branchenstandard** (SHK-Großhandel/GC-Gruppe), keine FEGA & Schmitt-spezifische Erfindung.

Warum nicht v1:

- Datenaustausch erfolgt batchweise als Datei (feste Satzlänge, 200 Byte/Satz) über FTP oder ein Portalverzeichnis — kein synchrones Request/Response.
- Eine Library-Funktion bräuchte entweder Polling ("Antwortdatei liegt vor?") oder einen Hintergrund-Job, der Dateien abholt — ein grundsätzlich anderes Betriebsmodell als der stdio-basierte Preis-/Verfügbarkeits-Aufruf.
- Zugangsdaten/Verzeichnisstruktur beim FEGA & Schmitt-FTP sind nicht bekannt (offener Punkt).
- Falls später umgesetzt: eigenes Untermodul `fega_schmitt_client.ugl4` mit reinen Dateiformat-Funktionen (`parse_response_file(...)`, `build_inquiry_file(...)`) — der eigentliche FTP-Transport/Scheduling bliebe bewusst außerhalb der Library, da das ein Betriebs-/Infrastrukturthema ist, kein API-Zugriffsthema.

## 8. Technologiewahl (Vorschlag, noch nicht festgelegt)

Konsistent mit anderen Python-Bibliotheken in diesem Workspace (z. B. `vnbdigital-client`):

- **Paketverwaltung:** `uv`, Linting/Formatting mit `ruff`
- **SOAP/XML:** leichtgewichtiges XML-Templating (`lxml`/`xml.etree`) statt eines vollen WSDL-getriebenen SOAP-Stacks wie `zeep` — die Schnittstelle ist klein, statisch und ohne WSDL-Dokument in der Spec referenziert
- **HTTP-Transport:** `httpx`
- **Tests:** `pytest`, mit den Beispiel-Request/-Response-Paaren aus dem Anhang der SOAP-Spezifikation als Fixtures
- **Veröffentlichung:** PyPI, via Trusted Publishing (GitHub Actions, kein manuell verwaltetes API-Token)

Diese Wahl ist ein Vorschlag und noch mit dem Auftraggeber abzustimmen, bevor Code entsteht.

## 9. Offene Fragen

Siehe README, Abschnitt "Offene Punkte".
