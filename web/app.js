/* Misja AED – najbliższy dostępny defibrylator i trasa piesza.
 * Dane: data/aed.json (generowane przez `aed run`), trasy: OSRM FOSSGIS (profil pieszy).
 * Zasada: prowadzimy tylko do AED dostępnych TERAZ (24/7, szafka zewnętrzna lub otwarte wg godzin). */
(() => {
  'use strict';

  const CFG = {
    dataUrl: 'data/aed.json',
    osrm: 'https://routing.openstreetmap.de/routed-foot',
    uug: 'https://services.gugik.gov.pl/uug/',
    nominatim: 'https://nominatim.openstreetmap.org/search',
    candidates: 6,          // ilu najbliższych (w linii prostej) porównujemy czasem dojścia
    preferCertainS: 60,     // AED „pewny 24/7” wygrywa z „wnioskowanym”, jeśli jest najwyżej o tyle dalej
    walkSpeed: 1.25,        // m/s – do szacunku, gdy serwis tras nie odpowiada
    detour: 1.3,            // współczynnik krętości trasy w szacunku
    farAwayM: 3000,
    requestTimeoutMs: 8000,
  };
  const COL = { lat: 0, lon: 1, klasa: 2, tydzien: 3, nazwa: 4, opis: 5, pietro: 6, wewnatrz: 7, godziny: 8, zrodla: 9, data: 10, id: 11, adres: 12 };
  const KLASY = [
    { label: 'Całodobowy', cls: 'k0', color: '#166534', fill: '#166534' },
    { label: 'Prawdopodobnie całodobowy', cls: 'k1', color: '#166534', fill: '#ffffff' },
    { label: 'Otwarty teraz', cls: 'k2', color: '#1d4ed8', fill: '#1d4ed8' },
  ];
  const SOURCE_NAMES = {
    osm: 'OpenStreetMap', um_warszawa: 'UM Warszawa (SCB)', legionowo: 'UM Legionowo', krosno: 'UM Krosno',
    marki: 'UM Marki', przemysl: 'UM Przemyśl', sopot: 'UM Sopot', inpost: 'InPost', lodz: 'UM Łódź',
    gdansk: 'UM Gdańsk', krakow_zpgis: 'UM Kraków', krakow_arcgis_prywatne: 'ArcGIS Kraków',
  };
  const DAY_PL = { Mo: 'pon.', Tu: 'wt.', We: 'śr.', Th: 'czw.', Fr: 'pt.', Sa: 'sob.', Su: 'niedz.' };
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const $ = (id) => document.getElementById(id);
  let data = null;
  let map, markersLayer, meMarker, routeLine, targetMarker;
  let origin = null;
  let scoredCache = [];
  let current = null;

  // ------------------------------------------------------------------ czas (Europe/Warsaw)
  function warsawNow(date = new Date()) {
    const parts = new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Europe/Warsaw', weekday: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
    }).formatToParts(date);
    const get = (t) => parts.find((p) => p.type === t).value;
    return { day: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].indexOf(get('weekday')), min: +get('hour') * 60 + +get('minute') };
  }
  const openInterval = (week, t) => (week || []).find(([d, s, e]) => d === t.day && s <= t.min && t.min < e) || null;

  function isOpenNow(row, t) {
    const k = row[COL.klasa];
    if (k === 0 || k === 1) return true;
    return !!openInterval(row[COL.tydzien], t);
  }

  /** Minuty do zamknięcia (z uwzględnieniem przedziałów przechodzących przez północ); Infinity dla 24/7. */
  function minutesUntilClose(row, t) {
    if (row[COL.klasa] !== 2) return Infinity;
    const week = row[COL.tydzien];
    const iv = openInterval(week, t);
    if (!iv) return 0;
    let until = iv[2] - t.min;
    let end = iv[2];
    let day = t.day;
    while (end === 1440) {
      const next = (day + 1) % 7;
      const nx = week.find(([d, s]) => d === next && s === 0);
      if (!nx) break;
      until += nx[2];
      end = nx[2];
      day = next;
      if (until > 7 * 1440) return Infinity;
    }
    return until;
  }
  const hhmm = (m) => `${String(Math.floor(m / 60) % 24).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
  const hoursPL = (osm) => osm.replace(/\b(Mo|Tu|We|Th|Fr|Sa|Su)\b/g, (d) => DAY_PL[d]).replace(/-/g, '–');

  // ------------------------------------------------------------------ geometria
  function haversine(lat1, lon1, lat2, lon2) {
    const R = 6371008.8, toRad = Math.PI / 180;
    const dp = (lat2 - lat1) * toRad, dl = (lon2 - lon1) * toRad;
    const h = Math.sin(dp / 2) ** 2 + Math.cos(lat1 * toRad) * Math.cos(lat2 * toRad) * Math.sin(dl / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
  }
  const GENERIC = 'Defibrylator AED';
  function displayName(row) {
    const name = row[COL.nazwa];
    if (name && name !== GENERIC) return name;
    if (row[COL.adres]) return `AED – ${row[COL.adres]}`;
    if (row[COL.opis]) return `AED – ${row[COL.opis].slice(0, 60)}`;
    return GENERIC;
  }
  const fmtDist = (m) => (m < 1000 ? `${Math.round(m / 10) * 10} m` : `${(m / 1000).toFixed(1).replace('.', ',')} km`);
  const fmtTime = (s) => `${Math.max(1, Math.round(s / 60))} min pieszo`;

  // ------------------------------------------------------------------ UI
  function setStatus(msg, isError = false) {
    const el = $('status');
    el.textContent = msg;
    el.classList.toggle('error', isError);
  }

  async function fetchJson(url, options = {}, timeoutMs = CFG.requestTimeoutMs) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const res = await fetch(url, { ...options, signal: ctrl.signal });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } finally {
      clearTimeout(timer);
    }
  }

  // ------------------------------------------------------------------ mapa
  function initMap() {
    map = L.map('map', { zoomControl: true, preferCanvas: true }).setView([52.07, 19.48], 6);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">współtwórcy OpenStreetMap</a> · trasy: FOSSGIS OSRM',
    }).addTo(map);
    markersLayer = L.layerGroup().addTo(map);
    map.on('zoomend', () => {
      const r = markerRadius();
      markersLayer.eachLayer((m) => m.setRadius(r));
    });
    map.on('click', (e) => setOrigin([e.latlng.lat, e.latlng.lng], 'wskazane na mapie'));
  }

  const markerRadius = () => { const z = map.getZoom(); return z < 9 ? 2 : z < 12 ? 4 : z < 15 ? 6 : 8; };

  function drawMarkers() {
    markersLayer.clearLayers();
    const t = warsawNow();
    const renderer = L.canvas({ padding: 0.3 });
    for (const row of data.rows) {
      if (!isOpenNow(row, t)) continue;
      const k = KLASY[row[COL.klasa]];
      L.circleMarker([row[COL.lat], row[COL.lon]], {
        renderer, radius: markerRadius(), color: k.color, weight: 2, fillColor: k.fill, fillOpacity: 0.95,
      }).bindTooltip(`${displayName(row)} – ${k.label}`).on('click', (e) => {
        L.DomEvent.stopPropagation(e);
        if (origin) selectTarget(scoreSingle(row));
      }).addTo(markersLayer);
    }
  }

  function showMe(latlng) {
    if (meMarker) meMarker.setLatLng(latlng);
    else {
      meMarker = L.marker(latlng, {
        icon: L.divIcon({ className: '', html: '<div class="me-marker"></div>', iconSize: [18, 18], iconAnchor: [9, 9] }),
        keyboard: false, title: 'Twoje położenie',
      }).addTo(map);
    }
  }

  // ------------------------------------------------------------------ trasy
  const lonlat = ([lat, lon]) => `${lon.toFixed(6)},${lat.toFixed(6)}`;

  async function osrmTable(from, rows) {
    const coords = [from, ...rows.map((r) => [r[COL.lat], r[COL.lon]])].map(lonlat).join(';');
    const j = await fetchJson(`${CFG.osrm}/table/v1/foot/${coords}?sources=0&annotations=duration,distance`);
    if (j.code !== 'Ok') throw new Error(j.code);
    return rows.map((row, i) => ({ row, duration: j.durations[0][i + 1], distance: j.distances[0][i + 1], approx: false }));
  }

  function estimate(from, row) {
    const d = haversine(from[0], from[1], row[COL.lat], row[COL.lon]) * CFG.detour;
    return { row, duration: d / CFG.walkSpeed, distance: d, approx: true };
  }

  async function osrmRoute(from, row) {
    const j = await fetchJson(`${CFG.osrm}/route/v1/foot/${lonlat(from)};${lonlat([row[COL.lat], row[COL.lon]])}?overview=full&geometries=geojson`);
    if (j.code !== 'Ok' || !j.routes.length) throw new Error(j.code);
    const r = j.routes[0];
    return { coords: r.geometry.coordinates.map(([x, y]) => [y, x]), duration: r.duration, distance: r.distance };
  }

  function decorate(s, t) {
    const arriveMin = Math.ceil(s.duration / 60);
    const left = minutesUntilClose(s.row, t);
    s.closesIn = left;
    s.closesBeforeArrival = left !== Infinity && left < arriveMin + 5;
    s.score = s.duration + (s.row[COL.klasa] === 1 ? CFG.preferCertainS : 0) + (s.closesBeforeArrival ? 3600 : 0);
    return s;
  }

  function scoreSingle(row) {
    const cached = scoredCache.find((s) => s.row === row);
    return cached || decorate(estimate(origin, row), warsawNow());
  }

  async function findNearest() {
    if (!data || !origin) return;
    setStatus('Szukam najbliższego dostępnego AED…');
    const t = warsawNow();
    const open = [];
    for (const row of data.rows) {
      if (isOpenNow(row, t)) open.push({ row, d: haversine(origin[0], origin[1], row[COL.lat], row[COL.lon]) });
    }
    if (!open.length) { setStatus('W danych nie ma teraz żadnego dostępnego AED.', true); return; }
    open.sort((a, b) => a.d - b.d);
    const nearest = open.slice(0, CFG.candidates).map((x) => x.row);

    let scored;
    try {
      scored = await osrmTable(origin, nearest);
      scored = scored.filter((s) => s.duration != null);
    } catch (e) {
      scored = nearest.map((row) => estimate(origin, row));
    }
    scored = scored.map((s) => decorate(s, t)).sort((a, b) => a.score - b.score);
    scoredCache = scored;
    await selectTarget(scored[0]);
    renderAlternatives(scored.slice(1, 4));
  }

  async function selectTarget(s) {
    current = s;
    renderResult(s);
    const row = s.row;
    const dest = [row[COL.lat], row[COL.lon]];
    if (targetMarker) targetMarker.remove();
    targetMarker = L.circleMarker(dest, { radius: 11, color: '#b91c1c', weight: 4, fillColor: '#fff', fillOpacity: 1 }).addTo(map);
    if (routeLine) routeLine.remove();
    let coords = [origin, dest];
    let approx = true;
    try {
      const r = await osrmRoute(origin, row);
      coords = [origin, ...r.coords, dest]; // trasa jest „przyciągana” do chodnika – domykamy do punktów
      approx = false;
      s.duration = r.duration;
      s.distance = r.distance;
      s.approx = false;
      renderResult(s);
    } catch (e) { /* zostaje linia prosta */ }
    routeLine = L.polyline(coords, { color: '#b91c1c', weight: 6, opacity: 0.9, dashArray: approx ? '8 10' : null }).addTo(map);
    map.fitBounds(L.latLngBounds([origin, dest, ...coords]), { padding: [40, 40], maxZoom: 18, animate: !reducedMotion });
    const far = s.distance > CFG.farAwayM ? ' Najbliższy dostępny AED jest daleko – jeśli ktoś nie oddycha, zacznij resuscytację i wezwij 112.' : '';
    setStatus(`Najbliższy dostępny AED: ${displayName(row)}, ${fmtTime(s.duration)}${approx ? ' (trasa orientacyjna)' : ''}.${far}`, !!far);
  }

  function renderResult(s) {
    const row = s.row;
    const k = KLASY[row[COL.klasa]];
    const t = warsawNow();
    $('result').hidden = false;
    $('result-time').textContent = (s.approx ? 'ok. ' : '') + fmtTime(s.duration);
    $('result-dist').textContent = `· ${fmtDist(s.distance)}`;
    $('result-name').textContent = displayName(row);
    const badge = $('result-badge');
    badge.className = `badge ${k.cls}`;
    badge.textContent = k.label;

    const where = [];
    if (row[COL.opis]) where.push(row[COL.opis]);
    if (row[COL.wewnatrz] === 1) where.push('wewnątrz budynku');
    if (row[COL.wewnatrz] === 0) where.push('na zewnątrz budynku');
    if (row[COL.pietro] !== null && row[COL.pietro] !== undefined) where.push(row[COL.pietro] === 0 ? 'parter' : `piętro ${row[COL.pietro]}`);
    $('result-where').textContent = where.join(' · ') || 'brak dokładniejszego opisu';
    $('result-address').textContent = row[COL.adres] || '—';

    let hours;
    if (row[COL.klasa] === 0) hours = 'Całą dobę (24/7)';
    else if (row[COL.klasa] === 1) hours = 'Brak podanych godzin – urządzenie na zewnątrz budynku, zwykle dostępne całą dobę';
    else hours = `${hoursPL(row[COL.godziny])} – otwarte teraz${s.closesIn !== Infinity ? `, do ${hhmm(t.min + s.closesIn)}` : ''}`;
    $('result-hours').textContent = hours;

    const warn = $('result-warning');
    warn.hidden = !s.closesBeforeArrival;
    if (s.closesBeforeArrival) warn.textContent = `Uwaga: obiekt może zostać zamknięty, zanim dotrzesz (o ${hhmm(t.min + s.closesIn)}). Sprawdź inne AED poniżej.`;

    const sources = String(row[COL.zrodla]).split(';').map((x) => SOURCE_NAMES[x] || x).join(', ');
    $('result-source').textContent = `${sources}, dane z ${row[COL.data]}`;
    $('btn-navigate').href = `https://www.google.com/maps/dir/?api=1&origin=${origin[0]},${origin[1]}&destination=${row[COL.lat]},${row[COL.lon]}&travelmode=walking`;
  }

  function renderAlternatives(list) {
    const ol = $('alt-list');
    ol.textContent = '';
    $('alternatives').hidden = !list.length;
    for (const s of list) {
      const li = document.createElement('li');
      const btn = document.createElement('button');
      btn.type = 'button';
      const time = document.createElement('span');
      time.className = 'alt-time';
      time.textContent = `${s.approx ? 'ok. ' : ''}${fmtTime(s.duration)} · ${fmtDist(s.distance)}`;
      btn.append(time, document.createElement('br'), `${displayName(s.row)} – ${KLASY[s.row[COL.klasa]].label.toLowerCase()}`);
      btn.addEventListener('click', () => selectTarget(s));
      li.append(btn);
      ol.append(li);
    }
  }

  // ------------------------------------------------------------------ lokalizacja
  function setOrigin(latlng, how) {
    origin = latlng;
    showMe(latlng);
    setStatus(`Twoje położenie: ${how}. Szukam AED…`);
    findNearest();
  }

  function locate() {
    if (!('geolocation' in navigator)) {
      setStatus('Przeglądarka nie udostępnia lokalizacji. Wpisz adres lub kliknij na mapie.', true);
      return;
    }
    setStatus('Ustalam Twoją lokalizację…');
    navigator.geolocation.getCurrentPosition(
      (pos) => setOrigin([pos.coords.latitude, pos.coords.longitude], `GPS (±${Math.round(pos.coords.accuracy)} m)`),
      (err) => {
        const why = err.code === 1 ? 'Brak zgody na lokalizację.' : 'Nie udało się ustalić lokalizacji.';
        setStatus(`${why} Wpisz adres poniżej lub kliknij swoje położenie na mapie.`, true);
      },
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 30000 },
    );
  }

  async function geocode(q) {
    try {
      const j = await fetchJson(`${CFG.uug}?request=GetAddress&srid=4326&address=${encodeURIComponent(q)}`);
      const hit = j && j.results && j.results['1'];
      if (hit) return [parseFloat(hit.y), parseFloat(hit.x)];
    } catch (e) { /* zapasowo Nominatim */ }
    const j = await fetchJson(`${CFG.nominatim}?format=json&limit=1&countrycodes=pl&q=${encodeURIComponent(q)}`);
    if (j.length) return [parseFloat(j[0].lat), parseFloat(j[0].lon)];
    return null;
  }

  // ------------------------------------------------------------------ start
  async function main() {
    initMap();
    $('btn-relocate').addEventListener('click', locate);
    $('btn-center').addEventListener('click', () => {
      if (current) map.setView([current.row[COL.lat], current.row[COL.lon]], 18, { animate: !reducedMotion });
    });
    $('locate-form').addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const q = $('address').value.trim();
      if (!q) return;
      setStatus('Szukam adresu…');
      try {
        const ll = await geocode(q);
        if (ll) setOrigin(ll, q);
        else setStatus('Nie znaleziono adresu. Spróbuj „miejscowość, ulica numer” albo kliknij na mapie.', true);
      } catch (e) {
        setStatus('Wyszukiwarka adresów nie odpowiada. Kliknij swoje położenie na mapie.', true);
      }
    });

    const params = new URLSearchParams(window.location.search);
    const pLat = parseFloat(params.get('lat'));
    const pLon = parseFloat(params.get('lon'));
    if (Number.isFinite(pLat) && Number.isFinite(pLon)) {
      setOrigin([pLat, pLon], 'z adresu strony (tryb demo)');
    } else {
      locate(); // równolegle z pobieraniem danych
    }
    try {
      data = await fetchJson(CFG.dataUrl, { cache: 'no-cache' }, 60000);
    } catch (e) {
      setStatus('Nie udało się wczytać danych o AED. Odśwież stronę.', true);
      return;
    }
    drawMarkers();
    if (origin) findNearest();
  }

  main();
})();
