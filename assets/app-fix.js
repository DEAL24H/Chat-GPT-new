const state = { items: [], category: 'All', query: '' };
const $ = (s) => document.querySelector(s);
const DATA_URLS = [new URL('data/news.json', document.baseURI).href, 'https://raw.githubusercontent.com/chayso2015-ctrl/Chat-GPT-new/main/data/news.json'];
const CATEGORY_LABELS = { 'Thời trang':'Fashion', 'Mỹ phẩm':'Beauty', 'Game':'Gaming', 'Tổng hợp':'Deals' };

function esc(value) { return String(value ?? '').replace(/[&<>\"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c])); }
function copyCode(code) {
  if (!code) return;
  navigator.clipboard?.writeText(code);
  const el = document.activeElement;
  if (el) { const old = el.textContent; el.textContent = 'Copied'; setTimeout(() => el.textContent = old, 1200); }
}
function age(iso) {
  const t = Date.parse(iso || ''); if (!t) return '';
  const m = Math.max(0, Math.floor((Date.now() - t) / 60000));
  if (m < 60) return `${m || 1} min ago`;
  const h = Math.floor(m / 60); if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}
function label(category) { return CATEGORY_LABELS[category] || category || 'Deal'; }
function renderFilters() {
  const cats = ['All', ...new Set(state.items.map(x => label(x.category)).filter(Boolean))];
  $('#filters').innerHTML = cats.map(c => `<button class="filter ${state.category === c ? 'active' : ''}" data-cat="${esc(c)}">${esc(c)}</button>`).join('');
  document.querySelectorAll('[data-cat]').forEach(b => b.onclick = () => { state.category = b.dataset.cat; render(); });
}
function render() {
  renderFilters();
  const q = state.query.toLowerCase().trim();
  const items = state.items.filter(x => (state.category === 'All' || label(x.category) === state.category) && (!q || [x.merchant,x.code,x.title,x.content,label(x.category)].join(' ').toLowerCase().includes(q)));
  $('#empty').classList.toggle('hidden', items.length !== 0);
  $('#news').innerHTML = items.map(item => `
    <article class="card">
      <div class="cardtop"><span class="tag">${esc(label(item.category))}</span><span class="time">${esc(age(item.last_checked || item.detected_at))}</span></div>
      <h2>${esc(item.merchant || item.title || 'Deal')}</h2>
      <p class="discount">${esc(item.discount || 'Special offer')}</p>
      <p>${esc(item.content || '')}</p>
      ${item.code ? `<div class="code"><strong>${esc(item.code)}</strong><button onclick="copyCode('${esc(item.code)}')">Copy code</button></div>` : ''}
      <div class="meta"><span>${item.verified ? '🟢 Verified' : '🔎 Public source'}</span><a href="${esc(item.source_url || item.url || '#')}" target="_blank" rel="noopener noreferrer">Source ↗</a></div>
    </article>`).join('');
}
async function load() {
  for (const url of DATA_URLS) {
    try {
      const r = await fetch(url, {cache:'no-store'}); if (!r.ok) continue;
      const data = await r.json(); if (!Array.isArray(data)) continue;
      state.items = data.filter(x => x && x.status !== 'expired');
      const latest = state.items.reduce((a,b) => (Date.parse(a?.last_checked || a?.detected_at || 0) > Date.parse(b?.last_checked || b?.detected_at || 0) ? a : b), state.items[0]);
      $('#updated').textContent = latest ? `Updated ${age(latest.last_checked || latest.detected_at)}` : 'No deals yet';
      render(); return;
    } catch (e) {}
  }
  $('#news').innerHTML = '<div class="loading">Could not load deals. Please try again later.</div>';
}
$('#search').addEventListener('input', e => { state.query = e.target.value; render(); });
$('#year').textContent = new Date().getFullYear();
setInterval(() => { $('#clock').textContent = new Date().toLocaleTimeString('en-US'); }, 1000);
load();
