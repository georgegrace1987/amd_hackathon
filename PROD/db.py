"""
db.py -- All DuckDB operations for the BFSI complaint pipeline.
Handles schema init, complaint CRUD, classification log, routing decisions,
user authentication, and KYC table.
"""

import duckdb
from config import DB_PATH, ROUTING_DB, DEFAULT_USERS, TEAM_MAP


# ── Connection helpers ────────────────────────────────────────────────────────

def get_conn() -> duckdb.DuckDBPyConnection:
    """Open a connection to complaints DB."""
    return duckdb.connect(DB_PATH)


def get_routing_conn() -> duckdb.DuckDBPyConnection:
    """Open a connection to routing DB."""
    return duckdb.connect(ROUTING_DB)


# ── Schema init ───────────────────────────────────────────────────────────────

def init_db() -> None:
    """Create all tables in complaints.duckdb and seed default users."""
    conn = get_conn()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            complaint_id  VARCHAR PRIMARY KEY,
            customer_id   VARCHAR NOT NULL,
            cust_name     VARCHAR NOT NULL,
            cust_email    VARCHAR,
            complaint     TEXT    NOT NULL,
            channel       VARCHAR,
            branch        VARCHAR,
            account_type  VARCHAR,
            category      VARCHAR,
            priority      VARCHAR,
            team          VARCHAR,
            sentiment     VARCHAR,
            sla_days      INTEGER,
            summary       TEXT,
            reasoning     TEXT,
            status        VARCHAR DEFAULT 'New',
            created_at    TIMESTAMP DEFAULT current_timestamp,
            sla_deadline  TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS synthetic_raw (
            customer_id   VARCHAR,
            cust_name     VARCHAR,
            cust_email    VARCHAR,
            complaint     TEXT,
            category      VARCHAR,
            channel       VARCHAR,
            branch        VARCHAR,
            account_type  VARCHAR,
            generated_at  TIMESTAMP DEFAULT current_timestamp
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS classification_log (
            complaint_id  VARCHAR,
            raw_response  TEXT,
            parse_success BOOLEAN,
            latency_ms    INTEGER,
            model_used    VARCHAR,
            logged_at     TIMESTAMP DEFAULT current_timestamp
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_authentication (
            UserID    VARCHAR PRIMARY KEY,
            Password  VARCHAR NOT NULL,
            UserType  VARCHAR NOT NULL,
            Team      VARCHAR NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS customer_kyc (
            customer_id     VARCHAR PRIMARY KEY,
            cust_name       VARCHAR NOT NULL,
            cust_email      VARCHAR,
            cust_phone      VARCHAR,
            date_of_birth   DATE,
            pan_number      VARCHAR,
            aadhaar_number  VARCHAR,
            address         TEXT,
            city            VARCHAR,
            state           VARCHAR,
            pincode         VARCHAR,
            kyc_status      VARCHAR DEFAULT 'pending',
            kyc_verified_at TIMESTAMP,
            created_at      TIMESTAMP DEFAULT current_timestamp
        )
    """)

    # seed default users
    conn.executemany("""
        INSERT OR IGNORE INTO user_authentication (UserID, Password, UserType, Team)
        VALUES (?, ?, ?, ?)
    """, DEFAULT_USERS)

    conn.close()
    print(f"[db] Initialised: {DB_PATH}")


def init_routing_db() -> None:
    """Create routing_decisions table in routing.duckdb."""
    conn = get_routing_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS routing_decisions (
            routing_id           VARCHAR PRIMARY KEY,
            complaint_id         VARCHAR NOT NULL,
            customer_id          VARCHAR,
            cust_name            VARCHAR,
            complaint            TEXT,
            category             VARCHAR,
            priority             VARCHAR,
            sentiment            VARCHAR,
            original_team        VARCHAR,
            routed_team          VARCHAR,
            escalate             BOOLEAN,
            escalate_to          VARCHAR,
            action               TEXT,
            routing_reason       TEXT,
            confidence           VARCHAR,
            team_email           VARCHAR,
            sla_hours            INTEGER,
            complaint_created_at TIMESTAMP,
            routing_status       VARCHAR DEFAULT 'routed',
            routed_at            TIMESTAMP DEFAULT current_timestamp,
            latency_ms           INTEGER,
            model_used           VARCHAR
        )
    """)
    conn.close()
    print(f"[db] Routing DB initialised: {ROUTING_DB}")


# ── Complaints ────────────────────────────────────────────────────────────────

def insert_complaint(record: dict) -> None:
    """Insert or replace a complaint record."""
    conn = get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO complaints
            (complaint_id, customer_id, cust_name, cust_email, complaint,
             channel, branch, account_type, category, priority, team,
             sentiment, sla_days, summary, reasoning, status, created_at, sla_deadline)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                current_timestamp, current_timestamp + INTERVAL (?) DAY)
    """, [
        record["complaint_id"], record["customer_id"], record["cust_name"],
        record.get("cust_email"), record["complaint"],
        record.get("channel"), record.get("branch"), record.get("account_type"),
        record.get("category"), record.get("priority"), record.get("team"),
        record.get("sentiment"), record.get("sla_days"), record.get("summary"),
        record.get("reasoning"), record.get("status", "New"),
        record.get("sla_days", 1),
    ])
    conn.close()


def fetch_queue(priority_filter: str = None, limit: int = 50) -> list[dict]:
    """Fetch complaints ordered by created_at desc, optionally filtered by priority."""
    conn = get_conn()
    if priority_filter:
        rows = conn.execute(
            "SELECT * FROM complaints WHERE priority=? ORDER BY created_at DESC LIMIT ?",
            [priority_filter, limit]
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM complaints ORDER BY created_at DESC LIMIT ?", [limit]
        ).fetchall()
    cols = [d[0] for d in conn.description]
    conn.close()
    return [dict(zip(cols, r)) for r in rows]


def fetch_stats() -> dict:
    """Return aggregate stats across complaints table."""
    conn = get_conn()
    total    = conn.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]
    by_cat   = dict(conn.execute(
        "SELECT category, COUNT(*) FROM complaints GROUP BY category").fetchall())
    by_pri   = dict(conn.execute(
        "SELECT priority, COUNT(*) FROM complaints GROUP BY priority").fetchall())
    breached = conn.execute(
        "SELECT COUNT(*) FROM complaints WHERE status='open' AND sla_deadline < current_timestamp"
    ).fetchone()[0]
    conn.close()
    return {
        "total": total,
        "by_category": by_cat,
        "by_priority": by_pri,
        "sla_breached": breached,
    }


# ── Classification log ────────────────────────────────────────────────────────

def log_classification(record: dict) -> None:
    """Append a row to classification_log."""
    conn = get_conn()
    conn.execute("""
        INSERT INTO classification_log
            (complaint_id, raw_response, parse_success, latency_ms, model_used)
        VALUES (?, ?, ?, ?, ?)
    """, [
        record["complaint_id"], record["raw_response"],
        record["parse_success"], record["latency_ms"], record["model_used"],
    ])
    conn.close()


# ── Synthetic raw ─────────────────────────────────────────────────────────────

def load_json_to_db(json_path: str) -> None:
    """Load a synthetic_complaints.json file into synthetic_raw table."""
    import json
    import os

    if not os.path.exists(json_path):
        print(f"[db] File not found: {json_path}")
        return
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    if not data:
        print("[db] JSON file is empty.")
        return

    conn = get_conn()
    conn.executemany("""
        INSERT INTO synthetic_raw
            (customer_id, cust_name, cust_email, complaint, category, channel, branch, account_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        (r["customer_id"], r["cust_name"], r.get("cust_email"), r["complaint"],
         r["category"], r["channel"], r.get("branch"), r["account_type"])
        for r in data
    ])
    conn.close()
    print(f"[db] Loaded {len(data)} records from {json_path} into synthetic_raw.")


