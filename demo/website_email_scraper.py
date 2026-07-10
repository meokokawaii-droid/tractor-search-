"""
Leeway Parts — Website Email Scraper
=====================================
Extracts contact emails from company websites.
Uses only stdlib (urllib, re, ssl, socket) — zero dependencies.

Usage:
    from website_email_scraper import scrape_emails_for_companies, load_email_cache, save_email_cache
    
    companies = [...]  # from b2b_companies.json
    results = scrape_emails_for_companies(companies)
    # results = {"Company Name": ["email1@example.com", ...], ...}
"""

import re
import ssl
import json
import time
import socket
from pathlib import Path
from urllib import request, error, parse

# ─── Configuration ────────────────────────────────────────────────────────

TIMEOUT_SECONDS = 5
DELAY_SECONDS = 0.5
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

# Common contact page paths to try
CONTACT_PATHS = [
    "/contact",
    "/contact-us",
    "/about",
    "/about-us",
    "/en/contact",
    "/en/contact-us",
    "/company",
    "/support",
    "/help",
]

# Email regex pattern
EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)

# Fake / placeholder emails to ignore
FAKE_EMAILS = {
    "example.com",
    "test.com",
    "domain.com",
    "yourdomain.com",
    "company.com",
    "email.com",
    "mail.com",
    "gmail.com",  # Keep gmail emails, but filter specific fake ones
}

FAKE_PREFIXES = {
    "example@",
    "test@",
    "admin@example",
    "info@example",
    "contact@example",
    "noreply@example",
    "sales@example",
    "support@example",
}

# ─── SSL Context ─────────────────────────────────────────────────────────

_ssl_ctx = None

def _get_ssl_ctx():
    global _ssl_ctx
    if _ssl_ctx is None:
        _ssl_ctx = ssl.create_default_context()
        _ssl_ctx.check_hostname = False
        _ssl_ctx.verify_mode = ssl.CERT_NONE
    return _ssl_ctx

# ─── Cache ─────────────────────────────────────────────────────────────────

CACHE_FILE = Path(__file__).parent / "email_scrape_cache.json"

def load_email_cache():
    """Load cached scrape results."""
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def save_email_cache(cache):
    """Save scrape results to cache."""
    _tmp = CACHE_FILE.with_suffix(".json.tmp")
    try:
        _tmp.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
        _tmp.replace(CACHE_FILE)
    except PermissionError:
        pass  # File locked — skip cache save

def clear_email_cache():
    """Remove cache file."""
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()

# ─── Core Scraping ───────────────────────────────────────────────────────────

def _fetch_url(url):
    """
    Fetch a URL and return (html_text, success).
    Handles redirects, SSL, timeouts, and encoding.
    """
    try:
        req = request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "identity",
                "Connection": "keep-alive",
            },
        )
        
        response = request.urlopen(req, timeout=TIMEOUT_SECONDS, context=_get_ssl_ctx())
        
        # Read raw bytes
        raw = response.read()
        
        # Try to detect encoding from headers or meta
        charset = response.headers.get_content_charset()
        if not charset:
            # Try meta tag detection
            meta_match = re.search(rb'<meta[^>]+charset=["\']?([^"\'>\s]+)', raw, re.IGNORECASE)
            if meta_match:
                charset = meta_match.group(1).decode('ascii', errors='ignore')
        
        # Decode
        try:
            html = raw.decode(charset or "utf-8", errors="replace")
        except (LookupError, TypeError):
            html = raw.decode("utf-8", errors="replace")
        
        return html, True
        
    except error.HTTPError as e:
        # Some 403/404 errors might still return HTML
        if e.code in (403, 404, 500, 502, 503):
            try:
                raw = e.read()
                html = raw.decode("utf-8", errors="replace")
                return html, False  # Mark as failed but still return HTML
            except Exception:
                pass
        return "", False
    except (error.URLError, socket.timeout, socket.error, Exception):
        return "", False


def _extract_emails(html):
    """
    Extract email addresses from HTML text.
    Returns deduplicated list of valid emails.
    """
    if not html:
        return []
    
    # Remove common HTML tags that might contain false emails
    # But keep text content
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    
    # Find all emails
    matches = EMAIL_PATTERN.findall(text)
    
    # Filter and deduplicate
    seen = set()
    emails = []
    for email in matches:
        email_lower = email.lower().strip()
        
        # Skip if already seen
        if email_lower in seen:
            continue
        seen.add(email_lower)
        
        # Skip common image host / CDN domains
        if any(domain in email_lower for domain in [
            "w3.org", "schema.org", "google.com", "facebook.com",
            "twitter.com", "instagram.com", "linkedin.com", "youtube.com",
            "github.com", "stackoverflow.com", "amazon.com",
        ]):
            continue
        
        # Skip obvious fake emails
        is_fake = False
        for prefix in FAKE_PREFIXES:
            if email_lower.startswith(prefix.lower()):
                is_fake = True
                break
        if is_fake:
            continue
        
        # Skip if domain is in fake list
        domain = email_lower.split("@")[-1]
        if domain in FAKE_EMAILS:
            continue
        
        # Skip if looks like a CSS class or variable (contains @ but not email)
        if ".." in email_lower or "//" in email_lower:
            continue
        
        # Must have valid TLD (at least 2 chars)
        if len(domain.split(".")[-1]) < 2:
            continue
        
        emails.append(email)
    
    return emails


