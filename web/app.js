/* HeartSpot – najbliższy dostępny defibrylator i trasa piesza.
 * Dane: data/aed.json (generowane przez `aed run`), trasy: OSRM FOSSGIS (profil pieszy).
 * Zasada: prowadzimy tylko do AED dostępnych TERAZ (24/7, szafka zewnętrzna lub otwarte wg godzin). */
(() => {
  'use strict';

  const CFG = {
    dataUrl: 'data/aed.json',
    osrm: 'https://routing.openstreetmap.de/routed-foot',
    brouter: 'https://brouter.de/brouter',
    routeTimeoutMs: 4000,          // po tym czasie przechodzimy na zapasowy serwis tras
    providerCooldownMs: 5 * 60 * 1000,
    uug: 'https://services.gugik.gov.pl/uug/',
    nominatim: 'https://nominatim.openstreetmap.org/search',
    candidates: 6,          // ilu najbliższych (w linii prostej) porównujemy czasem dojścia
    preferCertainS: 60,     // AED „pewny 24/7” wygrywa z „wnioskowanym”, jeśli jest najwyżej o tyle dalej
    walkSpeed: 1.25,        // m/s – do szacunku, gdy serwis tras nie odpowiada
    detour: 1.3,            // współczynnik krętości trasy w szacunku
    farAwayM: 3000,
    poorAccuracyM: 1000,     // gorsza dokładność = ostrzeżenie (to nie jest GPS)
    goodAccuracyM: 30,       // przy takiej dokładności kończymy nasłuch
    locateWatchMs: 10000,    // jak długo poprawiamy położenie kolejnymi odczytami GPS
    slowFixHintMs: 3000,     // po tym czasie bez odczytu podpowiadamy wpisanie adresu
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
    danegov: 'dane.gov.pl (dysponent)', dysponent: 'Twój wpis z „Dodaj AED” (niezweryfikowany, tylko na tym urządzeniu)',
  };
  const DRAFT_KEY = 'heartspot-dodaj-szkic'; // szkic z zakładki „Dodaj AED” (ten sam origin)
  const KLASA_CODE = { '24h_pewny': 0, '24h_wnioskowany': 1, godziny: 2 };
  const DAY_PL = { Mo: 'pon.', Tu: 'wt.', We: 'śr.', Th: 'czw.', Fr: 'pt.', Sa: 'sob.', Su: 'niedz.' };
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const $ = (id) => document.getElementById(id);
  let data = null;
  let map, markersLayer, meMarker, routeLine, targetMarker;
  let origin = null;
  let scoredCache = [];
  let current = null;
  let searchGen = 0;   // numer bieżącego wyszukiwania – odrzucamy spóźnione odpowiedzi
  let routeGen = 0;    // numer bieżącej trasy

  function clearRoute() {
    routeGen += 1;
    if (routeLine) { routeLine.remove(); routeLine = null; }
    if (targetMarker) { targetMarker.remove(); targetMarker = null; }
  }

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
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">współtwórcy OpenStreetMap</a> · trasy: OSRM (FOSSGIS), BRouter',
    }).addTo(map);
    markersLayer = L.layerGroup().addTo(map);
    map.on('zoomend', () => {
      const r = markerRadius();
      markersLayer.eachLayer((m) => m.setRadius(r));
    });
    map.on('click', (e) => { stopWatch(); showAccuracyWarning(0); setOrigin([e.latlng.lat, e.latlng.lng], 'wskazane na mapie'); });
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
  // Dostawcy tras: OSRM FOSSGIS (profil pieszy, macierz czasów), zapasowo BRouter (profil pieszy).
  // Gdy OSRM nie odpowiada, przez kilka minut omijamy go od razu, żeby nie czekać na każdy timeout.
  const lonlat = ([lat, lon]) => `${lon.toFixed(6)},${lat.toFixed(6)}`;
  let osrmDownUntil = 0;
  const osrmAvailable = () => Date.now() > osrmDownUntil;
  const markOsrmDown = () => { osrmDownUntil = Date.now() + CFG.providerCooldownMs; };

  async function osrmTable(from, rows) {
    const coords = [from, ...rows.map((r) => [r[COL.lat], r[COL.lon]])].map(lonlat).join(';');
    const j = await fetchJson(`${CFG.osrm}/table/v1/foot/${coords}?sources=0&annotations=duration,distance`, {}, CFG.routeTimeoutMs);
    if (j.code !== 'Ok') throw new Error(j.code);
    return rows.map((row, i) => ({ row, duration: j.durations[0][i + 1], distance: j.distances[0][i + 1], approx: false }));
  }

  async function osrmRoute(from, row) {
    const j = await fetchJson(`${CFG.osrm}/route/v1/foot/${lonlat(from)};${lonlat([row[COL.lat], row[COL.lon]])}?overview=full&geometries=geojson`, {}, CFG.routeTimeoutMs);
    if (j.code !== 'Ok' || !j.routes.length) throw new Error(j.code);
    const r = j.routes[0];
    return { coords: r.geometry.coordinates.map(([x, y]) => [y, x]), duration: r.duration, distance: r.distance };
  }

  async function brouterRoute(from, row) {
    const url = `${CFG.brouter}?lonlats=${lonlat(from)}|${lonlat([row[COL.lat], row[COL.lon]])}&profile=hiking-mountain&alternativeidx=0&format=geojson`;
    const j = await fetchJson(url, {}, CFG.routeTimeoutMs + 2000);
    const f = j.features && j.features[0];
    if (!f) throw new Error('brak trasy');
    const distance = Number(f.properties['track-length']);
    return { coords: f.geometry.coordinates.map(([x, y]) => [y, x]), distance, duration: distance / CFG.walkSpeed };
  }

  /** Trasa piesza: OSRM, a gdy nie działa – BRouter. Rzuca wyjątek, gdy oba zawiodą. */
  async function walkingRoute(from, row) {
    if (osrmAvailable()) {
      try { return await osrmRoute(from, row); } catch (e) { markOsrmDown(); }
    }
    return brouterRoute(from, row);
  }

  /** Czasy dojścia do kandydatów: macierz OSRM albo trasy BRouter dla kilku najbliższych. */
  async function walkingTimes(from, rows) {
    if (osrmAvailable()) {
      try {
        return (await osrmTable(from, rows)).filter((s) => s.duration != null);
      } catch (e) { markOsrmDown(); }
    }
    const top = rows.slice(0, 3);
    const results = await Promise.allSettled(top.map((row) => brouterRoute(from, row)));
    const ok = results.map((r, i) => (r.status === 'fulfilled' ? { row: top[i], duration: r.value.duration, distance: r.value.distance, approx: false, route: r.value } : null)).filter(Boolean);
    if (!ok.length) throw new Error('brak tras');
    return ok;
  }

  function estimate(from, row) {
    const d = haversine(from[0], from[1], row[COL.lat], row[COL.lon]) * CFG.detour;
    return { row, duration: d / CFG.walkSpeed, distance: d, approx: true };
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
    const gen = ++searchGen;
    const from = origin;
    const t = warsawNow();
    const open = [];
    for (const row of data.rows) {
      if (isOpenNow(row, t)) open.push({ row, d: haversine(from[0], from[1], row[COL.lat], row[COL.lon]) });
    }
    if (!open.length) { setStatus('W danych nie ma teraz żadnego dostępnego AED.', true); return; }
    open.sort((a, b) => a.d - b.d);
    const nearest = open.slice(0, CFG.candidates).map((x) => x.row);

    // 1) natychmiast: najlepszy wg szacunku z odległości – użytkownik od razu widzi cel
    let scored = nearest.map((row) => decorate(estimate(from, row), t)).sort((a, b) => a.score - b.score);
    scoredCache = scored;
    selectTarget(scored[0]);
    renderAlternatives(scored.slice(1, 4));

    // 2) doprecyzowanie rzeczywistymi czasami dojścia pieszo
    let refined;
    try { refined = await walkingTimes(from, nearest); } catch (e) { return; }
    if (gen !== searchGen) return; // w międzyczasie zmieniono lokalizację
    refined = refined.map((s) => decorate(s, t)).sort((a, b) => a.score - b.score);
    const rest = scored.filter((s) => !refined.some((r) => r.row === s.row));
    scored = [...refined, ...rest];
    scoredCache = scored;
    if (current && scored[0].row !== current.row) selectTarget(scored[0]);
    renderAlternatives(scored.slice(1, 4));
  }

  async function selectTarget(s) {
    clearRoute();
    const gen = routeGen;
    const from = origin;
    current = s;
    const row = s.row;
    const dest = [row[COL.lat], row[COL.lon]];
    targetMarker = L.circleMarker(dest, { radius: 11, color: '#b91c1c', weight: 4, fillColor: '#fff', fillOpacity: 1 }).addTo(map);

    const draw = (coords, approx) => {
      if (routeLine) routeLine.remove();
      routeLine = L.polyline(coords, { color: '#b91c1c', weight: 6, opacity: 0.9, dashArray: approx ? '8 10' : null }).addTo(map);
      routeLine.bringToBack();
      const far = s.distance > CFG.farAwayM ? ' Najbliższy dostępny AED jest daleko – jeśli ktoś nie oddycha, zacznij resuscytację i wezwij 112.' : '';
      setStatus(`Najbliższy dostępny AED: ${displayName(row)}, ${s.approx ? 'ok. ' : ''}${fmtTime(s.duration)}${approx ? ' (trasa orientacyjna – wyznaczam dokładną…)' : ''}.${far}`, !!far);
    };

    // od razu: linia prosta (orientacyjna), żeby nie czekać na serwer tras
    renderResult(s);
    draw([from, dest], true);
    map.fitBounds(L.latLngBounds([from, dest]), { padding: [60, 60], maxZoom: 18, animate: !reducedMotion });

    try {
      const r = s.route || await walkingRoute(from, row);
      if (gen !== routeGen) return; // użytkownik wybrał w międzyczasie inny cel lub lokalizację
      s.duration = r.duration;
      s.distance = r.distance;
      s.approx = false;
      renderResult(s);
      const coords = [from, ...r.coords, dest]; // trasa jest „przyciągana” do chodnika – domykamy do punktów
      draw(coords, false);
      map.fitBounds(L.latLngBounds(coords), { padding: [40, 40], maxZoom: 18, animate: !reducedMotion });
    } catch (e) {
      if (gen !== routeGen) return;
      setStatus(`Najbliższy dostępny AED: ${displayName(row)}, ok. ${fmtTime(s.duration)}. Serwis tras nie odpowiada – pokazujemy kierunek w linii prostej.`);
    }
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
    $('loc-line').hidden = false;
    $('loc-text').textContent = how;
    clearRoute();
    scoredCache = [];
    $('alternatives').hidden = true;
    showMe(latlng);
    setStatus(`Twoje położenie: ${how}. Szukam AED…`);
    findNearest();
  }

  // Telefon często najpierw podaje przybliżone położenie (z sieci komórkowej / IP – potrafi być 300 km obok),
  // a dopiero po chwili GPS. Dlatego nasłuchujemy kolejnych odczytów i bierzemy dokładniejsze.
  let watchId = null;
  let bestFix = null;
  let locateSession = 0; // odczyty z zakończonej sesji (np. po ręcznym wskazaniu miejsca) są ignorowane
  function stopWatch() {
    locateSession += 1;
    if (watchId !== null) { navigator.geolocation.clearWatch(watchId); watchId = null; }
  }

  function showAccuracyWarning(accuracy) {
    const el = $('loc-warning');
    if (!accuracy || accuracy <= CFG.poorAccuracyM) { el.hidden = true; return; }
    el.hidden = false;
    el.textContent = `Lokalizacja jest niedokładna (±${fmtDist(accuracy)}) – telefon podał przybliżone położenie zamiast GPS, `
      + 'więc wynik może być w złym miejscu (często przez sieć Wi-Fi lub operatora). Włącz w telefonie lokalizację (GPS) '
      + 'i dla przeglądarki zgodę na „dokładną lokalizację”, potem kliknij „Użyj mojej lokalizacji”. '
      + 'Najszybciej: wpisz adres poniżej lub kliknij swoje położenie na mapie.';
  }

  function locate() {
    if (!('geolocation' in navigator)) {
      setStatus('Przeglądarka nie udostępnia lokalizacji. Wpisz adres lub kliknij na mapie.', true);
      return;
    }
    stopWatch();
    bestFix = null;
    const session = locateSession;
    const started = Date.now();
    setStatus('Ustalam Twoją lokalizację…');

    let haveGpsFix = false;
    const onFix = (pos, fromGps) => {
      if (session !== locateSession) return;
      if (!fromGps && haveGpsFix) return; // szybki odczyt sieciowy nie nadpisuje odczytu z GPS
      const acc = pos.coords.accuracy;
      const ll = [pos.coords.latitude, pos.coords.longitude];
      if (bestFix) {
        const moved = haversine(ll[0], ll[1], bestFix.coords.latitude, bestFix.coords.longitude);
        // odczyty sprzeczne (np. Wi-Fi „±20 m” w innym mieście vs GPS) – ufamy odczytowi z GPS
        const inconsistent = moved > 3 * (acc + bestFix.coords.accuracy) + 200;
        const moreAccurate = acc < bestFix.coords.accuracy * 0.6;
        if (!(fromGps && inconsistent) && !moreAccurate) return;
        if (!inconsistent && moved < Math.max(50, acc)) { bestFix = pos; showAccuracyWarning(acc); return; } // to samo miejsce
      }
      if (fromGps) haveGpsFix = true;
      bestFix = pos;
      const how = acc <= 150 ? `GPS (±${Math.round(acc)} m)` : `przybliżone (±${fmtDist(acc)})`;
      setOrigin(ll, how);
      showAccuracyWarning(acc);
      if (acc <= CFG.goodAccuracyM) stopWatch();
    };

    // 1) natychmiast: ostatnie znane / sieciowe położenie (zwykle < 1 s), żeby od razu pokazać AED
    navigator.geolocation.getCurrentPosition((pos) => onFix(pos, false), () => {}, { enableHighAccuracy: false, maximumAge: 120000, timeout: 2500 });
    // 2) równolegle GPS – jeśli przyjdzie dokładniejszy odczyt, poprawiamy położenie i trasę
    watchId = navigator.geolocation.watchPosition(
      (pos) => { onFix(pos, true); if (session === locateSession && Date.now() - started > CFG.locateWatchMs) stopWatch(); },
      (err) => {
        if (bestFix || session !== locateSession) return; // mamy już odczyt albo użytkownik wskazał miejsce sam
        stopWatch();
        const why = err.code === 1
          ? 'Brak zgody na lokalizację (sprawdź ustawienia strony w przeglądarce).'
          : 'Nie udało się ustalić lokalizacji – sprawdź, czy lokalizacja (GPS) jest włączona w telefonie.';
        setStatus(`${why} Wpisz adres poniżej lub kliknij swoje położenie na mapie.`, true);
      },
      { enableHighAccuracy: true, timeout: CFG.locateWatchMs, maximumAge: 0 },
    );
    setTimeout(() => { if (session === locateSession) stopWatch(); }, CFG.locateWatchMs);
    // 3) jeśli po chwili nadal nic – nie każemy czekać, podpowiadamy wpisanie adresu
    setTimeout(() => {
      if (!bestFix && session === locateSession) {
        setStatus('Wciąż szukam sygnału GPS… Jeśli się spieszysz, wpisz adres poniżej albo kliknij swoje położenie na mapie.', true);
      }
    }, CFG.slowFixHintMs);
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
    $('btn-wrong-loc').addEventListener('click', () => {
      stopWatch(); // nie pozwalamy, by spóźniony odczyt nadpisał poprawione położenie
      const input = $('address');
      input.scrollIntoView({ block: 'center', behavior: reducedMotion ? 'auto' : 'smooth' });
      input.focus();
      setStatus('Wpisz adres i naciśnij „Szukaj” albo kliknij swoje położenie na mapie.');
    });
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
        if (ll) { stopWatch(); showAccuracyWarning(0); setOrigin(ll, q); }
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
    baseRows = data.rows;
    mergeDrafts();
    drawMarkers();
    if (origin) findNearest();
    // AED dodany w innej karcie („Dodaj AED”) pojawia się od razu
    window.addEventListener('storage', (ev) => {
      if (ev.key !== DRAFT_KEY) return;
      mergeDrafts();
      drawMarkers();
      if (origin) findNearest();
    });
  }

  // ------------------------------------------------------------------ wpisy z „Dodaj AED” (localStorage)
  let baseRows = [];
  let draftInfo = [];

  /** "Mo-Fr 08:00-16:00; Sa 09:00-13:00" -> [[0,480,960],...,[5,540,780]] (format generowany przez „Dodaj AED”). */
  function osmToWeek(osm) {
    const codes = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'];
    const week = [];
    for (const rule of String(osm || '').split(';')) {
      const m = rule.trim().match(/^(\w\w)(?:-(\w\w))?\s+(.+)$/);
      if (!m) continue;
      const a = codes.indexOf(m[1]);
      const b = m[2] ? codes.indexOf(m[2]) : a;
      if (a < 0 || b < 0) continue;
      for (const span of m[3].split(',')) {
        const t = span.trim().match(/^(\d\d):(\d\d)-(\d\d):(\d\d)$/);
        if (!t) continue;
        const s = +t[1] * 60 + +t[2];
        const e = +t[3] * 60 + +t[4];
        for (let d = a; d <= b; d += 1) {
          if (e > s) week.push([d, s, e]);
          else { week.push([d, s, 1440]); week.push([(d + 1) % 7, 0, e]); }
        }
      }
    }
    return week;
  }

  function mergeDrafts() {
    let drafts = [];
    try { drafts = JSON.parse(localStorage.getItem(DRAFT_KEY)) || []; } catch (e) { drafts = []; }
    const rows = [];
    draftInfo = [];
    for (const r of drafts) {
      const klasa = KLASA_CODE[r.klasa_dostepnosci];
      const lat = Number(r.szerokosc_geo);
      const lon = Number(r.dlugosc_geo);
      const name = r.nazwa_obiektu || 'AED';
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) { draftInfo.push({ name, reason: 'brak współrzędnych – wskaż miejsce na mapie w „Dodaj AED”' }); continue; }
      if (klasa === undefined) {
        draftInfo.push({ name, reason: r.klasa_dostepnosci === 'prywatny'
          ? 'oznaczony jako niepubliczny / ograniczony dostęp'
          : 'brak godzin dostępności – zaznacz godziny lub „Dostępny całą dobę” (albo „na zewnątrz” dla szafki publicznej)' });
        continue;
      }
      const week = klasa === 2 ? osmToWeek(r.godziny_dostepnosci) : 0;
      if (klasa === 2 && !week.length) { draftInfo.push({ name, reason: `nie rozpoznano godzin „${r.godziny_dostepnosci}”` }); continue; }
      draftInfo.push({ name, row: null, week, klasa, hours: r.godziny_dostepnosci });
      const addr = [r.ulica_cecha, r.ulica_nazwa, r.nr_budynku].filter(Boolean).join(' ') + (r.miejscowosc ? `, ${r.miejscowosc}` : '');
      rows.push([lat, lon, klasa, week, r.nazwa_obiektu || 'Defibrylator AED', r.opis_lokalizacji || '',
        r.pietro === '' || r.pietro === undefined ? null : Number(r.pietro),
        r.wewnatrz_budynku === 'true' ? 1 : (r.wewnatrz_budynku === 'false' ? 0 : null),
        r.godziny_dostepnosci || '', 'dysponent', r.data_danych || '', r.id, addr]);
      draftInfo[draftInfo.length - 1].row = rows[rows.length - 1];
    }
    data.rows = baseRows.concat(rows);
    renderDraftNote();
  }

  /** Informacja na mapie o wpisach z „Dodaj AED”: które są uwzględniane, a które pominięte i dlaczego. */
  function renderDraftNote() {
    const box = $('drafts-note');
    if (!box) return;
    box.textContent = '';
    box.hidden = !draftInfo.length;
    if (!draftInfo.length) return;
    const t = warsawNow();
    const p = document.createElement('p');
    p.textContent = `Twoje wpisy z „Dodaj AED” (${draftInfo.length}):`;
    const ul = document.createElement('ul');
    for (const d of draftInfo) {
      const li = document.createElement('li');
      let text;
      if (!d.row) text = `${d.name} – pominięty: ${d.reason}.`;
      else if (!isOpenNow(d.row, t)) text = `${d.name} – teraz zamknięty wg godzin (${hoursPL(d.hours)}), dlatego trasa prowadzi do innego AED.`;
      else text = `${d.name} – na mapie, uwzględniany w wyznaczaniu trasy.`;
      li.textContent = text;
      ul.append(li);
    }
    box.append(p, ul);
  }

  main();
})();
