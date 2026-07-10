"""继续抓取 B2B 公司邮箱 — 输出到文件避免编码问题"""
import json, sys, os, socket

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
socket.setdefaulttimeout(15)

from website_email_scraper import scrape_company_website, load_email_cache, save_email_cache

LOG = open('scrape_log.txt', 'w', encoding='utf-8')
def log(msg):
    LOG.write(msg + '\n')
    LOG.flush()

# Load B2B data
data = json.loads(open('b2b_companies.json', encoding='utf-8').read())
companies = data.get('companies', [])

# Load cache
cache = load_email_cache()
log(f"Cache: {len(cache)} entries, {sum(1 for v in cache.values() if v)} with emails")

# Find companies that still need scraping
need_scrape = []
for c in companies:
    name = c.get('company_name', '')
    website = c.get('website', '')
    has_email = bool(c.get('contact_email'))
    in_cache = name in cache and cache[name]
    if website and not has_email and not in_cache:
        need_scrape.append(c)

total_with = sum(1 for c in companies if c.get('contact_email'))
log(f"Total: {len(companies)} | With email: {total_with} | Need scraping: {len(need_scrape)}")
log("")

# Scrape one by one
found = 0
failed = 0
for i, c in enumerate(need_scrape, 1):
    name = c.get('company_name', '')
    website = c.get('website', '')
    
    try:
        emails = scrape_company_website(website, name)
        cache[name] = emails
        save_email_cache(cache)
        
        if emails:
            c['contact_email'] = emails[0]
            found += 1
            log(f"  [{i}/{len(need_scrape)}] {name[:35]} -> {emails[0]}")
        else:
            failed += 1
            log(f"  [{i}/{len(need_scrape)}] {name[:35]} -> (no email)")
    except Exception as e:
        failed += 1
        cache[name] = []
        save_email_cache(cache)
        log(f"  [{i}/{len(need_scrape)}] {name[:35]} -> ERROR: {str(e)[:50]}")

# Save updated B2B data
data['companies'] = companies
with open('b2b_companies.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

# Summary
with_email = [c for c in companies if c.get('contact_email')]
log(f"\n{'='*55}")
log(f"  Done! Found {found} new, {failed} without emails")
log(f"  Total: {len(with_email)}/{len(companies)} companies now have emails")
log(f"{'='*55}")
for c in with_email:
    log(f"  {c.get('company_name', '?')[:30]} | {c.get('contact_email')} | {c.get('country','?')}")

LOG.close()
