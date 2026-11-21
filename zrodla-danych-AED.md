# Źródła danych o defibrylatorach AED w Polsce

Stan na 2026-11-21. Legenda: **V** = pobrane i sprawdzone, **S** = widziane tylko w wyszukiwarce lub w prasie.

## A. Licencja jasna, można używać

| # | Źródło | Dane / endpoint | Format | Rekordy | Pola dostępności | Licencja | |
|---|---|---|---|---|---|---|---|
| A1 | **OpenStreetMap przez OpenAEDMap** (OSM Polska) | `https://openaedmap.org/api/v1/countries/PL.geojson` (bez logowania). Alternatywa: Overpass API, `emergency=defibrillator` | GeoJSON | **18 297** | `opening_hours` (37% rekordów, w tym 4 136 × `24/7`), `access` (92%: yes/customers/private/permit), `indoor` (87%), `defibrillator:location(:pl/:en)`, `level`, `operator`, `phone`, `check_date` | **ODbL 1.0**: wymaga atrybucji i udostępniania pochodnej bazy na tej samej licencji | V |
| A2 | **Warszawa**, Stołeczne Centrum Bezpieczeństwa (dane.um.warszawa.pl, w dane.gov.pl zbiór 39512) | `POST https://dane.um.warszawa.pl/api/action/get_scb_lokalizacja_defibrylatorow`, nagłówek `Authorization: <token>` (darmowa rejestracja) | JSON (GeoJSON-like) | ok. 500+ (nie liczone) | `device_availability` (24/7 czy ograniczona), `device_access_description` (godziny), `device_location` (wewnątrz/na zewnątrz), `device_public_access`, `device_manufacturer`, `location_*`, `attachment` (zdjęcie base64) | **CC BY**, aktualizacja codzienna | V (dokumentacja API; wymaga tokenu) |
| A3 | **Przemyśl** (dane.gov.pl, zbiór 4581) | `https://przemysl.skycms.com.pl/open-data/20/1730818801_b50R6UVxPgoVdBbq/{csv,geojson,json,gml}` | CSV, GeoJSON, JSON, GML | 21 | tylko opis tekstowy | **CC0 1.0** | V |
| A4 | **Legionowo** (dane.gov.pl, zbiór 40593) | `https://api.dane.gov.pl/media/resources/20260914/aed.csv` | CSV (adres z kodami TERC i SIMC) | 24 | brak | **CC0 1.0** | V |
| A5 | **Krosno** (dane.gov.pl, zbiór 3624) | `https://api.dane.gov.pl/media/resources/20240219/Defibrylator_jAmxQcp.csv` | CSV | 21 | brak | **CC0 1.0** | V |
| A6 | **Marki** (dane.gov.pl, zbiór 4955) | `https://api.dane.gov.pl/media/resources/20250710/Defibrylator_GminaMiastoMarki_1.csv` (+ `.xlsx`) | CSV, XLSX | 8 | brak (plik uszkodzony: cudzysłowy, zamienione lat/lon) | **CC BY 4.0** | V |
| A7 | **ZTM Gdańsk**, baza pojazdów (dane.gov.pl, zbiór 1803) | `https://files.cloudgdansk.pl/d/otwarte-dane/ztm/baza-pojazdow.json?v=2` | JSON | 278 pojazdów z `aed: true` (156 autobusów, 122 tramwaje) z 503 | nie dotyczy (AED mobilne) | **CC BY 4.0** | V |

Inne sprawdzenia:
- **dane.gov.pl** (wyszukiwanie po „defibrylator”, „AED” i odmianach) zwraca tylko A2–A7. Nie ma zbioru ogólnopolskiego.
- **data.europa.eu** pokazuje dla Polski tylko te same zbiory z dane.gov.pl.
- **Wikidata** ma 0 AED w Polsce (CC0).

## B. Wartościowe źródła o NIEJASNEJ licencji (do sprawdzenia)

