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
MAX_SOURCE_CHARS = 24000
MODEL = "llama3.1-8b"
HEADERS = {"User-Agent": "DiemTin24H/1.1 (+GitHub Pages editorial bot)"}
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
ALLOWED_LICENSES = ("CC BY", "CC BY-SA", "CC0", "Public domain", "PD")
STOPWORDS = {"và", "của", "với", "cho", "một", "các", "những", "được", "trong", "tháng", "năm", "tại", "từ", "sẽ", "là", "bị", "đã", "the", "and", "with"}


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
    response = requests.get(url, headers=HEADERS, timeout=25)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    paragraphs = []
    selectors = ["article.fck_detail p.Normal", ".fck_detail p.Normal", "p.Normal"]
    for selector in selectors:
        paragraphs = []
        for p in soup.select(selector):
            text = clean(p.get_text(" "))
            if len(text) >= 35:
                paragraphs.append(text)
        if paragraphs:
            break

    # Some VnExpress pages expose the article body in JSON-LD. Read it only transiently
    # for factual grounding; never write the source article back to news.json.
    if not paragraphs:
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                data = json.loads(script.string or script.get_text())
                objects = data if isinstance(data, list) else [data]
                for obj in objects:
                    body = obj.get("articleBody") if isinstance(obj, dict) else None
                    if body:
                        text = clean(body)
                        if len(text) >= 300:
                            paragraphs = [text]
                            break
            except Exception:
                continue
            if paragraphs:
                break
    return "\n\n".join(paragraphs)[:MAX_SOURCE_CHARS]


def _license_ok(meta):
    license_name = clean(meta.get("LicenseShortName", {}).get("value", ""))
    return license_name if license_name and any(x.lower() in license_name.lower() for x in ALLOWED_LICENSES) else ""


def _commons_search(query: str, wanted_tokens=None, limit=15):
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": 6,
        "gsrlimit": limit,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": 1200,
    }
    response = requests.get(COMMONS_API, params=params, headers=HEADERS, timeout=15)
    response.raise_for_status()
    pages = response.json().get("query", {}).get("pages", {})
    results = []
    wanted_tokens = set(wanted_tokens or [])
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        license_name = _license_ok(meta)
        if not license_name:
            continue
        title = clean(page.get("title", "")).replace("File:", "", 1).strip()
        haystack = title.lower()
        score = sum(1 for token in wanted_tokens if token and token.lower() in haystack)
        image_url = info.get("thumburl") or info.get("url")
        if image_url:
            results.append((score, {
                "image": image_url,
                "image_source": "Wikimedia Commons",
                "image_license": license_name,
                "image_title": title,
            }))
    results.sort(key=lambda x: x[0], reverse=True)
    return results


def _tokens(text):
    return [x for x in re.findall(r"[\wÀ-ỹà-ỹ]+", text or "", flags=re.UNICODE) if len(x) >= 3 and x.lower() not in STOPWORDS]


