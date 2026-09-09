import json
import re
from pathlib import Path
from urllib.parse import urlparse
from bot.catalog_utils import is_brand_host_allowed
ROOT=Path(__file__).resolve().parents[1];DATA=ROOT/'data/news.json';CATEGORIES={'Fashion','Electronics','Beauty & Personal Care','Home & Living'}
BAD_TEXT_RE=re.compile(r'\b(?:your cart is empty|estimated total|current price|original price|add to wishlist|sign in|log in|create account|privacy policy|terms(?: and conditions)?|cookie(?:s| policy)?|product advice|shipping address|billing address|search results|compare products|recently viewed|recommended for you|sort by|filter by|size guide|store locator|customer service|help center)\b',re.I)
PROMO_RE=re.compile(r'\b(?:sale|offer|offers|deal|deals|promotion|promotions|discount|coupon|promo|clearance|special offer|save|savings|voucher|limited time|bundle|buy\s+\d+\s+get\s+\d+|buy one get one|free (?:gift|shipping|delivery|item|set)|gift with purchase|no code required|code not required|member (?:price|savings|offer))\b',re.I)
BENEFIT_RE=re.compile(r'(?:\b\d{1,3}\s*%\s*(?:off|discount)\b|\b(?:save|off)\s+\$?\d+(?:[.,]\d+)?\b|\$\s?\d+(?:[.,]\d+)?\s*(?:off|discount)\b|\bbuy\s+\d+\s+get\s+\d+\b|\bbuy one get one\b|\bfree\s+(?:gift|shipping|delivery|item|set)\b|\bgift with purchase\b|\bspend\s+\$?\d+(?:[.,]\d+)?\s*(?:or more|\+)?\b|\b(?:no code required|code not required|without (?:a )?code)\b|\bmember (?:price|savings|offer)\b|\bbundle\b)',re.I)
def host(value):
 raw=str(value or '').strip()
 if '://' not in raw:raw='https://'+raw
 return(urlparse(raw).hostname or '').lower().removeprefix('www.')
def same_domain(a,b):
 x,y=host(a),host(b);return bool(x and y and(x==y or x.endswith('.'+y) or y.endswith('.'+x)))
def main():
 data=json.loads(DATA.read_text(encoding='utf-8'))
 if not isinstance(data,list):raise SystemExit('DEAL CONTRACT FAILED: news.json is not a list')
 failures=[];counts={category:0 for category in CATEGORIES}
 for index,item in enumerate(data):
  category=str(item.get('category') or '').strip();title=str(item.get('title') or '').strip();content=str(item.get('content') or '').strip();destination=str(item.get('final_purchase_url') or '').strip();promotion_url=str(item.get('promotion_url') or '').strip();source=str(item.get('source_url') or '').strip();code=str(item.get('code') or '').strip()
  if category not in CATEGORIES:failures.append((index,'bad_category',category));continue
  if item.get('offer_qualified') is not True:failures.append((index,'not_offer_qualified',title))
  if item.get('official_source') is not True:failures.append((index,'not_official_source',title))
  if item.get('source_verification_status')!='assistant_verified_first_party':failures.append((index,'bad_source_verification',title))
  if not destination or not promotion_url or not source or not host(destination) or not host(promotion_url) or not host(source):failures.append((index,'missing_destination_promotion_or_source',title))
  if not is_brand_host_allowed(item.get('merchant'),source):failures.append((index,'source_not_allowed_brand_host',source))
  if not same_domain(promotion_url,source):failures.append((index,'promotion_url_left_source_domain',promotion_url))
  if not is_brand_host_allowed(item.get('merchant'),destination):failures.append((index,'destination_not_allowed_brand_host',destination))
  if BAD_TEXT_RE.search(title):failures.append((index,'ui_or_product_noise_title',title))
  evidence=f'{title} {content}'
  if not PROMO_RE.search(evidence):failures.append((index,'no_promotion_evidence',title))
  if not BENEFIT_RE.search(evidence) and not code:failures.append((index,'no_specific_benefit_or_code',title))
  if code and len(code)<4:failures.append((index,'invalid_code',code))
  if code and item.get('promotion_type')!='coupon_code':failures.append((index,'code_type_mismatch',title))
  if not code and item.get('promotion_type')!='direct_promotion':failures.append((index,'direct_type_mismatch',title))
  counts[category]+=1
 print('DEAL CONTRACT COUNTS:',counts,'total=',len(data))
 if failures:
  for row in failures[:100]:print('FAIL',row)
  raise SystemExit(f'DEAL CONTRACT FAILED: {len(failures)} violations')
 if not data:raise SystemExit('DEAL CONTRACT FAILED: zero qualified promotions')
 print('DEAL CONTRACT PASS: promotion source and purchase destination are independently validated')
if __name__=='__main__':main()