| # | Źródło | Dane / endpoint | Format | Rekordy | Pola dostępności | Co wiadomo o licencji | |
|---|---|---|---|---|---|---|---|
| B1 | **Sopot**, otwartedane.sopot.pl, zbiór `defibrylatory-aed` | `https://otwartedane.sopot.pl/?api=plik&k=zdrowie-i-pomoc-spoleczna&z=defibrylatory-aed&f=defibrylatory.{csv,geojson,json,xlsx,zip}` | CSV, GeoJSON (EPSG:2180), JSON, XLSX, SHP | 26 | `Godziny dotępności` (17 × „24 h”, reszta godzin), `Lokalizacja` | Na samym zbiorze brak. Ogólny tekst portalu: „Udostępniane bez ograniczeń licencyjnych” | V |
| B2 | **InPost Helpbox 365** (AED w paczkomatach, z Centrum Ratownictwa) | `https://inpost.pl/aed-points`. Szczegóły punktu: `https://api-pl-points.easypack24.net/v1/points/<name>` | GeoJSON | 137 (strona podaje 188 aktywnych) | `opening_hours: "24/7"`, `location_247`, `location_description`, `status` | Brak informacji | V |
| B3 | **Łódź**, UMŁ: mapa defibrylatorów | KML: `https://www.google.com/maps/d/kml?mid=1FMKFbebKJPYqD4C87pXWPqNjEHuEswE&forcekml=1`. XLS: `https://uml.lodz.pl/files/public/dla_mieszkanca/Defiblyratory2025_10.xls` (blokada antybotowa, pobrać ręcznie w przeglądarce) | KML, XLS | 136 | opis tekstowy: „całodobowo”, „wewnątrz”, „w godz. …” | Brak informacji | KML V, XLS nie |
| B4 | **Koszalin**, „Punkty Życia” | `https://www.google.com/maps/d/kml?mid=1AQwJAfeZsGGB7fhz0-yBSxab83DwyIw&forcekml=1` | KML | 35 | opis tekstowy | Brak informacji | V |
| B5 | **Mikołów** (ArcGIS Online) | `https://services9.arcgis.com/E1ZsJFZqsk2tR9yK/arcgis/rest/services/Defibrylatory_AED/FeatureServer/0/query?where=1%3D1&outFields=*&f=geojson` | ArcGIS FeatureServer, GeoJSON | 21 | `Pietro`, `Położenie` (wewnątrz/na zewnątrz) | Brak na tej warstwie (inna warstwa gminy pozwala na reuse z atrybucją) | V |
| B6 | **Kraków**, ZPGIS (ArcGIS Online) | `https://services-eu1.arcgis.com/svTzSt3AvH7sK6q9/arcgis/rest/services/AED_zestawy_2022_sierpien/FeatureServer/0` | FeatureServer | 44 (stan 2023-11) | brak | Brak informacji | V |
| B7 | **Kraków**, krakow.pl „Mapa AED / Impuls Życia” | `https://www.krakow.pl/instcbi/3992/2432/{1..3}/` | tabela HTML (scraping) | 58 (stan 2026-10-01) | godziny tylko w nazwach | Brak informacji | V |
| B8 | **Gdańsk**, gdansk.pl (Wydział Bezpieczeństwa) | `https://www.gdansk.pl/wiadomosci/Defibrylatory,a,216952` | tabela HTML | 114 (stan 2022-02, nieaktualne) | „Czy znajduje się na zewnątrz budynku?”, „Godziny funkcjonowania?” | Brak informacji | V (odczyt) |
| B9 | **Politechnika Śląska** | PDF ze spisem AED (VI 2025) | PDF | ? | godziny dostępu | Brak informacji | S |

Pomijamy:
- Kraków, prywatne konto ArcGIS „wasniowskip” (150 rekordów): wydawca nieznany, to nie jest źródło oficjalne.
- Warstwa testowa mKraków (3 rekordy): przydatna tylko jako wzór schematu (pola `DOSTEP`, `DOS_G_O`, `DOS_G_D`, `DOS_TYDZ`, `AED_STAT`).

## C. Zamknięte lub niedostępne

| Źródło | Skala | Dlaczego niedostępne |
|---|---|---|
| **ZOSP RP**: aplikacje Pierwszy Ratownik i Reanimator (z PZU i Google Cloud) | >8 700 AED, największa baza spoza OSM | Brak eksportu i API. ZOSP jest „jedynym właścicielem rozwiązania”. Warto zapytać bezpośrednio. |
| **Staying Alive** / Fundacja Ogólnopolska Mapa AED | ok. 400 tys. na świecie | Ponowne użycie wymaga pisemnej zgody, API płatne |
| **Ratuj z sercem** (mapAED) | ? | Brak API i eksportu, brak warunków ponownego użycia |
| **GUGiK Geoportal**, warstwa „Defibrylatory” | – | Tylko obraz mapy (WMS), bez WFS i atrybutów. To kopia OpenAEDMap/OSM, więc dane i tak podlegają ODbL. |
| **Yanosik** | – | Zgłoszenia trafiały do OSM, więc pokrywa je A1 |

## D. Instytucje, które mają dane, ale ich nie publikują

Kandydaci do wniosku o udostępnienie albo do zaproszenia do akcji. Wiadomo o nich z tagów `source` i `operator` w OSM oraz z prasy:

- ZUS (ok. 177 AED),
- InPost (95 w OSM),
- Tauron (69),
- Tramwaje Warszawskie (38),
- Biedronka (36),
- UDT (30),
- NIK (20),
- PKL (18),
- Poczta Polska (40),
- PKP Intercity (ok. 40 pociągów),
- KW/KM PSP,
- uczelnie (UAM, SGH, UŚ, PG),
- lotniska, GDDKiA i koncesjonariusze autostrad (MOP-y).
