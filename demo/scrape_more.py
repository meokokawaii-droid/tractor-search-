"""继续抓取 B2B 公司邮箱 — 带超时保护，不会卡死"""
import json, sys, os, io, socket
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Set global socket timeout (15 seconds per connection)
socket.setdefaulttimeout(15)

from website_email_scraper import scrape_company_website, load_email_cache, save_email_cache

# Load B2B data
data = json.loads(open('b2b_companies.json', encoding='utf-8').read())
companies = data.get('companies', [])

# Load cache
cache = load_email_cache()
print(f"Cache: {len(cache)} entries, {sum(1 for v in cache.values() if v)} with emails")

# Find companies that still need scraping
need_scrape = []
for c in companies:
    name = c.get('company_name', '')
    website = c.get('website', '')
    has_email = bool(c.get('contact_email'))
    in_cache = name in cache and cache[name]
    if website and not has_email and not in_cache:
        need_scrape.append(c)

print(f"Total: {len(companies)} | With email: {sum(1 for c in companies if c.get('contact_email'))} | Need scraping: {len(need_scrape)}")
print()

# Scrape one by one with timeout
found = 0
failed = 0
for i, c in enumerate(need_scrape, 1):
    name = c.get('company_name', '')
    website = c.get('website', '')
    safe_name = name[:35].encode('ascii', 'replace').decode('ascii')
    
    try:
        emails = scrape_company_website(website, name)
        cache[name] = emails
        save_email_cache(cache)
        
        if emails:
            c['contact_email'] = emails[0]
            found += 1
            print(f"  [{i}/{len(need_scrape)}] {safe_name} -> {emails[0]}")
        else:
            failed += 1
            print(f"  [{i}/{len(need_scrape)}] {safe_name} -> (no email found)")
    except Exception as e:
        failed += 1
        cache[name] = []
        save_email_cache(cache)
        err = str(e)[:50].encode('ascii', 'replace').decode('ascii')
        print(f"  [{i}/{len(need_scrape)}] {safe_name} -> ERROR: {err}")

# Save updated B2B data
data['companies'] = companies
with open('b2b_companies.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

# Summary
with_email = [c for c in companies if c.get('contact_email')]
print(f"\n{'='*55}")
print(f"  Done! Found {found} new emails, {failed} without emails")
print(f"  Total: {len(with_email)}/{len(companies)} companies now have emails")
print(f"{'='*55}")
for c in with_email:
    safe = c.get('company_name', '?')[:30].encode('ascii','replace').decode('ascii')
    print(f"  {safe} | {c.get('contact_email')} | {c.get('country','?')}")
