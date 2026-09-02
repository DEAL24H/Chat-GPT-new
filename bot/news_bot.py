import hashlib
import json
import os
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import feedparser
import requests
from bs4 import BeautifulSoup
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "news.json"
SOURCES = {
    "Việt Nam": "https://vnexpress.net/rss/tin-moi-nhat.rss",
    "Thế giới": "https://vnexpress.net/rss/the-gioi.rss",
    "Kinh doanh": "https://vnexpress.net/rss/kinh-doanh.rss",
    "Công nghệ": "https://vnexpress.net/rss/so-hoa.rss",
    "Giải trí": "https://vnexpress.net/rss/giai-tri.rss",
}
MAX_POSTS = 5
MAX_SOURCE_CHARS = 12000
MODEL = "llama3.1-8b"
HEADERS = {"User-Agent": "DiemTin24H/1.0 (+GitHub Pages editorial bot)"}
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
ALLOWED_LICENSES = ("CC BY", "CC BY-SA", "CC0", "Public domain", "PD")


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", BeautifulSoup(text or "", "html.parser").get_text(" ")).strip()


def date_of(entry):
    for key in ("published", "updated"):
        value = entry.get(key)
        if value:
            try:
                return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
            except Exception:
                pass
    return datetime.now(timezone.utc).isoformat()


def post_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def fetch_article_text(url: str) -> str:
    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    paragraphs = []
    for p in soup.select("p.Normal"):
        text = clean(p.get_text(" "))
        if len(text) >= 35:
            paragraphs.append(text)
    return "\n\n".join(paragraphs)[:MAX_SOURCE_CHARS]


def find_openly_licensed_image(title: str, category: str):
    """Find a relevant Wikimedia Commons image whose metadata states an open/public-domain license."""
    queries = [f"{title} {category}", category, title]
    for query in queries:
        try:
            params = {
                "action": "query",
                "format": "json",
                "generator": "search",
                "gsrsearch": query,
                "gsrnamespace": 6,
                "gsrlimit": 10,
                "prop": "imageinfo",
                "iiprop": "url|extmetadata",
                "iiurlwidth": 1200,
            }
            response = requests.get(COMMONS_API, params=params, headers=HEADERS, timeout=15)
            response.raise_for_status()
            pages = response.json().get("query", {}).get("pages", {})
            for page in pages.values():
                info = (page.get("imageinfo") or [{}])[0]
                meta = info.get("extmetadata") or {}
                license_name = clean(meta.get("LicenseShortName", {}).get("value", ""))
                if not license_name or not any(x.lower() in license_name.lower() for x in ALLOWED_LICENSES):
                    continue
                image_url = info.get("thumburl") or info.get("url")
                if image_url:
                    return {
                        "image": image_url,
                        "image_source": "Wikimedia Commons",
                        "image_license": license_name,
                        "image_title": clean(page.get("title", "")).replace("File:", "", 1).strip(),
                    }
        except Exception as exc:
            print(f"Commons image search failed for {query!r}: {exc}")
    return {"image": "", "image_source": "", "image_license": "", "image_title": ""}


def ai_article(source_text: str, title: str, category: str) -> tuple[str, str]:
    api_key = os.environ.get("CEREBRAS_API_KEY")
    if not api_key or not source_text:
        return "", title

    client = OpenAI(base_url="https://api.cerebras.ai/v1", api_key=api_key)
    prompt = (
        "Bạn là biên tập viên của ĐIỂM TIN 24H. Dựa trên các dữ kiện trong tài liệu nguồn, "
        "hãy tạo một bài báo tiếng Việt DÀI và NGUYÊN BẢN, khoảng 600-900 từ nếu dữ kiện cho phép. "
        "Bài phải có tiêu đề mới và nhiều đoạn, trình bày mạch lạc, có bối cảnh, diễn biến, số liệu "
        "và ý nghĩa khi chúng thực sự có trong nguồn. Không chép nguyên câu hoặc tái tạo cấu trúc của "
        "bài nguồn; không bịa thêm dữ kiện, phát ngôn hay kết luận. Đây là bài biên tập độc lập dựa trên "
        "các sự kiện đã kiểm chứng. Trả về đúng JSON với hai trường title và content; content là văn bản "
        "thuần, các đoạn cách nhau bằng một dòng trống.\n\n"
        f"Chuyên mục: {category}\nTiêu đề tham khảo: {title}\n\n"
        f"Tài liệu dữ kiện nguồn:\n{source_text}"
    )
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0.25,
        messages=[
            {"role": "system", "content": "Tạo bài báo nguyên bản, chính xác theo dữ kiện; không sao chép văn bản nguồn."},
            {"role": "user", "content": prompt},
        ],
    )
    raw = (response.choices[0].message.content or "").strip()
    try:
        data = json.loads(raw)
        new_title = clean(data.get("title", title)) or title
        content = str(data.get("content", "")).strip()
    except json.JSONDecodeError:
        new_title = title
        content = raw
    return content, new_title


def main():
    candidates = []
    for category, feed_url in SOURCES.items():
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            title = clean(entry.get("title"))
            url = entry.get("link", "")
            if title and url:
                candidates.append({
                    "id": post_id(url),
                    "title": title,
                    "url": url,
                    "summary": clean(entry.get("summary", ""))[:300],
                    "category": category,
                    "source": "VnExpress",
                    "published_at": date_of(entry),
                })
                break

    candidates.sort(key=lambda item: item["published_at"], reverse=True)
    posts = []
    for item in candidates[:MAX_POSTS]:
        try:
            source_text = fetch_article_text(item["url"])
            content, new_title = ai_article(source_text, item["title"], item["category"])
            if content:
                item["title"] = new_title
                item["content"] = content
                item["summary"] = content.split("\n\n", 1)[0][:360]
                item["summary_type"] = "cerebras_ai_original_article"
            else:
                item["content"] = ""
                item["summary_type"] = "source_excerpt"
            item.update(find_openly_licensed_image(item["title"], item["category"]))
        except Exception as exc:
            print(f"Article processing failed for {item['url']}: {exc}")
            item["content"] = ""
            item["summary_type"] = "source_excerpt"
            item.update(find_openly_licensed_image(item["title"], item["category"]))
        posts.append(item)

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "items": posts,
        "policy": {
            "max_posts_per_run": MAX_POSTS,
            "full_source_text_stored": False,
            "source_images_stored": False,
            "source_attribution": True,
            "ai_mode": "original_detailed_article",
            "ai_provider": "Cerebras",
            "ai_model": MODEL,
            "image_provider": "Wikimedia Commons",
            "image_policy": "explicit open-license or public-domain metadata required",
        },
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Prepared {len(posts)} posts")


if __name__ == "__main__":
    main()
