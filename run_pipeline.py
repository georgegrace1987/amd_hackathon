"""
run_pipeline.py — BFSI complaint pipeline, top to bottom.
Run: python run_pipeline.py

Flow:
    1. Init DB (complaints.duckdb + routing.duckdb)
    2. (Optional) Seed KYC + synthetic complaint data
    3. Launch customer intake UI      → port 10001
    4. Launch bank employee portal    → port 10000
    5. Poll loop — every POLL_INTERVAL_SECS, classify + route new complaints
"""

import time
import threading
from config import JSON_PATH
from db import init_db, init_routing_db, get_conn
from data_generator import run_generator
from classifier import classify_from_json, classify
from router import run_router
from cust_ui import launch_ui

# ── Settings ──────────────────────────────────────────────────────────────────
SEED_DATA          = False   # True = generate synthetic data on first run
SEED_COUNT         = 80      # number of synthetic complaints to generate
POLL_INTERVAL_SECS = 60      # seconds between classify+route cycles
CUST_UI_PORT       = 10001   # customer intake form
EMPLOYEE_UI_PORT   = 10000   # bank employee routing portal
UI_SHARE           = True    # False if no internet on AMD VM


# ── Employee portal launcher (wraps app_form.py) ──────────────────────────────
def launch_employee_portal(port: int = 10000, share: bool = True) -> None:
    """Launch app_form.py as-is — no changes to that module."""
    import app_form_v2 as app_form
    app_form.app.launch(server_port=port, share=share)


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
# STEP 3 — Launch customer intake UI
# ════════════════════════════════════════════════════════════════════════════════
print(f"\n── Step 3: Customer UI → port {CUST_UI_PORT} ───────────────")
cust_thread = threading.Thread(
    target=launch_ui,
    kwargs={"port": CUST_UI_PORT, "share": UI_SHARE},
    daemon=True,
)
cust_thread.start()

# ════════════════════════════════════════════════════════════════════════════════
# STEP 4 — Launch bank employee portal
# ════════════════════════════════════════════════════════════════════════════════
print(f"\n── Step 4: Employee portal → port {EMPLOYEE_UI_PORT} ──────────")
employee_thread = threading.Thread(
    target=launch_employee_portal,
    kwargs={"port": EMPLOYEE_UI_PORT, "share": UI_SHARE},
    daemon=True,
)
employee_thread.start()

print("Both UIs starting. Waiting 4s...")
time.sleep(4)

# ════════════════════════════════════════════════════════════════════════════════
# STEP 5 — Poll loop: classify + route new complaints from customer UI
# ════════════════════════════════════════════════════════════════════════════════
print(f"\n── Step 5: Poll loop (every {POLL_INTERVAL_SECS}s) ─────────────────")
print(f"  Customer UI   → port {CUST_UI_PORT}")
print(f"  Employee UI   → port {EMPLOYEE_UI_PORT}")
print("  Ctrl+C to stop.\n")


def fetch_unclassified() -> list[dict]:
    """Fetch complaints submitted via UI with no category yet."""
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
    """Classify unclassified complaints then route unrouted ones."""
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


try:
    while True:
        classify_and_route_new()
        print(f"[poll] Sleeping {POLL_INTERVAL_SECS}s...\n")
        time.sleep(POLL_INTERVAL_SECS)
except KeyboardInterrupt:
    print("\nStopped. Goodbye.")
