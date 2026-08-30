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

// Copy-to-clipboard for anything carrying data-copy (the artifact cards).
document.querySelectorAll('[data-copy]').forEach((btn) => {
  btn.addEventListener('click', () => {
    const text = btn.dataset.copy;
    const flash = () => {
      const original = btn.textContent;
      btn.textContent = 'COPIED';
      setTimeout(() => (btn.textContent = original), 2000);
    };
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text).then(flash).catch(() => legacyCopy(text, flash));
    } else {
      legacyCopy(text, flash);
    }
  });
});

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

      // Same numbers into the marquee. usd()/price() already carry the formatting
      // contract, so the ticker can't drift from the strip above it.
      const mcap = p.marketCap != null ? p.marketCap : p.fdv;
      const vol = p.volume && p.volume.h24;
      const px = parseFloat(p.priceUsd);
      if (usd(mcap)) setTicker('tk-mcap', { raw: mcap, text: usd(mcap), format: usd });
      if (usd(vol)) setTicker('tk-vol', { raw: vol, text: usd(vol), format: usd });
      if (price(px)) setTicker('tk-price', { raw: px, text: price(px), format: price });
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

  const online = agents.filter((a) => a.online).length;
  setTicker('tk-agents', {
    raw: online,
    text: online + '/' + agents.length,
    format: (v) => Math.round(v) + '/' + agents.length,
  });

  // Queue depth is optional upstream — only show a total when at least one agent
  // actually reported one, so a missing field reads as absent, not as zero.
  const withPending = agents.filter((a) => typeof a.pending === 'number');
  if (withPending.length) {
    const total = withPending.reduce((n, a) => n + a.pending, 0);
    setTicker('tk-pending', {
      raw: total,
      text: String(total),
      format: (v) => String(Math.round(v)),
    });
  }

  // This section appears only once its data lands, which can be either side of
  // initReveal. Either way it goes straight to visible rather than waiting on an
  // intersection that may never be re-evaluated after display:none.
  section.classList.remove('reveal');
  section.classList.add('revealed');
  section.hidden = false;
}

// ── Offers / price sheet ──────────────────────────────────────────────────────
// The storefront. `offers` arrives from /api/swarm already joined to the price
// sheet the payment middleware enforces, so this renders prices rather than
// inventing them — the page cannot quote a number the swarm won't honour.

function tokenAmount(n) {
  if (!isFinite(n)) return null;
  if (n >= 1e6) return (n / 1e6).toFixed(n % 1e6 === 0 ? 0 : 1) + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(n % 1e3 === 0 ? 0 : 1) + 'K';
  return String(n);
}

function renderOffers(data) {
  const section = $('offers');
  const grid = $('offers-grid');
  if (!section || !grid) return;

  // Only priced rows belong in a price sheet; `status` and friends are public
  // and would read as free samples sitting next to paid work.
  const offers = ((data && data.offers) || []).filter((o) => o && o.price);
  if (!offers.length) {
    section.hidden = true;
    return;
  }

  const frag = document.createDocumentFragment();
  offers.forEach((o) => {
    const card = document.createElement('article');
    card.className = 'offer-card' + (o.open ? '' : ' offer-closed');

    const head = document.createElement('div');
    head.className = 'offer-head';

    const name = document.createElement('span');
    name.className = 'offer-id';
    name.textContent = o.id;

    const state = document.createElement('span');
    state.className = 'offer-state';
    // "closed" here means not yet reachable, not broken. The registry is
    // deliberately honest about this rather than advertising a dead endpoint.
    state.textContent = o.open ? 'OPEN' : 'SOON';

    head.append(name, state);

    const title = document.createElement('p');
    title.className = 'offer-title';
    title.textContent = o.title || '';

    const priceRow = document.createElement('div');
    priceRow.className = 'offer-price';
    const amount = tokenAmount(Number(o.price.amount));
    priceRow.innerHTML =
      '<span class="offer-amount"></span><span class="offer-unit">$REDACTED / call</span>';
    priceRow.querySelector('.offer-amount').textContent = amount || o.price.amount;

    const agent = document.createElement('span');
    agent.className = 'offer-agent';
    agent.textContent = o.agent || '';

    card.append(head, title, priceRow, agent);
    frag.appendChild(card);
  });
  grid.replaceChildren(frag);

  renderTreasury(data && data.treasury);

  section.classList.remove('reveal');
  section.classList.add('revealed');
  section.hidden = false;
}

