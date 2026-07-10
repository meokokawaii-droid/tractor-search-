"""
更新 viewer.html:
1. 用最新的 b2b_companies.json 替换嵌入数据
2. 修改排序逻辑：有邮箱的排前面（加分），再按原分数排序
3. 确保 B2B 卡片上显示邮箱地址
"""
import json, re, io

# Read viewer.html
with open('viewer.html', 'r', encoding='utf-8') as f:
    html = f.read()

# ── 1. Replace embedded B2B data ──
with open('b2b_companies.json', 'r', encoding='utf-8') as f:
    b2b_data = json.load(f)

b2b_json = json.dumps(b2b_data, ensure_ascii=False)
# Replace the _EMBEDDED_B2B_DATA assignment (line 350)
# Pattern: window._EMBEDDED_B2B_DATA = {...everything until the next newline that starts with non-JSON...
html = re.sub(
    r'window\._EMBEDDED_B2B_DATA\s*=\s*\{.*?\}\s*;',
    f'window._EMBEDDED_B2B_DATA = {b2b_json};',
    html,
    count=1,
    flags=re.DOTALL
)

print("1. B2B embedded data updated")

# ── 2. Fix signal sorting: email first, then priority_score ──
old_signal_sort = "filtered.sort(function(a, b) { return (b.priority_score || 0) - (a.priority_score || 0); });"
new_signal_sort = """filtered.sort(function(a, b) {
        var aEmail = a.contact_email ? 1 : 0;
        var bEmail = b.contact_email ? 1 : 0;
        if (aEmail !== bEmail) return bEmail - aEmail;
        return (b.priority_score || 0) - (a.priority_score || 0);
    });"""

if old_signal_sort in html:
    html = html.replace(old_signal_sort, new_signal_sort)
    print("2. Signal sorting updated (email first, then priority)")
else:
    print("2. WARNING: Signal sort pattern not found")

# ── 3. Fix B2B sorting: email first, then confidence ──
old_b2b_sort = "filtered.sort(function(a, b) { return (b.confidence || 0) - (a.confidence || 0); });"
new_b2b_sort = """filtered.sort(function(a, b) {
        var aEmail = a.contact_email ? 1 : 0;
        var bEmail = b.contact_email ? 1 : 0;
        if (aEmail !== bEmail) return bEmail - aEmail;
        return (b.confidence || 0) - (a.confidence || 0);
    });"""

if old_b2b_sort in html:
    html = html.replace(old_b2b_sort, new_b2b_sort)
    print("3. B2B sorting updated (email first, then confidence)")
else:
    print("3. WARNING: B2B sort pattern not found")

# ── 4. Add email badge to signal cards (if not already showing) ──
# Check current signal card email display
# From grep: line 822-824 shows email button only if contact_email exists
# Let's also add a visible email tag on the card even if not sendable

# Find the signal card rendering and add email display
# The current code at ~line 817 shows priority score
# Let's add email display next to it
old_score_line = """var score = s.priority_score != null ? '<span class="score">评分 <strong>' + s.priority_score + '</strong></span>' : '';"""
new_score_line = """var score = s.priority_score != null ? '<span class="score">评分 <strong>' + s.priority_score + '</strong></span>' : '';
        var emailTag = s.contact_email ? '<span class="tag contact">📧 ' + esc(s.contact_email) + '</span>' : '<span class="tag" style="color:#999">无邮箱</span>';"""

if old_score_line in html:
    html = html.replace(old_score_line, new_score_line)
    print("4. Email tag added to signal cards")
else:
    print("4. WARNING: Signal score line not found")

# Also add the emailTag to the card HTML
# Find where score is used in the card HTML
old_card_score = """+ score"""
new_card_score = """+ score + emailTag"""
# This might match multiple places, so we need to be careful
# Let's count occurrences
count = html.count(old_card_score)
if count == 1:
    html = html.replace(old_card_score, new_card_score)
    print("5. Email tag inserted into signal card HTML")
elif count > 1:
    print(f"5. WARNING: {count} matches for card score, skipping auto-insert")
else:
    print("5. WARNING: Card score pattern not found")

# ── 6. Write updated file ──
with open('viewer.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("\nviewer.html updated successfully!")
print(f"File size: {len(html):,} bytes")
