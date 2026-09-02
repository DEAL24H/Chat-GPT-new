const state = { items: [], category: 'Tất cả', query: '' };
const $ = (s) => document.querySelector(s);
const DATA_URLS = [new URL('data/news.json', document.baseURI).href, 'https://raw.githubusercontent.com/chayso2015-ctrl/Chat-GPT-new/main/data/news.json'];

function esc(value) {
  return String(value ?? '').replace(/[&<>\"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
}
function copyCode(code) {
  if (!code) return;
  navigator.clipboard?.writeText(code);
  const el = document.activeElement;
  if (el) { const old = el.textContent; el.textContent = 'Đã sao chép'; setTimeout(() => el.textContent = old, 1200); }
}
function age(iso) {
  const t = Date.parse(iso || ''); if (!t) return '';
  const m = Math.max(0, Math.floor((Date.now() - t) / 60000));
  if (m < 60) return `${m || 1} phút trước`;
  const h = Math.floor(m / 60); if (h < 24) return `${h} giờ trước`;
  return `${Math.floor(h / 24)} ngày trước`;
}
function renderFilters() {
  const cats = ['Tất cả', ...new Set(state.items.map(x => x.category).filter(Boolean))];
  $('#filters').innerHTML = cats.map(c => `<button class="filter ${state.category === c ? 'active' : ''}" data-cat="${esc(c)}">${esc(c)}</button>`).join('');
  document.querySelectorAll('[data-cat]').forEach(b => b.onclick = () => { state.category = b.dataset.cat; render(); });
}
function render() {
  renderFilters();
  const q = state.query.toLowerCase().trim();
  const items = state.items.filter(x => (state.category === 'Tất cả' || x.category === state.category) && (!q || [x.merchant,x.code,x.title,x.content,x.category].join(' ').toLowerCase().includes(q)));
  $('#empty').classList.toggle('hidden', items.length !== 0);
  $('#news').innerHTML = items.map(item => `
    <article class="card">
      <div class="cardtop"><span class="tag">${esc(item.category || 'Deal')}</span><span class="time">${esc(age(item.last_checked || item.detected_at))}</span></div>
      <h2>${esc(item.merchant || item.title || 'Ưu đãi')}</h2>
      <p class="discount">${esc(item.discount || 'Ưu đãi đang có')}</p>
      <p>${esc(item.content || '')}</p>
      ${item.code ? `<div class="code"><strong>${esc(item.code)}</strong><button onclick="copyCode('${esc(item.code)}')">Sao chép</button></div>` : ''}
      <div class="meta"><span>${item.verified ? '🟢 Đã xác minh' : '🔎 Nguồn công khai'}</span><a href="${esc(item.source_url || item.url || '#')}" target="_blank" rel="noopener noreferrer">Nguồn ↗</a></div>
    </article>`).join('');
}
async function load() {
  for (const url of DATA_URLS) {
    try {
      const r = await fetch(url, {cache:'no-store'}); if (!r.ok) continue;
      const data = await r.json(); if (!Array.isArray(data)) continue;
      state.items = data.filter(x => x && x.status !== 'expired');
      const latest = state.items.reduce((a,b) => (Date.parse(a?.last_checked || a?.detected_at || 0) > Date.parse(b?.last_checked || b?.detected_at || 0) ? a : b), state.items[0]);
      $('#updated').textContent = latest ? `Cập nhật ${age(latest.last_checked || latest.detected_at)}` : 'Chưa có deal';
      render(); return;
    } catch (e) {}
  }
  $('#news').innerHTML = '<div class="loading">Không tải được dữ liệu. Hãy thử lại sau.</div>';
}
$('#search').addEventListener('input', e => { state.query = e.target.value; render(); });
$('#year').textContent = new Date().getFullYear();
setInterval(() => { $('#clock').textContent = new Date().toLocaleTimeString('vi-VN'); }, 1000);
load();
