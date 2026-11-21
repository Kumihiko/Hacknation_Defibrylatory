(() => {
  'use strict';
  const CLASSES = {
    '24h_pewny': ['Całodobowy', 'Źródło jawnie podaje dostępność 24/7.'],
    '24h_wnioskowany': ['Prawdopodobnie całodobowy', 'Publiczny, na zewnątrz budynku, bez podanych godzin.'],
    godziny: ['Godziny', 'Znane godziny dostępności.'],
    nieznany: ['Nieznany', 'Brak informacji o dostępności – tu potrzebne są dane od dysponentów.'],
    prywatny: ['Prywatny / ograniczony', 'Niedostępny publicznie, wymaga zgody lub jest w pojeździe.'],
  };
  const nf = new Intl.NumberFormat('pl-PL');
  const el = (tag, text, attrs = {}) => {
    const e = document.createElement(tag);
    if (text !== undefined) e.textContent = text;
    Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v));
    return e;
  };

  function card(num, label) {
    const c = el('div', undefined, { class: 'card' });
    c.append(el('div', num, { class: 'num' }), el('div', label));
    return c;
  }

  fetch('dane/zrodla.json', { cache: 'no-cache' }).then((r) => r.json()).then((s) => {
    const z = s.zbior;
    const d = s.deduplikacja;
    const when = new Date(s.wygenerowano).toLocaleString('pl-PL', { timeZone: 'Europe/Warsaw' });
    document.getElementById('generated').textContent = `Ostatnia aktualizacja: ${when}`;
    document.getElementById('cards').append(
      card(nf.format(z.rekordow), 'defibrylatorów w zbiorze'),
      card(`${String(z.procent_z_godzinami).replace('.', ',')}%`, 'z informacją o godzinach lub 24/7'),
      card(nf.format(s.aplikacja_rekordow), 'AED, do których aplikacja może poprowadzić'),
      card(nf.format(d.polaczonych_klastrow), 'duplikatów połączonych między źródłami'),
    );

    const tbody = document.getElementById('sources');
    for (const src of s.zrodla) {
      const tr = el('tr');
      const name = el('td');
      const a = el('a', src.nazwa, { href: src.strona || src.url_danych });
      name.append(a, el('br'), el('span', src.wydawca, { class: 'muted' }));
      const st = src.statystyki;
      tr.append(
        name,
        el('td', src.licencja === 'NIEZNANA' ? 'do ustalenia' : src.licencja),
        el('td', st ? nf.format(st.rekordow) : '–'),
        el('td', st ? `${String(st.procent_z_godzinami).replace('.', ',')}%` : '–'),
        el('td', src.wlaczone ? 'w zbiorze' : 'czeka na potwierdzenie licencji'),
      );
      tbody.append(tr);
    }

    const cls = document.getElementById('classes');
    for (const [key, [label, desc]] of Object.entries(CLASSES)) {
      const tr = el('tr');
      tr.append(el('td', label), el('td', desc), el('td', nf.format(z.klasy_dostepnosci[key] || 0)));
      cls.append(tr);
    }
    const unknown = (z.klasy_dostepnosci.nieznany || 0);
    document.getElementById('unknown-count').textContent =
      `${nf.format(unknown)} AED nie ma informacji o dostępności – dlatego zachęcamy dysponentów do publikowania danych.`;

    const ul = document.getElementById('attribution');
    for (const src of s.zrodla.filter((x) => x.wlaczone)) ul.append(el('li', src.atrybucja));
  }).catch(() => {
    document.getElementById('generated').textContent = 'Nie udało się wczytać statystyk.';
  });
})();
