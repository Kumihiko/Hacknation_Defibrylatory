/* Wszystkie linki otwierają się w nowej karcie (również dodawane dynamicznie, np. atrybucja mapy).
 * Wyjątki: link „przejdź do treści”, tel:, kotwice na tej samej stronie i link do bieżącej strony.
 * Dla czytników ekranu dopisujemy informację o nowej karcie (WCAG – technika G201). */
(() => {
  'use strict';
  const NOTE = ' (otwiera się w nowej karcie)';

  function apply(a) {
    if (a.dataset.newTab) return;
    const href = a.getAttribute('href') || '';
    if (!href || href.startsWith('#') || href.startsWith('tel:') || href.startsWith('mailto:')) return;
    if (a.classList.contains('skip-link') || a.getAttribute('aria-current') === 'page') return;
    const url = new URL(href, window.location.href);
    if (url.origin === window.location.origin && url.pathname.replace(/index\.html$/, '') === window.location.pathname.replace(/index\.html$/, '')) return;
    a.dataset.newTab = '1';
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    if (a.hasAttribute('aria-label')) {
      a.setAttribute('aria-label', a.getAttribute('aria-label') + NOTE);
    } else {
      const note = document.createElement('span');
      note.className = 'visually-hidden';
      note.textContent = NOTE;
      a.append(note);
    }
  }

  const scan = (root) => root.querySelectorAll && root.querySelectorAll('a[href]').forEach(apply);
  scan(document);
  new MutationObserver((mutations) => {
    for (const m of mutations) {
      m.addedNodes.forEach((n) => {
        if (n.nodeType !== 1) return;
        if (n.matches && n.matches('a[href]')) apply(n);
        scan(n);
      });
    }
  }).observe(document.body, { childList: true, subtree: true });
})();
