"""
Leeway Parts — Demand Signal + B2B Merchant Extractor (v3)
---------------------------------------------------------------
Pipeline A — Demand Signals:
  1. Search Google via SerpAPI (buyer intent queries, past 30 days)
  2. Qwen extracts structured demand signals
  3. Match against Leeway Parts product inventory
  4. Generate outreach draft for matched signals
  5. Merge with previous runs (preserve contacted status)
  6. Output to signals_output.json

Pipeline B — B2B Merchants:
  1. Search Google (no time filter — companies don't expire)
  2. Qwen extracts company profiles (name, website, email, phone)
  3. Match against Leeway Parts product inventory
  4. Output to b2b_companies.json

Usage:
  python demo.py

Requirements: pip install -r requirements.txt
Env vars in .env: SERPAPI_KEY, QWEN_API_KEY
"""

import os
import sys
import json
import time
import re
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dotenv import load_dotenv

# Fix Windows console encoding — Japanese/Chinese chars crash GBK stdout
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

load_dotenv(Path(__file__).parent / ".env")

SERPAPI_KEY = os.getenv("SERPAPI_KEY")
QWEN_API_KEY = os.getenv("QWEN_API_KEY")

# LLM provider config — supports Qwen, DeepSeek, SiliconFlow, etc.
# Falls back to Qwen for backward compatibility
LLM_API_KEY = os.getenv("LLM_API_KEY") or QWEN_API_KEY
LLM_BASE_URL = os.getenv("LLM_BASE_URL") or "https://dashscope.aliyuncs.com/compatible-mode/v1"
LLM_MODEL = os.getenv("LLM_MODEL") or "qwen-turbo"

# Module-level warnings (don't raise — allow server.py to import safely)
if not SERPAPI_KEY:
    print("[WARN] SERPAPI_KEY not set — B2B refresh will not work")
if not LLM_API_KEY:
    print("[WARN] LLM_API_KEY (or QWEN_API_KEY) not set — B2B refresh will not work")

from serpapi import GoogleSearch
from openai import OpenAI
from product_inventory import match_product

import email_sender  # NEW: email outreach module (zero deps)

# Lazy-initialized OpenAI client (avoids crash on import if keys missing)
_client = None

def _get_client():
    global _client
    if _client is None:
        if not LLM_API_KEY:
            raise RuntimeError("LLM_API_KEY not configured")
        _client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    return _client

# ─── Stability ───────────────────────────────────────────────────────────
LLM_TIMEOUT = 20
LLM_MAX_RETRIES = 2
MAX_INPUT_CHARS = 3000

# ─── Target-market queries (developing countries, buyer intent) ──────────

QUERIES = [
    # ══════════ Southeast Asia ══════════
    '"Kubota tractor parts" needed looking supplier Philippines OR Vietnam OR Indonesia',
    '"Kubota tractor parts" importer Philippines OR Vietnam OR Indonesia',
    '"Yanmar" diesel engine parts wanted Thailand OR Malaysia',
    '"tractor spare parts" looking dealer India OR Bangladesh',
    '"Kubota" OR "Yanmar" hydraulic pump repair help',
    '"agricultural machinery" distributor India OR Bangladesh',
    # ══════════ East Asia (Japan / Korea) ══════════
    '"Kubota tractor parts" importer OR dealer Japan',
    '"Yanmar" engine parts distributor Japan OR South Korea',
    # Japanese-language: local forums, repair shops, dealers
    'クボタ トラクター 部品 探して います',
    'ヤンマー エンジン 修理 パーツ ディーラー',
    'トラクター部品 輸入 販売 Japan',
    # ══════════ Africa ══════════
    '"tractor spare parts" dealer looking supplier South Africa OR Kenya OR Nigeria',
    '"Kubota" OR "Yanmar" gear pump cylinder needed help repair',
    '"agricultural machinery" spare parts needed Ethiopia OR Tanzania OR Ghana',
    '"Massey Ferguson" OR "New Holland" parts wanted Africa',
    '"Massey Ferguson" OR "John Deere" importer Nigeria OR Kenya',
    # ══════════ Middle East ══════════
    '"agricultural machinery spare parts" supplier needed Dubai OR Egypt OR Pakistan',
    '"Massey Ferguson" OR "John Deere" replacement parts looking import',
    '"tractor parts" needed Turkey OR Iran',
    '"tractor spare parts" distributor Dubai OR Saudi Arabia',
    # ══════════ Latin America ══════════
    '"tractor parts" needed urgently Brazil OR Mexico',
    '"Kubota" OR "Yanmar" diesel engine repair parts',
    # Spanish / Portuguese: local-language buyer posts
    '"repuestos tractor" necesito Kubota OR Yanmar',
    '"peças trator" importador OR distribuidor Brasil',
    # ══════════ Russia / CIS ══════════
    'запчасти трактор Kubota OR Yanmar импортер',
    'трактор запчасти дистрибьютор Россия',
    # ══════════ Forum / social — buyer intent ══════════
    'site:reddit.com OR site:tractorbynet.com tractor parts broke need help',
    'site:facebook.com "tractor parts" looking needed buy',
    # ══════════ Global importer / procurement ══════════
    '"Kubota parts" "Purchasing Manager" OR "Procurement Manager" email',
    '"tractor aftermarket parts" importer OR distributor contact',
    # ══════════ Dealer / Distributor / Stockist (NEW) ══════════
    # EN — Southeast Asia
    '"Kubota tractor parts" dealer OR stockist wanted Philippines OR Vietnam',
    '"aftermarket tractor parts" wholesaler OR agent Indonesia OR Thailand',
    # EN — Africa
    '"tractor spare parts" import company looking franchise Nigeria OR Kenya',
    '"agricultural parts" trading company needed South Africa OR Ghana',
    # JP — Japan
    'クボタ トラクター部品 輸入代理店 募集',
    'ヤンマー 部品 正規ディーラー 仕入れ先',
    # FR — West Africa
    '"pièces tracteur" importateur OR distributeur cherche Afrique',
    '"pièces détachées agricoles" revendeur OR agent',
    # AR — Middle East
    '"قطع غيار جرارات" مستورد OR موزع مصر OR السعودية',
    '"استيراد قطع غيار" زراعية Kubota OR Yanmar',
    # ES — Latin America
    '"repuestos tractor" distribuidor autorizado busca importar',
    # EN — Global
    '"tractor parts" dealership opportunity OR agency wanted',
]

# ─── B2B Merchant Discovery queries (Japan primary, English secondary) ──
# NO time filter — companies and distributors are permanent entities.
# Focus: find importers, dealers, wholesalers, trading companies.

