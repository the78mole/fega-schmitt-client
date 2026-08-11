# Geplante Features

Kurzer Fahrplan für künftige Erweiterungen von `fega-schmitt-client`, über das bereits implementierte v1 (SOAP-Preis-/Verfügbarkeitsservice + IDS-Warenkorb senden/empfangen) hinaus. Details und Begründung stehen in [docs/architecture.md](docs/architecture.md) (Abschnitt 7) bzw. [docs/extensions.md](docs/extensions.md) — dieses Dokument ist nur die priorisierte Kurzfassung.

## 1. `fega_schmitt_client.web` — Webshop-Zugriff (höchste Priorität)

**Implementiert** (`src/fega_schmitt_client/web/`, Tests in `tests/test_web_*.py`), gegen echte HTML-Snapshots aus der Recherche sanity-geprüft. Details/Begründung je Methode: [docs/extensions.md](docs/extensions.md).

**CLI (12.08.2026):** Alle Methoden zusätzlich über `fega web <befehl>` erreichbar (`src/fega_schmitt_client/cli.py`, Tests in `tests/test_cli_web.py`), `--json`/`-j` für maschinenlesbare Ausgabe, `fega web --help` für die vollständige Befehlsliste. Läuft standalone via `uv tool install`, keine neue Abhängigkeit nötig (`click`/`httpx` bereits Kernabhängigkeiten).

Legende: **S** spezifiziert (in extensions.md beschrieben) · **I** implementiert · **T** Test vorhanden (Unit- oder respx-Integrationstest) · **L** live gegen den echten Server verifiziert.