# ── Routing decisions ─────────────────────────────────────────────────────────

def insert_routing_decision(d: dict) -> None:
    """Insert or replace a routing decision record."""
    conn = get_routing_conn()
    conn.execute("""
        INSERT OR REPLACE INTO routing_decisions (
            routing_id, complaint_id, customer_id, cust_name, complaint,
            category, priority, sentiment, original_team, routed_team,
            escalate, escalate_to, action, routing_reason, confidence,
            team_email, sla_hours, complaint_created_at,
            routing_status, routed_at, latency_ms, model_used
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                  'routed', current_timestamp, ?, ?)
    """, [
        d["routing_id"],    d["complaint_id"],
        d["customer_id"],   d["cust_name"],
        d["complaint"],     d["category"],
        d["priority"],      d["sentiment"],
        d["original_team"], d["routed_team"],
        d["escalate"],      d["escalate_to"],
        d["action"],        d["routing_reason"],
        d["confidence"],    d["team_email"],
        d["sla_hours"],     d["complaint_created_at"],
        d["latency_ms"],    d["model_used"],
    ])
    conn.close()


def fetch_unrouted() -> list[dict]:
    """Return complaints from complaints.duckdb not yet in routing_decisions."""
    src  = duckdb.connect(DB_PATH, read_only=True)
    rows = src.execute("""
        SELECT complaint_id, customer_id, cust_name, complaint,
               category, priority, sentiment, team, created_at
        FROM complaints
        ORDER BY priority ASC, created_at ASC
    """).fetchall()
    src.close()

    cols = ["complaint_id", "customer_id", "cust_name", "complaint",
            "category", "priority", "sentiment", "team", "created_at"]
    all_complaints = [dict(zip(cols, r)) for r in rows]

    try:
        rtr    = duckdb.connect(ROUTING_DB, read_only=True)
        routed = {r[0] for r in rtr.execute(
            "SELECT complaint_id FROM routing_decisions").fetchall()}
        rtr.close()
    except Exception:
        routed = set()

    pending = [c for c in all_complaints if c["complaint_id"] not in routed]
    print(f"[db] Total: {len(all_complaints)} | Routed: {len(routed)} | Pending: {len(pending)}")
    return pending