B2B_QUERIES = [
    # ══════════ Japan (primary — 農業機械部品 輸入/販売) ══════════
    'クボタ トラクター 部品 輸入 販売 会社',
    'ヤンマー 農機 部品 ディーラー 仕入れ',
    '農業機械 部品 輸入代理店 募集 OR 求人',
    'トラクター パーツ 貿易 商社 日本',
    '農機具 スペアパーツ 輸入 企業',
    'クボタ 部品 正規販売店 一覧',
    'ヤンマー トラクター パーツ 輸出 会社',
    '中古農機 輸出 業者 部品 日本',
    '農機 アフターマーケット 部品 販売 輸入',
    '農業機械 部品 商社 東京 OR 大阪 OR 北海道',
    'トラクター 部品 輸出入 専門 会社',
    'クボタ OR ヤンマー 部品 通販 法人 OR 企業',
    # ══════════ English — Japan / Asia dealers ══════════
    '"kubota" OR "yanmar" tractor parts importer OR distributor Japan',
    '"agricultural machinery parts" trading company Japan import export',
    'site:linkedin.com/company "agricultural machinery" import Japan',
    # ══════════ English — Global B2B ══════════
    '"tractor spare parts" dealer OR wholesaler email contact Africa OR Asia',
    'site:kompass.com "kubota" OR "yanmar" tractor parts',
    '"aftermarket tractor parts" importer OR distributor OR agent "contact us"',
]

# ─── Supplier filter ─────────────────────────────────────────────────────

SUPPLIER_SIGNALS = [
    "wholesale", "manufacturer", "add to cart",
    "buy now", "order now", "free shipping",
    "alibaba.com", "amazon.com", "ebay.com", "aliexpress.com", "made-in-china.com",
]

def is_likely_supplier(title: str, snippet: str, url: str) -> bool:
    text = (title + " " + snippet + " " + url).lower()
    return any(kw in text for kw in SUPPLIER_SIGNALS)

# ─── E-commerce URL blacklist ────────────────────────────────────────────
# These are product pages or marketplace listings, NOT buyer posts.
# Filtering them BEFORE LLM saves tokens and reduces false positives.

ECOMMERCE_URL_SIGNALS = [
    # Southeast Asia marketplaces
    "tokopedia.com", "shopee.co.id", "shopee.ph", "shopee.vn",
    "lazada.", "bukalapak.com", "tiki.vn",
    # Japan marketplaces
    "monotaro.com", "misumi", "askul.co.jp", "rakuten.co.jp",
    "yahoo.co.jp/shopping",
    # Cross-border e-commerce
    "ubuy.", "desertcart.", "noon.",
    # Parts-specific e-commerce
    "parts-machining.com", "sparepartstore24", "agriaffaires",
    "machinerytrader", "mascus.", "trademachines.",
    "grainger.com", "mcmaster.com", "indiamart.com",
    "directindustry.", "made-in-china.com",
    # International
    "amazon.com", "amazon.co.jp", "amazon.in", "amazon.de", "amazon.co.uk",
    "ebay.com", "aliexpress.com", "alibaba.com",
    "walmart.com", "target.com",
]

def is_ecommerce_page(url: str) -> bool:
    """Quick domain check: is this a known e-commerce / marketplace page?"""
    return any(kw in url.lower() for kw in ECOMMERCE_URL_SIGNALS)

# ─── LLM prompts ─────────────────────────────────────────────────────────

EXTRACT_PROMPT = """You are an agricultural machinery demand analyst for a B2B aftermarket parts exporter.

Given this Google search result, determine if it represents a BUYER (farmer, operator, local dealer) who needs to purchase or repair agricultural machinery parts.

Title: {title}
Snippet: {snippet}
URL: {url}

Today is 2026-07-02. A post older than 30 days is NOT a live signal.

Rules:
- Only extract if there is clear BUYER intent: asking for parts, reporting a breakdown, seeking repair help, requesting a quote, looking for supplier, dealer searching for stock
- Reject: supplier listings, product pages ("Buy now at $XXX"), e-commerce stores (Tokopedia, Amazon, eBay, Monotaro), news articles, ads, informational tutorials
- Common false positives — REJECT these patterns:
  * Price tags in snippet: "Rp 1.200.000", "$499 USD", "buy now"
  * Product catalog pages: parts list with SKU codes, "add to cart", "in stock"
  * Company self-promotion: "we sell", "welcome to our store", "Contact us for best price"
  * Job postings: "We are hiring", "Service Technician wanted"
  * News / press releases: "Company X launches", "New product lineup"
- buyer_type: "individual_farmer" (single machine owner), "local_dealer" (buying for resale/repair shop), "repair_shop" (service business), or "unknown"
- poster_username: forum username or author name if visible in title/snippet; otherwise null
- urgency_score: 0-100 (100 = machine is down, farmer can't work)
- urgency: "high" if urgency_score >= 65, "medium" if 30-64, "low" if < 30
- purchase_intent: "high" if actively trying to order, "medium" if researching, "low" if just browsing

Also extract any contact information visible in the title or snippet:
- contact_name: the poster's real name if mentioned (e.g. "Kiran Patel posted...", "by John Smith")
- contact_email: any email address visible in the snippet (e.g. "contact me at john@farm.com")
- company_name: company or shop name if mentioned (e.g. "Patel Tractor Repair", "ABC Trading Co.")
- website: company website URL if different from source_url (e.g. "visit us at tractorparts.com")
All four should be null if not visible in the text. Do NOT guess or fabricate.

Return ONLY valid JSON (no markdown):
{{
  "country": "country or region, or null",
  "machine_model": "specific model, or null",
  "part_type": "part needed, or null",
  "buyer_type": "individual_farmer | local_dealer | repair_shop | unknown",
  "poster_username": "forum username or null",
  "urgency": "low | medium | high",
  "urgency_score": <integer 0-100>,
  "purchase_intent": "low | medium | high",
  "contact_name": "person name or null",
  "contact_email": "email address or null",
  "company_name": "company or shop name or null",
  "website": "company website URL or null",
  "source_url": "{url}"
}}

If NOT a buyer signal, return exactly: null"""

# ─── B2B Company Extraction Prompt ──────────────────────────────────────
# Different from signal prompt: we're looking for COMPANY PROFILES, not
# demand expressions. Target: importers, dealers, wholesalers, trading cos.

B2B_EXTRACT_PROMPT = """You are a B2B lead researcher for Leeway Parts, an exporter of aftermarket Kubota/Yanmar tractor parts.

Given this Google search result, determine if it represents a COMPANY that distributes, imports, or trades agricultural machinery parts. We want to find potential distribution partners.

Title: {title}
Snippet: {snippet}
URL: {url}

Rules:
- Extract if this is a COMPANY profile, business listing, or company website that deals in agricultural machinery or tractor parts
- Good signals: company names, "importer of...", "we distribute...", "trading company", "株式会社", "有限会社", "PT", "CV", "Ltd", "PLC", "SARL"
- Reject: product-for-sale listings (e-commerce), news articles, job postings, personal blogs, forum posts, government sites, industry associations
- Reject: manufacturer's own website (Kubota official, Yanmar official) — we want local distributors, not the OEM
- Reject: results where no company name can be identified

- business_type: one of "importer", "distributor", "dealer", "wholesaler", "trading_company", "agent", "repair_shop", or "unknown"
- company_name: the legal or trading name of the business — extract exactly as shown
- website: the company's own website domain if visible (NOT the source_url of the search result page itself, unless the source_url IS the company's official website)
- contact_email: any email found in title or snippet (e.g. "info@abc.com", "sales@...")
- phone: any phone number found in title or snippet
- country: where the company is based
- product_focus: what categories of agricultural parts they deal in (e.g. "engine parts", "hydraulic systems", "general tractor spares")
- confidence: 0-100 (100 = clearly a distributor with contact info, 70-90 = clearly a company but missing contact, <50 = ambiguous)

Return ONLY valid JSON (no markdown):
{{
  "company_name": "company name or null",
  "business_type": "importer | distributor | dealer | wholesaler | trading_company | agent | repair_shop | unknown",
  "website": "company website domain or null",
  "contact_email": "email address or null",
  "phone": "phone number or null",
  "country": "country name or null",
  "product_focus": "what parts they deal in, or null",
  "confidence": <integer 0-100>,
  "source_url": "{url}"
}}

If NOT a B2B company, return exactly: null"""

