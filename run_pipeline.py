"""
run_pipeline.py — BFSI complaint pipeline, top to bottom.
Run: python run_pipeline.py

Flow:
    1. Init DB
    2. (Optional) Generate + classify + route synthetic data as seed
    3. Launch customer intake UI in background
    4. Poll loop — every POLL_INTERVAL_SECONDS, classify + route new complaints
"""

import time
import threading
from config import JSON_PATH
from db import init_db, init_routing_db, load_json_to_db, get_conn
from data_generator import run_generator
from classifier import classify_from_json, classify
from router import run_router
from cust_ui import launch_ui

# ── Settings ──────────────────────────────────────────────────────────────────
SEED_DATA          = False   # set True to generate synthetic data on first run
SEED_COUNT         = 80      # how many synthetic complaints to generate
POLL_INTERVAL_SECS = 60      # how often to check for new unclassified complaints
UI_PORT            = 10001
UI_SHARE           = True    # set False if no internet on AMD VM

# ════════════════════════════════════════════════════════════════════════════════
# STEP 1 — Init DB
# ════════════════════════════════════════════════════════════════════════════════
print("\n── Step 1: Init DB ─────────────────────────────────────")
init_db()
init_routing_db()

# ════════════════════════════════════════════════════════════════════════════════
# STEP 2 — (Optional) Seed with synthetic data
# ════════════════════════════════════════════════════════════════════════════════
if SEED_DATA:
    print("\n── Step 2: Seed synthetic data ─────────────────────────")
    dataset = run_generator(count=SEED_COUNT, output="both")
    results = classify_from_json(JSON_PATH)
    ok      = sum(1 for r in results if "error" not in r)
    print(f"Seeded and classified: {ok}/{len(results)}")
    decisions = run_router(rerun=False)
    print(f"Seeded and routed: {len(decisions)}")
else:
    print("\n── Step 2: Skipping seed (SEED_DATA=False) ─────────────")

# ════════════════════════════════════════════════════════════════════════════════
# STEP 3 — Launch UI in background thread
# ════════════════════════════════════════════════════════════════════════════════
print(f"\n── Step 3: Launching UI on port {UI_PORT} ──────────────")

ui_thread = threading.Thread(
    target=launch_ui,
    kwargs={"port": UI_PORT, "share": UI_SHARE},
    daemon=True,
)
ui_thread.start()
print("UI started. Waiting 3s for it to come up...")
time.sleep(3)

# ════════════════════════════════════════════════════════════════════════════════
# STEP 4 — Polling loop: pick up new complaints from UI, classify + route them
# ════════════════════════════════════════════════════════════════════════════════
print(f"\n── Step 4: Poll loop (every {POLL_INTERVAL_SECS}s) ─────────────────")
print("Submit complaints via the UI — they will be classified and routed automatically.\n")

def fetch_unclassified() -> list[dict]:
    """Fetch complaints with no category yet (submitted via UI)."""
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


def classify_and_route_new():
    """Classify unclassified complaints then route unrouted ones."""
    pending = fetch_unclassified()

    if pending:
        print(f"[poll] {len(pending)} new complaint(s) found — classifying...")
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
        print(f"[poll] No new complaints.")

    decisions = run_router(rerun=False)
    if decisions:
        print(f"[poll] Routed {len(decisions)} complaint(s).")


# ── Main poll loop ────────────────────────────────────────────────────────────
try:
    while True:
        classify_and_route_new()
        print(f"[poll] Sleeping {POLL_INTERVAL_SECS}s...\n")
        time.sleep(POLL_INTERVAL_SECS)
except KeyboardInterrupt:
    print("\nStopped. Goodbye.")
