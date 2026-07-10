"""
Tractor Search Demo — MCP Server (v0.1)
========================================
Exposes demo pipeline capabilities as MCP tools for AI assistants.

Tools (v0.1):
  - search_demand_signal  : Search Google for demand signals via SerpAPI + Qwen
  - search_b2b_company    : Search Google for B2B companies via SerpAPI + Qwen
  - generate_email        : Generate multilingual outreach email for a signal/company
  - run_full_pipeline     : Run the complete demo.py pipeline
  - get_pipeline_status   : Get status of the last pipeline run

Design principles:
  - Does NOT modify any existing file (demo.py, server.py, etc.)
  - Reuses existing functions directly — no business logic duplication
  - Client-agnostic: follows MCP specification, works with any MCP client
  - Graceful degradation: tools that need API keys return clear errors if
    keys are missing, while data-query tools still work

Usage:
    python mcp_server.py

Transport: stdio (universal MCP transport)
"""

import io
import json
import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from contextlib import contextmanager

# ─── Path Setup ──────────────────────────────────────────────────────────

DEMO_DIR = Path(__file__).parent
sys.path.insert(0, str(DEMO_DIR))

# Load .env for API keys (idempotent — safe to call multiple times)
from dotenv import load_dotenv
load_dotenv(DEMO_DIR / ".env")

# ─── MCP SDK ─────────────────────────────────────────────────────────────

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("tractor-search-demo")


# ─── Stdout Suppression ──────────────────────────────────────────────────
# CRITICAL: MCP stdio transport uses stdout for JSON-RPC messages.
# demo.py and email_sender.py use print() extensively, which would
# corrupt the protocol. This context manager safely captures stdout.

@contextmanager
def _suppress_stdout():
    """Redirect sys.stdout to a buffer during the block."""
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        yield
    finally:
        sys.stdout = old_stdout


# ─── Safe Imports ────────────────────────────────────────────────────────
# product_inventory.py — pure Python, no side effects, safe to import
from product_inventory import match_product

# email_sender.py — lazy Qwen init, no module-level key checks, safe to import
from email_sender import (
    generate_outreach_email,
    count_sent_today,
    load_email_config,
    LANGUAGE_NAMES,
)

# demo.py — has module-level API key checks that raise SystemExit.
# We catch it so the MCP server still starts; search/extract tools
# will return a clear error if keys are missing, while data-query
# tools (get_pipeline_status, generate_email from cached data) still work.
_demo = None
try:
    import demo
    _demo = demo
except SystemExit:
    pass


# ─── Data Helpers ────────────────────────────────────────────────────────

def _load_signals() -> list[dict]:
    """Load demand signals from signals_output.json."""
    path = DEMO_DIR / "signals_output.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("signals", []) if isinstance(data, dict) else data
    except Exception:
        return []


def _load_b2b() -> list[dict]:
    """Load B2B companies from b2b_companies.json."""
    path = DEMO_DIR / "b2b_companies.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("companies", []) if isinstance(data, dict) else data
    except Exception:
        return []


def _find_item(source_url: str, source_type: str) -> dict | None:
    """Find an item by source_url in signals or b2b data."""
    pool = _load_signals() if source_type == "signal" else _load_b2b()
    for item in pool:
        if item.get("source_url") == source_url:
            return item
    return None


def _require_demo():
    """Get demo module or raise a descriptive error."""
    if _demo is None:
        raise RuntimeError(
            "demo.py not available — SERPAPI_KEY and QWEN_API_KEY must be set "
            "in demo/.env for search and extraction tools"
        )
    return _demo


# ─── MCP Tools (v0.1) ────────────────────────────────────────────────────