OUTREACH_PROMPT = """You are Mona, Product Manager at Baoding Jutuo Agricultural Machinery, a direct factory specializing in aftermarket Kubota, Yanmar, and John Deere tractor parts. We export worldwide, cost 20% lower than OEM, and support small-batch orders.

Write ONE outreach email in {language} for this customer:

- Part needed: {part_type}
- Machine model: {machine_model}
- Buyer type: {buyer_type}
- Country: {country}
- Contact person: {contact_name} (use "friend" if empty)
- Company name: {company_name}
- Product match: {matched_category}
- Reference draft: {email_draft}

Requirements:

1. PERSONALIZED OPENING: Reference {buyer_type} and available details naturally. Show you understand their needs — don't copy-paste.

2. FACTORY PERSPECTIVE: We are a direct factory (not a trading company). Aftermarket Kubota/Yanmar/John Deere parts, 20% lower than OEM, small batches welcome, fast global shipping.

3. LANGUAGE — STRICTLY ENFORCED:
   - You MUST write the ENTIRE email in {language} ONLY.
   - NO English if language is not English.
   - NO Chinese characters anywhere in the output.
   - If {language} is Japanese (ja), use natural business Japanese. Use 「」quotes, proper keigo level.
   - If {language} is Korean (ko), use natural business Korean with appropriate honorifics.
   - If {language} is Indonesian (id), use formal but warm Bahasa Indonesia.
   - If {language} is Spanish (es), use formal but warm business Spanish (usted form).

4. CTA based on buyer_type:
   - dealer / distributor / importer / wholesaler → invite to request product catalog or wholesale price list
   - repair_shop → offer sample parts with specifications
   - individual_farmer / unknown → ask what specific models they need, offer to check stock

5. NATURAL SIGNATURE — like a real person, not a corporate template:
   WhatsApp: +86 173 2093 2309 (Mona)
   Alibaba: https://gyquanfeng.en.alibaba.com/

6. TONE: Warm, genuine, peer-to-peer communication. No sales pitch. No "revolutionary" or "game-changing" language. Just a factory person reaching out to help.

7. SUBJECT LINE: Creative, genuine, natural. ABSOLUTELY NO: "high quality", "best price", "best quality", "top", "premium", "professional manufacturer" in the subject.

8. LENGTH: 150-200 words (Japanese/Korean/Indonesian: similar natural length, not word-by-word translation).

9. UNSUBSCRIBE FOOTER at the very end:
{unsubscribe}

Return ONLY the email text — no markdown, no quotes, no commentary. Start directly with the subject line on its own line, then a blank line, then the body."""

# ─── Utility helpers ─────────────────────────────────────────────────────

def get_contact_method(url: str) -> str:
    """Determine how to reach the poster based on platform."""
    url_lower = url.lower()
    if "facebook.com" in url_lower:
        return "Facebook Messenger / Comment"
    if "reddit.com" in url_lower:
        return "Reddit DM / Comment"
    if "tractorbynet.com" in url_lower or "mytractorforum.com" in url_lower:
        return "Forum Reply (register required)"
    if "youtube.com" in url_lower:
        return "YouTube Comment"
    if "justanswer.com" in url_lower:
        return "Site reply"
    return "Direct message / Comment"

# ─── Country fallback from search query ──────────────────────────────────
# When LLM returns country=null (82% of cases), infer from the query's
# geographic keywords.

_COUNTRY_KEYWORDS = {
    "philippines": "Philippines", "vietnam": "Vietnam", "indonesia": "Indonesia",
    "thailand": "Thailand", "malaysia": "Malaysia", "india": "India",
    "bangladesh": "Bangladesh", "japan": "Japan", "korea": "South Korea",
    "south africa": "South Africa", "kenya": "Kenya", "nigeria": "Nigeria",
    "ethiopia": "Ethiopia", "tanzania": "Tanzania", "ghana": "Ghana",
    "dubai": "UAE", "egypt": "Egypt", "pakistan": "Pakistan",
    "turkey": "Turkey", "iran": "Iran", "saudi": "Saudi Arabia",
    "brazil": "Brazil", "mexico": "Mexico", "россия": "Russia",
    "ブラジル": "Brazil", "メキシコ": "Mexico",
    "africa": "Africa",
    # Japan-specific
    "東京": "Japan", "大阪": "Japan", "日本": "Japan",
    "北海道": "Japan", "関東": "Japan", "九州": "Japan",
    "愛知": "Japan", "福岡": "Japan",
    # Japan kanji patterns
    "株式会社": "Japan", "輸入": "Japan", "輸出": "Japan",
    "商社": "Japan", "代理店": "Japan",
}

def infer_country_from_query(query: str) -> str | None:
    """Fallback: extract country from the search query keywords."""
    q = query.lower()
    for kw, country in sorted(_COUNTRY_KEYWORDS.items(), key=lambda x: -len(x[0])):
        if kw in q:
            return country
    return None

# ─── Email Language Routing ────────────────────────────────────────────────

def get_email_language(country: str | None) -> str:
    """Map country to email language code: ja, ko, id, es, or en (default)."""
    if not country:
        return "en"
    c = country.strip().lower()
    if c in ("japan", "jp"):
        return "ja"
    if c in ("korea", "south korea", "kr"):
        return "ko"
    if c in ("indonesia", "id"):
        return "id"
    if c in ("spain", "es", "mexico", "mx", "argentina", "ar",
             "colombia", "co", "peru", "pe", "chile", "cl",
             "venezuela", "ve", "ecuador", "ec", "bolivia", "bo",
             "paraguay", "py", "uruguay", "uy", "costa rica", "cr",
             "panama", "pa", "guatemala", "gt", "honduras", "hn",
             "el salvador", "sv", "nicaragua", "ni", "dominican republic", "do",
             "cuba", "cu", "puerto rico", "pr"):
        return "es"
    return "en"

UNSUBSCRIBE_TEXT = {
    "en": 'If you\'d prefer not to hear from us, just reply "unsubscribe".',
    "ja": "ご不要の場合は「配信停止」とご返信ください。",
    "ko": '수신을 원하지 않으시면 "수신거부"라고 답장해 주세요.',
    "id": 'Jika tidak ingin menerima email dari kami, balas "berhenti berlangganan".',
    "es": 'Si prefiere no recibir nuestros correos, responda "cancelar suscripción".',
}

