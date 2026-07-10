"""
Leeway Parts — Email Outreach Module (zero dependencies)
==========================================================
Sends personalized outreach emails via Gmail SMTP (App Password).
Supports manual approval, batch send, daily quota, and YAMM CSV export.
v3.6 — Added multilingual routing (ja/ko/id/es/en) + Qwen dynamic generation.

Usage:
    from email_sender import load_email_config, get_email_candidates, manual_approve_and_send, export_yamm_csv
"""

import os
import csv
import json
import smtplib
import io
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Lazy import website_email_scraper (avoids circular deps, only loads cache when needed)

def _load_email_cache():
    """Load cached email scrape results. Lazy import to avoid circular deps."""
    from website_email_scraper import load_email_cache as _cache
    return _cache()

# ─── Language Routing ──────────────────────────────────────────────────────

def get_email_language(country):
    """Map country to email language code: ja, ko, id, es, or en (default)."""
    if not country:
        return "en"
    c = str(country).strip().lower()
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

# ─── Qwen client (lazy init) ─────────────────────────────────────────────

_qwen_client = None

def _get_qwen():
    global _qwen_client
    if _qwen_client is None:
        from openai import OpenAI
        from dotenv import load_dotenv
        env_path = Path(__file__).parent / ".env"
        load_dotenv(env_path)
        api_key = os.getenv("QWEN_API_KEY")
        _qwen_client = OpenAI(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
    return _qwen_client

def _call_qwen(prompt, timeout=30):
    """Call Qwen-turbo for dynamic email generation."""
    try:
        client = _get_qwen()
        response = client.chat.completions.create(
            model="qwen-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=800,
            timeout=timeout,
        )
        content = response.choices[0].message.content
        return content.strip() if content else None
    except Exception as e:
        print(f"     [Qwen error] {e}")
        return None

# ─── Dynamic Email Generator ──────────────────────────────────────────────

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

6. TONE: Warm, genuine, peer-to-peer communication. No sales pitch.

7. SUBJECT LINE: Creative, genuine, natural. ABSOLUTELY NO: "high quality", "best price", "best quality", "top", "premium" in the subject.

8. LENGTH: 150-200 words (Japanese/Korean/Indonesian: similar natural length).

9. UNSUBSCRIBE FOOTER at the very end:
{unsubscribe}

Return ONLY the email text. Start with the subject line on its own line, then a blank line, then the body."""


def generate_outreach_email(item, source_type="signal"):
    """
    Generate a language-appropriate outreach email via Qwen.
    item: dict with signal or B2B company data.
    Returns: (full_email_text, language_code)
    """
    country = item.get("country") or ""
    lang = get_email_language(country)

    if source_type == "signal":
        part_type = item.get("part_type", "tractor parts")
        machine_model = item.get("machine_model", "unknown model")
        buyer_type = item.get("buyer_type", "unknown")
        contact_name = item.get("contact_name") or ""
        company_name = item.get("company_name") or ""
        matched_category = item.get("matched_category", "our parts catalog")
        draft_ref = item.get("outreach_draft") or ""
    else:
        part_type = item.get("product_focus", "agricultural machinery parts")
        machine_model = "Kubota / Yanmar / John Deere"
        buyer_type = item.get("business_type", "unknown")
        contact_name = item.get("contact_name") or item.get("company_name") or ""
        company_name = item.get("company_name") or ""
        matched_category = item.get("matched_category", "aftermarket tractor parts")
        draft_ref = ""

    prompt = OUTREACH_PROMPT.format(
        part_type=part_type,
        machine_model=machine_model,
        buyer_type=buyer_type,
        country=country,
        contact_name=contact_name,
        company_name=company_name,
        matched_category=matched_category,
        email_draft=draft_ref,
        language=LANGUAGE_NAMES.get(lang, "English"),
        unsubscribe=UNSUBSCRIBE_TEXT.get(lang, UNSUBSCRIBE_TEXT["en"]),
    )

    body = _call_qwen(prompt)
    return body, lang

# ─── Config ────────────────────────────────────────────────────────────────

EMAIL_DIR = Path(__file__).parent  # same dir as email_sender.py

def load_email_config():
    """Read SMTP credentials from .env. Returns a config dict."""
    from dotenv import load_dotenv
    env_path = EMAIL_DIR / ".env"
    load_dotenv(env_path)
    
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_APP_PASSWORD", "").strip()
    sender_name = os.getenv("SMTP_SENDER_NAME", "Leeway Parts").strip()
    
    return {
        "user": user,
        "password": password,
        "sender_name": sender_name,
        "valid": bool(user and password),
    }

# ─── Email Message Builder ────────────────────────────────────────────────

def build_email_message(to_email, subject, body, sender_email, sender_name):
    """Construct a MIME email message. Returns EmailMessage object."""
    msg = MIMEMultipart("alternative")
    msg["From"] = f"{sender_name} <{sender_email}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Reply-To"] = sender_email
    msg["Date"] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    
    # Plain text body (safe for Gmail and most clients)
    body_plain = body if body else "Please check attached file."
    msg.attach(MIMEText(body_plain, "plain", "utf-8"))
    
    return msg

# ─── Gmail SMTP Sender ────────────────────────────────────────────────────

def send_email_via_gmail(to_email, subject, body, config):
    """
    Send email via Gmail SMTP (STARTTLS, port 587).
    Returns (success: bool, error_msg: str or None).
    """
    if not config.get("valid"):
        return False, "Email config not set in .env"
    
    sender = config["user"]
    password = config["password"]
    sender_name = config.get("sender_name", "Leeway Parts")
    
    msg = build_email_message(to_email, subject, body, sender, sender_name)
    
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=30)
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, [to_email], msg.as_string())
        server.quit()
        return True, None
    except smtplib.SMTPAuthenticationError as e:
        return False, f"SMTP Auth failed (check App Password): {e}"
    except smtplib.SMTPRecipientsRefused as e:
        return False, f"Recipient refused: {e}"
    except (smtplib.SMTPConnectError, smtplib.SMTPException, socket.timeout) as e:
        # Retry once
        try:
            import time
            time.sleep(3)
            server = smtplib.SMTP("smtp.gmail.com", 587, timeout=30)
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, [to_email], msg.as_string())
            server.quit()
            return True, None
        except Exception as retry_err:
            return False, f"Network error (retry failed): {retry_err}"
    except Exception as e:
        return False, f"Unexpected error: {type(e).__name__}: {e}"

import socket

# ─── Quota Tracking ────────────────────────────────────────────────────────

LOG_PATH = EMAIL_DIR / "email_log.json"

# In-memory fallback when sandbox blocks disk writes
_email_log_memory = []

def count_sent_today():
    """Count emails sent in the last 24 hours."""
    log = []
    # Try disk first
    if LOG_PATH.exists():
        try:
            log = json.loads(LOG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    # Merge with memory fallback (sandbox may block disk writes)
    if _email_log_memory:
        log = log + _email_log_memory
    
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    count = 0
    for entry in log:
        try:
            ts = datetime.fromisoformat(entry.get("timestamp", "").replace("Z", "+00:00"))
            if ts >= cutoff:
                count += 1
        except Exception:
            continue
    return count

def log_email_sent(to_email, subject, source_type, source_url, success=True):
    """Append one entry to email_log.json (or memory fallback)."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "to": to_email,
        "subject": subject,
        "source_type": source_type,
        "source_url": source_url,
        "success": success,
    }
    
    # Try disk first
    disk_ok = False
    if LOG_PATH.exists():
        try:
            log = json.loads(LOG_PATH.read_text(encoding="utf-8"))
        except Exception:
            log = []
        log.append(entry)
        try:
            LOG_PATH.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
            disk_ok = True
        except PermissionError:
            pass  # fallback to memory
    
    if not disk_ok:
        _email_log_memory.append(entry)
        print(f"[WARN] Email logged to memory (disk write blocked): {to_email}")

