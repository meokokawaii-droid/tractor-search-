"""用缓存的邮箱更新 b2b_companies.json，然后修改 viewer.html 排序"""
import json, sys, os, io
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Load cache
try:
    cache = json.loads(open('email_scrape_cache.json', encoding='utf-8').read())
except FileNotFoundError:
    cache = {}

print(f"Cache entries: {len(cache)}, with emails: {sum(1 for v in cache.values() if v)}")

# Load B2B data
data = json.loads(open('b2b_companies.json', encoding='utf-8').read())
companies = data.get('companies', [])

# Update with cached emails
updated = 0
for c in companies:
    name = c.get('company_name', '')
    if name in cache and cache[name] and not c.get('contact_email'):
        c['contact_email'] = cache[name][0]
        updated += 1

print(f"Updated {updated} companies with cached emails")

# Save
data['companies'] = companies
with open('b2b_companies.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

with_email = [c for c in companies if c.get('contact_email')]
print(f"Final: {len(with_email)}/{len(companies)} companies have emails")
for c in with_email:
    safe = c.get('company_name', '?')[:30].encode('ascii','replace').decode('ascii')
    print(f"  {safe} | {c.get('contact_email')} | {c.get('country','?')}")