LANGUAGE_NAMES = {"ja": "Japanese", "ko": "Korean", "id": "Bahasa Indonesia", "es": "Spanish", "en": "English"}

# ─── Priority / tags ──────────────────────────────────────────────────────

def calculate_priority(signal: dict) -> int:
    """Composite priority score 0-100 based on urgency, product match, and recency."""
    score = signal.get("urgency_score", 0) * 0.5
    if signal.get("has_product"):
        score += 30
    post_date = signal.get("post_date")
    if post_date:
        try:
            days_ago = (datetime.now(timezone.utc) - datetime.fromisoformat(post_date)).days
            if days_ago <= 3:
                score += 20
            elif days_ago <= 7:
                score += 10
        except (ValueError, TypeError):
            pass
    return min(100, int(score))

def generate_tags(signal: dict) -> list[str]:
    """Auto-generate Chinese tags from signal fields."""
    tags = []
    part = (signal.get("part_type") or "").lower()
    cat = (signal.get("matched_category") or "").lower()
    buyer = signal.get("buyer_type") or ""
    urgency = signal.get("urgency") or ""

    # Part type tags
    if any(kw in part for kw in ("hydraulic", "pump", "cylinder", "valve")):
        tags.append("液压件")
    if any(kw in part for kw in ("gear", "gear pump")):
        tags.append("齿轮")
    if any(kw in part for kw in ("engine", "fuel", "oil filter", "gasket", "piston", "water pump", "fuel pump")):
        tags.append("发动机")
    if any(kw in part for kw in ("seat", "hood", "fender", "grille", "headlight")):
        tags.append("车身件")
    if any(kw in part for kw in ("link", "tie rod", "pto", "axle", "clutch", "bearing")):
        tags.append("底盘传动")
    if any(kw in part for kw in ("filter", "seal", "gasket", "o-ring")):
        tags.append("易损件")

    # Urgency tag
    if urgency == "high":
        tags.append("急单")

    # Buyer type tag
    if buyer == "local_dealer":
        tags.append("经销商")
    elif buyer == "repair_shop":
        tags.append("维修厂")

    # Brand tag
    brand = (signal.get("matched_brand") or "").lower()
    if "kubota" in brand:
        tags.append("久保田")
    if "yanmar" in brand:
        tags.append("洋马")

    return tags[:6]  # max 6 tags

# ─── Google Search ───────────────────────────────────────────────────────

def search_google(query, num=20, pages=1):
    """Single SerpAPI query, past-30-days filter, with manual pagination."""
    params = {
        "engine": "google",
        "q": query,
        "num": num,
        "api_key": SERPAPI_KEY,
        "hl": "en",
        "tbs": "qdr:m",  # Past 30 days
    }
    all_organic = []
    for page in range(pages):
        params["start"] = page * num
        results = GoogleSearch(params).get_dict()
        organic = results.get("organic_results", [])
        all_organic.extend(organic)
        if len(organic) < num:
            break
    print(f"         {page + 1} page(s), {len(all_organic)} results")
    return [
        {"title": r.get("title", ""),
         "snippet": r.get("snippet", ""),
         "url": r.get("link", ""),
         "date": r.get("date", "")}
        for r in all_organic
    ]

# ─── B2B Google Search (no time filter, one page, Japan geo) ────────────

def search_google_b2b(query, num=20):
    """B2B merchant search — NO time filter, companies are permanent entities."""
    params = {
        "engine": "google",
        "q": query,
        "num": num,
        "api_key": SERPAPI_KEY,
        "hl": "en",
        "gl": "jp",  # Bias towards Japan results
    }
    try:
        results = GoogleSearch(params).get_dict()
    except Exception as e:
        print(f"         Search error: {e}")
        return []
    organic = results.get("organic_results", [])
    print(f"         {len(organic)} results")
    return [
        {"title": r.get("title", ""),
         "snippet": r.get("snippet", ""),
         "url": r.get("link", ""),
         "date": r.get("date", "")}
        for r in organic
    ]

# ─── Qwen extraction ─────────────────────────────────────────────────────

def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rstrip()
    return cut.rsplit(" ", 1)[0] + "\u2026"  # …

def _call_llm_once(prompt: str) -> str | None:
    response = _get_client().chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=500,
        timeout=LLM_TIMEOUT,
    )
    content = response.choices[0].message.content
    return content.strip() if content else None

def extract_signal(result: dict) -> tuple[dict | None, bool]:
    """Extract demand signal via Qwen. Returns (signal_or_None, had_error)."""
    title = result.get("title", "")
    snippet = result.get("snippet", "")
    url = result.get("url", "")

    # ── Hard pre-filter: skip obvious product detail pages ──
    if any(pat in url.lower() for pat in [
        "/product/", "/p/", "/products/", "product_id=", "productId=",
        "/item/", "item_id=", "productdetail", "product-detail",
        "add-to-cart", "add_to_cart", "checkout", "cart.",
    ]):
        return None, False

    text_budget = MAX_INPUT_CHARS - 400
    half = text_budget // 2
    title = _truncate(title, half)
    snippet = _truncate(snippet, text_budget - len(title))
    prompt = EXTRACT_PROMPT.format(title=title, snippet=snippet, url=url)

    def _try_once():
        raw = _call_llm_once(prompt)
        if raw is None:
            return None
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        if raw.lower() == "null" or not raw:
            return None
        return json.loads(raw)

    for attempt in range(LLM_MAX_RETRIES + 1):
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(_try_once)
        try:
            signal = future.result(timeout=LLM_TIMEOUT)
            executor.shutdown(wait=False)
            return signal, False
        except FutureTimeoutError:
            executor.shutdown(wait=False)
            err_msg = "timed out after 20s"
        except json.JSONDecodeError:
            return None, False
        except Exception as e:
            err_msg = str(e)[:100]

        if attempt < LLM_MAX_RETRIES:
            wait = (attempt + 1) * 1.5
            print(f"       Retry {attempt + 1}/{LLM_MAX_RETRIES}: {err_msg}")
            time.sleep(wait)
        else:
            print(f"       FAIL after {LLM_MAX_RETRIES + 1} attempts: {err_msg}")
            return None, True

    return None, False

# ─── B2B Company Extraction ─────────────────────────────────────────────

