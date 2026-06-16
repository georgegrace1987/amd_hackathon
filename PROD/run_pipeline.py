"""
run_pipeline.py — BFSI complaint pipeline, top to bottom.
Run: python run_pipeline.py

Flow:
    1. Init DB
    2. (Optional) Seed synthetic data
    3. Poll loop in background thread (classify + route)
    4. Unified app in main thread → single URL for both customer and employee UI

Folder layout (all flat imports like `from db import X` still work because
the folders below are added to sys.path at startup — no import lines were
changed anywhere in the project):
    config/    config.py
    data/      db.py
    model/     classifier.py, router.py, data_generator.py
    security/  pii_redactor.py, content_security.py
    ui/        unified_app.py, login_form.py, list_form.py,
               details_form.py, dashboard_form.py
"""

import os
import sys

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
for _sub in ("config", "data", "model", "security", "ui"):
    _path = os.path.join(_BASE_DIR, _sub)
    if _path not in sys.path:
        sys.path.insert(0, _path)

import time
import threading
from config import JSON_PATH
from db import init_db, init_routing_db, get_conn
from data_generator import run_generator
from classifier import classify_from_json, classify
from router import run_router

# ── Settings ──────────────────────────────────────────────────────────────────
SEED_DATA          = False   # production default — set True only for demo/test seeding
SEED_COUNT         = 8
POLL_INTERVAL_SECS = 60
UNIFIED_PORT       = 8001
UI_SHARE           = True


# ── Poll loop ─────────────────────────────────────────────────────────────────
def fetch_unclassified() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("""
        SELECT complaint_id, customer_id, cust_name, cust_email,
               complaint, channel, branch, account_type
        FROM complaints
        WHERE category IS NULL
        ORDER BY created_at ASC
    """).fetchall()
    cols = ["complaint_id", "customer_id", "cust_name", "cust_email",
            "complaint", "channel", "branch", "account_type"]
    conn.close()
    return [dict(zip(cols, r)) for r in rows]


def classify_and_route_new() -> None:
    pending = fetch_unclassified()
    if pending:
        print(f"[poll] {len(pending)} new complaint(s) — classifying...")
        for c in pending:
            try:
                result = classify(
                    complaint=c["complaint"],
                    customer_id=c["customer_id"],
                    cust_name=c["cust_name"],
                    cust_email=c.get("cust_email"),
                    channel=c.get("channel", "web"),
                    branch=c.get("branch"),
                    account_type=c.get("account_type", "savings"),
                )
                print(f"  ✓ {result['complaint_id']} → {result['category']} {result['priority']}")
            except Exception as e:
                print(f"  ✗ {c['complaint_id']} failed: {e}")
    else:
        print("[poll] No new complaints.")

    decisions = run_router(rerun=False)
    if decisions:
        print(f"[poll] Routed {len(decisions)} complaint(s).")


def poll_loop() -> None:
    while True:
        classify_and_route_new()
        print(f"[poll] Sleeping {POLL_INTERVAL_SECS}s...\n")
        time.sleep(POLL_INTERVAL_SECS)


# ════════════════════════════════════════════════════════════════════════════════
# STEP 1 — Init DB
# ════════════════════════════════════════════════════════════════════════════════
print("\n── Step 1: Init DB ─────────────────────────────────────")
init_db()
init_routing_db()

# ════════════════════════════════════════════════════════════════════════════════
# STEP 2 — (Optional) Seed synthetic data
# ════════════════════════════════════════════════════════════════════════════════
if SEED_DATA:
    print("\n── Step 2: Seed synthetic data ─────────────────────────")
    dataset = run_generator(count=SEED_COUNT, output="both")
    results = classify_from_json(JSON_PATH)
    ok      = sum(1 for r in results if "error" not in r)
    print(f"Classified: {ok}/{len(results)}")
    decisions = run_router(rerun=False)
    print(f"Routed: {len(decisions)}")
else:
    print("\n── Step 2: Skipping seed (SEED_DATA=False) ─────────────")

# ════════════════════════════════════════════════════════════════════════════════
# STEP 3 — Poll loop in background thread
# ════════════════════════════════════════════════════════════════════════════════
print(f"\n── Step 3: Poll loop → every {POLL_INTERVAL_SECS}s (background)")
poll_thread = threading.Thread(target=poll_loop, daemon=True)
poll_thread.start()

# ════════════════════════════════════════════════════════════════════════════════
# STEP 4 — Unified app in main thread (single URL for customer + employee)
# ════════════════════════════════════════════════════════════════════════════════
print(f"\n── Step 4: Unified portal → port {UNIFIED_PORT}")
print("  Tab 1: Lodge Complaint (customer)")
print("  Tab 2: Employee Portal (bank staff)")
print("  Ctrl+C to stop.\n")

from unified_app import launch_unified
launch_unified(port=UNIFIED_PORT, share=UI_SHARE)