@mcp.tool()
def search_demand_signal(query: str, num_results: int = 20) -> str:
    """Search Google for agricultural machinery demand signals.

    Uses SerpAPI to search Google (past 30 days), then Qwen LLM to extract
    structured demand signals from the results. Filters out supplier listings
    and e-commerce pages. Matches extracted signals against the product
    inventory to flag items we can supply.

    Args:
        query: Google search query, e.g. '"Kubota tractor parts" needed looking supplier Philippines'
        num_results: Number of Google results to fetch (default 20)

    Returns:
        JSON string with:
        - query: The search query used
        - google_results: Total results from SerpAPI
        - filtered: Results after removing suppliers/e-commerce
        - signals_extracted: Number of signals extracted by Qwen
        - signals: List of extracted signal objects, each with:
            country, machine_model, part_type, urgency, buyer_type,
            source_url, contact_email, matched_category, has_product, etc.
    """
    try:
        demo = _require_demo()

        with _suppress_stdout():
            # Step 1: Search Google via SerpAPI (reuse existing function)
            results = demo.search_google(query, num=num_results)

            # Step 2: Filter out suppliers and e-commerce pages
            filtered = [
                r for r in results
                if not demo.is_likely_supplier(r["title"], r["snippet"], r["url"])
                and not demo.is_ecommerce_page(r["url"])
            ]

            # Step 3: Extract demand signals via Qwen LLM
            extracted = []
            for result in filtered:
                signal, had_error = demo.extract_signal(result)
                if had_error:
                    continue
                if signal:
                    # Post-process (same logic as demo.py main pipeline)
                    signal["snippet"] = result.get("snippet", "")
                    signal["post_date"] = result.get("date") or None
                    signal["contact_method"] = demo.get_contact_method(
                        signal.get("source_url", "")
                    )
                    # Country fallback from query
                    if not signal.get("country"):
                        signal["country"] = demo.infer_country_from_query(query)
                    # Step 4: Match against product inventory
                    signal = match_product(signal)
                    extracted.append(signal)

        return json.dumps({
            "query": query,
            "google_results": len(results),
            "filtered": len(filtered),
            "signals_extracted": len(extracted),
            "signals": extracted,
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
def search_b2b_company(query: str, num_results: int = 20) -> str:
    """Search Google for B2B agricultural machinery companies.

    Uses SerpAPI to search Google (no time filter, B2B-focused), then Qwen LLM
    to extract structured company profiles from the results. Filters out
    e-commerce pages and supplier listings. Matches extracted companies
    against the product inventory.

    Args:
        query: Google search query, e.g. '"kubota" tractor parts importer Japan'
        num_results: Number of Google results to fetch (default 20)

    Returns:
        JSON string with:
        - query: The search query used
        - google_results: Total results from SerpAPI
        - filtered: Results after filtering
        - companies_extracted: Number of company profiles extracted
        - companies: List of extracted company objects, each with:
            company_name, business_type, country, website, contact_email,
            phone, product_focus, confidence, matched_category, has_product, etc.
    """
    try:
        demo = _require_demo()

        with _suppress_stdout():
            # Step 1: Search Google via SerpAPI — B2B mode (reuse existing function)
            results = demo.search_google_b2b(query, num=num_results)

            # Step 2: Filter out e-commerce and supplier pages
            filtered = [
                r for r in results
                if not demo.is_ecommerce_page(r["url"])
                and not demo.is_likely_supplier(r["title"], r["snippet"], r["url"])
            ]

            # Step 3: Extract company profiles via Qwen LLM
            extracted = []
            for result in filtered:
                company, had_error = demo.extract_b2b_company(result)
                if had_error:
                    continue
                if company:
                    # Post-process (same logic as demo.py B2B pipeline)
                    company["snippet"] = result.get("snippet", "")
                    company["post_date"] = result.get("date") or None
                    # Country fallback from query
                    if not company.get("country"):
                        company["country"] = demo.infer_country_from_query(query)
                    # Japanese company name detection
                    cname = company.get("company_name") or ""
                    if (not company.get("country") and
                            any('\u3040' <= c <= '\u30ff' or '\u4e00' <= c <= '\u9fff'
                                for c in cname)):
                        company["country"] = "Japan"
                    # Step 4: Match against product inventory
                    company["part_type"] = company.get("product_focus") or ""
                    company = match_product(company)
                    extracted.append(company)

        return json.dumps({
            "query": query,
            "google_results": len(results),
            "filtered": len(filtered),
            "companies_extracted": len(extracted),
            "companies": extracted,
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
def generate_email(source_url: str, source_type: str = "signal") -> str:
    """Generate a multilingual outreach email for a demand signal or B2B company.

    Uses Qwen LLM to generate a personalized outreach email in the appropriate
    language based on the target's country (Japanese, Korean, Indonesian,
    Spanish, or English). The item must already exist in signals_output.json
    or b2b_companies.json from a previous pipeline run.

    Args:
        source_url: The source_url of the signal or company (from search results
                    or pipeline output)
        source_type: "signal" for demand signals, "b2b" for B2B companies

    Returns:
        JSON string with:
        - source_url: The source URL
        - source_type: The source type
        - subject: Email subject line
        - body: Full email body text
        - language: Language name (e.g., "Japanese", "English")
        - lang_code: Language code (e.g., "ja", "en")
    """
    try:
        # Find the item by source_url in cached pipeline data
        item = _find_item(source_url, source_type)
        if not item:
            available = len(_load_signals()) if source_type == "signal" else len(_load_b2b())
            return json.dumps({
                "error": (
                    f"Item not found with source_url='{source_url}' "
                    f"and source_type='{source_type}' "
                    f"({available} items available in cache)"
                )
            }, ensure_ascii=False)

        # Generate outreach email using existing email_sender function
        with _suppress_stdout():
            body, lang_code = generate_outreach_email(item, source_type)

        if not body:
            return json.dumps({
                "error": "Email generation failed — Qwen API error or timeout"
            }, ensure_ascii=False)

        # Parse subject from first line
        lines = body.strip().split("\n")
        subject = lines[0].strip()
        if subject.lower().startswith("subject:"):
            subject = subject[8:].strip()

        return json.dumps({
            "source_url": source_url,
            "source_type": source_type,
            "subject": subject,
            "body": body,
            "language": LANGUAGE_NAMES.get(lang_code, "English"),
            "lang_code": lang_code,
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
def run_full_pipeline() -> str:
    """Run the complete demand signal + B2B extraction pipeline.

    Executes demo.py as a subprocess, which performs:
    1. SerpAPI Google search (42 demand signal queries + 18 B2B queries)
    2. Qwen LLM extraction of demand signals and B2B company profiles
    3. Product inventory matching
    4. Outreach email draft generation
    5. History merge with previous runs
    6. Output to signals_output.json and b2b_companies.json

    This is a long-running operation (typically 10-30 minutes).
    The interactive email-sending step is automatically skipped.

    Returns:
        JSON string with:
        - exit_code: Process exit code (0 = success)
        - duration_seconds: Total execution time
        - stdout_tail: Last 2000 characters of stdout
        - stderr_tail: Last 2000 characters of stderr
        - signals_output_exists: Whether signals_output.json was updated
        - b2b_output_exists: Whether b2b_companies.json was updated
    """
    try:
        start_time = datetime.now(timezone.utc)

        # Run demo.py as subprocess.
        # Pipe "n" to stdin to skip the interactive email-sending prompt.
        result = subprocess.run(
            [sys.executable, "demo.py"],
            cwd=str(DEMO_DIR),
            capture_output=True,
            text=True,
            timeout=3600,  # 1 hour max
            input="n\n",
        )

        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()

        signals_path = DEMO_DIR / "signals_output.json"
        b2b_path = DEMO_DIR / "b2b_companies.json"

        return json.dumps({
            "exit_code": result.returncode,
            "duration_seconds": round(duration, 1),
            "stdout_tail": result.stdout[-2000:] if result.stdout else "",
            "stderr_tail": result.stderr[-2000:] if result.stderr else "",
            "signals_output_exists": signals_path.exists(),
            "b2b_output_exists": b2b_path.exists(),
        }, ensure_ascii=False, indent=2)

    except subprocess.TimeoutExpired:
        return json.dumps({
            "error": "Pipeline timed out after 3600 seconds"
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
def get_pipeline_status() -> str:
    """Get the status of the last pipeline run.

    Reads metadata from signals_output.json and b2b_companies.json to report
    on the latest extraction results, including signal counts, urgency
    breakdown, country coverage, and email quota.

    Returns:
        JSON string with:
        - last_run_timestamp: ISO timestamp of last pipeline run
        - signals: {total, matched, high/medium/low urgency, contacted,
                    with_email, countries, run metadata}
        - b2b: {total, high_confidence, contacted, with_email, with_website,
                countries, run metadata}
        - email_quota: {sent_today, daily_limit, remaining, smtp_configured}
    """
    try:
        # ── Signals metadata ──
        signals_path = DEMO_DIR / "signals_output.json"
        signals_meta = {}
        signals = []
        if signals_path.exists():
            data = json.loads(signals_path.read_text(encoding="utf-8"))
            signals_meta = {
                "run_timestamp": data.get("run_timestamp"),
                "total_queries": data.get("total_queries"),
                "total_results": data.get("total_results"),
                "total_signals": data.get("total_signals"),
                "matched_signals": data.get("matched_signals"),
            }
            signals = data.get("signals", []) if isinstance(data, dict) else data

        # ── B2B metadata ──
        b2b_path = DEMO_DIR / "b2b_companies.json"
        b2b_meta = {}
        b2b = []
        if b2b_path.exists():
            data = json.loads(b2b_path.read_text(encoding="utf-8"))
            b2b_meta = {
                "run_timestamp": data.get("run_timestamp"),
                "total_b2b_queries": data.get("total_b2b_queries"),
                "total_b2b_results": data.get("total_b2b_results"),
                "total_companies": data.get("total_companies"),
                "matched_product": data.get("matched_product"),
            }
            b2b = data.get("companies", []) if isinstance(data, dict) else data

        # ── Signal stats ──
        signal_stats = {
            "total": len(signals),
            "high_urgency": sum(1 for s in signals if s.get("urgency") == "high"),
            "medium_urgency": sum(1 for s in signals if s.get("urgency") == "medium"),
            "low_urgency": sum(1 for s in signals if s.get("urgency") == "low"),
            "contacted": sum(1 for s in signals if s.get("contacted")),
            "with_email": sum(1 for s in signals if s.get("contact_email")),
            "countries": sorted(set(
                s.get("country") for s in signals if s.get("country")
            )),
        }

        # ── B2B stats ──
        b2b_stats = {
            "total": len(b2b),
            "high_confidence": sum(
                1 for c in b2b if (c.get("confidence") or 0) >= 70
            ),
            "contacted": sum(1 for c in b2b if c.get("contacted")),
            "with_email": sum(1 for c in b2b if c.get("contact_email")),
            "with_website": sum(1 for c in b2b if c.get("website")),
            "countries": sorted(set(
                c.get("country") for c in b2b if c.get("country")
            )),
        }

        # ── Email quota ──
        try:
            sent_today = count_sent_today()
            config = load_email_config()
            daily_limit = 30
            email_quota = {
                "sent_today": sent_today,
                "daily_limit": daily_limit,
                "remaining": max(0, daily_limit - sent_today),
                "smtp_configured": config.get("valid", False),
            }
        except Exception:
            email_quota = {"error": "Could not read email quota"}

        return json.dumps({
            "last_run_timestamp": (
                signals_meta.get("run_timestamp")
                or b2b_meta.get("run_timestamp")
            ),
            "signals": {**signals_meta, **signal_stats},
            "b2b": {**b2b_meta, **b2b_stats},
            "email_quota": email_quota,
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ─── Entry Point ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
