/* HeartSpot – „Dodaj AED”: formularz i walidator danych dysponenta wg wzorcowego zakresu (dane/aed.schema.json),
 * eksport CSV / GeoJSON / XML importu dane.gov.pl. Bez backendu – szkic trzymany w localStorage. */
(() => {
  'use strict';

  const DAYS = [['Mo', 'Poniedziałek'], ['Tu', 'Wtorek'], ['We', 'Środa'], ['Th', 'Czwartek'], ['Fr', 'Piątek'], ['Sa', 'Sobota'], ['Su', 'Niedziela']];
  const STORAGE_KEY = 'heartspot-dodaj-szkic';
  const UUG = 'https://services.gugik.gov.pl/uug/';
  const NS = 'urn:otwarte-dane:harvester:1.13';
  const $ = (id) => document.getElementById(id);

  let schema = null;
  let records = load();
  let point = null;
  let geo = {};            // kody TERYT z geokodera GUGiK
  let editingId = null;
  let map, marker;

  // ------------------------------------------------------------------ szkic w przeglądarce
  function load() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || []; } catch (e) { return []; }
  }
  function save() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(records)); } catch (e) { /* tryb prywatny – trudno */ }
  }

  // ------------------------------------------------------------------ godziny
  function buildWeekEditor() {
    const box = $('week-editor');
    for (const [code, label] of DAYS) {
      const row = document.createElement('div');
      row.className = 'week-row';
      row.innerHTML = `
        <span class="week-day" id="lbl-${code}">${label}</span>
        <label class="checkbox-inline"><input type="checkbox" id="open-${code}" aria-describedby="lbl-${code}"> dostępny</label>
        <label class="visually-hidden" for="from-${code}">${label} od</label>
        <input type="time" id="from-${code}" value="08:00" disabled>
        <span aria-hidden="true">–</span>
        <label class="visually-hidden" for="to-${code}">${label} do</label>
        <input type="time" id="to-${code}" value="16:00" disabled>`;
      box.append(row);
      $(`open-${code}`).addEventListener('change', (e) => {
        $(`from-${code}`).disabled = !e.target.checked;
        $(`to-${code}`).disabled = !e.target.checked;
      });
    }
    $('h24').addEventListener('change', (e) => { box.hidden = e.target.checked; });
    $('preset-weekdays').addEventListener('click', () => {
      DAYS.forEach(([code], i) => setDay(code, i < 5, '08:00', '16:00'));
      $('h24').checked = false;
      box.hidden = false;
    });
  }
  function setDay(code, open, from, to) {
    $(`open-${code}`).checked = open;
    $(`from-${code}`).disabled = $(`to-${code}`).disabled = !open;
    if (from) $(`from-${code}`).value = from;
    if (to) $(`to-${code}`).value = to;
  }
  /** Godziny z edytora w składni OSM opening_hours (dni o tych samych godzinach są grupowane). */
  function weekToOsm() {
    if ($('h24').checked) return '24/7';
    const per = DAYS.map(([code]) => ($(`open-${code}`).checked ? `${$(`from-${code}`).value}-${$(`to-${code}`).value}` : null));
    const rules = [];
    for (let i = 0; i < 7;) {
      if (!per[i]) { i += 1; continue; }
      let j = i;
      while (j + 1 < 7 && per[j + 1] === per[i]) j += 1;
      rules.push(`${i === j ? DAYS[i][0] : `${DAYS[i][0]}-${DAYS[j][0]}`} ${per[i]}`);
      i = j + 1;
    }
    return rules.join('; ');
  }
  function osmToEditor(osm) {
    DAYS.forEach(([code]) => setDay(code, false));
    $('h24').checked = osm === '24/7';
    $('week-editor').hidden = osm === '24/7';
    if (!osm || osm === '24/7') return;
    for (const rule of osm.split(';')) {
      const m = rule.trim().match(/^(\w\w)(?:-(\w\w))?\s+(\d\d:\d\d)-(\d\d:\d\d)$/);
      if (!m) continue;
      const a = DAYS.findIndex(([c]) => c === m[1]);
      const b = m[2] ? DAYS.findIndex(([c]) => c === m[2]) : a;
      for (let i = a; i <= b; i += 1) setDay(DAYS[i][0], true, m[3], m[4]);
    }
  }

  // ------------------------------------------------------------------ mapa
  function initMap() {
    map = L.map('pick-map').setView([52.07, 19.48], 6);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">współtwórcy OpenStreetMap</a>',
    }).addTo(map);
    map.on('click', (e) => setPoint([e.latlng.lat, e.latlng.lng]));
  }
  function setPoint(ll, zoom) {
    point = [Math.round(ll[0] * 1e6) / 1e6, Math.round(ll[1] * 1e6) / 1e6];
    if (!marker) {
      const icon = L.divIcon({
        className: 'pin-marker',
        html: '<svg viewBox="0 0 32 44" width="32" height="44" aria-hidden="true"><path fill="#b91c1c" stroke="#fff" stroke-width="2" d="M16 1C7.7 1 1 7.6 1 15.8 1 27 16 43 16 43s15-16 15-27.2C31 7.6 24.3 1 16 1z"/><path fill="#fff" d="M17.5 7 10 19h5l-1.5 9L21 16h-5z"/></svg>',
        iconSize: [32, 44], iconAnchor: [16, 43],
      });
      marker = L.marker(point, { draggable: true, title: 'Położenie AED – przeciągnij, aby poprawić', keyboard: true, icon }).addTo(map);
      marker.on('dragend', () => { const p = marker.getLatLng(); setPoint([p.lat, p.lng]); });
    } else marker.setLatLng(point);
    if (zoom) map.setView(point, zoom);
    $('coords-out').textContent = `${point[0].toFixed(6)}, ${point[1].toFixed(6)}`;
  }
  async function uug(address) {
    const res = await fetch(`${UUG}?request=GetAddress&srid=4326&address=${encodeURIComponent(address)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const j = await res.json();
    const hit = (j && j.results && j.results['1']) || null;
    if (hit) hit.found = Number(j['found objects']) || 1;
    return hit;
  }
  /** "{Polska,mazowieckie,wołomiński,Marki}" -> "gm. Marki, pow. wołomiński, woj. mazowieckie" */
  function unitText(hit) {
    const parts = String(hit.jednostka || '').replace(/[{}]/g, '').split(',');
    if (parts.length < 4) return '';
    return `gm. ${parts[3]}, pow. ${parts[2]}, woj. ${parts[1]}`;
  }

  /** Geokodowanie ze stopniowym zawężaniem: dokładny adres -> sama ulica -> miejscowość (GUGiK) -> Nominatim (OSM).
   *  GUGiK przyjmuje tylko numery istniejące w państwowym rejestrze adresów, stąd kolejne próby. */
  async function geocode() {
    const city = $('miejscowosc').value.trim();
    const street = $('ulica_nazwa').value.trim().replace(/^(ul|al|pl|os)\.?\s+/i, '');
    const number = $('nr_budynku').value.trim();
    const status = $('geo-status');
    if (!city) { status.textContent = 'Najpierw wpisz miejscowość (i najlepiej ulicę z numerem).'; return; }
    status.textContent = 'Szukam…';
    const attempts = [];
    if (street && number) attempts.push({ q: `${city}, ${street} ${number}`, zoom: 18, level: 'adres' });
    if (street) attempts.push({ q: `${city}, ${street}`, zoom: 17, level: 'ulica' });
    attempts.push({ q: city, zoom: 14, level: 'miejscowość' });
    let networkError = false;
    for (const a of attempts) {
      let hit = null;
      try { hit = await uug(a.q); } catch (e) { networkError = true; break; }
      if (!hit) continue;
      setPoint([parseFloat(hit.y), parseFloat(hit.x)], a.zoom);
      geo = { kod_terc: hit.teryt || '', kod_simc: hit.simc || '', kod_ulic: hit.ulic || '' };
      if (hit.code && !$('kod_pocztowy').value) $('kod_pocztowy').value = hit.code;
      const unit = unitText(hit);
      const found = [hit.city, [hit.street, hit.number].filter(Boolean).join(' ')].filter(Boolean).join(', ') + (unit ? ` (${unit})` : '');
      const ambiguous = a.level !== 'adres' && hit.found > 1
        ? ' Uwaga: w Polsce jest więcej miejsc o tej nazwie – sprawdź, czy mapa pokazuje właściwą miejscowość; jeśli nie, dopisz ulicę z numerem albo wskaż miejsce ręcznie.'
        : '';
      if (a.level === 'adres') {
        status.textContent = `Znaleziono w rejestrze adresów GUGiK: ${found}. Przeciągnij znacznik dokładnie w miejsce, gdzie wisi AED.`;
      } else if (a.level === 'miejscowość' && !street) {
        status.textContent = `Ustawiono środek miejscowości: ${found}. Przesuń znacznik w dokładne miejsce na mapie.${ambiguous}`;
      } else {
        const missing = a.level === 'ulica' ? `numeru „${number}”` : `ulicy „${street}”`;
        status.textContent = `W rejestrze adresów GUGiK nie ma ${missing} – ustawiono: ${found}. Przesuń znacznik w dokładne miejsce na mapie.${ambiguous}`;
      }
      return;
    }
    // zapasowo OpenStreetMap (Nominatim)
    try {
      const q = [street && number ? `${street} ${number}` : street, city].filter(Boolean).join(', ');
      const res = await fetch(`https://nominatim.openstreetmap.org/search?format=json&limit=1&countrycodes=pl&q=${encodeURIComponent(q)}`);
      const j = await res.json();
      if (j.length) {
        setPoint([parseFloat(j[0].lat), parseFloat(j[0].lon)], 17);
        status.textContent = 'Adres znaleziony w OpenStreetMap (bez kodów TERYT). Sprawdź i popraw znacznik na mapie.';
        return;
      }
    } catch (e) { networkError = true; }
    status.textContent = networkError
      ? 'Wyszukiwarka adresów jest teraz niedostępna (brak połączenia). Wskaż miejsce, klikając na mapie.'
      : 'Nie znaleziono takiego adresu – sprawdź pisownię albo wskaż miejsce, klikając na mapie.';
  }

  // ------------------------------------------------------------------ walidacja wg schematu
  function validate(rec) {
    const errors = [];
    for (const f of schema.fields) {
      const v = rec[f.name];
      const c = f.constraints || {};
      const empty = v === undefined || v === null || v === '';
      if (empty) {
        if (c.required) errors.push(`${f.title}: pole wymagane`);
        continue;
      }
      const s = String(v);
      if (f.type === 'number' && Number.isNaN(Number(s))) errors.push(`${f.title}: oczekiwana liczba z kropką dziesiętną`);
      if (f.type === 'integer' && !/^-?\d+$/.test(s)) errors.push(`${f.title}: oczekiwana liczba całkowita`);
      if (f.type === 'boolean' && !/^(true|false)$/.test(s)) errors.push(`${f.title}: dozwolone true lub false`);
      if (f.type === 'date' && !/^\d{4}-\d{2}-\d{2}$/.test(s)) errors.push(`${f.title}: data w formacie RRRR-MM-DD`);
      if (c.enum && !c.enum.includes(s)) errors.push(`${f.title}: dozwolone ${c.enum.join(', ')}`);
      if (c.pattern && !new RegExp(c.pattern).test(s)) errors.push(`${f.title}: niepoprawny format („${s}”)`);
      if (c.minimum !== undefined && Number(s) < c.minimum) errors.push(`${f.title}: poza obszarem Polski`);
      if (c.maximum !== undefined && Number(s) > c.maximum) errors.push(`${f.title}: poza obszarem Polski`);
    }
    return errors;
  }

  function classify(rec) {
    if (['prywatny', 'ograniczony', 'mobilny'].includes(rec.typ_dostepu)) return 'prywatny';
    if (rec.dostepny_24_7 === 'true') return '24h_pewny';
    if (rec.godziny_dostepnosci) return 'godziny';
    if (rec.typ_dostepu === 'publiczny' && rec.wewnatrz_budynku === 'false') return '24h_wnioskowany';
    return 'nieznany';
  }

  const phone = (v) => { const d = String(v || '').replace(/\D/g, '').replace(/^48(?=\d{9}$)/, ''); return d.length === 9 ? d : (v || ''); };
  const today = () => new Date().toISOString().slice(0, 10);

  function fromForm() {
    const val = (id) => $(id).value.trim();
    const hours = weekToOsm();
    const rec = {
      id: editingId || (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`),
      nazwa_obiektu: val('nazwa_obiektu'), ulica_cecha: val('ulica_cecha'), ulica_nazwa: val('ulica_nazwa'),
      nr_budynku: val('nr_budynku'), kod_pocztowy: val('kod_pocztowy'), miejscowosc: val('miejscowosc'),
      kod_terc: geo.kod_terc || '', kod_simc: geo.kod_simc || '', kod_ulic: geo.kod_ulic || '',
      szerokosc_geo: point ? String(point[0]) : '', dlugosc_geo: point ? String(point[1]) : '',
      wewnatrz_budynku: val('wewnatrz_budynku'), pietro: val('pietro'), opis_lokalizacji: val('opis_lokalizacji'),
      dostepny_24_7: hours === '24/7' ? 'true' : (hours ? 'false' : ''), godziny_dostepnosci: hours,
      typ_dostepu: val('typ_dostepu'), szafka_zamknieta: $('szafka_zamknieta').checked ? 'true' : 'false',
      telefon_dostep: phone(val('telefon_dostep')), status: val('status'), producent: val('producent'), model: val('model'),
      elektrody_pediatryczne: $('elektrody_pediatryczne').checked ? 'true' : 'false',
      data_przegladu: val('data_przegladu'), data_waznosci_elektrod: val('data_waznosci_elektrod'),
      dysponent_nazwa: val('dysponent_nazwa'), dysponent_regon: val('dysponent_regon').replace(/\D/g, ''),
      dysponent_telefon: phone(val('dysponent_telefon')),
      data_danych: today(), data_weryfikacji: today(),
    };
    return finalize(rec);
  }

  function finalize(rec) {
    rec.klasa_dostepnosci = classify(rec);
    rec.zrodla = rec.zrodla || 'dysponent';
    rec.zrodlo_id = rec.zrodlo_id || `dysponent:${rec.id}`;
    rec.zrodlo_licencja = $('licencja').value === 'CC BY 4.0' ? 'CC-BY-4.0' : 'CC0-1.0';
    return rec;
  }

  function toForm(rec) {
    for (const f of schema.fields) {
      const el = $(f.name);
      if (!el) continue;
      if (el.type === 'checkbox') el.checked = rec[f.name] === 'true';
      else el.value = rec[f.name] || '';
    }
    geo = { kod_terc: rec.kod_terc, kod_simc: rec.kod_simc, kod_ulic: rec.kod_ulic };
    osmToEditor(rec.godziny_dostepnosci);
    if (rec.szerokosc_geo) setPoint([Number(rec.szerokosc_geo), Number(rec.dlugosc_geo)], 18);
  }

  // ------------------------------------------------------------------ lista
  const ACCESS_PL = { '24h_pewny': 'całą dobę', '24h_wnioskowany': 'prawdopodobnie całą dobę', godziny: 'w godzinach', nieznany: 'brak informacji', prywatny: 'niepubliczny' };

  function renderList() {
    $('count').textContent = records.length;
    const tbody = $('list');
    tbody.textContent = '';
    for (const r of records) {
      const tr = document.createElement('tr');
      const td = (text) => { const c = document.createElement('td'); c.textContent = text; return c; };
      const actions = document.createElement('td');
      const edit = Object.assign(document.createElement('button'), { type: 'button', className: 'btn btn-link', textContent: 'Edytuj' });
      edit.setAttribute('aria-label', `Edytuj: ${r.nazwa_obiektu}`);
      edit.addEventListener('click', () => { editingId = r.id; toForm(r); $('btn-add').textContent = 'Zapisz zmiany'; $('nazwa_obiektu').focus(); });
      const del = Object.assign(document.createElement('button'), { type: 'button', className: 'btn btn-link', textContent: 'Usuń' });
      del.setAttribute('aria-label', `Usuń: ${r.nazwa_obiektu}`);
      del.addEventListener('click', () => { records = records.filter((x) => x.id !== r.id); save(); renderList(); });
      actions.append(edit, ' ', del);
      tr.append(td(r.nazwa_obiektu), td([r.ulica_cecha, r.ulica_nazwa, r.nr_budynku, r.miejscowosc].filter(Boolean).join(' ')),
        td(`${ACCESS_PL[r.klasa_dostepnosci]}${r.godziny_dostepnosci && r.godziny_dostepnosci !== '24/7' ? ` (${r.godziny_dostepnosci})` : ''}`), actions);
      tbody.append(tr);
    }
  }

  function showErrors(errors) {
    const box = $('form-errors');
    box.hidden = !errors.length;
    box.textContent = '';
    if (!errors.length) return;
    const p = document.createElement('p');
    p.textContent = 'Popraw dane:';
    const ul = document.createElement('ul');
    errors.forEach((e) => { const li = document.createElement('li'); li.textContent = e; ul.append(li); });
    box.append(p, ul);
  }

  // ------------------------------------------------------------------ CSV
  function parseCsv(text) {
    const rows = [];
    let row = [], cell = '', quoted = false;
    const delim = (text.split('\n')[0].match(/;/g) || []).length > (text.split('\n')[0].match(/,/g) || []).length ? ';' : ',';
    for (let i = 0; i < text.length; i += 1) {
      const ch = text[i];
      if (quoted) {
        if (ch === '"' && text[i + 1] === '"') { cell += '"'; i += 1; } else if (ch === '"') quoted = false; else cell += ch;
      } else if (ch === '"') quoted = true;
      else if (ch === delim) { row.push(cell); cell = ''; }
      else if (ch === '\n' || ch === '\r') {
        if (ch === '\r' && text[i + 1] === '\n') i += 1;
        row.push(cell); rows.push(row); row = []; cell = '';
      } else cell += ch;
    }
    if (cell || row.length) { row.push(cell); rows.push(row); }
    return rows.filter((r) => r.some((c) => c.trim() !== ''));
  }

  const csvCell = (v) => { const s = v === undefined || v === null ? '' : String(v); return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  function toCsv(list) {
    const names = schema.fields.map((f) => f.name);
    return [names.join(','), ...list.map((r) => names.map((n) => csvCell(r[n])).join(','))].join('\r\n') + '\r\n';
  }

  function importCsv(text) {
    const rows = parseCsv(text.replace(/^\uFEFF/, ''));
    const report = $('import-report');
    report.textContent = '';
    if (rows.length < 2) { report.textContent = 'Plik jest pusty lub nie ma wierszy danych.'; return; }
    const header = rows[0].map((h) => h.trim());
    const known = new Set(schema.fields.map((f) => f.name));
    const unknownCols = header.filter((h) => !known.has(h));
    const missing = schema.fields.filter((f) => (f.constraints || {}).required && !['id', 'klasa_dostepnosci', 'zrodla', 'zrodlo_id', 'zrodlo_licencja', 'data_danych'].includes(f.name) && !header.includes(f.name));
    const ul = document.createElement('ul');
    const add = (msg) => { const li = document.createElement('li'); li.textContent = msg; ul.append(li); };
    if (unknownCols.length) add(`Kolumny spoza schematu (zostaną pominięte): ${unknownCols.join(', ')}`);
    if (missing.length) add(`Brak wymaganych kolumn: ${missing.map((f) => f.name).join(', ')}`);
    let ok = 0, bad = 0;
    rows.slice(1).forEach((cells, i) => {
      const rec = {};
      header.forEach((h, j) => { if (known.has(h)) rec[h] = (cells[j] || '').trim(); });
      rec.id = rec.id || (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${i}`);
      rec.data_danych = rec.data_danych || today();
      finalize(rec);
      const errors = validate(rec);
      if (errors.length) { bad += 1; add(`Wiersz ${i + 2}: ${errors.join('; ')}`); } else { ok += 1; records.push(rec); }
    });
    save();
    renderList();
    const summary = document.createElement('p');
    summary.textContent = `Wczytano ${ok} poprawnych rekordów${bad ? `, ${bad} z błędami (nie dodano – popraw plik i wczytaj ponownie)` : ''}.`;
    report.append(summary, ul);
  }

  // ------------------------------------------------------------------ eksport
  function download(name, content, type) {
    const blob = new Blob([content], { type });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.dataset.newTab = '1';
    document.body.append(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }
  function needRecords() {
    if (records.length) return true;
    $('export-status').textContent = 'Lista jest pusta – dodaj co najmniej jeden AED.';
    return false;
  }
  const slug = (s) => (s || 'instytucja').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/ł/g, 'l').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 24);

  function toGeoJson(list) {
    return JSON.stringify({
      type: 'FeatureCollection',
      features: list.map((r) => ({
        type: 'Feature', id: r.id,
        geometry: { type: 'Point', coordinates: [Number(r.dlugosc_geo), Number(r.szerokosc_geo)] },
        properties: Object.fromEntries(Object.entries(r).filter(([k, v]) => v !== '' && !['szerokosc_geo', 'dlugosc_geo'].includes(k))),
      })),
    }, null, 1);
  }

  function toXml(list) {
    const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const inst = list[0].dysponent_nazwa || 'Instytucja';
    const id = `aed-${slug(inst)}`.slice(0, 30);
    const url = $('csv-url').value.trim();
    const now = new Date().toISOString().replace(/\.\d+Z$/, 'Z');
    const licence = $('licencja').value;
    return `<?xml version="1.0" encoding="UTF-8"?>
<p:datasets xmlns:p="${NS}">
  <dataset status="published">
    <extIdent>${esc(id)}</extIdent>
    <title>
      <polish>${esc(`Defibrylatory AED – ${inst}`.slice(0, 300))}</polish>
      <english>${esc(`AED defibrillators – ${inst}`.slice(0, 300))}</english>
    </title>
    <description>
      <polish>${esc(`Lokalizacja i dostępność defibrylatorów AED, których dysponentem jest ${inst}. Dane zgodne ze wzorcowym zakresem danych HeartSpot.`.slice(0, 1000))}</polish>
      <english>${esc(`Location and availability of AED defibrillators managed by ${inst}.`.slice(0, 1000))}</english>
    </description>
    <updateFrequency>irregular</updateFrequency>
    <categories><category>HEAL</category></categories>
    <conditions>
      <source>${licence === 'CC BY 4.0'}</source>
      <modification>false</modification>
      <dbOrCopyrightedLicenseChosen>${licence}</dbOrCopyrightedLicenseChosen>
    </conditions>
    <resources>
      <resource status="published">
        <extIdent>${esc(`${id}-csv`)}</extIdent>
        <url>${esc(url)}</url>
        <title><polish>${esc(`Defibrylatory AED – ${inst} (CSV)`.slice(0, 300))}</polish><english>${esc(`AED – ${inst} (CSV)`.slice(0, 300))}</english></title>
        <description><polish>Wykaz AED w formacie CSV zgodnym ze wzorcowym zakresem danych HeartSpot.</polish><english>AED list in CSV format (HeartSpot data standard).</english></description>
        <availability>local</availability>
        <dataDate>${today()}</dataDate>
        <hasDynamicData>false</hasDynamicData>
        <hasHighValueData>false</hasHighValueData>
        <hasHighValueDataFromEuropeanCommissionList>false</hasHighValueDataFromEuropeanCommissionList>
        <hasResearchData>false</hasResearchData>
        <containsProtectedData>false</containsProtectedData>
      </resource>
    </resources>
    <tags><tag lang="pl">defibrylator</tag><tag lang="pl">AED</tag><tag lang="pl">HeartSpot</tag><tag lang="en">defibrillator</tag></tags>
    <lastUpdateDate>${now}</lastUpdateDate>
  </dataset>
</p:datasets>
`;
  }

  // ------------------------------------------------------------------ start
  async function main() {
    buildWeekEditor();
    initMap();
    renderList();
    try {
      schema = await (await fetch('dane/aed.schema.json', { cache: 'no-cache' })).json();
    } catch (e) {
      showErrors(['Nie udało się wczytać schematu danych – odśwież stronę.']);
      return;
    }
    $('btn-geocode').addEventListener('click', geocode);
    $('aed-form').addEventListener('submit', (ev) => {
      ev.preventDefault();
      const rec = fromForm();
      const errors = validate(rec);
      if (!point) errors.unshift('Położenie: wskaż AED na mapie lub użyj „Znajdź adres na mapie”');
      if (!rec.dysponent_nazwa) errors.push('Dysponent: pole wymagane');
      showErrors([...new Set(errors)]);
      if (errors.length) { $('form-errors').focus(); return; }
      records = records.filter((r) => r.id !== rec.id).concat(rec);
      save();
      renderList();
      editingId = null;
      $('btn-add').textContent = 'Dodaj do listy';
      const routable = ['24h_pewny', '24h_wnioskowany', 'godziny'].includes(rec.klasa_dostepnosci);
      $('add-status').textContent = routable
        ? `Dodano: ${rec.nazwa_obiektu}. Widać go już na mapie HeartSpot na tym urządzeniu (jako niezweryfikowany wpis).`
        : `Dodano: ${rec.nazwa_obiektu}. Uwaga: mapa nie poprowadzi do tego AED, bo ${rec.klasa_dostepnosci === 'prywatny' ? 'nie jest publicznie dostępny' : 'nie podano godzin dostępności ani 24/7 (zaznacz godziny albo „Dostępny całą dobę”, a dla szafki na zewnątrz wybierz „na zewnątrz”)'}.`;
    });
    $('aed-form').addEventListener('reset', () => {
      editingId = null; point = null; geo = {};
      if (marker) { marker.remove(); marker = null; }
      $('coords-out').textContent = 'nie wskazano';
      $('btn-add').textContent = 'Dodaj do listy';
      setTimeout(() => osmToEditor(''), 0);
      showErrors([]);
    });
    $('csv-file').addEventListener('change', async (ev) => {
      const file = ev.target.files[0];
      if (file) importCsv(await file.text());
      ev.target.value = '';
    });
    $('dl-csv').addEventListener('click', () => {
      if (!needRecords()) return;
      records.forEach(finalize);
      download(`aed-${slug(records[0].dysponent_nazwa)}.csv`, toCsv(records), 'text/csv;charset=utf-8');
      $('export-status').textContent = `Pobrano CSV z ${records.length} rekordami.`;
    });
    $('dl-geojson').addEventListener('click', () => {
      if (!needRecords()) return;
      download(`aed-${slug(records[0].dysponent_nazwa)}.geojson`, toGeoJson(records), 'application/geo+json');
    });
    $('dl-xml').addEventListener('click', () => {
      if (!needRecords()) return;
      const url = $('csv-url').value.trim();
      if (!/^https:\/\/.+/.test(url)) {
        $('export-status').textContent = 'Podaj adres https://…, pod którym opublikujesz plik CSV – jest wymagany przez dane.gov.pl.';
        $('csv-url').focus();
        return;
      }
      download(`danegov-import-${slug(records[0].dysponent_nazwa)}.xml`, toXml(records), 'application/xml');
      $('export-status').textContent = 'Pobrano plik importu dane.gov.pl.';
    });
  }

  main();
})();