# ── Auth ──────────────────────────────────────────────────────────────────────

def authenticate_user(user_id: str, password: str) -> dict | None:
    """
    Validate credentials against user_authentication table.
    Returns {"UserID": ..., "UserType": ...} on success, None on failure.
    """
    conn = get_conn()
    row  = conn.execute(
        "SELECT UserID, UserType FROM user_authentication WHERE UserID=? AND Password=?",
        [user_id, password]
    ).fetchone()
    conn.close()
    if row:
        return {"UserID": row[0], "UserType": row[1]}
    return None


# ── UI functions (used by app_form.py and details_form.py) ────────────────────

def get_routing_conn_ro() -> duckdb.DuckDBPyConnection:
    """Read-only connection to routing DB -- safe for concurrent access."""
    return duckdb.connect(ROUTING_DB, read_only=True)

def authenticate_user_ui(user_id: str, password: str) -> tuple:
    """
    UI version -- returns (True, UserType, Team) or (False, None, None).
    Used by app_form.py login handler.
    """
    conn   = duckdb.connect(DB_PATH, read_only=True)
    result = conn.execute(
        "SELECT UserType, Team FROM user_authentication WHERE UserID=? AND Password=?",
        [user_id, password]
    ).fetchone()
    conn.close()
    if result:
        return True, result[0], result[1]
    return False, None, None


TEAM_ROUTING_MAP = {
    "Fraud":     "Fraud Response Team",
    "KYC":       "KYC Team",
    "Card":      "Card Operations",
    "Loan":      "Loan Servicing",
    "Digital":   "Digital Banking",
    "Branch":    "Branch Support",
    "Insurance": "Insurance Claims",
    "Corporate": "General Support",
    "General":   "General Support",
    "Admin":     None,
}


def fetch_requests_list(user_type: str, team: str = ""):
    """
    Fetch routing_decisions for the logged-in user.
    Admin    -> all rows.
    Others   -> rows matching their Team from user_authentication
                mapped to routed_team via TEAM_ROUTING_MAP.
    """
    import pandas as pd
    conn = get_routing_conn_ro()

    if user_type == "Admin":
        df = conn.execute(
            "SELECT * FROM routing_decisions ORDER BY priority ASC, routed_at DESC"
        ).fetchdf()
    else:
        routed_team = TEAM_ROUTING_MAP.get(team)
        if routed_team:
            df = conn.execute(
                "SELECT * FROM routing_decisions WHERE routed_team=? "
                "ORDER BY priority ASC, routed_at DESC",
                [routed_team]
            ).fetchdf()
        else:
            df = conn.execute(
                "SELECT * FROM routing_decisions ORDER BY priority ASC, routed_at DESC"
            ).fetchdf()

    conn.close()
    return df


