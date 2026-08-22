// ── REDACTED.MEME — Pattern Blue Edition ──
'use strict';

const $ = (id) => document.getElementById(id);

// ── Copy CA to clipboard ──────────────────────────────────────────────────────

function copyCA() {
  const text = $('ca-text').textContent.trim();
  const done = () => {
    const confirmEl = $('copy-confirm');
    confirmEl.classList.add('show');
    setTimeout(() => confirmEl.classList.remove('show'), 2000);
    const btn = $('copy-btn');
    btn.textContent = 'COPIED';
    setTimeout(() => (btn.textContent = 'COPY'), 2000);
  };
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(done).catch(() => legacyCopy(text, done));
  } else {
    legacyCopy(text, done);
  }
}

function legacyCopy(text, done) {
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.select();
  try {
    document.execCommand('copy');
  } catch (e) {
    /* nothing else to try */
  }
  document.body.removeChild(ta);
  done();
}

// ── Navigation ────────────────────────────────────────────────────────────────

const toggle = $('nav-toggle');
const navLinks = $('nav-links');

if (toggle && navLinks) {
  toggle.addEventListener('click', () => {
    const open = navLinks.classList.toggle('open');
    toggle.setAttribute('aria-expanded', String(open));
    document.body.classList.toggle('nav-open', open);
  });
}

if (navLinks) {
  navLinks.querySelectorAll('a').forEach((a) => {
    a.addEventListener('click', () => {
      navLinks.classList.remove('open');
      document.body.classList.remove('nav-open');
      if (toggle) toggle.setAttribute('aria-expanded', 'false');
    });
  });
}

// SYSTEMS dropdown — hover-opened on pointer devices via CSS, click-toggled everywhere.
const systemsBtn = $('systems-btn');
const systemsLi = systemsBtn && systemsBtn.parentElement;

if (systemsBtn && systemsLi) {
  systemsBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    const open = systemsLi.classList.toggle('open');
    systemsBtn.setAttribute('aria-expanded', String(open));
  });
  document.addEventListener('click', () => {
    systemsLi.classList.remove('open');
    systemsBtn.setAttribute('aria-expanded', 'false');
  });
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    systemsLi.classList.remove('open');
    systemsBtn.setAttribute('aria-expanded', 'false');
    if (navLinks) navLinks.classList.remove('open');
    document.body.classList.remove('nav-open');
    if (toggle) toggle.setAttribute('aria-expanded', 'false');
  });
}

// Nav border darkens once scrolled off the hero.
const nav = $('nav');
if (nav) {
  const onScroll = () => nav.classList.toggle('scrolled', window.scrollY > 40);
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
}

// ── Reveal on scroll ──────────────────────────────────────────────────────────
// The hidden state is applied by JS, never in the stylesheet, so a page with JS
// disabled or broken renders every section at full opacity.

function initReveal() {
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduced || !('IntersectionObserver' in window)) return;

  const els = document.querySelectorAll('section, .agent-card, .phil-card, .sys-link');
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((e) => {
        if (!e.isIntersecting) return;
        e.target.classList.add('revealed');
        observer.unobserve(e.target);
      });
    },
    { threshold: 0.08 }
  );

  els.forEach((el) => {
    // The hero is visible immediately; anything still hidden (the live sections,
    // before their data lands) would be observed with no box and never fire.
    if (el.id === 'hero' || el.hidden) return;
    el.classList.add('reveal');
    observer.observe(el);
  });
}

// ── Agent roster ──────────────────────────────────────────────────────────────
// data/agents.json is the source of truth. The HTML already carries the same cards
// as a fallback, so a failed fetch simply leaves them in place.

function renderAgents(data) {
  const grid = $('agents-grid');
  if (!grid || !data || !Array.isArray(data.agents) || !data.agents.length) return;

  const frag = document.createDocumentFragment();
  data.agents.forEach((a) => {
    const card = document.createElement('div');
    card.className = 'agent-card ' + String(a.tier || '').toLowerCase();
    card.dataset.agent = a.id || '';

    const tier = document.createElement('div');
    tier.className = 'agent-tier';
    tier.textContent = a.tier || '';
    if (a.live) {
      const dot = document.createElement('span');
      dot.className = 'agent-live';
      dot.title = 'Live on the mesh';
      dot.textContent = '●';
      tier.append(' ', dot);
    }

    const name = document.createElement('h3');
    name.textContent = a.name || a.id || '';

    const desc = document.createElement('p');
    desc.textContent = a.desc || '';

    const meta = document.createElement('div');
    meta.className = 'agent-meta';
    [a.host, a.stack].forEach((v) => {
      if (!v) return;
      const span = document.createElement('span');
      span.textContent = v;
      meta.appendChild(span);
    });

    const dim = document.createElement('div');
    dim.className = 'agent-dim';
    dim.textContent = a.dimension || '';

    card.append(tier, name, desc, meta, dim);
    frag.appendChild(card);
  });

  grid.replaceChildren(frag);

  const intro = document.querySelector('.swarm-intro p');
  if (intro && data.summary) intro.textContent = data.summary;
}

