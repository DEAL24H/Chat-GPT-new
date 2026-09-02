const state = { items: [], category: 'All', query: '' };
const $ = (s) => document.querySelector(s);
const DATA_URLS = [new URL('data/news.json', document.baseURI).href, 'https://raw.githubusercontent.com/chayso2015-ctrl/Chat-GPT-new/main/data/news.json'];
const CATEGORY_LABELS = { 'Thời trang':'Fashion', 'Mỹ phẩm':'Beauty', 'Game':'Gaming', 'Tổng hợp':'Deals' };
const BRAND_DOMAINS = {
  dell:'dell.com', nike:'nike.com', adidas:'adidas.com', puma:'puma.com', shein:'shein.com', asos:'asos.com', mango:'shop.mango.com', hm:'hm.com', 'h&m':'hm.com', uniqlo:'uniqlo.com', zara:'zara.com', crocs:'crocs.com', gap:'gap.com', converse:'converse.com', 'under armour':'underarmour.com',
  sephora:'sephora.com', ulta:'ulta.com', nars:'narscosmetics.com', mac:'maccosmetics.com', cerave:'cerave.com', 'the ordinary':'theordinary.com', farmacy:'farmacybeauty.com', 'bobbi brown':'bobbibrowncosmetics.com', kosas:'kosas.com', paulaschoice:'paulaschoice.com', 'paula\'s choice':'paulaschoice.com', glossier:'glossier.com', clinique:'clinique.com',
  steam:'store.steampowered.com', epic:'store.epicgames.com', playstation:'playstation.com', xbox:'xbox.com', nintendo:'nintendo.com', humble:'humblebundle.com', fanatical:'fanatical.com', ubisoft:'ubisoft.com', ea:'ea.com',
  reebok:'reebok.com', iherb:'iherb.com', lenovo:'lenovo.com', hp:'hp.com', 'best buy':'bestbuy.com'
};
function esc(value) { return String(value ?? '').replace(/[&<>\"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c])); }
function copyCode(code) { if (!code) return; navigator.clipboard?.writeText(code); const el = document.activeElement; if (el) { const old = el.textContent; el.textContent = 'Copied'; setTimeout(() => el.textContent = old, 1200); } }
function age(iso) { const t = Date.parse(iso || ''); if (!t) return ''; const m = Math.max(0, Math.floor((Date.now() - t) / 60000)); if (m < 60) return `${m || 1} min ago`; const h = Math.floor(m / 60); if (h < 24) return `${h}h ago`; return `${Math.floor(h / 24)}d ago`; }
function label(category) { return CATEGORY_LABELS[category] || category || 'Deal'; }
function findBrandKey(item) {
  const text = `${item.merchant || ''} ${item.title || ''} ${item.content || ''}`.toLowerCase();
  return Object.keys(BRAND_DOMAINS).find(k => new RegExp(`(^|[^a-z0-9])${k.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')}([^a-z0-9]|$)`, 'i').test(text));
}
function brandName(item) { const hit = findBrandKey(item); if (!hit) return item.merchant || item.title || 'Deal'; if (hit === 'hm') return 'H&M'; if (hit === 'puma') return 'PUMA'; return hit.replace(/(^|\s)\S/g, s => s.toUpperCase()); }
function brandDomain(item) { const hit = findBrandKey(item); return hit ? BRAND_DOMAINS[hit] : (item.merchant_domain || ''); }
function brandLogo(item) { const domain = brandDomain(item); return domain ? `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=128` : ''; }
function brandSlug(name) { return String(name || '').toLowerCase().replace(/&/g,'and').replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,''); }
function brandHref(item) { const brand = brandSlug(brandName(item)); const cat = label(item.category).toLowerCase(); return brand && cat !== 'deals' ? `${cat}/${brand}-coupons/` : '#'; }
function renderFilters() { const cats = ['All', ...new Set(state.items.map(x => label(x.category)).filter(Boolean))]; $('#filters').innerHTML = cats.map(c => `<button class="filter ${state.category === c ? 'active' : ''}" data-cat="${esc(c)}">${esc(c)}</button>`).join(''); document.querySelectorAll('[data-cat]').forEach(b => b.onclick = () => { state.category = b.dataset.cat; render(); }); }
function render() {
  renderFilters(); const q = state.query.toLowerCase().trim();
  const items = state.items.filter(x => (state.category === 'All' || label(x.category) === state.category) && (!q || [x.merchant,x.code,x.title,x.content,label(x.category)].join(' ').toLowerCase().includes(q)));
  $('#empty').classList.toggle('hidden', items.length !== 0);
  $('#news').innerHTML = items.map(item => {
    const brand = brandName(item), logo = brandLogo(item), href = brandHref(item);
    return `<article class="card"><div class="brandrow"><div class="brandlogo">${logo ? `<img src="${esc(logo)}" alt="${esc(brand)} logo" loading="lazy" onerror="this.style.display='none';this.nextElementSibling.style.display='grid'">` : ''}<span class="brandfallback" style="${logo ? 'display:none' : ''}">${esc(String(brand).slice(0,2).toUpperCase())}</span></div><div class="brandinfo"><a class="brandname" href="${esc(href)}">${esc(brand)}</a><span class="tag">${esc(label(item.category))} coupons</span></div><span class="time">${esc(age(item.last_checked || item.detected_at))}</span></div><h2>${esc(brand)} Coupon Code${item.discount ? ` — ${esc(item.discount)}` : ''}</h2><p>${esc(item.content || 'Fresh public coupon or promotional offer.')}</p>${item.code ? `<div class="code"><strong>${esc(item.code)}</strong><button onclick="copyCode('${esc(item.code)}')">Copy code</button></div>` : ''}<div class="meta"><span>${item.verified ? '🟢 Verified' : '🔎 Public source'}</span><a href="${esc(item.source_url || item.url || '#')}" target="_blank" rel="noopener noreferrer">Source ↗</a></div></article>`;
  }).join('');
}
async function load() { for (const url of DATA_URLS) { try { const r = await fetch(url, {cache:'no-store'}); if (!r.ok) continue; const data = await r.json(); if (!Array.isArray(data)) continue; state.items = data.filter(x => x && x.status !== 'expired'); const latest = state.items.reduce((a,b) => (Date.parse(a?.last_checked || a?.detected_at || 0) > Date.parse(b?.last_checked || b?.detected_at || 0) ? a : b), state.items[0]); $('#updated').textContent = latest ? `Updated ${age(latest.last_checked || latest.detected_at)}` : 'No deals yet'; render(); return; } catch (e) {} } $('#news').innerHTML = '<div class="loading">Could not load deals. Please try again later.</div>'; }
$('#search').addEventListener('input', e => { state.query = e.target.value; render(); });
$('#year').textContent = new Date().getFullYear();
setInterval(() => { $('#clock').textContent = new Date().toLocaleTimeString('en-US'); }, 1000);
load();
