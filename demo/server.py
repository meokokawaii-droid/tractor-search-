"""
Leeway Parts — Email Outreach Server (Flask)
=============================================
Lightweight local server for one-click email sending from viewer.html.

Start: python server.py
Access: http://localhost:5010

Endpoints:
  GET  /api/quota       — daily quota status
  GET  /api/candidates  — list email candidates
  POST /api/send-one    — send single email {url, source_type}
  POST /api/send-batch  — send multiple emails [{url, source_type}, ...]
  GET  /api/yamm-csv    — download YAMM CSV
  GET  /                — serve viewer.html
"""

import os
import sys
import json
import io
import csv as csv_module
import threading
import uuid
import traceback
import logging
from pathlib import Path

# Fix Windows console encoding — Japanese/Chinese chars crash GBK stdout
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add current dir to path so imports work
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from flask import Flask, jsonify, request, send_file, send_from_directory
from datetime import datetime, timezone

app = Flask(__name__, static_folder=str(HERE))

# ─── Import email & scraper modules ───────────────────────────────────────

from email_sender import (
    load_email_config,
    get_email_candidates,
    send_email_via_gmail,
    count_sent_today,
    log_email_sent,
    export_yamm_csv,
    generate_outreach_email,
    UNSUBSCRIBE_TEXT,
    LANGUAGE_NAMES,
    get_email_language,
)
from website_email_scraper import (
    scrape_emails_for_companies,
    load_email_cache,
    save_email_cache,
)

DAILY_LIMIT = 30

# ─── B2B Refresh Task State ──────────────────────────────────────────────
_refresh_state = {
    "task_id": None,
    "status": "idle",          # idle | running | completed | error
    "progress_pct": 0,         # 0-100
    "message": "",
    "companies_found": 0,
    "emails_found": 0,
    "started_at": None,
    "completed_at": None,
    "error": None,
}
_refresh_lock = threading.Lock()

# ─── Helper: load data from JSON files ────────────────────────────────────

def _load_signals():
    path = HERE / "signals_output.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("signals", []) if isinstance(data, dict) else data
    except Exception:
        return []

def _load_b2b():
    path = HERE / "b2b_companies.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("companies", []) if isinstance(data, dict) else data
    except Exception:
        return []

def _save_signals(signals):
    path = HERE / "signals_output.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["signals"] = signals
        except Exception:
            data = {"signals": signals}
    else:
        data = {"signals": signals}
    try:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except PermissionError:
        print(f"[WARN] Cannot write {path} (sandbox). Skipping save.")

def _save_b2b(companies):
    path = HERE / "b2b_companies.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["companies"] = companies
        except Exception:
            data = {"companies": companies}
    else:
        data = {"companies": companies}
    try:
        _tmp = path.with_suffix(".json.tmp")
        _tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        _tmp.replace(path)
    except PermissionError:
        print(f"[WARN] Cannot write {path} (file locked). Skipping save.")

# ─── API: Quota ───────────────────────────────────────────────────────────

@app.route("/api/quota")
def api_quota():
    sent = count_sent_today()
    return jsonify({
        "sent_today": sent,
        "daily_limit": DAILY_LIMIT,
        "remaining": max(0, DAILY_LIMIT - sent),
        "ok": sent < DAILY_LIMIT,
    })

# ─── API: Candidates ──────────────────────────────────────────────────────

@app.route("/api/candidates")
def api_candidates():
    signals = _load_signals()
    b2b = _load_b2b()
    candidates = get_email_candidates(signals, b2b, daily_limit=DAILY_LIMIT)

    result = []
    for c in candidates:
        url = c.get("source_url", "")
        key = f"{url}"
        # Check if already sent in localStorage (handled by frontend)
        result.append({
            "source_url": url,
            "source_type": c.get("source_type", ""),
            "email": c.get("email", ""),
            "name": c.get("name", ""),
            "subject": c.get("subject", ""),
            "body_preview": (c.get("body") or "")[:120],
            "priority": c.get("priority", 0),
            "language": c.get("language", "English"),
            "lang_code": c.get("lang_code", "en"),
            "matched_category": c.get("matched_category", ""),
        })

    return jsonify({"candidates": result, "total": len(result)})