| Methode | Beschreibung | S | I | T | L |
| --- | --- | :-: | :-: | :-: | :-: |
| `search(q)` | Artikelnummer, EAN, Herstellerteilenummer, Freitext über ein gemeinsames Suchfeld | ✅ | ✅ | ✅ | ✅ |
| `get_article(material_number)` | **Neu (Refactor 11.08.2026):** liefert einen `Article`-Baum mit allem, was diese Library zu einem Artikel weiß (EAN, Herstellernummern, Kategorie, eigene Artikelnummer, Attribute, Bilder, Zubehör/Varianten/Alternativen/Cross-Sell, `documents` bislang immer leer), aus einem einzigen Seitenabruf; `Article.to_dict()` liefert die JSON-Form. Alle `get_article_*()`-Methoden unten sind jetzt dünne Wrapper darauf | ✅ | ✅ | ✅ | ✅ |
| `get_article_detail(material_number)` | Kategorie, EAN, Herstellerteilenummer(n), eigene Artikelnummer — Ausschnitt aus `get_article()` als älteres `ArticleDetail`-Shape | ✅ | ✅ | ✅ | ✅ |
| `get_article_category(material_number)` | Alias-Methode auf `get_article` | ✅ | ✅ | ✅ | ✅ |
| `get_article_number(material_number)` | Alias-Methode auf `get_article` (eigene Artikelnummer lesen) | ✅ | ✅ | ✅ | ✅ |
| `get_article_images(material_number)` | | ✅ | ✅ | ✅ | ✅ |
| `list_articles_by_category(uwg_id)` | Paginierung/Vollständigkeit bei großen Kategorien weiterhin ungeklärt | ✅ | ✅ | ✅ | ✅ |
| `get_favorite_list()` | | ✅ | ✅ | ✅ | ✅ |
| `get_deal_campaigns()` | Listet Kampagnen (z. B. "Sonderabverkauf Licht"), keine Artikel direkt — **Korrektur gegenüber ursprünglicher Annahme**, siehe unten | ✅ | ✅ | ✅ | ✅ |
| `get_deal_articles(campaign_id)` | Artikel einer Kampagne, `cmd=Deal/<Kampagnen-ID>&mode=1` | ✅ | ✅ | ✅ | ✅ |
| `get_daily_deals()` | `cmd=TagA` — bei drei unabhängigen Live-Aufrufen (zuletzt 11.08.2026) immer leer, Trefferformat bei echten Tagesangeboten weiterhin ungetestet | ✅ | ✅ | ✅ | ⬜ |
| `get_second_choice_articles()` | 2. Wahl/B-Ware, `cmd=Deal/3342&svc=2Wahl` | ✅ | ✅ | ✅ | ✅ |
| `get_cart_list()` | kombiniert aktuell offenen Warenkorb mit "andere Warenkörbe"-Auswahl | ✅ | ✅ | ✅ | ✅ |
| `get_cart(id)` | | ✅ | ✅ | ✅ | ✅ |
| `get_order_list()` | Status-Extraktion Best-Effort — funktioniert für einen beobachteten Status-Typ zuverlässig, sonst `None` statt Ratewert | ✅ | ✅ | ✅ | ✅ |
| `get_order(order_number)` | | ✅ | ✅ | ✅ | ✅ |
| `set_article_number(material_number, value)` | Schreiben — End-to-End-Roundtrip live bestätigt (11.08.2026, Artikel 253439, idempotent gegen den real vom Nutzer gepflegten Wert getestet) | ✅ | ✅ | ✅ | ✅ |
| `get_article_attributes(material_number)` | Kategorie-/artikeltyp-spezifische Attribute (`dict[str, str]`, z. B. "Farbe"/"Nennspannung") aus dem Produktdetails-Grid | ✅ | ✅ | ✅ | ✅ |
| `get_article_accessories(material_number)` | Artikelnummern aus dem "Zubehör"-Bereich | ✅ | ✅ | ✅ | ✅ |
| `get_article_variants(material_number)` | **Erweitert (11.08.2026):** liest jetzt die vollständige Attribut-Varianten-Matrix aus dem `data-variables`-JSON (bis zu 512 Artikelnummern bei einem Testartikel statt zuvor 3 aus der kleinen "Varianten"-Teaser-Liste, die nur noch als Fallback dient) | ✅ | ✅ | ✅ | ✅ |
| `get_article_alternatives(material_number)` | Artikelnummern aus dem "Alternativen"-Bereich; kann leer sein, wenn der Shop nur den separaten JS-Attributfinder anbietet (siehe unten) | ✅ | ✅ | ✅ | ✅ |
| `get_article_cross_sell(material_number)` | Artikelnummern aus "Oft zusammengekauft mit" — nicht ursprünglich geplant, ergab sich beim Recherchieren der obigen vier kostenlos aus demselben Muster | ✅ | ✅ | ✅ | ✅ |
| `get_cable_lengths(material_number)` | **Neu (11.08.2026):** verfügbare Kabeltrommeln/Reststücke je Lagerstandort (`cmd=AjaxKLaeng/<matnr>`) — einziger Artikel-Endpunkt, der ohne vorherigen `search()`-Schritt auskommt (Artikelnummer direkt im Pfad) | ✅ | ✅ | ✅ | ✅ |
| `has_cable_lengths(material_number)` | Alias-Methode auf `get_cable_lengths` (`bool`) | ✅ | ✅ | ✅ | ✅ |
| `get_cutting_fee(material_number)` / `Article.cutting_fee` | Schnittkosten-Hinweistext von der Artikeldetailseite (`None` bei Nicht-Kabelartikeln) | ✅ | ✅ | ✅ | ✅ |
| Kategoriebaum-Baseline (`web/data/categories.json`) | generiert aus [docs/fega_categories.md](docs/fega_categories.md), samt Suffix-Normalisierung | ✅ | ✅ | ✅ | ✅ |

### 1.1 Bekannte Lücken

- **Formale Angebote/Preisangebote** (`get_quote_list`/`get_quote`, Kundenangebote im B2B-Sinn) — **kein Endpunkt gefunden**, weder durch Raten noch in der bisherigen Navigation. Der Navigationspunkt ist ein JS-Trigger ohne direkten Link. Nächster Schritt: ein von dir im Browser beobachteter Link, wie beim B-Ware-Fund
- **2. Wahl / B-Ware Kampagnen-ID (`3342`)** ist ein hartkodierter Default (per Konstruktorparameter überschreibbar), keine dokumentierte Konstante — Stabilität über die Zeit ungeklärt
- **Bestellungs-Status** in `get_order_list()` nur für einen von mehreren beobachteten Status-Typen extrahiert (siehe oben)
- **`get_daily_deals()`**: bislang bei jedem Live-Aufruf (drei unabhängige Male) leer — Trefferformat für echte Tagesangebote weiterhin unbestätigt
- **Varianten-/Alternativen-/Cross-Sell-Vollständigkeit**: `data-compare`-Listen wurden bei bis zu 12–13 Einträgen beobachtet, es gibt aber einen zusätzlichen "Alle anzeigen"-Link (`cmd=ShowAll/<matnr>&mode=var|alter|cross`) — ob die inline-Liste bei sehr vielen verwandten Artikeln gekappt wird und `ShowAll` dann mehr liefert, ist ungetestet (extensions.md 2.9)