// ── Live market readout (Dexscreener) ─────────────────────────────────────────

const CA = '9mtKd1o8Ht7F1daumKgs5D8EdVyopWBfYQwNmMojpump';

function usd(n) {
  if (!isFinite(n)) return null;
  if (n >= 1e9) return '$' + (n / 1e9).toFixed(2) + 'B';
  if (n >= 1e6) return '$' + (n / 1e6).toFixed(2) + 'M';
  if (n >= 1e3) return '$' + (n / 1e3).toFixed(1) + 'K';
  return '$' + n.toFixed(0);
}

function price(n) {
  if (!isFinite(n) || n <= 0) return null;
  if (n >= 1) return '$' + n.toFixed(4);
  // Sub-dollar: four significant figures beats a row of leading zeroes.
  return '$' + n.toPrecision(4);
}

function loadMarket() {
  const strip = $('market-strip');
  if (!strip) return;

  fetch('https://api.dexscreener.com/latest/dex/tokens/' + CA, { cache: 'no-store' })
    .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then((data) => {
      const pairs = (data && data.pairs) || [];
      if (!pairs.length) throw new Error('no pairs');
      // Deepest pool is the honest quote.
      const p = pairs.reduce((best, cur) =>
        ((cur.liquidity && cur.liquidity.usd) || 0) > ((best.liquidity && best.liquidity.usd) || 0)
          ? cur
          : best
      );

      const set = (id, val) => {
        const el = $(id);
        if (el && val) el.textContent = val;
      };
      set('mk-price', price(parseFloat(p.priceUsd)));
      set('mk-liq', usd(p.liquidity && p.liquidity.usd));
      set('mk-vol', usd(p.volume && p.volume.h24));
      set('mk-mcap', usd(p.marketCap != null ? p.marketCap : p.fdv));

      const chg = p.priceChange && parseFloat(p.priceChange.h24);
      const chgEl = $('mk-change');
      if (chgEl && isFinite(chg)) {
        chgEl.textContent = (chg > 0 ? '+' : '') + chg.toFixed(2) + '%';
        chgEl.classList.add(chg < 0 ? 'neg' : 'pos');
      }

      if (p.url) $('mk-src').href = p.url;
      strip.hidden = false;
    })
    .catch(() => {
      strip.hidden = true;
    });
}

// ── Live mesh status ──────────────────────────────────────────────────────────
// Served by our own origin (serve.py proxies the swarm's status endpoint). An
// unreachable or unconfigured endpoint returns {"agents": []} and the whole
// section stays hidden — better silence than a wall of OFFLINE.

function renderStatus(data) {
  const section = $('status');
  const grid = $('status-grid');
  if (!section || !grid) return;

  const agents = (data && data.agents) || [];
  if (!agents.length) {
    section.hidden = true;
    return;
  }

  const frag = document.createDocumentFragment();
  agents.forEach((a) => {
    const li = document.createElement('li');
    li.className = 'status-row ' + (a.online ? 'online' : 'offline');

    const dot = document.createElement('span');
    dot.className = 'status-dot';
    dot.setAttribute('aria-hidden', 'true');
    dot.textContent = '●';

    const name = document.createElement('span');
    name.className = 'status-name';
    name.textContent = a.label || a.id;

    const state = document.createElement('span');
    state.className = 'status-state';
    state.textContent = a.online ? 'ONLINE' : 'OFFLINE';

    const seen = document.createElement('span');
    seen.className = 'status-seen';
    seen.textContent = a.last_seen || '';

    li.append(dot, name, state, seen);
    frag.appendChild(li);
  });

  grid.replaceChildren(frag);

  const stamp = $('status-updated');
  if (stamp) stamp.textContent = new Date().toISOString().slice(11, 19) + 'Z';

  // This section appears only once its data lands, which can be either side of
  // initReveal. Either way it goes straight to visible rather than waiting on an
  // intersection that may never be re-evaluated after display:none.
  section.classList.remove('reveal');
  section.classList.add('revealed');
  section.hidden = false;
}

function loadStatus() {
  fetch('/api/swarm', { cache: 'no-store' })
    .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then(renderStatus)
    .catch(() => {
      const s = $('status');
      if (s) s.hidden = true;
    });
}

// ── Boot ──────────────────────────────────────────────────────────────────────

fetch('data/agents.json', { cache: 'no-store' })
  .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
  .then(renderAgents)
  .catch(() => {
    /* server-rendered cards stand */
  })
  .finally(initReveal);

loadMarket();
setInterval(loadMarket, 120000);

loadStatus();
setInterval(loadStatus, 60000);
