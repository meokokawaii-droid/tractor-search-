"""
修改 server.py 和 viewer.html，让"爬取邮箱"按钮能真正刷新列表。

改动1: server.py — /api/scrape-emails 返回更新后的公司列表
改动2: viewer.html — scrapeEmails() 用返回数据刷新 allB2b 并重新渲染
"""

# ── 改动1: server.py ──
with open('server.py', 'r', encoding='utf-8') as f:
    server_code = f.read()

# 在 scrape endpoint 的两个 return 中加入 companies 字段
# Response 1: "No new companies to scrape"
old_resp1 = '''        return jsonify({
            "ok": True,
            "scraped": 0,
            "found": updated,
            "total_companies": len(b2b),
            "message": f"No new companies to scrape. Filled {updated} emails from cache."
        })'''
new_resp1 = '''        return jsonify({
            "ok": True,
            "scraped": 0,
            "found": updated,
            "total_companies": len(b2b),
            "companies": b2b,
            "message": f"No new companies to scrape. Filled {updated} emails from cache."
        })'''

if old_resp1 in server_code:
    server_code = server_code.replace(old_resp1, new_resp1)
    print("1a. server.py response 1 updated")
else:
    print("1a. WARNING: response 1 pattern not found")

# Response 2: "Scraped N companies"
old_resp2 = '''    return jsonify({
        "ok": True,
        "scraped": len(to_scrape),
        "found": found,
        "total_companies": len(b2b),
        "message": f"Scraped {len(to_scrape)} companies, found {found} new emails."
    })'''
new_resp2 = '''    return jsonify({
        "ok": True,
        "scraped": len(to_scrape),
        "found": found,
        "total_companies": len(b2b),
        "companies": b2b,
        "message": f"Scraped {len(to_scrape)} companies, found {found} new emails."
    })'''

if old_resp2 in server_code:
    server_code = server_code.replace(old_resp2, new_resp2)
    print("1b. server.py response 2 updated")
else:
    print("1b. WARNING: response 2 pattern not found")

with open('server.py', 'w', encoding='utf-8') as f:
    f.write(server_code)

# ── 改动2: viewer.html — scrapeEmails() ──
with open('viewer.html', 'r', encoding='utf-8') as f:
    html = f.read()

old_scrape = '''      if (data.ok) {
        btn.textContent = '爬取完成';
        statusEl.className = 'send-status ok';
        statusEl.textContent = data.message || ('爬取完成，找到 ' + data.found + ' 个新邮箱');
        // Reload page data to show newly found emails
        setTimeout(function() {
          loadData();
          btn.disabled = false;
          btn.textContent = '爬取邮箱';
        }, 2000);'''

new_scrape = '''      if (data.ok) {
        btn.textContent = '爬取完成';
        statusEl.className = 'send-status ok';
        statusEl.textContent = data.message || ('爬取完成，找到 ' + data.found + ' 个新邮箱');
        // Update embedded data with fresh companies from server
        if (data.companies) {
          window._EMBEDDED_B2B_DATA.companies = data.companies;
        }
        // Reload data and re-render B2B list
        setTimeout(function() {
          loadData();
          renderB2b();
          btn.disabled = false;
          btn.textContent = '爬取邮箱';
        }, 1000);'''

if old_scrape in html:
    html = html.replace(old_scrape, new_scrape)
    print("2. viewer.html scrapeEmails() updated")
else:
    print("2. WARNING: scrapeEmails pattern not found")

with open('viewer.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("\nDone! Both files updated.")
