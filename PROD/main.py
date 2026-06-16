"""
main.py — Single entry point for the BFSI complaint pipeline. Not needed if run using run_pipelinev2.py

Usage:
    python main.py --mode initdb        # initialise DB tables only
    python main.py --mode cust-ui       # launch customer intake form (port 10001)
    python main.py --mode employee-ui   # launch bank employee portal (port 10000)
    python main.py --mode generate      # generate synthetic complaints
    python main.py --mode classify      # classify complaints from JSON
    python main.py --mode route         # route classified complaints
    python main.py --mode pipeline      # full end-to-end (no UI)

Options:
    --count   N     number of complaints to generate (default: 80)
    --rerun         re-route already routed complaints
    --port    N     Gradio UI port (default depends on mode)
    --share         expose Gradio public URL (default: True)
    --json    PATH  path to complaints JSON (overrides config.JSON_PATH)
"""

import argparse
import sys


def run_initdb():
    from db import init_db, init_routing_db
    init_db()
    init_routing_db()
    print("[main] DB initialisation complete.")


def run_cust_ui(port: int = 10001, share: bool = True):
    from db import init_db
    from cust_ui import launch_ui
    init_db()
    print(f"[main] Launching customer UI on port {port}...")
    launch_ui(port=port, share=share)


def run_employee_ui(port: int = 10000, share: bool = True):
    from db import init_db, init_routing_db
    import app_form_v2
    init_db()
    init_routing_db()
    print(f"[main] Launching employee portal on port {port}...")
    app_form_v2.app.launch(server_port=port, share=share)


def run_generate(count: int = 80, json_path: str = None):
    from db import init_db
    from data_generator import run_generator
    import config
    init_db()
    if json_path:
        config.JSON_PATH = json_path
    run_generator(count=count, output="both")


def run_classify(json_path: str = None):
    from db import init_db
    from classifier import classify_from_json
    import config
    init_db()
    if json_path:
        config.JSON_PATH = json_path
    results = classify_from_json(config.JSON_PATH)
    ok     = sum(1 for r in results if "error" not in r)
    failed = len(results) - ok
    print(f"\n[main] Classification done. OK: {ok} | Failed: {failed}")


def run_route(rerun: bool = False):
    from db import init_db, init_routing_db
    from router import run_router
    init_db()
    init_routing_db()
    run_router(rerun=rerun)


def run_pipeline(count: int = 80, json_path: str = None):
    """Full end-to-end: generate → classify → route (no UI)."""
    print("\n[main] ── Step 1: Generate ──────────────────────────")
    run_generate(count=count, json_path=json_path)

    print("\n[main] ── Step 2: Classify ──────────────────────────")
    run_classify(json_path=json_path)

    print("\n[main] ── Step 3: Route ─────────────────────────────")
    run_route()

    print("\n[main] Pipeline complete.")


# ── CLI ───────────────────────────────────────────────────────────────────────
def parse_args():
    # Jupyter-safe: skip argparse if kernel args present
    if any("ipykernel" in a or a.endswith(".json") for a in sys.argv[1:]):
        return argparse.Namespace(
            mode="cust-ui", count=80, rerun=False,
            port=10001, share=True, json=None,
        )

    parser = argparse.ArgumentParser(description="BFSI Complaint Pipeline")
    parser.add_argument(
        "--mode", required=True,
        choices=["initdb", "cust-ui", "employee-ui", "generate", "classify", "route", "pipeline"],
        help="Which module to run",
    )
    parser.add_argument("--count",  type=int,  default=80,    help="Complaints to generate")
    parser.add_argument("--rerun",  action="store_true",       help="Re-route all complaints")
    parser.add_argument("--port",   type=int,  default=None,   help="Gradio UI port")
    parser.add_argument("--share",  action="store_true", default=True, help="Gradio share=True")
    parser.add_argument("--json",   type=str,  default=None,   help="JSON file path")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.mode == "initdb":
        run_initdb()

    elif args.mode == "cust-ui":
        run_cust_ui(port=args.port or 10001, share=args.share)

    elif args.mode == "employee-ui":
        run_employee_ui(port=args.port or 10000, share=args.share)

    elif args.mode == "generate":
        run_generate(count=args.count, json_path=args.json)

    elif args.mode == "classify":
        run_classify(json_path=args.json)

    elif args.mode == "route":
        run_route(rerun=args.rerun)

    elif args.mode == "pipeline":
        run_pipeline(count=args.count, json_path=args.json)