def fetch_complaint_details(complaint_id: str) -> dict:
    """Fetch a single routing_decision row as dict."""
    conn = get_routing_conn_ro()
    row  = conn.execute(
        "SELECT * FROM routing_decisions WHERE complaint_id=?", [complaint_id]
    ).fetchone()
    cols = [d[0] for d in conn.description]
    conn.close()
    return dict(zip(cols, row)) if row else {}


def get_dropdown_choices() -> tuple:
    """
    Returns (user_ids, teams) for details_form dropdowns.
    user_ids from user_authentication in complaints.duckdb.
    teams from distinct routed_team in routing_decisions, falls back to TEAM_MAP.
    """
    c_conn   = duckdb.connect(DB_PATH, read_only=True)
    user_ids = [r[0] for r in c_conn.execute(
        "SELECT UserID FROM user_authentication ORDER BY UserID"
    ).fetchall()]
    c_conn.close()

    r_conn = get_routing_conn_ro()
    try:
        teams = [r[0] for r in r_conn.execute(
            "SELECT DISTINCT routed_team FROM routing_decisions "
            "WHERE routed_team IS NOT NULL ORDER BY routed_team"
        ).fetchall()]
        if not teams:
            teams = sorted(TEAM_MAP.values())
    except Exception:
        teams = sorted(TEAM_MAP.values())
    r_conn.close()

    return user_ids, teams


def update_complaint_routing(
    complaint_id:   str,
    routed_team:    str,
    escalate:       bool,
    escalate_to:    str,
    action:         str,
    routing_reason: str,
    team_email:     str,
) -> None:
    """Update editable fields on a routing_decision row."""
    conn = get_routing_conn()
    conn.execute("""
        UPDATE routing_decisions
        SET routed_team=?, escalate=?, escalate_to=?, action=?,
            routing_reason=?, team_email=?
        WHERE complaint_id=?
    """, [routed_team, escalate, escalate_to, action,
          routing_reason, team_email, complaint_id])
    conn.close()


# ── Dashboard functions (used by app_form_v2.py) ──────────────────────────────

def get_filter_choices() -> tuple:
    """Return distinct category, priority, status values for dashboard dropdowns."""
    conn       = get_routing_conn_ro()
    categories = [r[0] for r in conn.execute(
        "SELECT DISTINCT category FROM routing_decisions WHERE category IS NOT NULL"
    ).fetchall()]
    priorities = [r[0] for r in conn.execute(
        "SELECT DISTINCT priority FROM routing_decisions WHERE priority IS NOT NULL"
    ).fetchall()]
    statuses   = [r[0] for r in conn.execute(
        "SELECT DISTINCT routing_status FROM routing_decisions WHERE routing_status IS NOT NULL"
    ).fetchall()]
    conn.close()
    return categories, priorities, statuses


def fetch_dashboard_data(
    user_type: str,
    category:  str = None,
    priority:  str = None,
    escalate:  str = None,
    status:    str = None,
) -> tuple:
    """
    Fetch filtered routing_decisions for the supervisor dashboard.
    Returns (df, total, escalated, avg_sla, cat_df, pri_df).
    """
    import pandas as pd

    conn   = get_routing_conn_ro()
    query  = "SELECT * FROM routing_decisions WHERE routed_team = ?"
    params = [user_type]

    if category: query += " AND category = ?";        params.append(category)
    if priority: query += " AND priority = ?";        params.append(priority)
    if escalate: query += " AND escalate = ?";        params.append(escalate == "True")
    if status:   query += " AND routing_status = ?";  params.append(status)

    df = conn.execute(query, params).fetchdf()
    conn.close()

    if df.empty:
        return (
            df, 0, 0, "0 hrs",
            pd.DataFrame(columns=["Category", "Count"]),
            pd.DataFrame(columns=["Priority",  "Count"]),
        )

    total     = len(df)
    escalated = int(df["escalate"].sum())
    avg_sla   = f"{df['sla_hours'].mean():.1f} hrs"

    cat_df          = df["category"].value_counts().reset_index()
    cat_df.columns  = ["Category", "Count"]
    pri_df          = df["priority"].value_counts().reset_index()
    pri_df.columns  = ["Priority", "Count"]

    return df, total, escalated, avg_sla, cat_df, pri_df
