// ── REDACTED.MEME — Pattern Blue Edition ──

// Copy CA to clipboard
function copyCA() {
  const text = document.getElementById('ca-text').textContent.trim();
  navigator.clipboard.writeText(text).then(() => {
    const confirm = document.getElementById('copy-confirm');
    confirm.classList.add('show');
    setTimeout(() => confirm.classList.remove('show'), 2000);
    const btn = document.getElementById('copy-btn');
    btn.textContent = 'COPIED';
    setTimeout(() => btn.textContent = 'COPY', 2000);
  }).catch(() => {
    // Fallback for older browsers
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    const confirm = document.getElementById('copy-confirm');
    confirm.classList.add('show');
    setTimeout(() => confirm.classList.remove('show'), 2000);
  });
}

// Mobile nav toggle
const toggle = document.getElementById('nav-toggle');
const navLinks = document.getElementById('nav-links');
if (toggle && navLinks) {
  toggle.addEventListener('click', () => {
    navLinks.classList.toggle('open');
  });
}

// Close mobile nav on link click
navLinks && navLinks.querySelectorAll('a').forEach(a => {
  a.addEventListener('click', () => navLinks.classList.remove('open'));
});

// Nav background opacity on scroll
const nav = document.getElementById('nav');
window.addEventListener('scroll', () => {
  if (window.scrollY > 40) {
    nav.style.borderBottomColor = 'rgba(61,62,64,0.8)';
  } else {
    nav.style.borderBottomColor = '';
  }
}, { passive: true });

// Intersection observer — fade-in sections
const fadeEls = document.querySelectorAll('section, .agent-card, .phil-card, .sys-link');
const observer = new IntersectionObserver((entries) => {
  entries.forEach(e => {
    if (e.isIntersecting) {
      e.target.style.opacity = '1';
      e.target.style.transform = 'translateY(0)';
      observer.unobserve(e.target);
    }
  });
}, { threshold: 0.08 });

fadeEls.forEach(el => {
  el.style.opacity = '0';
  el.style.transform = 'translateY(16px)';
  el.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
  observer.observe(el);
});

// Hero section stays visible immediately
const hero = document.getElementById('hero');
if (hero) {
  hero.style.opacity = '1';
  hero.style.transform = 'none';
}