def _find_item(source_url, source_type):
    """Find item by source_url in signals or b2b data."""
    if source_type == "signal":
        for s in _load_signals():
            if s.get("source_url") == source_url:
                return s, "signal"
    else:
        for c in _load_b2b():
            if c.get("source_url") == source_url:
                return c, "b2b"
    return None, None


# ─── API: Preview Email ─────────────────────────────────────────────────

@app.route("/api/preview-email", methods=["POST"])
def api_preview_email():
    data = request.get_json() or {}
    source_url = data.get("source_url")
    source_type = data.get("source_type", "b2b")

    if not source_url:
        return jsonify({"ok": False, "error": "Missing source_url"}), 400

    item, _ = _find_item(source_url, source_type)
    if not item:
        return jsonify({"ok": False, "error": "Item not found"}), 404

    body, lang = generate_outreach_email(item, source_type)
    if not body:
        return jsonify({"ok": False, "error": "AI generation failed"}), 500

    lines = body.strip().split("\n")
    subject = lines[0].strip() if lines else "Leeway Parts Outreach"
    if subject.lower().startswith("subject:"):
        subject = subject[8:].strip()

    return jsonify({
        "ok": True,
        "subject": subject,
        "body": body,
        "language": LANGUAGE_NAMES.get(lang, "English"),
        "lang_code": lang,
    })


# ─── API: Send One ────────────────────────────────────────────────────────

@app.route("/api/send-one", methods=["POST"])
def api_send_one():
    data = request.get_json() or {}
    source_url = data.get("source_url", "")
    source_type = data.get("source_type", "signal")

    if not source_url:
        return jsonify({"ok": False, "error": "Missing source_url"}), 400

    # Check quota
    sent_today = count_sent_today()
    if sent_today >= DAILY_LIMIT:
        return jsonify({"ok": False, "error": f"Daily limit ({DAILY_LIMIT}) reached"}), 429

    # Find the item
    item = None
    if source_type == "signal":
        for s in _load_signals():
            if s.get("source_url") == source_url:
                item = s
                break
    else:
        for c in _load_b2b():
            if c.get("source_url") == source_url:
                item = c
                break

    if not item:
        return jsonify({"ok": False, "error": "Item not found"}), 404

    email = item.get("contact_email")
    if not email:
        return jsonify({"ok": False, "error": "No email for this item"}), 400

    # Generate dynamic email
    dynamic_body, lang = generate_outreach_email(item, source_type)
    if not dynamic_body:
        return jsonify({"ok": False, "error": "Email generation failed"}), 500

    # Parse subject from first line
    lines = dynamic_body.strip().split("\n")
    subject = lines[0].strip()
    if subject.lower().startswith("subject:"):
        subject = subject[8:].strip()
    if len(subject) > 120:
        subject = subject[:117] + "..."

    # Send
    config = load_email_config()
    success, error = send_email_via_gmail(email, subject, dynamic_body, config)

    if success:
        log_email_sent(email, subject, source_type, source_url, True)
        # Mark as contacted in JSON
        item["contacted"] = True
        item["contacted_at"] = datetime.now(timezone.utc).isoformat()
        item["status"] = "contacted"
        if item.get("notes") is None:
            item["notes"] = "Email sent via viewer"
        # Save back
        if source_type == "signal":
            signals = _load_signals()
            for i, s in enumerate(signals):
                if s.get("source_url") == source_url:
                    signals[i] = item
                    break
            _save_signals(signals)
        else:
            companies = _load_b2b()
            for i, c in enumerate(companies):
                if c.get("source_url") == source_url:
                    companies[i] = item
                    break
            _save_b2b(companies)

        return jsonify({
            "ok": True,
            "message": f"Sent to {email}",
            "subject": subject,
            "body": dynamic_body,
            "language": LANGUAGE_NAMES.get(lang, "English"),
            "remaining_quota": max(0, DAILY_LIMIT - count_sent_today()),
        })
    else:
        log_email_sent(email, subject, source_type, source_url, False)
        return jsonify({"ok": False, "error": error or "Send failed"}), 500

