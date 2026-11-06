// AI Tools Directory — vanilla JS, no build step.
(function () {
  'use strict';

  const PAGE = 50;
  const SAVED_KEY = 'aiToolsDirectory.bookmarks'; // same key as before, so old bookmarks survive
  const $ = (id) => document.getElementById(id);
  const els = { q: $('q'), cat: $('cat'), sort: $('sort'), saved: $('saved'), savedCount: $('savedCount'),
                list: $('list'), more: $('more'), status: $('status'), count: $('count'), tpl: $('item') };

  let tools = [];
  let results = [];
  let shown = 0;
  let saved = loadSaved();
  const state = { q: '', cat: '', sort: 'new', saved: false };

  // ---- data ---------------------------------------------------------------
  fetch('data.json', { cache: 'no-cache' })
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then((data) => {
      tools = data.map((t) => ({
        ...t,
        url: t.url || t.affiliate_link,
        // searchable text, lowercased once
        _name: (t.name || '').toLowerCase(),
        _text: [t.name, t.description, t.category, t.source].join(' ').toLowerCase(),
      }));
      els.count.textContent = tools.length.toLocaleString() + ' tools.';
      buildCategories();
      readUrl();
      update();
    })
    .catch(() => { els.status.textContent = 'Could not load the directory. Refresh to try again.'; });

  function buildCategories() {
    const counts = {};
    tools.forEach((t) => { counts[t.category] = (counts[t.category] || 0) + 1; });
    const cats = Object.keys(counts).sort((a, b) =>
      (a === 'Other') - (b === 'Other') || counts[b] - counts[a]);
    els.cat.innerHTML = '';
    els.cat.append(new Option(`All categories (${tools.length})`, ''));
    cats.forEach((c) => els.cat.append(new Option(`${c} (${counts[c]})`, c)));
  }

  // ---- search -------------------------------------------------------------
  // Every word must appear somewhere (name, description, category or source),
  // in any order. Name matches rank first.
  function search() {
    const words = state.q.toLowerCase().split(/\s+/).filter(Boolean);
    let list = tools.filter((t) =>
      (!state.cat || t.category === state.cat) &&
      (!state.saved || saved.has(String(t.id))) &&
      words.every((w) => t._text.includes(w)));

    const byNew = (a, b) => (b.added || '').localeCompare(a.added || '') || a._name.localeCompare(b._name);
    const byName = (a, b) => a._name.localeCompare(b._name);
    const base = state.sort === 'az' ? byName : byNew;

    if (words.length) {
      const score = (t) => words.reduce((s, w) =>
        s + (t._name.startsWith(w) ? 3 : t._name.includes(w) ? 2 : 0), 0);
      list = list.map((t) => [score(t), t]).sort((a, b) => b[0] - a[0] || base(a[1], b[1])).map((x) => x[1]);
    } else {
      list.sort(base);
    }
    return list;
  }

  function update() {
    results = search();
    shown = 0;
    els.list.innerHTML = '';
    renderMore();
    const n = results.length;
    els.status.textContent = n
      ? `${n.toLocaleString()} ${n === 1 ? 'tool' : 'tools'}`
      : state.saved && !saved.size ? 'Nothing saved yet. Use the bookmark icon on any tool.' : 'No tools match. Try fewer or different words.';
    els.savedCount.textContent = saved.size ? `(${saved.size})` : '';
    writeUrl();
  }

  function renderMore() {
    const frag = document.createDocumentFragment();
    results.slice(shown, shown + PAGE).forEach((t) => frag.append(row(t)));
    shown = Math.min(shown + PAGE, results.length);
    els.list.append(frag);
    els.more.hidden = shown >= results.length;
    els.more.textContent = `Show more (${(results.length - shown).toLocaleString()} left)`;
  }

  function row(t) {
    const li = els.tpl.content.firstElementChild.cloneNode(true);
    const a = li.querySelector('.name');
    a.textContent = t.name;
    a.href = safeUrl(t.url);
    li.querySelector('.desc').textContent = t.description || '';
    li.querySelector('.meta').textContent = [t.category, t.source, formatDate(t.added)].filter(Boolean).join(' · ');
    const btn = li.querySelector('.save');
    setSaved(btn, saved.has(String(t.id)));
    btn.addEventListener('click', () => toggleSave(t, btn));
    return li;
  }

  // ---- saved --------------------------------------------------------------
  function loadSaved() {
    try { return new Set(JSON.parse(localStorage.getItem(SAVED_KEY)) || []); } catch (e) { return new Set(); }
  }
  function toggleSave(t, btn) {
    const id = String(t.id);
    saved.has(id) ? saved.delete(id) : saved.add(id);
    try { localStorage.setItem(SAVED_KEY, JSON.stringify([...saved])); } catch (e) { /* private mode */ }
    setSaved(btn, saved.has(id));
    els.savedCount.textContent = saved.size ? `(${saved.size})` : '';
    if (state.saved) update();
  }
  function setSaved(btn, on) {
    btn.setAttribute('aria-pressed', String(on));
    btn.setAttribute('aria-label', on ? 'Remove from saved' : 'Save');
  }

  // ---- url state (so searches can be shared) -------------------------------
  function readUrl() {
    const p = new URLSearchParams(location.search);
    state.q = p.get('q') || '';
    state.cat = p.get('cat') || '';
    state.sort = p.get('sort') === 'az' ? 'az' : 'new';
    els.q.value = state.q;
    els.cat.value = state.cat;
    if (els.cat.value !== state.cat) state.cat = els.cat.value = '';
    els.sort.value = state.sort;
  }
  function writeUrl() {
    const p = new URLSearchParams();
    if (state.q) p.set('q', state.q);
    if (state.cat) p.set('cat', state.cat);
    if (state.sort !== 'new') p.set('sort', state.sort);
    const qs = p.toString();
    history.replaceState(null, '', qs ? '?' + qs : location.pathname);
  }

  // ---- helpers ------------------------------------------------------------
  function safeUrl(u) {
    try { const x = new URL(u); return /^https?:$/.test(x.protocol) ? x.href : '#'; } catch (e) { return '#'; }
  }
  function formatDate(d) {
    if (!d) return '';
    const dt = new Date(d + 'T00:00:00');
    return isNaN(dt) ? '' : dt.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  }
  function debounce(fn, ms) {
    let t;
    return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
  }

  // ---- events -------------------------------------------------------------
  els.q.addEventListener('input', debounce(() => { state.q = els.q.value.trim(); update(); }, 120));
  els.cat.addEventListener('change', () => { state.cat = els.cat.value; update(); });
  els.sort.addEventListener('change', () => { state.sort = els.sort.value; update(); });
  els.saved.addEventListener('click', () => {
    state.saved = !state.saved;
    els.saved.setAttribute('aria-pressed', String(state.saved));
    update();
  });
  els.more.addEventListener('click', renderMore);
  document.addEventListener('keydown', (e) => {
    if (e.key === '/' && document.activeElement !== els.q) { e.preventDefault(); els.q.focus(); }
  });
})();