def extract_b2b_company(result: dict) -> tuple[dict | None, bool]:
    """Extract B2B company profile via Qwen. Returns (company_or_None, had_error)."""
    title = result.get("title", "")
    snippet = result.get("snippet", "")
    url = result.get("url", "")

    # ── Hard pre-filter: skip obvious non-company pages ──
    url_lower = url.lower()
    # E-commerce / product pages
    if any(kw in url_lower for kw in ECOMMERCE_URL_SIGNALS):
        return None, False
    if any(pat in url_lower for pat in [
        "/product/", "/p/", "/products/", "product_id=", "productId=",
        "/item/", "item_id=", "productdetail", "product-detail",
        "add-to-cart", "cart.", "checkout",
    ]):
        return None, False
    # Social media posts / forums → not B2B companies
    if any(pat in url_lower for pat in [
        "facebook.com", "twitter.com", "x.com", "instagram.com",
        "reddit.com", "tiktok.com", "youtube.com/watch",
        "tractorbynet.com", "mytractorforum.com",
    ]):
        return None, False

    text_budget = MAX_INPUT_CHARS - 400
    half = text_budget // 2
    title = _truncate(title, half)
    snippet = _truncate(snippet, text_budget - len(title))
    prompt = B2B_EXTRACT_PROMPT.format(title=title, snippet=snippet, url=url)

    def _try_once():
        raw = _call_llm_once(prompt)
        if raw is None:
            return None
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        if raw.lower() == "null" or not raw:
            return None
        return json.loads(raw)

    for attempt in range(LLM_MAX_RETRIES + 1):
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(_try_once)
        try:
            company = future.result(timeout=LLM_TIMEOUT)
            executor.shutdown(wait=False)
            return company, False
        except FutureTimeoutError:
            executor.shutdown(wait=False)
            err_msg = "timed out after 20s"
        except json.JSONDecodeError:
            return None, False
        except Exception as e:
            err_msg = str(e)[:100]

        if attempt < LLM_MAX_RETRIES:
            wait = (attempt + 1) * 1.5
            print(f"       Retry {attempt + 1}/{LLM_MAX_RETRIES}: {err_msg}")
            time.sleep(wait)
        else:
            print(f"       FAIL after {LLM_MAX_RETRIES + 1} attempts: {err_msg}")
            return None, True

    return None, False

# ─── Outreach generation ──────────────────────────────────────────────────

def generate_outreach(signal: dict) -> str | None:
    """Generate one outreach draft for a matched signal, using language routing."""
    country = signal.get("country") or ""
    lang = get_email_language(country)
    prompt = OUTREACH_PROMPT.format(
        part_type=signal.get("part_type", "tractor parts"),
        machine_model=signal.get("machine_model", "unknown model"),
        buyer_type=signal.get("buyer_type", "unknown"),
        country=country,
        contact_name=signal.get("contact_name") or "",
        company_name=signal.get("company_name") or "",
        matched_category=signal.get("matched_category", "our parts catalog"),
        email_draft=signal.get("outreach_draft") or "",
        language=LANGUAGE_NAMES.get(lang, "English"),
        unsubscribe=UNSUBSCRIBE_TEXT.get(lang, UNSUBSCRIBE_TEXT["en"]),
    )
    try:
        raw = _call_llm_once(prompt)
        return raw
    except Exception:
        return None

def generate_b2b_outreach(company: dict) -> str | None:
    """Generate an outreach email for a B2B company, using language routing."""
    country = company.get("country") or ""
    lang = get_email_language(country)
    prompt = OUTREACH_PROMPT.format(
        part_type=company.get("product_focus", "agricultural machinery parts"),
        machine_model="Kubota / Yanmar / John Deere",
        buyer_type=company.get("business_type", "unknown"),
        country=country,
        contact_name=company.get("contact_name") or company.get("company_name") or "",
        company_name=company.get("company_name") or "",
        matched_category=company.get("matched_category", "aftermarket tractor parts"),
        email_draft="",
        language=LANGUAGE_NAMES.get(lang, "English"),
        unsubscribe=UNSUBSCRIBE_TEXT.get(lang, UNSUBSCRIBE_TEXT["en"]),
    )
    try:
        raw = _call_llm_once(prompt)
        return raw
    except Exception:
        return None

# ─── History merge ───────────────────────────────────────────────────────

def merge_history(new_signals: list[dict]) -> list[dict]:
    """Merge new signals with previous run: preserve contacted status, notes, and follow-up state."""
    output_path = Path(__file__).parent / "signals_output.json"
    if not output_path.exists():
        for s in new_signals:
            s.setdefault("status", "new")
            s.setdefault("notes", None)
        return new_signals

    try:
        raw = json.loads(output_path.read_text(encoding="utf-8"))
        old = raw if isinstance(raw, list) else raw.get("signals", [])
    except (json.JSONDecodeError, FileNotFoundError):
        for s in new_signals:
            s.setdefault("status", "new")
            s.setdefault("notes", None)
        return new_signals

    old_by_url = {s.get("source_url"): s for s in old if s.get("source_url")}

    merged = []
    seen = set()
    for s in new_signals:
        url = s.get("source_url")
        if url and url in old_by_url:
            # Preserve contacted status and notes from old run
            old_s = old_by_url[url]
            s["contacted"] = old_s.get("contacted", False)
            s["contacted_at"] = old_s.get("contacted_at")
            s["status"] = old_s.get("status", "new")
            s["notes"] = old_s.get("notes")
        else:
            s["contacted"] = False
            s["contacted_at"] = None
            s["status"] = "new"
            s["notes"] = None
        seen.add(url)
        merged.append(s)

    # Re-add old contacted signals that didn't appear in this run
    for old_s in old:
        url = old_s.get("source_url")
        if url and url not in seen and old_s.get("contacted"):
            merged.append(old_s)

    return merged

# ─── B2B Pipeline (standalone, callable from server.py) ─────────────────

def run_b2b_pipeline(progress_callback=None):
    """
    Run the full B2B merchant discovery pipeline.

    Args:
        progress_callback: Optional callable(step, total_steps, message)
            Called at each major step for real-time progress reporting.

    Returns:
        dict with keys:
            - companies: list of B2B company dicts (the full b2b_final list)
            - total_companies: int
            - matched_product: int
            - b2b_output: dict (the full output structure saved to JSON)
            - error: str | None (if pipeline failed)
    """
    # Validate API keys
    if not SERPAPI_KEY:
        return {"companies": [], "total_companies": 0, "matched_product": 0, "b2b_output": {}, "error": "SERPAPI_KEY not configured"}
    if not LLM_API_KEY:
        return {"companies": [], "total_companies": 0, "matched_product": 0, "b2b_output": {}, "error": "LLM_API_KEY not configured"}

    # ── Safe stdout: swallow UnicodeEncodeError on Windows console ──
    import builtins
    _real_print = builtins.print
    def _safe_print(*args, **kwargs):
        try:
            _real_print(*args, **kwargs)
        except (UnicodeEncodeError, OSError, ValueError):
            pass
    builtins.print = _safe_print

    import traceback as _tb
    try:
        return _run_b2b_pipeline_inner(progress_callback, _safe_print)
    except Exception as e:
        builtins.print = _real_print  # Restore before error handling
        return {
            "companies": [],
            "total_companies": 0,
            "matched_product": 0,
            "b2b_output": {},
            "error": str(e),
            "traceback": _tb.format_exc(),
        }
    finally:
        builtins.print = _real_print


def _load_existing_b2b() -> dict:
    """Load existing B2B companies for resume/skip logic.
    Returns {source_url: company_dict}."""
    b2b_path = Path(__file__).parent / "b2b_companies.json"
    if not b2b_path.exists():
        return {}
    try:
        old_data = json.loads(b2b_path.read_text(encoding="utf-8"))
        old_list = old_data if isinstance(old_data, list) else old_data.get("companies", [])
        return {c.get("source_url"): c for c in old_list if c.get("source_url")}
    except (json.JSONDecodeError, FileNotFoundError):
        return {}