# ─── API: Send Batch ──────────────────────────────────────────────────────

@app.route("/api/send-batch", methods=["POST"])
def api_send_batch():
    data = request.get_json() or {}
    items_list = data.get("items", [])

    if not items_list:
        return jsonify({"ok": False, "error": "Empty items list"}), 400

    config = load_email_config()
    results = []
    sent = 0
    failed = 0

    for item_data in items_list:
        source_url = item_data.get("source_url", "")
        source_type = item_data.get("source_type", "signal")

        # Check quota
        if count_sent_today() >= DAILY_LIMIT:
            results.append({"source_url": source_url, "ok": False, "error": "Quota reached"})
            failed += 1
            continue

        # Find item
        item = None
        if source_type == "signal":
            for s in _load_signals():
                if s.get("source_url") == source_url:
                    item = s
                    break
        else:
            for c in _load_b2b():
                if c.get("source_url") == source_url:
                    item = c
                    break

        if not item:
            results.append({"source_url": source_url, "ok": False, "error": "Not found"})
            failed += 1
            continue

        email = item.get("contact_email")
        if not email:
            results.append({"source_url": source_url, "ok": False, "error": "No email"})
            failed += 1
            continue

        # Generate & send
        dynamic_body, lang = generate_outreach_email(item, source_type)
        if not dynamic_body:
            results.append({"source_url": source_url, "ok": False, "error": "Generation failed"})
            failed += 1
            continue

        lines = dynamic_body.strip().split("\n")
        subject = lines[0].strip()
        if subject.lower().startswith("subject:"):
            subject = subject[8:].strip()
        if len(subject) > 120:
            subject = subject[:117] + "..."

        success, error = send_email_via_gmail(email, subject, dynamic_body, config)
        log_email_sent(email, subject, source_type, source_url, success)

        if success:
            item["contacted"] = True
            item["contacted_at"] = datetime.now(timezone.utc).isoformat()
            item["status"] = "contacted"
            if item.get("notes") is None:
                item["notes"] = "Email sent via viewer"
            sent += 1
            results.append({
                "source_url": source_url,
                "ok": True,
                "email": email,
                "language": LANGUAGE_NAMES.get(lang, "English"),
            })
        else:
            failed += 1
            results.append({"source_url": source_url, "ok": False, "error": error or "Send failed"})

    # Save updates
    if source_type == "signal":
        _save_signals(_load_signals())
    # For mixed types, save both
    _save_signals(_load_signals())
    _save_b2b(_load_b2b())

    return jsonify({
        "ok": True,
        "sent": sent,
        "failed": failed,
        "remaining": max(0, DAILY_LIMIT - count_sent_today()),
        "results": results,
    })

# ─── API: Scrape Emails from Websites ─────────────────────────────────────

@app.route("/api/scrape-emails", methods=["POST"])
def api_scrape_emails():
    """
    Scrape emails from company websites for B2B companies that lack contact_email.
    Returns the number of new emails found.
    """
    b2b = _load_b2b()
    
    # Find companies without email but with website
    to_scrape = []
    for comp in b2b:
        if not comp.get("contact_email") and comp.get("website") and not comp.get("contacted"):
            to_scrape.append(comp)
    
    if not to_scrape:
        # Even if nothing to scrape, try to refresh from cache
        email_cache = load_email_cache()
        updated = 0
        for comp in b2b:
            if not comp.get("contact_email") and comp.get("company_name") in email_cache:
                emails = email_cache[comp.get("company_name")]
                if emails:
                    comp["contact_email"] = emails[0]
                    updated += 1
        if updated > 0:
            _save_b2b(b2b)
        return jsonify({
            "ok": True,
            "scraped": 0,
            "found": updated,
            "total_companies": len(b2b),
            "companies": b2b,
            "message": f"No new companies to scrape. Filled {updated} emails from cache."
        })
    
    # Scrape emails
    try:
        results = scrape_emails_for_companies(to_scrape, use_cache=True)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    
    # Update b2b_companies.json with found emails
    found = 0
    for comp in b2b:
        name = comp.get("company_name", "").strip()
        if name in results and results[name]:
            if not comp.get("contact_email"):
                comp["contact_email"] = results[name][0]
                found += 1
    
    _save_b2b(b2b)
    
    return jsonify({
        "ok": True,
        "scraped": len(to_scrape),
        "found": found,
        "total_companies": len(b2b),
        "companies": b2b,
        "message": f"Scraped {len(to_scrape)} companies, found {found} new emails."
    })

