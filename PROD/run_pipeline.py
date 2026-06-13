"""
run_pipeline.py — BFSI complaint pipeline, top to bottom.
Run: python run_pipeline.py

Flow:
    1. Init DB
    2. (Optional) Seed synthetic data
    3. Launch employee portal in background thread  → port 10000
    4. Poll loop in background thread (classify + route)
    5. Launch customer UI in main thread            → port 10001  (blocks here)
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
SEED_DATA          = False
SEED_COUNT         = 80
POLL_INTERVAL_SECS = 60
CUST_UI_PORT       = 10001
EMPLOYEE_UI_PORT   = 10000
UI_SHARE           = True


def launch_employee_portal(port: int = 10000, share: bool = True) -> None:
    import app_form
    app_form.app.launch(server_port=port, share=share)


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
# STEP 3 — Launch employee portal in background thread
# ════════════════════════════════════════════════════════════════════════════════
print(f"\n── Step 3: Employee portal → port {EMPLOYEE_UI_PORT} (background)")
employee_thread = threading.Thread(
    target=launch_employee_portal,
    kwargs={"port": EMPLOYEE_UI_PORT, "share": UI_SHARE},
    daemon=True,
)
employee_thread.start()
print("Waiting 3s for employee portal to start...")
time.sleep(3)

# ════════════════════════════════════════════════════════════════════════════════
# STEP 4 — Poll loop in background thread
# ════════════════════════════════════════════════════════════════════════════════
print(f"\n── Step 4: Poll loop → every {POLL_INTERVAL_SECS}s (background)")
poll_thread = threading.Thread(target=poll_loop, daemon=True)
poll_thread.start()

# ════════════════════════════════════════════════════════════════════════════════
# STEP 5 — Customer UI in main thread (keeps process alive)
# ════════════════════════════════════════════════════════════════════════════════
print(f"\n── Step 5: Customer UI → port {CUST_UI_PORT} (main thread)")
print(f"  Employee portal → port {EMPLOYEE_UI_PORT}")
print("  Ctrl+C to stop.\n")
launch_ui(port=CUST_UI_PORT, share=UI_SHARE)
