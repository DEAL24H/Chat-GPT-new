import json, re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
import feedparser

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data'/'news.json'
SOURCES={
 'Việt Nam':'https://vnexpress.net/rss/tin-moi-nhat.rss',
 'Thế giới':'https://vnexpress.net/rss/the-gioi.rss',
 'Kinh doanh':'https://vnexpress.net/rss/kinh-doanh.rss',
 'Công nghệ':'https://vnexpress.net/rss/so-hoa.rss',
 'Thể thao':'https://vnexpress.net/rss/the-thao.rss',
 'Giải trí':'https://vnexpress.net/rss/giai-tri.rss',
}

def clean(s): return re.sub(r'\\s+',' ',re.sub('<[^>]+>',' ',s or '')).strip()
def date_of(e):
    for key in ('published','updated'):
        if e.get(key):
            try:return parsedate_to_datetime(e[key]).astimezone(timezone.utc).isoformat()
            except Exception:pass
    return datetime.now(timezone.utc).isoformat()

def main():
    items=[]
    for cat,url in SOURCES.items():
        feed=feedparser.parse(url)
        for e in feed.entries[:12]:
            title=clean(e.get('title'))
            link=e.get('link','')
            if not title or not link: continue
            items.append({'title':title,'url':link,'summary':clean(e.get('summary',''))[:300],'category':cat,'source':'VnExpress','published_at':date_of(e)})
    seen=set(); unique=[]
    for x in sorted(items,key=lambda z:z['published_at'],reverse=True):
        k=x['url']
        if k not in seen: seen.add(k); unique.append(x)
    payload={'updated_at':datetime.now(timezone.utc).isoformat(),'items':unique[:60]}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Collected {len(unique[:60])} articles')
if __name__=='__main__': main()