# ─── API: Refresh B2B (background pipeline) ──────────────────────────────

def _run_b2b_refresh_task(task_id):
    """Background thread: run B2B pipeline + email scraping."""
    try:
        # Lazy import to avoid crashing server if API keys are missing at startup
        from demo import run_b2b_pipeline

        # Step 1: Run B2B pipeline with progress callback
        def _progress_callback(step, total_steps, message):
            with _refresh_lock:
                if _refresh_state["task_id"] != task_id:
                    return  # Stale task, ignore
                pct = int(((step + 1) / (total_steps + 1)) * 80)  # Pipeline = 80% of total
                _refresh_state.update({
                    "progress_pct": min(pct, 80),
                    "message": message,
                })

        result = run_b2b_pipeline(progress_callback=_progress_callback)

        if result.get("error"):
            with _refresh_lock:
                _refresh_state.update({
                    "status": "error",
                    "progress_pct": 0,
                    "message": result["error"][:200],
                    "error": result["error"][:500],
                    "traceback": result.get("traceback", "")[:3000],
                })
            return

        b2b_companies = result["companies"]

        with _refresh_lock:
            _refresh_state["companies_found"] = len(b2b_companies)

        # Step 2: Auto-scrape emails for companies without email
        with _refresh_lock:
            _refresh_state.update({
                "progress_pct": 82,
                "message": "爬取网站邮箱...",
            })

        b2b_data = _load_b2b()
        to_scrape = [c for c in b2b_data if not c.get("contact_email") and c.get("website") and not c.get("contacted")]

        found_emails = 0
        if to_scrape:
            def _scrape_progress(current, total, name):
                with _refresh_lock:
                    pct = 80 + int((current / total) * 18)  # Scraping = 18%
                    _refresh_state.update({
                        "progress_pct": min(pct, 98),
                        "message": f"爬取邮箱: {current}/{total} ({name[:30]})",
                    })

            scrape_results = scrape_emails_for_companies(to_scrape, use_cache=True, progress_callback=_scrape_progress)

            # Update b2b_companies.json with scraped emails
            for comp in b2b_data:
                name = comp.get("company_name", "").strip()
                if name in scrape_results and scrape_results[name]:
                    if not comp.get("contact_email"):
                        comp["contact_email"] = scrape_results[name][0]
                        found_emails += 1
            _save_b2b(b2b_data)

        with _refresh_lock:
            _refresh_state["emails_found"] = found_emails

        # Step 3: Complete
        with _refresh_lock:
            _refresh_state.update({
                "status": "completed",
                "progress_pct": 100,
                "message": f"完成! 发现 {len(b2b_companies)} 家公司, 新增 {found_emails} 个邮箱",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })

    except Exception as e:
        error_msg = str(e)
        full_traceback = traceback.format_exc()
        # Try to write log file (may fail due to sandbox/permissions)
        log_path = HERE / "refresh_error.log"
        try:
            with open(str(log_path), "w", encoding="utf-8") as f:
                f.write(f"[{datetime.now(timezone.utc).isoformat()}] B2B refresh error:\n\n")
                f.write(f"Error: {error_msg}\n\nTraceback:\n{full_traceback}")
        except Exception:
            pass  # Don't let logging failure mask the real error
        with _refresh_lock:
            _refresh_state.update({
                "status": "error",
                "progress_pct": 0,
                "message": f"Pipeline error: {error_msg[:200]}",
                "error": error_msg[:500],
                "traceback": full_traceback[:2000],
            })