function renderTreasury(t) {
  const box = $('treasury-box');
  if (!box || !t) return;

  const burned = Number(t.burned_total || 0);
  const set = (id, val) => {
    const el = $(id);
    if (el) el.textContent = val;
  };
  set('tr-burned', tokenAmount(burned) || '0');
  set('tr-settlements', String(t.settlements_24h == null ? 0 : t.settlements_24h));
  if (t.split) {
    set('tr-split', t.split.burn + '/' + t.split.compute + '/' + t.split.rewards);
  }

  const solscanLink = (id, sig) => {
    const el = $(id);
    if (!el) return;
    if (sig) {
      el.href = 'https://solscan.io/tx/' + sig;
      el.hidden = false;
    } else {
      el.hidden = true;
    }
  };
  solscanLink('tr-last', t.last_settlement_sig);
  solscanLink('tr-burn-last', t.last_burn_sig);

  setTicker('tk-burned', {
    raw: burned,
    text: tokenAmount(burned) || '0',
    format: (v) => tokenAmount(Math.round(v)) || '0',
  });

  // SWARM RUNWAY: treasury value ÷ trailing daily compute spend. The single
  // most differentiating number on the page — it goes up when people use the
  // swarm. A null (metrics loop hasn't populated it) leaves the cell hidden.
  const rw = Number(t.runway_days);
  if (t.runway_days != null && isFinite(rw)) {
    const fmtDays = (v) => (v >= 3650 ? '10Y+' : Math.round(v) + ' D');
    setTicker('tk-runway', { raw: rw, text: fmtDays(rw), format: fmtDays });
  }

  renderSettlements(t.recent);

  box.hidden = false;
}

// The settlement feed — recent paid jobs, each linking to its on-chain memo
// transaction. Our version of a "total paid out" counter, except the number is
// driven by product usage, not by volume that decays.
function renderSettlements(list) {
  const feed = $('settlements-feed');
  if (!feed) return;
  const rows = Array.isArray(list) ? list.filter((e) => e && e.sig) : [];
  if (!rows.length) {
    feed.hidden = true;
    return;
  }

  const frag = document.createDocumentFragment();
  rows.forEach((e) => {
    const li = document.createElement('li');
    li.className = 'settlement-row';

    const a = document.createElement('a');
    a.href = 'https://solscan.io/tx/' + e.sig;
    a.target = '_blank';
    a.rel = 'noopener';
    a.className = 'settlement-sig';
    a.textContent = String(e.sig).slice(0, 8) + '…';

    const ep = document.createElement('span');
    ep.className = 'settlement-endpoint';
    ep.textContent = e.endpoint || '';

    const amt = document.createElement('span');
    amt.className = 'settlement-amount';
    amt.textContent = (tokenAmount(Number(e.amount)) || e.amount || '') + ' $REDACTED';

    const burn = document.createElement('span');
    burn.className = 'settlement-burn';
    burn.textContent = '⌁ ' + (tokenAmount(Number(e.burn)) || e.burn || '0');

    const age = document.createElement('span');
    age.className = 'settlement-age';
    age.textContent = e.age || '';

    li.append(a, ep, amt, burn, age);
    frag.appendChild(li);
  });
  feed.replaceChildren(frag);
  feed.hidden = false;
}

function loadStatus() {
  fetch('/api/swarm', { cache: 'no-store' })
    .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then((data) => {
      renderStatus(data);
      renderOffers(data);
    })
    .catch(() => {
      const s = $('status');
      if (s) s.hidden = true;
      const o = $('offers');
      if (o) o.hidden = true;
    });
}


// ── Live ticker ───────────────────────────────────────────────────────────────
// The marquee under the hero carries real telemetry, not decoration. Values come from
// the same two polls that feed the mesh section and the market strip, so the strip is
// only ever as live as the page already is. It stays hidden until something resolves.

const tickerState = Object.create(null);
const reduceMotion =
  window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// Count up to a numeric value. Falls straight through to the final text when the
// value isn't numeric, when nothing changed, or when the reader asked for less motion.
function animateValue(el, next) {
  const prevRaw = el.getAttribute('data-raw');
  el.setAttribute('data-raw', String(next.raw == null ? '' : next.raw));

  if (reduceMotion || next.raw == null || prevRaw === null || prevRaw === '') {
    el.textContent = next.text;
    return;
  }
  const from = Number(prevRaw);
  const to = Number(next.raw);
  if (!isFinite(from) || !isFinite(to) || from === to) {
    el.textContent = next.text;
    if (from !== to) flash(el);
    return;
  }

  // Land the real value first, then animate towards it. requestAnimationFrame is
  // throttled to a standstill in a backgrounded tab, so a loop that only assigns the
  // final text in its last frame leaves a stale number on screen indefinitely. This
  // way the correct value is always displayed and the count-up is pure decoration.
  el.textContent = next.text;

  const start = performance.now();
  const dur = 650;
  function step(now) {
    const t = Math.min(1, (now - start) / dur);
    // easeOutCubic — fast to settle, no bounce past the real value
    const v = from + (to - from) * (1 - Math.pow(1 - t, 3));
    el.textContent = t < 1 && next.format ? next.format(v) : next.text;
    if (t < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
  flash(el);
}

function flash(el) {
  if (reduceMotion) return;
  el.classList.remove('val-flash');
  void el.offsetWidth; // restart the animation on a repeat change
  el.classList.add('val-flash');
}

// Both sequences carry the same data-live ids (the second copy is the marquee's
// duplicate), so every update writes to all matching cells.
function setTicker(id, value) {
  tickerState[id] = value;
  document.querySelectorAll('[data-live="' + id + '"]').forEach((el) => {
    animateValue(el, value);
    // Mark the whole item live. Cells that never resolve stay hidden rather than
    // scrolling an em-dash past the reader — the strip carries readings, not slots.
    const item = el.closest('.ticker-item');
    if (item) item.classList.add('is-live');
  });
  const strip = $('live-ticker');
  if (strip && strip.hidden) strip.hidden = false;
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