# ─── Candidate Extraction ─────────────────────────────────────────────────

def get_email_candidates(signals, b2b_companies, daily_limit=30):
    """
    Extract candidates with email from both pipelines.
    Deduplicates by email address. Returns sorted list.
    
    If contact_email is missing but website exists, attempts to fill from
    the email_scrape_cache (populated by website_email_scraper).
    """
    # Load cached scraped emails
    email_cache = _load_email_cache()
    
    seen_emails = set()
    candidates = []
    
    # From signals (Pipeline A)
    for sig in signals:
        email = sig.get("contact_email")
        if not email or sig.get("contacted"):
            continue
        email_lower = email.strip().lower()
        if email_lower in seen_emails:
            continue
        seen_emails.add(email_lower)

        lang = get_email_language(sig.get("country"))
        candidates.append({
            "source_type": "signal",
            "source_url": sig.get("source_url", ""),
            "email": email,
            "name": sig.get("contact_name") or sig.get("company_name") or "",
            "subject": f"Leeway Parts — {sig.get('part_type', 'Tractor Parts')} Inquiry",
            "body": sig.get("outreach_draft") or "",
            "priority": sig.get("priority_score", 0),
            "urgency": sig.get("urgency", "low"),
            "matched_category": sig.get("matched_category", ""),
            "language": LANGUAGE_NAMES.get(lang, "English"),
            "lang_code": lang,
            "_ref": sig,
        })
    
    # From B2B (Pipeline B)
    for comp in b2b_companies:
        email = comp.get("contact_email")
        
        # Try to fill from cache if email is missing but website exists
        if not email and not comp.get("contacted"):
            website = (comp.get("website") or "").strip()
            company_name = (comp.get("company_name") or "").strip()
            if website:
                # Look up in cache by company name
                cached = email_cache.get(company_name, [])
                if cached:
                    email = cached[0]  # Use first cached email
                else:
                    # Try to find by matching domain in cache
                    for name, emails in email_cache.items():
                        if emails and website in name.lower():
                            email = emails[0]
                            break
        
        if not email or comp.get("contacted"):
            continue
        email_lower = email.strip().lower()
        if email_lower in seen_emails:
            continue
        seen_emails.add(email_lower)

        lang = get_email_language(comp.get("country"))
        candidates.append({
            "source_type": "b2b",
            "source_url": comp.get("source_url", ""),
            "email": email,
            "name": comp.get("company_name") or "",
            "subject": f"Leeway Parts — {comp.get('product_focus', 'Agricultural Parts')} Partnership",
            "body": comp.get("outreach_draft") or "",
            "priority": comp.get("confidence", 0),
            "urgency": "medium",
            "matched_category": comp.get("matched_category", ""),
            "language": LANGUAGE_NAMES.get(lang, "English"),
            "lang_code": lang,
            "_ref": comp,
        })
    
    # Sort by priority descending
    candidates.sort(key=lambda c: c["priority"], reverse=True)
    return candidates

