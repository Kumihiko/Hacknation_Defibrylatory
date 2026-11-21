# HeartSpot – najbliższy dostępny AED i otwarte dane o defibrylatorach

Rozwiązanie zadania „Misja AED – Dane na ratunek” (HackNation 2026, Ministerstwo Cyfryzacji).

1. **Agregator otwartych danych o AED.** Pobiera dane z wielu rozproszonych źródeł, sprowadza je do
   **wzorcowego zakresu danych**, łączy duplikaty i publikuje zbiór w formatach zgodnych ze
   Standardem technicznym dane.gov.pl. Generuje też plik importu XML dla harwestera dane.gov.pl.
2. **Aplikacja „najbliższy dostępny AED”.** Po otwarciu od razu wyznacza pieszą trasę do najbliższego
   defibrylatora **dostępnego teraz**: całodobowego albo otwartego według godzin. AED o nieznanym statusie
   pomija, żeby nie prowadzić do zamkniętych drzwi.
3. **Zakładka „Dodaj AED” dla dysponentów.** Gmina, szkoła albo firma wpisuje swoje AED w formularzu albo wczytuje
   gotowy plik CSV. Narzędzie sprawdza dane względem wzorcowego zakresu, a geokoder GUGiK uzupełnia kody TERYT.
   Na koniec dysponent pobiera CSV, GeoJSON i plik importu XML dla dane.gov.pl. Gdy opublikuje zbiór na
   dane.gov.pl, konektor `danegov` sam go znajdzie i dołączy do HeartSpot, z licencją podaną przy zbiorze.

## Szybki start

Wymagany Python 3.11+.

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"      # Windows: .venv\Scripts\pip install -e ".[dev]"
.venv/bin/aed run                      # pobiera źródła i generuje web/data oraz web/dane
.venv/bin/python -m http.server 8000 -d web
```

Otwórz http://localhost:8000. Geolokalizacja działa na `localhost` i przez HTTPS.

- **Tryb demo bez GPS:** http://localhost:8000/?lat=52.2319&lon=21.0067 (centrum Warszawy).
- **Testy z dowolną lokalizacją:** w DevTools (Chrome/Brave) otwórz Ctrl+Shift+P → „Show Sensors” → Location.

Inne polecenia:

```bash
aed run --offline              # buduje z danych zapisanych w data/raw (bez pobierania)
aed run --enable sopot,inpost  # dołącza źródła wyłączone w konfiguracji
aed sources                    # lista źródeł i ich licencji
pytest -q                      # testy
```

Opcjonalnie skopiuj `.env.example` do `.env` i podaj token API m.st. Warszawy (`WAW_API_TOKEN`).
Bez tokenu dane Warszawy są pobierane z publicznej kopii ArcGIS.

## Jak to działa

```
źródła ─► konektory ─► data/raw ─► normalizacja ─► klasa dostępności ─► deduplikacja ─► zbiór (ODbL)
                                                                                         ├─► web/dane: CSV, GeoJSON, XLSX, CSVW, XML dane.gov.pl
                                                                                         └─► web/data/aed.json ─► aplikacja (Leaflet + OSRM)