def find_openly_licensed_images(title: str, category: str):
    """Return only topical Commons images with explicit open/public-domain metadata.
    If no relevant licensed image is found, return none rather than an unrelated picture.
    """
    selected = []
    lower_title = title.lower()

    # For people/entertainment stories, search the named people directly. This is much safer
    # than searching a broad category and accidentally getting a random document or object.
    person_queries = []
    if "thu trang" in lower_title:
        person_queries.append(("Thu Trang", ["thu", "trang"]))
    if "tiến luật" in lower_title or "tien luat" in lower_title:
        person_queries.append(("Tiến Luật", ["tiến", "luật", "tien", "luat"]))

    for query, tokens in person_queries:
        try:
            results = _commons_search(query, tokens)
            if results:
                selected.append(results[0][1])
        except Exception as exc:
            print(f"Commons people image search failed for {query!r}: {exc}")

    # For other topics, require visible overlap between the article title and Commons filename.
    if not selected:
        tokens = _tokens(title)
        query = " ".join(tokens[:6]) or category
        try:
            results = _commons_search(query, tokens[:6])
            for score, image in results:
                if score >= 1:
                    selected.append(image)
                    break
        except Exception as exc:
            print(f"Commons topical image search failed for {title!r}: {exc}")

    # Never publish a random category image merely to fill the slot.
    dedup = []
    seen = set()
    for image in selected:
        if image["image"] not in seen:
            seen.add(image["image"])
            dedup.append(image)
    return dedup[:2]


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+[\wÀ-ỹà-ỹ'-]*\b", text or "", flags=re.UNICODE))


def ai_article(source_text: str, title: str, category: str) -> tuple[str, str]:
    api_key = os.environ.get("CEREBRAS_API_KEY")
    if not api_key or not source_text:
        return "", title

    client = OpenAI(base_url="https://api.cerebras.ai/v1", api_key=api_key)
    prompt = (
        "Bạn là biên tập viên của ĐIỂM TIN 24H. Dựa trên các dữ kiện trong tài liệu nguồn, "
        "hãy viết một bài báo tiếng Việt DÀI, NGUYÊN BẢN và có chiều sâu. Mục tiêu 900-1200 từ, "
        "tối thiểu 750 từ nếu dữ kiện nguồn đủ. Không được biến thành một đoạn tóm tắt ngắn. "
        "Hãy khai thác đầy đủ các dữ kiện đáng chú ý: diễn biến, nhân vật, số liệu, bối cảnh, nguyên nhân, "
        "hệ quả hoặc tác động khi nguồn thực sự cung cấp. Chia bài thành nhiều đoạn, có mở bài, phần triển khai "
        "và kết bài tự nhiên. Không bịa thêm dữ kiện, phát ngôn, con số hoặc sự kiện. Không chép nguyên câu, "
        "không tái tạo cấu trúc hay cách diễn đạt của bài nguồn. Đây là bài biên tập độc lập dựa trên sự kiện. "
        "Trả về đúng JSON với hai trường title và content; content là văn bản thuần, các đoạn cách nhau bằng một dòng trống.\n\n"
        f"Chuyên mục: {category}\nTiêu đề tham khảo: {title}\n\n"
        f"Tài liệu dữ kiện nguồn:\n{source_text}"
    )
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0.3,
        max_tokens=3200,
        messages=[
            {"role": "system", "content": "Tạo bài báo nguyên bản, dài, chính xác theo dữ kiện; không sao chép văn bản nguồn."},
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

    if word_count(content) < 750:
        expand_prompt = (
            "Mở rộng bản thảo dưới đây thành bài báo tiếng Việt khoảng 900-1200 từ. Giữ nguyên mọi dữ kiện đã có; "
            "phát triển bối cảnh, giải thích và mạch kể chỉ khi chúng đã được hỗ trợ bởi bản thảo; không bịa thêm, "
            "không lặp ý và không sao chép nguồn. Trả về văn bản thuần với nhiều đoạn.\n\n"
            f"Bản thảo cần mở rộng:\n{content}"
        )
        expanded = client.chat.completions.create(
            model=MODEL,
            temperature=0.3,
            max_tokens=3200,
            messages=[
                {"role": "system", "content": "Mở rộng bài báo nguyên bản, không thêm dữ kiện không được hỗ trợ."},
                {"role": "user", "content": expand_prompt},
            ],
        )
        expanded_text = (expanded.choices[0].message.content or "").strip()
        if word_count(expanded_text) > word_count(content):
            content = expanded_text
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
            # RSS summary is only a fallback grounding signal when a page exposes no article body.
            if len(source_text) < 500:
                source_text = item["summary"]
            content, new_title = ai_article(source_text, item["title"], item["category"])
            if content:
                item["title"] = new_title
                item["content"] = content
                item["summary"] = content.split("\n\n", 1)[0][:360]
                item["summary_type"] = "cerebras_ai_original_article"
            else:
                item["content"] = ""
                item["summary_type"] = "source_excerpt"
            images = find_openly_licensed_images(item["title"], item["category"])
            item["images"] = images
            item.update(images[0] if images else {"image": "", "image_source": "", "image_license": "", "image_title": ""})
        except Exception as exc:
            print(f"Article processing failed for {item['url']}: {exc}")
            item["content"] = ""
            item["summary_type"] = "source_excerpt"
            images = find_openly_licensed_images(item["title"], item["category"])
            item["images"] = images
            item.update(images[0] if images else {"image": "", "image_source": "", "image_license": "", "image_title": ""})
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
            "target_article_words": "900-1200",
            "minimum_article_words": 750,
            "ai_provider": "Cerebras",
            "ai_model": MODEL,
            "image_provider": "Wikimedia Commons",
            "image_policy": "only topically relevant files with explicit open-license or public-domain metadata; otherwise no image",
        },
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Prepared {len(posts)} posts")


if __name__ == "__main__":
    main()