def _normalize_website(website):
    """
    Normalize a website URL. Ensure it has scheme and no trailing path.
    """
    if not website:
        return None
    
    w = website.strip().lower()
    
    # Remove common prefixes that aren't part of the domain
    if w.startswith("http://"):
        w = w[7:]
    elif w.startswith("https://"):
        w = w[8:]
    if w.startswith("www."):
        w = w[4:]
    
    # Remove trailing slashes and paths
    w = w.split("/")[0].strip()
    
    if not w:
        return None
    
    return f"https://{w}"


def scrape_company_website(website, company_name=""):
    """
    Scrape emails from a company website.
    Tries homepage first, then common contact pages.
    Returns deduplicated list of emails found.
    """
    base_url = _normalize_website(website)
    if not base_url:
        return []
    
    all_emails = []
    urls_to_try = [base_url]
    
    # Add contact page variations
    for path in CONTACT_PATHS:
        urls_to_try.append(f"{base_url}{path}")
    
    for url in urls_to_try:
        html, success = _fetch_url(url)
        if html:
            emails = _extract_emails(html)
            all_emails.extend(emails)
        
        # If we found emails on the first page, we can stop early
        # But still try contact pages as they often have more specific emails
        if len(all_emails) >= 3 and url == base_url:
            # Found enough on homepage, still try 1 contact page
            pass
        
        time.sleep(DELAY_SECONDS)
    
    # Deduplicate while preserving order
    seen = set()
    unique_emails = []
    for email in all_emails:
        lower = email.lower()
        if lower not in seen:
            seen.add(lower)
            unique_emails.append(email)
    
    return unique_emails


# ─── Batch Processing ────────────────────────────────────────────────────

def scrape_emails_for_companies(companies, use_cache=True, progress_callback=None):
    """
    Scrape emails for a list of companies.
    
    Args:
        companies: List of dicts with 'company_name' and 'website' keys.
        use_cache: Whether to use cached results and skip already-scraped companies.
        progress_callback: Optional function(current, total, company_name) for progress updates.
    
    Returns:
        Dict mapping company_name -> list of emails found.
    """
    cache = load_email_cache() if use_cache else {}
    results = {}
    total = len(companies)
    
    for i, comp in enumerate(companies):
        name = comp.get("company_name", "").strip()
        website = comp.get("website", "")
        
        if not name or not website:
            continue
        
        # Check cache
        if use_cache and name in cache:
            results[name] = cache[name]
            if progress_callback:
                progress_callback(i + 1, total, name)
            continue
        
        # Scrape
        emails = scrape_company_website(website, name)
        results[name] = emails
        
        # Update cache immediately
        if use_cache:
            cache[name] = emails
            save_email_cache(cache)
        
        if progress_callback:
            progress_callback(i + 1, total, name)
    
    return results


# ─── CLI / Standalone ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import json as json_mod
    
    # Load b2b_companies.json
    demo_dir = Path(__file__).parent
    b2b_path = demo_dir / "b2b_companies.json"
    
    if not b2b_path.exists():
        print(f"  [ERROR] File not found: {b2b_path}")
        sys.exit(1)
    
    data = json_mod.loads(b2b_path.read_text(encoding="utf-8"))
    companies = data.get("companies", []) if isinstance(data, dict) else data
    
    # Only companies with website
    with_website = [c for c in companies if c.get("website")]
    print(f"  Found {len(with_website)} companies with website (out of {len(companies)} total)")
    print(f"  Starting scrape... (Ctrl+C to interrupt, progress saved to cache)")
    print()
    
    total = len(with_website)
    found_count = 0
    
    def show_progress(current, total, name):
        pct = int(current / total * 100)
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        print(f"  [{bar}] {pct}% | {current}/{total} | {name[:40]}", end="\r")
    
    try:
        results = scrape_emails_for_companies(with_website, use_cache=True, progress_callback=show_progress)
    except KeyboardInterrupt:
        print("\n\n  [Interrupted] Progress saved to cache.")
        sys.exit(0)
    
    print()  # New line after progress bar
    print()
    
    # Summary
    for name, emails in results.items():
        if emails:
            found_count += 1
    
    print(f"  Done! Found emails for {found_count}/{total} companies")
    print()
    
    # Show details
    for name, emails in results.items():
        if emails:
            print(f"  ✓ {name}: {', '.join(emails[:3])}")
    
    print()
    print(f"  Cache saved to: {CACHE_FILE}")
