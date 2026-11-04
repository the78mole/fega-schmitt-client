# DATANORM bei FEGA & Schmitt: Format & Umsetzung

> Status: **SQLite-Import und S3-Archivierung umgesetzt** (`fega datanorm import`, `fega datanorm upload`). Eine offizielle Formatspezifikation von FEGA & Schmitt liegt nicht vor (siehe [docs/architecture.md §7.3](docs/architecture.md#73-datanorm-v5-artikel-stammdatenpreislisten) und [PLANNED_FEATURES.md](PLANNED_FEATURES.md) Punkt 2). Alle Feldbedeutungen unten sind daher **aus echten Lieferungen abgeleitet**; die Sicherheit ist je Feld angegeben.

Jeder FEGA-Kunde erhält seine eigene DATANORM: Einkaufspreise und eigene Artikelnummern sind kundenspezifisch. Dieses Dokument beschreibt deshalb nur den Aufbau. Mengenangaben sind Größenordnungen und können je Kunde und Lieferung abweichen. Die Beispielzeilen sind erfunden.

## 1. Was FEGA liefert

Die Lieferung kommt als Mail-Anhang („Artikelpreispflege“, Betreff „datanorm.zip Versand“) und lässt sich über die FEGA-Website anfordern. Der Absender kann wechseln, eine Lieferung erkennt man also besser am Betreff. **Offene Frage an FEGA:** Gibt es neben dem Mail-Versand einen FTP-Zugang und einen regelmäßigen Versand? Für eine automatisierte Pipeline wäre FTP (Pull, Scheduling) besser geeignet als ein Mail-Anhang.

Der Anhang `datanorm.zip` (rund 16 MB gepackt, 45 MB entpackt) enthält drei Dateien:

| Datei | Zeilen (Größenordnung) | Satzarten | Inhalt |
| --- | --- | --- | --- |
| `datanorm.001` | 270.000 | `V`,`A`,`Z`,`E` | Artikelstammdaten und Zuschläge |
| `datanorm.wrg` | 380 | `V`,`S`,`E` | Warengruppen |
| `datpreis.001` | 490.000 | `V`,`P`,`E` | Preise |

**Encoding:** Alle drei Dateien sind **CP850** (DOS/OEM). Ein pauschales `latin-1` liefert kaputte Umlaute (München → M-fnchen). `datpreis.001` enthält nur ein einziges Nicht-ASCII-Byte, das `ß` in „Elektrogroßhandel“ im Kopfsatz (`0xE1`, in CP850 `ß`, in ISO-8859-1 `á`).

**Zeilenformat:** CRLF, semikolon-getrennt, jede Zeile endet mit `;`. Der `E`-Satz enthält die Zeilenzahl der Datei **einschließlich** `V`- und `E`-Satz (z. B. 1 + 375 + 1 = `E;377`). Der Import prüft das, damit eine abgeschnittene Datei nicht als kleinere Lieferung durchgeht.

**Volllieferung:** Jeder `A`- und `Z`-Satz trägt das Verarbeitungskennzeichen `N`. Es ist also eine vollständige Liste, keine Änderungsliste (DATANORM kennt dafür `A` = Änderung, `L` = Löschung). Der Import lehnt Lieferungen mit anderen Kennzeichen ab, statt eine Änderungsliste versehentlich als vollständigen Bestand zu übernehmen.

**Keine `.rab`-Datei:** Die Begleitmail nennt die Reihenfolge `Datanorm.rab → Datanorm.wrg → Datanorm.00n → Datpreis.001`, jeweils „wenn vorhanden“; eine Rabattdatei war bisher nicht enthalten. Sie wird auch nicht gebraucht: `datpreis.001` liefert den Einkaufspreis mit eingerechnetem Rabatt (Abschnitt 2.4), und die Rabattgruppe im Artikelsatz ist durchgehend leer.

**Version:** Der `V`-Satz beginnt mit `V;050;...` → **DATANORM 5.0**.

## 2. Satzarten im Detail (aus den Daten abgeleitet)

### 2.1 `datanorm.001` — Artikelstammdaten (`A`-Satz)

```text
V;050;A;<JJJJMMTT>;EUR;Artikelstammdaten;;;FEGA & Schmitt;Elektrogroßhandel GmbH;;Rettistr. 5;;;91522 Ansbach;
A;N;1234567;ABCD Beispielartikel;XY 100 grau;STCK;1;1;6310; ;30;05;XY 100;;;;XY 100;;4000000000000; ;;;4;;;;;;1;
...
E;<Zeilenzahl>;
```

30 Felder je Zeile, 1-indiziert:

| # | Beispielwert | Bedeutung | Sicherheit |
| --- | --- | --- | --- |
| 1 | `A` | Satzkennung | sicher |
| 2 | `N` | Verarbeitungskennzeichen, immer `N` (Volllieferung) | hoch |
| 3 | `1234567` | **FEGA-Artikelnummer**, eindeutig; genau die `MATERIAL_NUMBER` für `get_price_availability` | sicher |
| 4 | `ABCD Beispielartikel` | Kurztext 1: Hersteller-Kürzel und Produktart | hoch |
| 5 | `XY 100 grau` | Kurztext 2: technische Ergänzung | hoch |
| 6 | `STCK` | Mengeneinheit (`STCK`, `MTR`, `PACK`, `SET`, `PCE`, …) | hoch |
| 7 | `1` | unklar, bisher immer `1` (nach DATANORM-Konvention vielleicht Preiskennzeichen) | niedrig |
| 8 | `1` | **Preiseinheit**: der Preis gilt je 1, 100 oder 1000 Mengeneinheiten | **hoch** — deckt sich mit der Preiseinheit in `datpreis.001` |
| 9 | `6310` | **Listenpreis** in Cent je Preiseinheit (→ 63,10 €) | **sicher** — identisch mit Preisart 1 in `datpreis.001` |
| 10 | (leer) | Rabattgruppe, durchgehend leer | mittel |
| 11 | `30` | **Hauptgruppe** | **sicher** — gegen `datanorm.wrg` verifiziert |
| 12 | `05` | **Warengruppe** (Untergruppe) | **sicher** |
| 13 | `XY 100` | Typbezeichnung des Herstellers (oft mit Leerzeichen) | mittel |
| 15 | (meist leer) | **Eigene Artikelnummer des Kunden**, auf 15 Zeichen gekürzt; passt zu dem im Webshop gepflegten Wert (`set_article_number`), aber bisher nur an einem Artikel beobachtet | mittel |
| 17 | `XY 100` | Bestellnummer des Herstellers; meist gleich Feld 13 | mittel |
| 19 | `4000000000000` | **EAN**, bei gut 90 % der Artikel gefüllt | hoch |
| 23 | `4` | unklar: `4` oder `0` (0 bei rund 2 %, ohne erkennbares Muster) | niedrig |
| 28 | (leer) | unklar: Zahl, bei rund 10 % gefüllt | niedrig |
| 29 | `1` | unklar, fast immer `1` (ganz vereinzelt `3`) | niedrig |

Die übrigen Felder (14, 16, 18, 20–22, 24–27, 30) sind leer.

**Preiseinheit beachten:** Bei rund 18 % der Artikel gilt der Preis je 100 oder 1000 Einheiten; Kabel meist je 100 m (`MTR` mit Preiseinheit 100). `6505` bei `MTR`/100 heißt 65,05 € für 100 m, also 0,65 €/m. Die Preiseinheit eines Artikels kann sich zwischen zwei Lieferungen ändern. **Preise immer zusammen mit der Preiseinheit vergleichen.**

**Wichtigster Fund für dieses Projekt:** Feld 3 ist exakt die Nummer, die die SOAP-Schnittstelle referenziert („die FEGA & Schmitt-Artikelnummer, die Sie über eine andere Schnittstelle (z.B. DATANORM) bezogen haben“, `Schnittstellenbeschreibung_SOAP.pdf` Abschnitt 1). Ein DATANORM-Import ist damit der fehlende Baustein, um `get_price_availability` ohne manuelle Artikelnummer-Recherche im Webshop zu befüllen.

### 2.2 `datanorm.001` — `Z`-Sätze (Zuschläge)

Feld 3 ist die Artikelnummer, Feld 4 eine laufende Nummer `01`–`04` (ein Artikel kann mehrere Zuschläge haben). Zwei Formen, unterschieden durch Feld 5:

```text
Z;N;1234567;01;3;CU;2;100;15000;10;290;1000;
Z;N;7654321;01;1;Auftragsp v. LP (#);Auftragsp v. LP (#);2;+;2;1;454;;;;;
```

| Form | Anteil | Beobachtung |
| --- | --- | --- |
| Feld 5 = `3`: Metallzuschlag | rund 60 % | Material in Feld 6: `CU` Kupfer, `AG` Silber, `MS` Messing, `AL` Aluminium. `15000` passt zur üblichen Kupferbasis 150 €/100 kg, `290` vermutlich Metallgewicht (z. B. kg je 1000 m) — plausibel, nicht bestätigt |
| Feld 5 = `1`: Freitext-Zuschlag | rund 40 % | Bezeichnung in Feld 6/7, z. B. „Auftragsp v. LP (#)“, „Verpackung (#)“, „Messingzuschlag VK #“; Vorzeichen `+` und Betrag folgen |

Inhaltlich dieselbe Kategorie wie `SURCHARGE_REBATE_LIST` in der SOAP-Antwort (`Surcharge` in [models.py](src/fega_schmitt_client/models.py)). Ob sich Metallzuschläge damit offline berechnen lassen, bleibt offen, bis die Feldsemantik geklärt ist. Der Import legt die Felder deshalb roh ab (JSON-Liste ab Feld 5).

### 2.3 `datanorm.wrg` — Warengruppen

```text
V;050;S;<JJJJMMTT>;EUR;Warengruppenstammdaten;;;FEGA & Schmitt;Elektrogroßhandel GmbH;;Rettistr. 5;;;91522 Ansbach;
S;12;;Großgeräte;
S;12;24;Industriesteuerungen SPS;
S;30;;Sonstige Installationsgeräte und Systeme;
...
E;<Zeilenzahl>;
```

`S;<Hauptgruppe>;<Untergruppe oder leer>;<Bezeichnung>;` — zweistufig, 17 Hauptgruppen. Unabhängig von der webshop-eigenen `UWG_*`-Kategoriestruktur in [docs/fega_categories.md](docs/fega_categories.md); eine 1:1-Beziehung ist ohne weitere Prüfung nicht anzunehmen.

### 2.4 `datpreis.001` — Preise

```text
V;050;P;<JJJJMMTT>;EUR;Preisstammdaten;;;FEGA & Schmitt;Elektrogroßhandel GmbH;;Rettistr. 5;;;91522 Ansbach;
P;1234567;1;1;6310;;
P;1234567;2;1;4500;;
...
E;<Zeilenzahl>;
```

`P;<Artikelnummer>;<Preisart>;<Preiseinheit>;<Preis in Cent>;` — je Artikel **genau zwei Zeilen**:

- **Preisart 1 = Listenpreis.** Identisch mit Feld 9 des Artikelsatzes.
- **Preisart 2 = Einkaufspreis (netto, kundenspezifisch).** Nie höher als der Listenpreis, kann ihm aber gleich sein.

Damit ist der Rabatt des jeweiligen Kunden bereits eingerechnet — das erklärt die fehlende `.rab`-Datei und die leere Rabattgruppe. Endgültig bestätigen lässt es sich durch einen Vergleich einiger Preise mit dem Webshop.

Einzelne Artikel haben keinen Preissatz.

## 3. Umsetzung

```text
fega_schmitt_client/
    datanorm/
        __init__.py     # Public API: import_delivery, default_db_path, upload_file, ...
        _parser.py      # Datei-Leser: CP850, V/E-Prüfung, ZIP oder Verzeichnis
        db.py           # SQLite-Schema, Import, Vergleich mit der vorherigen Datenbank
        s3.py           # Archivierung in einen S3-kompatiblen Store
```

**`fega datanorm import SOURCE [-s] [--db PFAD]`** lädt eine Lieferung (`datanorm.zip` oder Verzeichnis) nach `~/.cache/fega-schmitt-client/datanorm.db` (bzw. `$XDG_CACHE_HOME`). Jeder Import baut die Datenbank neu auf, passend zur Volllieferung. Die neue Datenbank entsteht erst als `datanorm.db.new` und ersetzt die alte erst, wenn alle Dateien gelesen und geprüft sind. Eine vorhandene Datenbank wird vorher nach `datanorm-<ihr Lieferdatum>.db` kopiert. `-s/--summary` gibt die Änderungen gegenüber der vorherigen Datenbank aus.

Tabellen:

| Tabelle | Inhalt |
| --- | --- |
| `articles` | ein Satz je Artikel; Felder mit unklarer Bedeutung als `field_7`, `field_23`, `field_28`, `field_29`, sonstige gefüllte Felder als JSON in `extra` |
| `prices` | `(material_number, price_type)` → Preiseinheit, Preis in Cent |
| `groups` | `(main_group, sub_group)` → Bezeichnung; `sub_group = ''` für die Hauptgruppe |
| `surcharges` | `(material_number, seq)` → Felder ab 5 als JSON-Liste |
| `deliveries` | Kopfsatz und Zeilenzahl je Datei |
| View `article_prices` | Artikel mit Listen- und Einkaufspreis in Euro, Einkaufspreis je Einheit und Warengruppennamen |

`material_number` heißt bewusst wie `PriceAvailRequestItem.material_number`, damit „DATANORM-Import → `PriceAvailRequestItem` → `get_price_availability`“ ohne Umbenennung durchläuft.

**`fega datanorm upload`** archiviert die Lieferung in einen S3-kompatiblen Store unter `fega/<lieferdatum>/` (siehe README).

## 4. Offene Punkte

1. Einige Einkaufspreise (Preisart 2) mit dem Webshop vergleichen, um „Preisart 2 = Nettopreis“ zu bestätigen.
2. Feld 15 an weiteren Artikeln prüfen, um „eigene Artikelnummer des Kunden“ zu bestätigen.
3. `Z`-Sätze / Metallzuschlags-Verzahnung mit `Surcharge`: zurückstellen, bis die Feldsemantik geklärt ist.
4. Bei FEGA nachfragen: (a) gibt es neben dem Mail-Versand FTP und einen regelmäßigen Versand? (b) gibt es eine Feldspezifikation für FEGAs DATANORM-5.0-Export? (c) Bedeutung der Felder 7, 23, 28 und 29.
