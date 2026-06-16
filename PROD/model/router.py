"""
router.py — BFSI complaint routing agent.
Reads classified complaints from complaints.duckdb,
reasons over each via vLLM, writes decisions to routing.duckdb.
"""

import json
import time
import uuid
from openai import OpenAI
from config import (
    VLLM_BASE_URL, VLLM_MODEL, VLLM_API_KEY,
    TEAM_PROFILES, ROUTER_SYSTEM,
)
from db import (
    init_routing_db,
    insert_routing_decision,
    fetch_unrouted,
    get_routing_conn,
    DB_PATH,
    ROUTING_DB,
)
import duckdb

_client: OpenAI = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=VLLM_BASE_URL, api_key=VLLM_API_KEY)
    return _client


def route_one(c: dict) -> dict:
    """
    Run routing agent on a single complaint dict.
    Returns routing decision dict.
    Raises ValueError on non-JSON model response.
    """
    routing_id   = "RTR-" + str(uuid.uuid4())[:8].upper()
    profiles_str = json.dumps(
        {k: v["handles"] for k, v in TEAM_PROFILES.items()}, indent=2
    )
    system_prompt = ROUTER_SYSTEM.format(team_profiles=profiles_str)
    user_msg = (
        f"Complaint ID  : {c['complaint_id']}\n"
        f"Customer      : {c['cust_name']}\n"
        f"Complaint     : {c['complaint']}\n"
        f"Category      : {c['category']}\n"
        f"Priority      : {c['priority']}\n"
        f"Sentiment     : {c['sentiment']}\n"
        f"Created at    : {c['created_at']}\n"
        f"Initial team  : {c['team']}"
    )

    t0       = time.time()
    response = get_client().chat.completions.create(
        model=VLLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_msg},
        ],
        temperature=0.1,
        max_tokens=400,
    )
    latency_ms = int((time.time() - t0) * 1000)
    raw        = response.choices[0].message.content.strip()

    try:
        result = json.loads(raw.replace("```json", "").replace("```", "").strip())
    except json.JSONDecodeError:
        raise ValueError(f"Non-JSON response: {raw[:200]}")

    routed_team  = result.get("routed_team", c["team"])
    team_profile = TEAM_PROFILES.get(routed_team, {})

    return {
        "routing_id":           routing_id,
        "complaint_id":         c["complaint_id"],
        "customer_id":          c["customer_id"],
        "cust_name":            c["cust_name"],
        "complaint":            c["complaint"],
        "category":             c["category"],
        "priority":             c["priority"],
        "sentiment":            c["sentiment"],
        "original_team":        c["team"],
        "routed_team":          routed_team,
        "escalate":             result.get("escalate", False),
        "escalate_to":          result.get("escalate_to"),
        "action":               result.get("action", ""),
        "routing_reason":       result.get("routing_reason", ""),
        "confidence":           result.get("confidence", "medium"),
        "team_email":           team_profile.get("email", ""),
        "sla_hours":            team_profile.get("sla_hours", 120),
        "complaint_created_at": c["created_at"],
        "latency_ms":           latency_ms,
        "model_used":           VLLM_MODEL,
    }


def run_router(rerun: bool = False) -> list[dict]:
    """
    Route complaints from complaints.duckdb → routing.duckdb.
    rerun=False: only route complaints not yet in routing_decisions.
    rerun=True:  re-route all complaints.
    Returns list of decision dicts.
    """
    init_routing_db()

    if rerun:
        src  = duckdb.connect(DB_PATH, read_only=True)
        rows = src.execute("""
            SELECT complaint_id, customer_id, cust_name, complaint,
                   category, priority, sentiment, team, created_at
            FROM complaints ORDER BY priority ASC, created_at ASC
        """).fetchall()
        src.close()
        cols       = ["complaint_id", "customer_id", "cust_name", "complaint",
                      "category", "priority", "sentiment", "team", "created_at"]
        complaints = [dict(zip(cols, r)) for r in rows]
    else:
        complaints = fetch_unrouted()

    if not complaints:
        print("[router] Nothing to route.")
        return []

    print(f"\n[router] Routing {len(complaints)} complaint(s) via {VLLM_MODEL}...\n")
    decisions, failed = [], 0

    for i, c in enumerate(complaints):
        try:
            d = route_one(c)
            insert_routing_decision(d)
            decisions.append(d)
            flag = " ⚑ ESCALATE" if d["escalate"] else ""
            print(
                f"[{i+1}/{len(complaints)}] {c['complaint_id']} "
                f"| {c['created_at']} "
                f"→ {d['routed_team']} [{d['confidence']}]{flag} "
                f"({d['latency_ms']}ms)"
            )
        except Exception as e:
            print(f"[{i+1}/{len(complaints)}] FAILED {c['complaint_id']}: {e}")
            failed += 1

    print(f"\n[router] Done. Routed: {len(decisions)} | Failed: {failed}")
    return decisions


def fetch_routing_summary() -> dict:
    """Return summary stats from routing_decisions table."""
    conn     = get_routing_conn()
    by_team  = conn.execute("""
        SELECT routed_team, COUNT(*) AS total,
               SUM(CASE WHEN escalate THEN 1 ELSE 0 END) AS escalations
        FROM routing_decisions GROUP BY routed_team ORDER BY total DESC
    """).fetchall()
    by_conf  = dict(conn.execute(
        "SELECT confidence, COUNT(*) FROM routing_decisions GROUP BY confidence"
    ).fetchall())
    rerouted = conn.execute(
        "SELECT COUNT(*) FROM routing_decisions WHERE routed_team != original_team"
    ).fetchone()[0]
    conn.close()
    return {
        "by_team":  [{"team": r[0], "total": r[1], "escalations": r[2]} for r in by_team],
        "by_confidence": by_conf,
        "rerouted": rerouted,
    }
