/* ==========================================================================
   AI Tools & Automation Directory — app.js
   Vanilla ES6+, no dependencies, no build step.
   ========================================================================== */

(function () {
  'use strict';

  const DATA_URL = 'data.json';
  const BOOKMARKS_KEY = 'aiToolsDirectory.bookmarks';
  const CATEGORY_ALL = 'All';
  const CATEGORY_SAVED = 'Saved';

  // ---- State ----------------------------------------------------------
  let allTools = [];
  let bookmarkedIds = loadBookmarks();
  let activeCategory = CATEGORY_ALL;
  let searchTerm = '';

  // ---- DOM refs ---------------------------------------------------------
  const els = {
    skeletonGrid: document.getElementById('skeletonGrid'),
    toolGrid: document.getElementById('toolGrid'),
    emptyState: document.getElementById('emptyState'),
    errorState: document.getElementById('errorState'),
    searchInput: document.getElementById('searchInput'),
    categoryPills: document.getElementById('categoryPills'),
    resultsCount: document.getElementById('resultsCount'),
    toolCountBadge: document.getElementById('toolCountBadge'),
    clearFiltersBtn: document.getElementById('clearFiltersBtn'),
    bookmarksToggle: document.getElementById('bookmarksToggle'),
    cardTemplate: document.getElementById('cardTemplate'),
    skeletonTemplate: document.getElementById('skeletonTemplate'),
    year: document.getElementById('year'),
  };

  // ---- Init ---------------------------------------------------------
  document.addEventListener('DOMContentLoaded', init);

  function init() {
    els.year.textContent = new Date().getFullYear();
    renderSkeletons(6);
    bindEvents();
    fetchTools();
  }

  function bindEvents() {
    els.searchInput.addEventListener('input', debounce((e) => {
      searchTerm = e.target.value.trim().toLowerCase();
      renderGrid();
    }, 120));

    els.clearFiltersBtn.addEventListener('click', () => {
      searchTerm = '';
      activeCategory = CATEGORY_ALL;
      els.searchInput.value = '';
      setActivePillUI();
      renderGrid();
    });

    els.bookmarksToggle.addEventListener('click', () => {
      activeCategory = activeCategory === CATEGORY_SAVED ? CATEGORY_ALL : CATEGORY_SAVED;
      setActivePillUI();
      renderGrid();
    });
  }

  // ---- Data fetching ---------------------------------------------------
  async function fetchTools() {
    try {
      const res = await fetch(DATA_URL, { cache: 'no-store' });
      if (!res.ok) throw new Error('Network response was not ok (' + res.status + ')');
      const data = await res.json();
      allTools = Array.isArray(data) ? data : [];
      // Featured tools first, otherwise preserve original order.
      allTools.sort((a, b) => Number(!!b.featured) - Number(!!a.featured));

      els.toolCountBadge.textContent = allTools.length;
      buildCategoryPills(allTools);
      renderGrid();

      els.skeletonGrid.classList.add('hidden');
      els.toolGrid.classList.remove('hidden');
    } catch (err) {
      console.error('Failed to load tools directory:', err);
      els.skeletonGrid.classList.add('hidden');
      els.errorState.classList.remove('hidden');
      els.errorState.classList.add('flex');
    }
  }

  // ---- Category pills ---------------------------------------------------
  function buildCategoryPills(tools) {
    const categories = [CATEGORY_ALL, ...uniqueSorted(tools.map((t) => t.category))];
    els.categoryPills.innerHTML = '';

    categories.forEach((cat) => {
      const pill = document.createElement('button');
      pill.type = 'button';
      pill.dataset.category = cat;
      pill.textContent = cat;
      pill.className = pillClasses(cat === activeCategory);
      pill.addEventListener('click', () => {
        activeCategory = cat;
        setActivePillUI();
        renderGrid();
      });
      els.categoryPills.appendChild(pill);
    });
  }

  function pillClasses(isActive) {
    const base = 'px-3.5 py-1.5 rounded-full text-sm font-medium border transition-colors';
    return isActive
      ? base + ' bg-gradient-to-r from-accent-indigo to-accent-violet text-white border-transparent shadow-glow'
      : base + ' bg-surface text-slate-400 border-border hover:text-slate-200 hover:border-slate-500';
  }

  function setActivePillUI() {
    [...els.categoryPills.children].forEach((pill) => {
      const isActive = pill.dataset.category === activeCategory;
      pill.className = pillClasses(isActive);
    });
    els.bookmarksToggle.classList.toggle('text-violet-300', activeCategory === CATEGORY_SAVED);
  }

  // ---- Filtering + rendering ---------------------------------------------------
  function getFilteredTools() {
    return allTools.filter((tool) => {
      const matchesCategory =
        activeCategory === CATEGORY_ALL ||
        (activeCategory === CATEGORY_SAVED && bookmarkedIds.has(String(tool.id))) ||
        tool.category === activeCategory;

      if (!matchesCategory) return false;
      if (!searchTerm) return true;

      const haystack = (
        (tool.name || '') + ' ' + (tool.description || '') + ' ' + (tool.category || '')
      ).toLowerCase();
      return haystack.includes(searchTerm);
    });
  }

  function renderGrid() {
    const filtered = getFilteredTools();

    els.resultsCount.textContent = filtered.length
      ? `${filtered.length} tool${filtered.length === 1 ? '' : 's'}`
      : '';

    els.toolGrid.innerHTML = '';

    if (!filtered.length) {
      els.toolGrid.classList.add('hidden');
      els.emptyState.classList.remove('hidden');
      els.emptyState.classList.add('flex');
      return;
    }

    els.emptyState.classList.add('hidden');
    els.emptyState.classList.remove('flex');
    els.toolGrid.classList.remove('hidden');

    const fragment = document.createDocumentFragment();
    filtered.forEach((tool) => fragment.appendChild(buildCard(tool)));
    els.toolGrid.appendChild(fragment);
  }

  function buildCard(tool) {
    const node = els.cardTemplate.content.cloneNode(true);
    const article = node.querySelector('article');

    node.querySelector('.tool-name').textContent = tool.name || 'Untitled tool';
    node.querySelector('.category-badge').textContent = tool.category || 'Uncategorized';
    node.querySelector('.tool-desc').textContent = tool.description || '';

    const tryBtn = node.querySelector('.try-btn');
    tryBtn.href = buildAffiliateUrl(tool.affiliate_link);

    const bookmarkBtn = node.querySelector('.bookmark-btn');
    const starIcon = node.querySelector('.star-icon');
    const isBookmarked = bookmarkedIds.has(String(tool.id));
    setBookmarkUI(bookmarkBtn, starIcon, isBookmarked);

    bookmarkBtn.addEventListener('click', () => toggleBookmark(tool.id, bookmarkBtn, starIcon));

    if (tool.featured) {
      const badge = document.createElement('span');
      badge.textContent = '★ Featured';
      badge.className =
        'absolute -top-2.5 left-4 text-[11px] font-mono font-medium tracking-wide px-2 py-0.5 rounded-full bg-amber-400/15 text-amber-300 border border-amber-400/30';
      article.appendChild(badge);
    }

    return node;
  }

  // ---- Affiliate link handling ---------------------------------------------------
  function buildAffiliateUrl(rawUrl, extraParams) {
    if (!rawUrl) return '#';
    try {
      const url = new URL(rawUrl);
      const params = extraParams || {}; // hook: inject dynamic affiliate params here if needed
      Object.entries(params).forEach(([key, value]) => url.searchParams.set(key, value));
      return url.toString();
    } catch (e) {
      return rawUrl; // fall back to raw string if it isn't a valid absolute URL
    }
  }

  // ---- Bookmarks (localStorage) ---------------------------------------------------
  function loadBookmarks() {
    try {
      const raw = localStorage.getItem(BOOKMARKS_KEY);
      return new Set(raw ? JSON.parse(raw) : []);
    } catch (e) {
      return new Set();
    }
  }

  function saveBookmarks() {
    try {
      localStorage.setItem(BOOKMARKS_KEY, JSON.stringify([...bookmarkedIds]));
    } catch (e) {
      console.warn('Could not persist bookmarks to localStorage:', e);
    }
  }

  function toggleBookmark(id, btn, iconEl) {
    const key = String(id);
    const isBookmarked = bookmarkedIds.has(key);
    if (isBookmarked) {
      bookmarkedIds.delete(key);
    } else {
      bookmarkedIds.add(key);
    }
    saveBookmarks();
    setBookmarkUI(btn, iconEl, !isBookmarked);

    if (activeCategory === CATEGORY_SAVED) renderGrid();
  }

  function setBookmarkUI(btn, iconEl, isBookmarked) {
    btn.setAttribute('aria-pressed', String(isBookmarked));
    btn.classList.toggle('text-amber-300', isBookmarked);
    btn.classList.toggle('border-amber-400/40', isBookmarked);
    iconEl.setAttribute('fill', isBookmarked ? 'currentColor' : 'none');
  }

  // ---- Loading skeletons ---------------------------------------------------
  function renderSkeletons(count) {
    const fragment = document.createDocumentFragment();
    for (let i = 0; i < count; i++) {
      fragment.appendChild(els.skeletonTemplate.content.cloneNode(true));
    }
    els.skeletonGrid.appendChild(fragment);
  }

  // ---- Utilities ---------------------------------------------------
  function uniqueSorted(arr) {
    return [...new Set(arr.filter(Boolean))].sort((a, b) => a.localeCompare(b));
  }

  function debounce(fn, wait) {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), wait);
    };
  }
})();