def _save_b2b_intermediate(companies, search_results, _print=print):
    """Save intermediate B2B results so partial work survives crashes.
    Preserves old contacted companies that aren't in the current batch."""
    b2b_path = Path(__file__).parent / "b2b_companies.json"
    run_ts = datetime.now(timezone.utc).isoformat()

    # Merge: preserve old contacted companies not in current batch
    existing = _load_existing_b2b()
    seen_urls = {c.get("source_url") for c in companies}
    extra_old = [old_c for url, old_c in existing.items()
                 if url not in seen_urls and old_c.get("contacted")]
    companies_merged = list(companies) + extra_old

    output = {
        "run_timestamp": run_ts,
        "total_b2b_queries": len(B2B_QUERIES),
        "total_b2b_results": len(search_results),
        "total_companies": len(companies_merged),
        "matched_product": sum(1 for c in companies_merged if c.get("has_product")),
        "companies": companies_merged,
    }
    _json_str = json.dumps(output, indent=2, ensure_ascii=False)
    _tmp_path = b2b_path.with_suffix(".json.tmp")
    try:
        _tmp_path.write_text(_json_str, encoding="utf-8")
        _tmp_path.replace(b2b_path)
    except PermissionError:
        try:
            b2b_path.write_text(_json_str, encoding="utf-8")
        except PermissionError:
            _print(f"  WARNING: Cannot save intermediate results (file locked)")


def _run_b2b_pipeline_inner(progress_callback=None, _print=print):
    """Inner pipeline body — separated so run_b2b_pipeline can wrap it with error handling."""
    TOTAL_STEPS = 5  # search, extract, match, outreach, merge

    # ── Step 1: Search ──
    if progress_callback:
        progress_callback(0, TOTAL_STEPS, f"开始B2B搜索 (0/{len(B2B_QUERIES)} 查询)...")
    b2b_all: list[dict] = []
    seen_b2b: set[str] = set()
    for i, query in enumerate(B2B_QUERIES, 1):
        print(f"  [{i}/{len(B2B_QUERIES)}] {query[:72]}")
        try:
            results = search_google_b2b(query)
            filtered = [r for r in results
                        if not is_ecommerce_page(r["url"])
                        and not is_likely_supplier(r["title"], r["snippet"], r["url"])]
            for r in filtered:
                r["_source_query"] = query
                if r["url"] not in seen_b2b:
                    seen_b2b.add(r["url"])
                    b2b_all.append(r)
            print(f"         {len(results)} results, {len(filtered)} after filters ({len(b2b_all)} unique total)")
        except Exception as e:
            print(f"         Search error: {e}")
        if i < len(B2B_QUERIES):
            time.sleep(0.5)
        if progress_callback:
            progress_callback(0, TOTAL_STEPS, f"搜索进度: {i}/{len(B2B_QUERIES)} 查询, 已获取 {len(b2b_all)} 条结果")

    print(f"\n  {len(b2b_all)} unique B2B results to analyze...\n")

    # ── Step 2: Extract company profiles ──
    if progress_callback:
        progress_callback(1, TOTAL_STEPS, f"提取公司信息: 0/{len(b2b_all)}")
    b2b_companies: list[dict] = []
    b2b_failed = 0
    b2b_skipped = 0
    b2b_existing = _load_existing_b2b()
    for i, result in enumerate(b2b_all, 1):
        url = result.get("url", "")
        # Skip already-extracted companies (saves LLM tokens on re-runs)
        if url in b2b_existing and b2b_existing[url].get("company_name"):
            old_c = b2b_existing[url]
            old_c["snippet"] = result.get("snippet", "")
            old_c["post_date"] = result.get("date") or None
            b2b_companies.append(old_c)
            b2b_skipped += 1
            name = (old_c.get("company_name") or "?")[:30]
            print(f"  [{i:02d}/{len(b2b_all):02d}] [CACHED] {name} | {old_c.get('country') or '?'}")
            continue
        title_preview = result["title"][:55]
        print(f"  [{i:02d}/{len(b2b_all):02d}] {title_preview}", end="", flush=True)
        company, had_error = extract_b2b_company(result)
        if had_error:
            b2b_failed += 1
            print(f"\r  [{i:02d}/{len(b2b_all):02d}] API error — skipped")
        elif company:
            company["snippet"] = result.get("snippet", "")
            company["post_date"] = result.get("date") or None
            if not company.get("country"):
                company["country"] = infer_country_from_query(result.get("_source_query", ""))
            cname = company.get("company_name") or ""
            if not company.get("country") and any('\u3040' <= c <= '\u30ff' or '\u4e00' <= c <= '\u9fff' for c in cname):
                company["country"] = "Japan"
            b2b_companies.append(company)
            conf = company.get("confidence", 0)
            name = (company.get("company_name") or "?")[:30]
            print(f"\r  [{i:02d}/{len(b2b_all):02d}] [{conf}%] {name} | {company.get('country') or '?'} | {company.get('business_type','?')}")
        else:
            print(f"\r  [{i:02d}/{len(b2b_all):02d}] -- not a company")
        time.sleep(0.3)
        # Save intermediate results every 10 new extractions
        if len(b2b_companies) > 0 and len(b2b_companies) % 10 == 0:
            _save_b2b_intermediate(b2b_companies, b2b_all, _print)
        if progress_callback and (i % 5 == 0 or i == len(b2b_all)):
            progress_callback(1, TOTAL_STEPS, f"提取公司信息: {i}/{len(b2b_all)}, 已发现 {len(b2b_companies)} 家 (缓存{b2b_skipped})")

    print(f"\n  B2B Extracted: {len(b2b_companies)} companies ({b2b_skipped} cached), {b2b_failed} API failures\n")

    # Save intermediate results after extraction completes
    _save_b2b_intermediate(b2b_companies, b2b_all, _print)

    # ── Step 3: Product matching ──
    if progress_callback:
        progress_callback(2, TOTAL_STEPS, "产品匹配...")
    b2b_matched = []
    if b2b_companies:
        for c in b2b_companies:
            pf = c.get("product_focus") or ""
            c["part_type"] = pf
            c = match_product(c)
            if c.get("has_product"):
                b2b_matched.append(c)
        print(f"  B2B Product match: {len(b2b_matched)}/{len(b2b_companies)} deal in our product categories\n")

    # ── Step 4: Generate outreach drafts ──
    outreach_skipped = sum(1 for c in b2b_companies if c.get("outreach_draft"))
    if progress_callback:
        progress_callback(3, TOTAL_STEPS, f"生成开发信: {outreach_skipped}/{len(b2b_companies)}")
    if b2b_companies:
        print(f"  Generating B2B outreach drafts... ({outreach_skipped} already have drafts)\n")
        for i, c in enumerate(b2b_companies, 1):
            cname = (c.get("company_name") or "?")[:30]
            # Skip companies that already have outreach drafts (saves LLM tokens)
            if c.get("outreach_draft"):
                lang = get_email_language(c.get("country"))
                print(f"  [{i}/{len(b2b_companies)}] {cname} [{LANGUAGE_NAMES.get(lang, 'en')}] [CACHED]")
                continue
            print(f"  [{i}/{len(b2b_companies)}] {cname}", end="", flush=True)
            lang = get_email_language(c.get("country"))
            print(f" [{LANGUAGE_NAMES.get(lang, 'en')}]", end="", flush=True)
            draft = generate_b2b_outreach(c)
            c["outreach_draft"] = draft
            print(f"\r  [{i}/{len(b2b_companies)}] {cname} [{LANGUAGE_NAMES.get(lang, 'en')}] outreach generated")
            time.sleep(0.8)
            # Save intermediate results every 5 new outreach drafts
            if i % 5 == 0:
                _save_b2b_intermediate(b2b_companies, b2b_all, _print)
            if progress_callback and (i % 5 == 0 or i == len(b2b_companies)):
                progress_callback(3, TOTAL_STEPS, f"生成开发信: {i}/{len(b2b_companies)}")
        # Save after outreach completes
        _save_b2b_intermediate(b2b_companies, b2b_all, _print)
        print("")

    # ── Step 5: Merge B2B history ──
    if progress_callback:
        progress_callback(4, TOTAL_STEPS, "合并历史数据...")
    run_ts = datetime.now(timezone.utc).isoformat()
    b2b_path = Path(__file__).parent / "b2b_companies.json"
    b2b_old = {}
    if b2b_path.exists():
        try:
            old_data = json.loads(b2b_path.read_text(encoding="utf-8"))
            old_list = old_data if isinstance(old_data, list) else old_data.get("companies", [])
            b2b_old = {c.get("source_url"): c for c in old_list if c.get("source_url")}
        except (json.JSONDecodeError, FileNotFoundError):
            pass

    b2b_final = []
    for c in b2b_companies:
        url = c.get("source_url")
        if url and url in b2b_old:
            c["contacted"] = b2b_old[url].get("contacted", False)
            c["contacted_at"] = b2b_old[url].get("contacted_at")
            c["status"] = b2b_old[url].get("status", "new")
            c["notes"] = b2b_old[url].get("notes")
            # Preserve existing contact_email from history if current extraction didn't find one
            if not c.get("contact_email") and b2b_old[url].get("contact_email"):
                c["contact_email"] = b2b_old[url]["contact_email"]
        else:
            c["contacted"] = False
            c["contacted_at"] = None
            c["status"] = "new"
            c["notes"] = None
        b2b_final.append(c)

    # Re-add old contacted companies
    seen_b2b_urls = {c.get("source_url") for c in b2b_final}
    for old_c in b2b_old.values():
        if old_c.get("source_url") not in seen_b2b_urls and old_c.get("contacted"):
            b2b_final.append(old_c)

    b2b_output = {
        "run_timestamp": run_ts,
        "total_b2b_queries": len(B2B_QUERIES),
        "total_b2b_results": len(b2b_all),
        "total_companies": len(b2b_companies),
        "matched_product": len(b2b_matched),
        "companies": b2b_final,
    }
    _json_str = json.dumps(b2b_output, indent=2, ensure_ascii=False)
    # Write to temp file first, then replace — avoids PermissionError from file locks
    _tmp_path = b2b_path.with_suffix(".json.tmp")
    try:
        _tmp_path.write_text(_json_str, encoding="utf-8")
        _tmp_path.replace(b2b_path)
    except PermissionError:
        # If replace fails (file locked by editor/browser), keep the .tmp file
        # and try direct write as fallback
        try:
            b2b_path.write_text(_json_str, encoding="utf-8")
        except PermissionError:
            _print(f"  WARNING: Cannot save to {b2b_path.name} (file locked). Data saved to {_tmp_path.name}")

    # ── Summary ──
    b2b_high = [c for c in b2b_final if c.get("confidence", 0) >= 70]
    b2b_mid = [c for c in b2b_final if 40 <= c.get("confidence", 0) < 70]
    b2b_low = [c for c in b2b_final if c.get("confidence", 0) < 40]
    b2b_new = sum(1 for c in b2b_final if not c.get("contacted"))

    print("=" * 60)
    print(f"  B2B RESULTS: {len(b2b_final)} companies found")
    print(f"     High confidence: {len(b2b_high)}   Mid: {len(b2b_mid)}   Low: {len(b2b_low)}")
    print(f"     New: {b2b_new}   Previously contacted: {len(b2b_final) - b2b_new}")
    print(f"  Saved to: {b2b_path}")
    print("=" * 60)

    for c in b2b_high:
        email = c.get("contact_email") or ""
        website = c.get("website") or ""
        contacted = " [CONTACTED]" if c.get("contacted") else ""
        print(f"\n  {c.get('company_name','?')[:40]} | {c.get('country','?')} | {c.get('business_type','?')} | conf:{c.get('confidence',0)}{contacted}")
        if website:
            print(f"       Web: {website}")
        if email:
            print(f"       Email: {email}")
        print(f"       URL: {c.get('source_url','')}")

    if progress_callback:
        progress_callback(5, TOTAL_STEPS, f"完成! 发现 {len(b2b_final)} 家公司")

    return {
        "companies": b2b_final,
        "total_companies": len(b2b_companies),
        "matched_product": len(b2b_matched),
        "b2b_output": b2b_output,
        "error": None,
    }