# ─── Manual Approval & Send ───────────────────────────────────────────────

def manual_approve_and_send(candidates, daily_limit=30, batch_mode=False):
    """
    Interactive CLI approval loop.
    Returns (sent_count, skipped_count, failed_count).
    """
    config = load_email_config()
    if not config.get("valid"):
        print("  [ERROR] Email config not set. Add SMTP_USER, SMTP_APP_PASSWORD to demo/.env")
        return 0, len(candidates), 0
    
    sent = 0
    skipped = 0
    failed = 0
    remaining_quota = daily_limit - count_sent_today()
    
    if remaining_quota <= 0:
        print(f"  [ERROR] Daily limit ({daily_limit}) reached. Continue tomorrow or export to CSV.")
        return 0, len(candidates), 0
    
    if not candidates:
        print("  No candidates with email found.")
        return 0, 0, 0
    
    print(f"\n  {'─'*50}")
    print(f"  EMAIL OUTREACH — Manual Approval Mode")
    print(f"  Daily quota: {daily_limit} | Already sent: {count_sent_today()} | Remaining: {remaining_quota}")
    print(f"  Candidates: {len(candidates)}")
    print(f"  {'─'*50}")
    
    for i, c in enumerate(candidates):
        if sent >= remaining_quota:
            print(f"\n  ⚠️  Daily limit reached ({remaining_quota} sent). Stopping.")
            break
        
        print(f"\n  [{i+1}/{len(candidates)}] {c['source_type'].upper()}")
        print(f"     Name:    {c['name'][:50]}")
        print(f"     Email:   {c['email']}")
        print(f"     Subject: {c['subject'][:70]}")
        print(f"     Priority:{c['priority']}")
        print(f"     Body:    {(c['body'] or '')[:100]}...")
        
        if batch_mode:
            # In batch mode, auto-approve all
            _send_one(c, config, daily_limit)
            result_sent, result_skipped, result_failed = 1, 0, 0
        else:
            choice = input("     Send [y] / Skip [n] / Batch all [b] / Stop [q]: ").strip().lower()
            
            if choice == 'q':
                print("  Stopping outreach.")
                skipped += (len(candidates) - i)
                break
            elif choice == 'b':
                # Switch to batch mode for remaining
                print("  Switching to batch mode for remaining candidates.")
                batch_mode = True
                result_sent, result_skipped, result_failed = 0, 0, 0
            elif choice == 'y':
                result_sent, result_skipped, result_failed = _send_one(c, config, daily_limit)
            else:
                skipped += 1
                result_sent, result_skipped, result_failed = 0, 1, 0
        
        sent += result_sent
        skipped += result_skipped
        failed += result_failed
        
        if result_sent:
            remaining_quota -= 1
    
    print(f"\n  {'─'*50}")
    print(f"  EMAIL OUTREACH COMPLETE")
    print(f"     Sent:   {sent}")
    print(f"     Skipped: {skipped}")
    print(f"     Failed:  {failed}")
    print(f"  {'─'*50}")
    
    return sent, skipped, failed

