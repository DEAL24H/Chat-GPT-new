const $=s=>document.querySelector(s);
function esc(s){return String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#039;'}[c]))}
function fmt(d){try{return new Intl.DateTimeFormat('vi-VN',{dateStyle:'full',timeStyle:'short'}).format(new Date(d))}catch{return d}}
async function load(){
  const id=new URLSearchParams(location.search).get('id');
  if(!id){$('#post').innerHTML='<div class="empty">Không tìm thấy mã bài viết.</div>';return}
  try{
    const r=await fetch('data/news.json',{cache:'no-store'}); if(!r.ok) throw Error(r.status);
    const d=await r.json(); const item=(d.items||[]).find(x=>x.id===id);
    if(!item){$('#post').innerHTML='<div class="empty">Bài viết không còn trong danh sách.</div>';return}
    document.title=`${item.title} · ĐIỂM TIN 24H`;
    $('#post').innerHTML=`
      <div class="tag">${esc(item.category||'Tin tức')}</div>
      <h1>${esc(item.title)}</h1>
      <div class="post-meta">${esc(item.source||'Nguồn tham khảo')} · ${fmt(item.published_at)}</div>
      <div class="post-body">
        <p>${esc(item.summary||'Nội dung đang được cập nhật.')}</p>
      </div>
      <div class="source-note">Nguồn tham khảo: <strong>${esc(item.source||'Nguồn gốc')}</strong></div>`;
  }catch(e){$('#post').innerHTML='<div class="empty">Không thể tải bài viết lúc này.</div>'}
}
$('#year').textContent=new Date().getFullYear();load();