# ─── Main pipeline ───────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Leeway Parts — Signal + B2B Extractor v3")
    print("=" * 60)

    # ═══ Step 1: Search ═══
    print(f"\nSearching {len(QUERIES)} queries via SerpAPI (past 30 days, paginated)...\n")
    all_results: list[dict] = []
    for i, query in enumerate(QUERIES, 1):
        print(f"  [{i}/{len(QUERIES)}] {query[:72]}")
        try:
            results = search_google(query, pages=2)
            filtered = [r for r in results if not is_likely_supplier(r["title"], r["snippet"], r["url"]) and not is_ecommerce_page(r["url"])]
            # Attach source query for country fallback
            for r in filtered:
                r["_source_query"] = query
            print(f"         {len(results)} results, {len(filtered)} after filters")
            all_results.extend(filtered)
        except Exception as e:
            print(f"         Search error: {e}")
        if i < len(QUERIES):
            time.sleep(0.5)

    # Deduplicate
    seen_urls: set[str] = set()
    unique: list[dict] = []
    for r in all_results:
        if r["url"] not in seen_urls:
            seen_urls.add(r["url"])
            unique.append(r)

    print(f"\n{len(unique)} unique results to analyze...\n")

    # ═══ Step 2: Extract signals ═══
    raw_signals: list[dict] = []
    failed = 0
    for i, result in enumerate(unique, 1):
        title_preview = result["title"][:55]
        print(f"  [{i:02d}/{len(unique):02d}] {title_preview}", end="", flush=True)
        signal, had_error = extract_signal(result)
        if had_error:
            failed += 1
            print(f"\r  [{i:02d}/{len(unique):02d}] API error — skipped")
        elif signal:
            signal["snippet"] = result.get("snippet", "")
            signal["post_date"] = result.get("date") or None
            signal["contact_method"] = get_contact_method(signal.get("source_url", ""))
            # Country fallback: if LLM returned null, infer from the source query
            if not signal.get("country"):
                signal["country"] = infer_country_from_query(
                    result.get("_source_query", "")
                )
            raw_signals.append(signal)
            icon = {"high": "RED", "medium": "YLW", "low": "GRN"}.get(signal.get("urgency", ""), "---")
            part_str = signal.get('part_type') or '?'
            print(f"\r  [{i:02d}/{len(unique):02d}] [{icon}] {part_str[:35]} | {signal.get('country') or '?'}")
        else:
            print(f"\r  [{i:02d}/{len(unique):02d}] -- no signal")
        time.sleep(0.3)

    print(f"\nExtracted: {len(raw_signals)} signals, {failed} API failures\n")

    # ═══ Step 3: Product matching ═══
    if not raw_signals:
        print("  No signals to match. Done.\n")
        return

    matched = []
    unmatched = []
    for s in raw_signals:
        s = match_product(s)
        if s.get("has_product"):
            matched.append(s)
        else:
            unmatched.append(s)

    print(f"Product matching: {len(matched)} matched, {len(unmatched)} not in inventory\n")

    # ═══ Step 4: Generate outreach ═══
    if matched:
        print("Generating outreach drafts for matched signals...\n")
        for i, s in enumerate(matched, 1):
            print(f"  [{i}/{len(matched)}] {s.get('part_type','?')[:40]}", end="", flush=True)
            lang = get_email_language(s.get("country"))
            print(f" [{LANGUAGE_NAMES.get(lang, 'en')}]", end="", flush=True)
            draft = generate_outreach(s)
            s["outreach_draft"] = draft
            s["priority_score"] = calculate_priority(s)
            s["tags"] = generate_tags(s)
            print(f"\r  [{i}/{len(matched)}] outreach draft generated [{LANGUAGE_NAMES.get(lang, 'en')}]")
            time.sleep(0.8)
        print("")

    # ═══ Step 4.5: Add timestamp ═══
    run_ts = datetime.now(timezone.utc).isoformat()

    # ═══ Step 5: Merge history ═══
    final_signals = merge_history(matched)

    previously_contacted = sum(1 for s in final_signals if s.get("contacted"))
    fresh = len(final_signals) - previously_contacted

    # ═══ Step 6: Output ═══
    output_path = Path(__file__).parent / "signals_output.json"
    output_data = {
        "run_timestamp": run_ts,
        "total_queries": len(QUERIES),
        "total_results": len(unique),
        "total_signals": len(raw_signals),
        "matched_signals": len(matched),
        "signals": final_signals,
    }
    output_path.write_text(json.dumps(output_data, indent=2, ensure_ascii=False), encoding="utf-8")

    # ═══════════════════════════════════════════════════════════════════
    # Pipeline B: B2B Merchant Discovery — Japan primary, Global secondary
    # ═══════════════════════════════════════════════════════════════════

    print("\n" + "=" * 60)
    print("  Pipeline B: B2B Merchant Discovery")
    print("=" * 60)

    result = run_b2b_pipeline()
    b2b_final = result["companies"]
    b2b_output = result["b2b_output"]

    b2b_high = [c for c in b2b_final if c.get("confidence", 0) >= 70]

    print("\n" + "=" * 60)
    print(f"  SIGNAL Pipeline: {len(final_signals)} leads")
    print(f"  B2B Pipeline:    {len(b2b_final)} companies ({len(b2b_high)} high-conf)")
    print(f"  Total:           {len(final_signals) + len(b2b_final)} potential contacts")
    print("=" * 60)

    # ═══ Email Outreach (NEW v3.5) ═══
    email_cfg = email_sender.load_email_config()
    if email_cfg.get("valid"):
        candidates = email_sender.get_email_candidates(final_signals, b2b_final, daily_limit=30)
        if candidates:
            print(f"\n{'='*60}")
            print(f"  EMAIL OUTREACH: {len(candidates)} candidates with email")
            print(f"  Daily quota: 30 | Already sent today: {email_sender.count_sent_today()}")
            print(f"{'='*60}")
            choice = input("\n  Send emails? [y=manual one-by-one / batch=approve all / c=CSV only / n=skip]: ").strip().lower()
            if choice == 'y':
                email_sender.manual_approve_and_send(candidates, daily_limit=30)
            elif choice in ('batch', 'b'):
                email_sender.manual_approve_and_send(candidates, daily_limit=30, batch_mode=True)
            elif choice == 'c':
                csv_path = email_sender.export_yamm_csv(candidates, "yamm_outreach.csv")
                print(f"  YAMM CSV exported: {csv_path}")
            else:
                print("  Skipping outreach.")
        else:
            print(f"  No candidates with email found — skipping outreach.")
    else:
        print(f"\n  [INFO] SMTP config not set. Add SMTP_USER and SMTP_APP_PASSWORD to demo/.env to enable email outreach.")

    # ═══ Generate viewer.html ═══
    generate_viewer(output_data, b2b_output)