@app.route("/api/refresh-b2b", methods=["POST"])
def api_refresh_b2b():
    """Start B2B pipeline refresh in background thread. Returns task_id immediately."""
    with _refresh_lock:
        if _refresh_state["status"] == "running":
            return jsonify({
                "ok": False,
                "error": "Pipeline already running",
                "task_id": _refresh_state["task_id"],
                "status": _refresh_state["status"],
            }), 409

        task_id = str(uuid.uuid4())[:8]
        _refresh_state.update({
            "task_id": task_id,
            "status": "running",
            "progress_pct": 0,
            "message": "Starting B2B pipeline...",
            "companies_found": 0,
            "emails_found": 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "error": None,
        })

    thread = threading.Thread(target=_run_b2b_refresh_task, args=(task_id,), daemon=True)
    thread.start()

    return jsonify({
        "ok": True,
        "task_id": task_id,
        "status": "running",
        "message": "B2B refresh started in background",
    })


@app.route("/api/refresh-b2b/status")
def api_refresh_b2b_status():
    """Return current progress of B2B refresh task."""
    with _refresh_lock:
        state = dict(_refresh_state)
    return jsonify({
        "ok": True,
        "task_id": state["task_id"],
        "status": state["status"],
        "progress_pct": state["progress_pct"],
        "message": state["message"],
        "companies_found": state["companies_found"],
        "emails_found": state["emails_found"],
        "started_at": state["started_at"],
        "completed_at": state["completed_at"],
        "error": state["error"],
        "traceback": state.get("traceback", ""),
    })


@app.route("/api/b2b-data")
def api_b2b_data():
    """Return current B2B companies data from b2b_companies.json."""
    b2b = _load_b2b()
    return jsonify({
        "ok": True,
        "companies": b2b,
        "total": len(b2b),
    })


# ─── API: YAMM CSV ────────────────────────────────────────────────────────

@app.route("/api/yamm-csv")
def api_yamm_csv():
    signals = _load_signals()
    b2b = _load_b2b()
    candidates = get_email_candidates(signals, b2b, daily_limit=DAILY_LIMIT)

    output = io.StringIO()
    writer = csv_module.writer(output)
    writer.writerow(["Email", "FirstName", "LastName", "Company", "Subject", "Body", "SourceURL", "Priority"])

    for c in candidates:
        name = c.get("name", "")
        parts = name.split() if name else []
        first = parts[0] if parts else ""
        last = " ".join(parts[1:]) if len(parts) > 1 else ""
        body = (c.get("body") or "").replace('\n', ' ')
        writer.writerow([
            c.get("email", ""), first, last, c.get("name", ""),
            c.get("subject", ""), body,
            c.get("source_url", ""), c.get("priority", 0),
        ])

    csv_bytes = output.getvalue().encode("utf-8-sig")
    return send_file(
        io.BytesIO(csv_bytes),
        mimetype="text/csv",
        as_attachment=True,
        download_name="yamm_outreach.csv",
    )

# ─── Serve viewer.html ────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(str(HERE), "viewer.html")

# ─── Main ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("  Leeway Parts Email Outreach Server")
    print(f"  http://localhost:5010")
    print("=" * 50)

    config = load_email_config()
    if config.get("valid"):
        print(f"  SMTP: {config['user']}  [OK]")
    else:
        print(f"  SMTP: NOT CONFIGURED — add SMTP_USER/APP_PASSWORD to .env")

    print(f"  Quota: {count_sent_today()}/{DAILY_LIMIT} sent today")
    print("=" * 50)
    print()

    app.run(host="127.0.0.1", port=5010, debug=False, threaded=True)
