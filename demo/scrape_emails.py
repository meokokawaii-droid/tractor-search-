"""为 B2B 公司批量抓取网站邮箱，更新 b2b_companies.json"""
import json, sys, os, io
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from website_email_scraper import scrape_emails_for_companies

# Load B2B data
data = json.loads(open('b2b_companies.json', encoding='utf-8').read())
companies = data.get('companies', [])
print(f"Loaded {len(companies)} B2B companies")

# Count those with websites but no email
need_scrape = [c for c in companies if c.get('website') and not c.get('contact_email')]
print(f"{len(need_scrape)} companies have website but no email - will scrape")

# Run scraper
def progress(idx, total, name):
    safe_name = name[:40].encode('ascii', 'replace').decode('ascii')
    print(f"  [{idx}/{total}] {safe_name}")

email_map = scrape_emails_for_companies(need_scrape, use_cache=True, progress_callback=progress)

# Update companies with scraped emails
updated = 0
for c in companies:
    name = c.get('company_name', '')
    if name in email_map and email_map[name]:
        c['contact_email'] = email_map[name][0]
        updated += 1

print(f"\nUpdated {updated} companies with scraped emails")

# Save
data['companies'] = companies
with open('b2b_companies.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
print("Saved to b2b_companies.json")

# Summary
with_email = [c for c in companies if c.get('contact_email')]
print(f"\nFinal: {len(with_email)}/{len(companies)} companies now have emails")
for c in with_email:
    cn = c.get('company_name', '?')[:30]
    em = c.get('contact_email', '')
    co = c.get('country', '?')
    safe_cn = cn.encode('ascii', 'replace').decode('ascii')
    print(f"  - {safe_cn} | {em} | {co}")