### 1.2 Neue Kandidaten

Von dir gewünscht. Vier der fünf Kandidaten sind mittlerweile live verifiziert und in die Tabelle oben gewandert (`get_article_attributes`, `get_article_accessories`, `get_article_variants`, `get_article_alternatives`) — plus ein ungeplanter Bonusfund (`get_article_cross_sell`). Details/Fundstellen: [docs/extensions.md](docs/extensions.md) Abschnitt 2.9.

**Dokumente — weiterhin offen, nicht implementiert.** Endpunkt strukturell identifiziert (`cmd=AjaxDetailDocs&art=detail&title=technik&krnr=<Lieferantennummer>`, mit einer `data-json-wert`-JSON-Map Dokumenttyp→Artikelnummer), aber mehrere plausible Aufrufvarianten (GET/POST, verschiedene Parameternamen/-kodierungen, mit/ohne AJAX-Header) lieferten am 11.08.2026 durchgängig `200` mit leerem Body — nicht klar, ob falsche Parameter oder die drei Testartikel schlicht keine Dokumente hinterlegt haben. Analog zum Angebote-Endpunkt (1.1): nächster Schritt ist ein echter Browser-Mitschnitt, kein weiteres Parameter-Raten.

Nebenbefund, jetzt gegenstandslos: Der `cmd=AjaxVarianten&mode=getVariants`-Endpunkt (EAV-Radiobuttons für Farbe/Größe/etc.) lieferte bei allen getesteten Aufrufen `HTTP 500` und wurde nicht weiter verfolgt — sich als unnötig herausgestellt, weil die vollständige Varianten-Matrix bereits im normal abgerufenen Seiten-HTML steckt (siehe unten).

**Vollständige Varianten-Matrix statt kleiner Teaser-Liste (11.08.2026):** Auf Hinweis des Nutzers (ein Artikel mit einer auffällig großen, klickbaren Variantenauswahl in der Shop-UI) untersucht — mit Playwright im headed-Modus (Headless wurde vom Server mit "The URL you requested has been blocked" abgewiesen, `httpx` war davon nicht betroffen). Fund: Der bereits genutzte `data-variables`-JSON-Blob auf der Artikeldetailseite (Korrektur nebenbei: sitzt auf `<body>`, nicht auf einem eigenen `<div>`, siehe extensions.md 2.4) trägt zusätzlich ein `"variants"`-Array mit der kompletten Attributkombinatorik — 512 Artikelnummern bei einem Testartikel (Leitungsschutzschalter) statt 3 aus der alten Teaser-Liste. Kein Playwright/AJAX für die Daten selbst nötig, alles bereits im `httpx`-Response enthalten. `get_article_variants()` liest jetzt daraus, mit Fallback auf die alte Extraktion. EF/EV-Attributcodes werden bewusst noch nicht in lesbare Namen aufgelöst (Zusatzaufwand, siehe extensions.md 2.9) — auf Nutzerwunsch zunächst nur die flache Artikelnummernliste.

## 2. DATANORM v5 Submodul

Wartet auf Zugangsdaten + Format-Spezifikation von FEGA & Schmitt (beantragt, siehe [docs/architecture.md](docs/architecture.md#73-datanorm-v5-artikel-stammdatenpreislisten)).

- Datei-Parsing für Artikel-Stammdaten/Preislisten (reine Funktionen, kein FTP-Transport in der Library, analog UGL4-Zuschnitt)
- Falls Hersteller-Nr./EAN enthalten sind: robusterer, offizieller Ersatz für Teile von `web` (siehe extensions.md Abschnitt 6)

## 3. Rest der IDS-Schnittstelle

Niedrige Priorität.

- Artikeldeeplink, Artikelsuche, Login-Informationen, Schnittstellenversion, Heatinglabel
- IDS-Artikelsuche funktional teilweise durch `web` abgedeckt (dort ohne Handwerkersoftware-Rücksprung nötig)

## 4. UGL4 Flatfile

Niedrigste Priorität — FTP-Zugang und Relevanz für dieses Projekt weiterhin ungeklärt.

## Ausdrücklich nicht geplant

- **Playwright-Backend** für `web`: laut Praxisverifikation (>200 Requests über zwei Sitzungen, kein Bot-Schutz beobachtet) bisher keine Notwendigkeit — bleibt dokumentierte Eskalationsstufe, kein aktives Vorhaben.