# ─── Viewer generator ────────────────────────────────────────────────────

def generate_viewer(signals_output: dict, b2b_output: dict):
    """Update viewer.html with fresh embedded data from both pipelines + email stats."""
    viewer_path = Path(__file__).parent / "viewer.html"
    if not viewer_path.exists():
        print("  viewer.html not found — skipping")
        return

    # Load email log for stats
    log_path = Path(__file__).parent / "email_log.json"
    email_log = []
    sent_today = 0
    if log_path.exists():
        try:
            email_log = json.loads(log_path.read_text(encoding="utf-8"))
            from datetime import timedelta
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            for entry in email_log:
                try:
                    ts = datetime.fromisoformat(entry.get("timestamp", "").replace("Z", "+00:00"))
                    if ts >= cutoff:
                        sent_today += 1
                except Exception:
                    continue
        except Exception:
            pass

    email_stats = {
        "sent_today": sent_today,
        "daily_limit": 30,
        "remaining": max(0, 30 - sent_today),
    }

    html = viewer_path.read_text(encoding="utf-8")
    # Update both embedded datasets (multi-line JSON, DOTALL for cross-line match)
    html = re.sub(
        r'window\._EMBEDDED_DATA\s*=\s*\{.*?\};',
        f'window._EMBEDDED_DATA = {json.dumps(signals_output, ensure_ascii=False)};',
        html, count=1, flags=re.DOTALL
    )
    html = re.sub(
        r'window\._EMBEDDED_B2B_DATA\s*=\s*\{.*?\};',
        f'window._EMBEDDED_B2B_DATA = {json.dumps(b2b_output, ensure_ascii=False)};',
        html, count=1, flags=re.DOTALL
    )
    # Update email stats
    html = re.sub(
        r'window\._EMAIL_STATS\s*=\s*\{.*?\};',
        f'window._EMAIL_STATS = {json.dumps(email_stats, ensure_ascii=False)};',
        html, count=1, flags=re.DOTALL
    )
    viewer_path.write_text(html, encoding="utf-8")
    print(f"  viewer.html updated!")


if __name__ == "__main__":
    if not SERPAPI_KEY:
        raise SystemExit("SERPAPI_KEY not set in demo/.env")
    if not QWEN_API_KEY or QWEN_API_KEY == "your_qwen_api_key_here":
        raise SystemExit("QWEN_API_KEY not set in demo/.env")
    main()