def _send_one(c, config, daily_limit):
    """Send one email. Regenerates dynamic email before sending. Returns (sent, skipped, failed)."""
    # Dynamically generate email via Qwen for this specific candidate
    ref = c.get("_ref")
    source_type = c.get("source_type", "signal")
    if ref:
        print(f"     Generating dynamic email ({c.get('language', 'English')})...", end="")
        dynamic_body, lang = generate_outreach_email(ref, source_type)
        if dynamic_body:
            # Parse subject from first line
            lines = dynamic_body.strip().split("\n")
            subject = lines[0].strip()
            # Strip any "Subject:" prefix if present
            if subject.lower().startswith("subject:"):
                subject = subject[8:].strip()
            if len(subject) > 120:
                subject = subject[:117] + "..."
            c["subject"] = subject
            c["body"] = dynamic_body
            print(f" done")
        else:
            print(f" FAILED, using static draft")
            # Fall back to existing body - try to extract subject from it
            if c.get("body"):
                lines = c["body"].strip().split("\n")
                first_line = lines[0].strip()
                if first_line and not first_line.startswith(("Dear", "Hi", "Hello", "こんにちは", "안녕하세요")):
                    c["subject"] = first_line[:120]
    
    success, error = send_email_via_gmail(c["email"], c["subject"], c["body"], config)
    
    log_email_sent(c["email"], c["subject"], c["source_type"], c["source_url"], success)
    
    # Update JSON file to mark as contacted
    if success:
        ref = c.get("_ref")
        if ref:
            ref["contacted"] = True
            ref["contacted_at"] = datetime.now(timezone.utc).isoformat()
            ref["status"] = "contacted"
            if ref.get("notes") is None:
                ref["notes"] = "Email sent via demo.py"
    
    if success:
        print(f"     ✓ Sent successfully")
        return 1, 0, 0
    else:
        print(f"     ✗ Failed: {error}")
        return 0, 0, 1

# ─── YAMM CSV Export ──────────────────────────────────────────────────────

def export_yamm_csv(candidates, filepath="yamm_outreach.csv"):
    """
    Export candidates to CSV compatible with YAMM (Yet Another Mail Merge).
    Columns: Email, FirstName, LastName, Company, Subject, Body, SourceURL, Priority
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Email", "FirstName", "LastName", "Company", "Subject", "Body", "SourceURL", "Priority"])
    
    for c in candidates:
        name = c.get("name", "")
        parts = name.split() if name else []
        first = parts[0] if parts else ""
        last = " ".join(parts[1:]) if len(parts) > 1 else ""
        
        # Clean body for CSV (escape quotes, newlines)
        body = (c.get("body") or "").replace('"', '""').replace('\n', ' ')
        
        writer.writerow([
            c.get("email", ""),
            first,
            last,
            c.get("name", ""),
            c.get("subject", ""),
            body,
            c.get("source_url", ""),
            c.get("priority", 0),
        ])
    
    csv_path = EMAIL_DIR / filepath
    csv_path.write_text(output.getvalue(), encoding="utf-8")
    print(f"  YAMM CSV exported: {csv_path} ({len(candidates)} rows)")
    return csv_path
