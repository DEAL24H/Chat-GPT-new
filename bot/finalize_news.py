import json
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "news.json"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {"User-Agent": "DiemTin24H/1.3 editorial bot"}


def words(text):
    return len(re.findall(r"\b[\wÀ-ỹà-ỹ'-]+\b", text or "", re.UNICODE))


def norm(text):
    return re.sub(r"[^\wÀ-ỹà-ỹ]+", " ", (text or "").lower(), flags=re.UNICODE).split()


def license_ok(name):
    n = (name or "").lower().replace("–", "-").strip()
    if n in {"cc0", "pd", "pd-us", "pd-old"} or n.startswith("public domain"):
        return True
    if n.startswith("cc by") and "nc" not in n and "nd" not in n:
        return True
    return False


def commons_search(query, required_groups):
    params = {
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": query, "gsrnamespace": 6, "gsrlimit": 30,
        "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": 1200,
    }
    data = requests.get(COMMONS_API, params=params, headers=HEADERS, timeout=20).json()
    candidates = []
    for page in (data.get("query", {}).get("pages", {}) or {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        lic = (meta.get("LicenseShortName", {}).get("value", "") or "").strip()
        if not license_ok(lic):
            continue
        title = (page.get("title", "") or "").replace("File:", "", 1).strip()
        tokens = set(norm(title))
        if not all(any(token in tokens for token in group) for group in required_groups):
            continue
        image = info.get("thumburl") or info.get("url")
        if not image:
            continue
        candidates.append({
            "image": image,
            "image_source": "Wikimedia Commons",
            "image_license": lic,
            "image_title": title,
            "image_page": "https://commons.wikimedia.org/wiki/" + (page.get("title", "") or "").replace(" ", "_"),
        })
    return candidates


def valid_existing_image(item, image):
    if not image or not license_ok(image.get("image_license", "")):
        return False
    title = set(norm(image.get("image_title", "")))
    context = " ".join([item.get("title", ""), item.get("summary", "")]).lower()
    if "thu trang" in context and "thu" not in title:
        return False
    if "tiến luật" in context or "tien luat" in context:
        if not ({"tien", "luat"} <= title or {"tiến", "luật"} <= title):
            return False
    if "2g" in context or "2g" in norm(item.get("title", "")):
        if not ({"2g"} <= title or "gsm" in title):
            return False
        if not ({"phone", "mobile", "cellphone", "telephone"} & title):
            return False
    if "peru" in context and "peru" not in title:
        return False
    if "iran" in context and "iran" not in title:
        return False
    if "mixue" in context and "mixue" not in title:
        return False
    return True


def find_replacement(item):
    context = (item.get("title", "") + " " + item.get("summary", "")).lower()
    if "thu trang" in context:
        found = commons_search("Thu Trang", [["thu"], ["trang"]])
        if found:
            return found[0]
    if "tiến luật" in context or "tien luat" in context:
        found = commons_search("Tien Luat", [["tien", "tiến"], ["luat", "luật"]])
        if found:
            return found[0]
    if "2g" in context:
        found = commons_search("2G GSM mobile phone", [["2g", "gsm"], ["phone", "mobile", "cellphone"]])
        if found:
            return found[0]
    if "peru" in context:
        found = commons_search("Peru flag", [["peru"], ["flag", "flagge", "bandera"]])
        if found:
            return found[0]
    if "iran" in context:
        found = commons_search("Iran flag", [["iran"], ["flag", "flagge", "bandera"]])
        if found:
            return found[0]
    if "mixue" in context:
        found = commons_search("Mixue", [["mixue"]])
        if found:
            return found[0]
    return None


def main():
    data = json.loads(OUT.read_text(encoding="utf-8"))
    failures = []
    for item in data.get("items", []):
        item["source_url"] = item.get("url", "")
        item["source_label"] = "Đọc bài gốc tại VnExpress"

        if words(item.get("content", "")) < 750:
            failures.append(f"Bài quá ngắn: {item.get('title', '')} ({words(item.get('content', ''))} từ)")

        valid = [img for img in (item.get("images") or []) if valid_existing_image(item, img)]
        if not valid:
            replacement = find_replacement(item)
            valid = [replacement] if replacement else []
        item["images"] = valid[:2]
        if valid:
            item.update(valid[0])
        else:
            item.update({"image": "", "image_source": "", "image_license": "", "image_title": "", "image_page": ""})

    data.setdefault("policy", {})["source_article"] = "original article available through source_url; site stores an original editorial article, not the full source text"
    data["policy"]["image_policy"] = "strict relevance validation; licensed Commons only; never use an unrelated fallback"
    data["policy"]["minimum_article_words"] = 750
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    if failures:
        print("\n".join(failures), file=sys.stderr)
        print("News validation failed: no short article is allowed to reach Pages.", file=sys.stderr)
        return 1
    print(f"Validated {len(data.get('items', []))} articles and image licenses/relevance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