```

- **Źródła** (`config/sources.yaml`): nowe źródło dodaje się konfiguracją. Mamy konektory generyczne
  (CSV, GeoJSON, ArcGIS, KML) z mapowaniem kolumn w YAML oraz konektory dedykowane
  (OpenAEDMap/OSM, API Warszawy, tabela HTML Gdańska z geokodowaniem GUGiK UUG).
- **Normalizacja** (`aed/normalize/`):
  - parser godzin: składnia OSM `opening_hours` i polskie opisy („pn.-pt. 7.00-15.30”, „całodobowo”),
  - naprawa zamienionych współrzędnych i przeliczenie z PUWG 1992 (EPSG:2180),
  - rozbicie adresu na pola, telefon w formacie 9 cyfr,
  - kontrola współrzędnych odstających od obszaru źródła.
- **Klasy dostępności:**

  | Klasa | Znaczenie | Trasa |
  |---|---|---|
  | `24h_pewny` | Źródło jawnie podaje dostępność 24/7 | tak |
  | `24h_wnioskowany` | Publiczny, na zewnątrz budynku, bez podanych godzin | tak, z adnotacją |
  | `godziny` | Znane godziny | tak, gdy otwarty |
  | `nieznany` | Brak informacji | nie |
  | `prywatny` | Prywatny, ograniczony lub mobilny | nie |

  Gdy opis godzin jest niejednoznaczny, parser zostawia „brak informacji” zamiast zgadywać.
- **Deduplikacja** (`aed/dedupe.py`):
  - łączy tylko rekordy z różnych źródeł: do 12 m od razu, do 40 m przy podobnej nazwie lub adresie,
    a powiązania z tagu OSM `ref:api-um-warszawa-pl` niezależnie od tej odległości (do 150 m),
  - pola bierze ze źródła o najwyższym priorytecie (oficjalne przed OSM), a współrzędne z OSM,
  - zachowuje listę źródeł i identyfikatory.
- **Aplikacja** (`web/`): statyczna strona bez backendu.
  1. Spośród AED dostępnych teraz wybiera 6 najbliższych w linii prostej.
  2. Z macierzy OSRM (FOSSGIS, profil pieszy) bierze rzeczywiście najszybszy i sprawdza, czy AED
     będzie jeszcze otwarty w chwili dotarcia.
  3. Gdy OSRM nie odpowiada, rysuje trasę orientacyjną.

## Wzorcowy zakres danych i zgodność z dane.gov.pl

- Schemat: `schema/aed.schema.json` (Frictionless Table Schema). To jedyne źródło prawdy dla CSV, XLSX i CSVW.
- Plik do zgłoszenia: `schema/wzorcowy-zakres-danych-AED.xlsx` (opis pól, słowniki, przykładowe dane, źródła).
- CSV zgodny z RFC 4180:
  - kodowanie UTF-8, separator przecinek, końce wierszy CRLF, jeden wiersz nagłówka,
  - daty ISO 8601, kropka dziesiętna, wartości logiczne `true`/`false`,
  - adres w osobnych polach z kodami TERYT, telefon jako 9 cyfr.
- `aed.csv-metadata.json`: metadane CSVW (W3C) z typami i odwołaniami do schema.org, wymagane na 4. poziomie otwartości.
- `danegov-import.xml`: plik importu dla harwestera dane.gov.pl, **walidowany względem oficjalnego XSD**
  (`schema/vendor/otwarte_dane_harvester_1.13.xsd`, test w `tests/`).

## Publikacja (GitHub Pages)

1. Utwórz repozytorium na GitHubie i wypchnij kod.
2. W Settings → Pages jako źródło wybierz „GitHub Actions”.
3. Opcjonalnie dodaj sekret `WAW_API_TOKEN`.

Workflow `.github/workflows/update-data.yml` uruchamia testy, buduje dane i publikuje `web/`
codziennie oraz po każdym pushu do `main`. Adres strony trafia automatycznie do pliku importu dane.gov.pl.

## Źródła danych i licencje

| Źródło | Licencja | W zbiorze |
|---|---|---|
| OpenStreetMap (przez OpenAEDMap) | ODbL 1.0 | tak |
| m.st. Warszawa – Stołeczne Centrum Bezpieczeństwa | CC BY | tak |
| UM Legionowo, UM Krosno, UM Przemyśl | CC0 1.0 | tak |
| UM Marki | CC BY 4.0 | tak |
| UM Sopot (otwartedane.sopot.pl) | portal deklaruje „bez ograniczeń licencyjnych” | tak |
| Zbiory dysponentów na dane.gov.pl we wzorcowym zakresie (konektor `danegov`) | licencja każdego zbioru | tak (automatycznie) |
| InPost Helpbox 365 | „wszelkie prawa zastrzeżone” | nie |
| Łódź, Gdańsk, Kraków (ZPGIS, konto prywatne) | brak informacji o licencji | konektory gotowe, `enabled: false` |

Zbiór zawiera dane OSM, więc jest udostępniany na licencji **ODbL 1.0** (© współtwórcy OpenStreetMap).
Pole licencji w XSD dane.gov.pl przyjmuje tylko licencje Creative Commons, dlatego warunki ODbL opisujemy w polu
`dbOrCopyrighted`. Źródło każdego rekordu podają kolumny `zrodla`, `zrodlo_id` i `zrodlo_licencja`.

## Użyte komponenty

| Komponent | Licencja | Do czego |
|---|---|---|
| Python, PyYAML | PSF, MIT | pipeline, konfiguracja |
| rapidfuzz | MIT | porównywanie nazw przy deduplikacji |
| openpyxl | MIT | XLSX |
| lxml, pytest | BSD, MIT | testy (walidacja XSD) |
| Leaflet 1.9.4 | BSD-2 | mapa (kopia lokalna w `web/vendor`) |
| Kafelki OpenStreetMap | ODbL / CC BY-SA | podkład mapy |
| OSRM (serwer FOSSGIS), zapasowo BRouter (brouter.de) | – | trasy piesze (usługi publiczne; przy awarii OSRM aplikacja przełącza się na BRouter) |
| GUGiK UUG, Nominatim | – | wyszukiwanie adresu |

## Ograniczenia

- 63% AED w OSM nie ma podanych godzin, dlatego aplikacja pomija je, jeśli nie są na zewnątrz budynku.
  Rozwiązaniem jest publikowanie danych przez dysponentów według wzorcowego zakresu.
- Klasa `24h_wnioskowany` to wnioskowanie: publiczna szafka na zewnątrz zwykle jest dostępna przez całą dobę.
- Publiczne usługi tras i geokodowania (FOSSGIS, Nominatim) mają limity użycia odpowiednie dla prototypu.
  Wdrożenie produkcyjne wymaga własnej instancji OSRM.
- Część źródeł samorządowych nie podaje licencji. Ich konektory są gotowe i czekają na potwierdzenie licencji.

## Wykorzystanie AI

Zgodnie z §2 pkt 8 regulaminu: *(uzupełnia zespół – zakres użycia asystenta AI przy researchu źródeł,
kodzie i dokumentacji oraz to, co zespół zweryfikował i zaprojektował samodzielnie)*.

## Licencja kodu

MIT – zob. plik `LICENSE`.
