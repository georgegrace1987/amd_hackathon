# ============================================================
# complaints_app.py
# Complaint Management System — Streamlit UI
# ============================================================

import streamlit as st
import duckdb
import pandas as pd
import uuid
import json
import os
from datetime import datetime, timedelta

# ── Configuration ──────────────────────────────────────────────
DB_PATH = "complaints.duckdb"
JSON_PATH = "synthetic_complaints.json"

VALID_STATUSES = ["open", "in_progress", "resolved", "closed", "escalated"]
VALID_PRIORITIES = ["critical", "high", "medium", "low"]
VALID_CATEGORIES = [
    "fraud", "billing", "service", "technical",
    "account", "loan", "card", "insurance", "other",
]
VALID_CHANNELS = ["email", "phone", "chat", "branch", "web", "social_media"]
VALID_ACCOUNT_TYPES = ["savings", "current", "credit_card", "loan", "fixed_deposit"]
VALID_TEAMS = [
    "fraud_investigation", "billing_resolution", "customer_service",
    "technical_support", "loan_servicing", "card_services",
    "insurance_claims", "escalation_desk",
]
VALID_SENTIMENTS = ["negative", "neutral", "positive"]

# ── Database helpers ───────────────────────────────────────────

def get_conn():
    """Return a DuckDB connection to the complaints database."""
    return duckdb.connect(DB_PATH)


def init_db():
    """Create all required tables if they do not already exist."""
    conn = get_conn()
    try:
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
                status        VARCHAR DEFAULT 'open',
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
    finally:
        conn.close()


def insert_complaint(record: dict):
    """Insert or replace a single complaint record."""
    conn = get_conn()
    try:
        sla_days_val = record.get("sla_days") or 1
        conn.execute("""
            INSERT OR REPLACE INTO complaints
                (complaint_id, customer_id, cust_name, cust_email, complaint,
                 channel, branch, account_type, category, priority, team,
                 sentiment, sla_days, summary, reasoning, status,
                 created_at, sla_deadline)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    current_timestamp,
                    current_timestamp + INTERVAL '?' DAY)
        """, [
            record["complaint_id"],
            record["customer_id"],
            record["cust_name"],
            record.get("cust_email"),
            record["complaint"],
            record.get("channel"),
            record.get("branch"),
            record.get("account_type"),
            record.get("category"),
            record.get("priority"),
            record.get("team"),
            record.get("sentiment"),
            record.get("sla_days"),
            record.get("summary"),
            record.get("reasoning"),
            record.get("status", "open"),
            str(sla_days_val),       # INTERVAL expects string literal
        ])
    finally:
        conn.close()


def update_complaint_status(complaint_id: str, new_status: str):
    """Update the status of an existing complaint."""
    if new_status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {new_status}")
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE complaints SET status = ? WHERE complaint_id = ?",
            [new_status, complaint_id],
        )
    finally:
        conn.close()


def log_classification(record: dict):
    """Insert a classification‑log entry."""
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO classification_log
                (complaint_id, raw_response, parse_success, latency_ms, model_used)
            VALUES (?, ?, ?, ?, ?)
        """, [
            record["complaint_id"],
            record["raw_response"],
            record["parse_success"],
            record["latency_ms"],
            record["model_used"],
        ])
    finally:
        conn.close()


def load_json_to_db(json_path: str = JSON_PATH):
    """Load synthetic_complaints.json into the synthetic_raw table."""
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"File not found: {json_path}")
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    if not data:
        raise ValueError("JSON file is empty.")
    conn = get_conn()
    try:
        conn.executemany("""
            INSERT INTO synthetic_raw
                (customer_id, cust_name, cust_email, complaint,
                 category, channel, branch, account_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (
                r["customer_id"], r["cust_name"], r.get("cust_email"),
                r["complaint"], r["category"], r["channel"],
                r.get("branch"), r["account_type"],
            )
            for r in data
        ])
    finally:
        conn.close()
    return len(data)


def fetch_queue(priority_filter: str | None = None,
                status_filter: str | None = None,
                category_filter: str | None = None,
                limit: int = 50):
    """Return a list of complaint dicts, newest first."""
    conn = get_conn()
    try:
        clauses, params = [], []
        if priority_filter:
            clauses.append("priority = ?")
            params.append(priority_filter)
        if status_filter:
            clauses.append("status = ?")
            params.append(status_filter)
        if category_filter:
            clauses.append("category = ?")
            params.append(category_filter)

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = conn.execute(
            f"SELECT * FROM complaints{where} ORDER BY created_at DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        cols = [d[0] for d in conn.description]
    finally:
        conn.close()
    return [dict(zip(cols, r)) for r in rows]


def fetch_complaint_by_id(complaint_id: str):
    """Return a single complaint dict or None."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM complaints WHERE complaint_id = ?",
            [complaint_id],
        ).fetchall()
        if not rows:
            return None
        cols = [d[0] for d in conn.description]
        return dict(zip(cols, rows[0]))
    finally:
        conn.close()


def fetch_stats():
    """Return aggregate statistics for the dashboard."""
    conn = get_conn()
    try:
        total = conn.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]
        by_cat = dict(
            conn.execute(
                "SELECT category, COUNT(*) FROM complaints GROUP BY category"
            ).fetchall()
        )
        by_pri = dict(
            conn.execute(
                "SELECT priority, COUNT(*) FROM complaints GROUP BY priority"
            ).fetchall()
        )
        by_status = dict(
            conn.execute(
                "SELECT status, COUNT(*) FROM complaints GROUP BY status"
            ).fetchall()
        )
        breached = conn.execute(
            "SELECT COUNT(*) FROM complaints "
            "WHERE status='open' AND sla_deadline < current_timestamp"
        ).fetchone()[0]
        return {
            "total": total,
            "by_category": by_cat,
            "by_priority": by_pri,
            "by_status": by_status,
            "sla_breached": breached,
        }
    finally:
        conn.close()


def fetch_classification_logs(limit: int = 100):
    """Return recent classification‑log entries."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM classification_log ORDER BY logged_at DESC LIMIT ?",
            [limit],
        ).fetchall()
        cols = [d[0] for d in conn.description]
    finally:
        conn.close()
    return [dict(zip(cols, r)) for r in rows]


def fetch_synthetic_raw(limit: int = 100):
    """Return rows from the synthetic_raw staging table."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM synthetic_raw ORDER BY generated_at DESC LIMIT ?",
            [limit],
        ).fetchall()
        cols = [d[0] for d in conn.description]
    finally:
        conn.close()
    return [dict(zip(cols, r)) for r in rows]


# ── Initialise DB on first import ──────────────────────────────
init_db()


# ══════════════════════════════════════════════════════════════
#  Streamlit UI
# ══════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Complaint Management System",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar Navigation ────────────────────────────────────────
st.sidebar.title("📋 Complaint Mgmt")
page = st.sidebar.radio(
    "Navigate",
    ["🏠 Dashboard", "📑 Complaints Queue", "➕ Submit Complaint",
     "📜 Classification Log", "📥 Data Ingestion"],
    index=0,
)
st.sidebar.markdown("---")
st.sidebar.caption(f"DB: `{DB_PATH}`")


# ── Page: Dashboard ───────────────────────────────────────────
if page == "🏠 Dashboard":
    st.title("🏠 Dashboard")
    try:
        stats = fetch_stats()
    except Exception as exc:
        st.error(f"Could not load stats: {exc}")
        st.stop()

    # KPI cards
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Complaints", stats["total"])
    col2.metric("SLA Breached (Open)", stats["sla_breached"],
                delta=None if stats["sla_breached"] == 0 else f"-{stats['sla_breached']}",
                delta_color="inverse")
    col3.metric("Open", stats.get("by_status", {}).get("open", 0))
    col4.metric("Resolved", stats.get("by_status", {}).get("resolved", 0))

    st.markdown("---")

    left, right = st.columns(2)

    # Priority breakdown
    with left:
        st.subheader("By Priority")
        pri_data = stats.get("by_priority", {})
        if pri_data:
            df_pri = pd.DataFrame(
                {"Priority": list(pri_data.keys()), "Count": list(pri_data.values())}
            ).sort_values("Count", ascending=False)
            st.bar_chart(df_pri.set_index("Priority"), use_container_width=True)
        else:
            st.info("No data yet.")

    # Category breakdown
    with right:
        st.subheader("By Category")
        cat_data = stats.get("by_category", {})
        if cat_data:
            df_cat = pd.DataFrame(
                {"Category": list(cat_data.keys()), "Count": list(cat_data.values())}
            ).sort_values("Count", ascending=False)
            st.bar_chart(df_cat.set_index("Category"), use_container_width=True)
        else:
            st.info("No data yet.")

    # Status breakdown table
    st.subheader("Status Breakdown")
    status_data = stats.get("by_status", {})
    if status_data:
        df_status = pd.DataFrame(
            {"Status": list(status_data.keys()), "Count": list(status_data.values())}
        )
        st.dataframe(df_status, use_container_width=True, hide_index=True)
    else:
        st.info("No status data available.")


# ── Page: Complaints Queue ────────────────────────────────────
elif page == "📑 Complaints Queue":
    st.title("📑 Complaints Queue")

    # Filters
    filter_col1, filter_col2, filter_col3 = st.columns(3)
    with filter_col1:
        priority_filter = st.selectbox(
            "Priority", [None] + VALID_PRIORITIES,
            format_func=lambda x: "All" if x is None else x.title(),
        )
    with filter_col2:
        status_filter = st.selectbox(
            "Status", [None] + VALID_STATUSES,
            format_func=lambda x: "All" if x is None else x.replace("_", " ").title(),
        )
    with filter_col3:
        category_filter = st.selectbox(
            "Category", [None] + VALID_CATEGORIES,
            format_func=lambda x: "All" if x is None else x.title(),
        )

    limit = st.slider("Rows", min_value=10, max_value=200, value=50, step=10)

    try:
        rows = fetch_queue(
            priority_filter=priority_filter,
            status_filter=status_filter,
            category_filter=category_filter,
            limit=limit,
        )
    except Exception as exc:
        st.error(f"Error fetching queue: {exc}")
        st.stop()

    if not rows:
        st.info("No complaints match the current filters.")
    else:
        df = pd.DataFrame(rows)
        # Highlight SLA-breached rows
        df["sla_breached"] = (
            (df["status"] == "open")
            & (pd.to_datetime(df["sla_deadline"]) < pd.Timestamp.now())
        )

        st.subheader(f"Showing {len(df)} complaint(s)")

        # Display full table
        display_cols = [
            "complaint_id", "cust_name", "category", "priority",
            "status", "team", "created_at", "sla_deadline", "sla_breached",
        ]
        existing_cols = [c for c in display_cols if c in df.columns]
        st.dataframe(
            df[existing_cols],
            use_container_width=True,
            hide_index=True,
            column_config={
                "sla_breached": st.column_config.CheckboxColumn("SLA Breached"),
            },
        )

        # Detail view
        st.markdown("---")
        st.subheader("🔍 Complaint Detail")
        selected_id = st.selectbox(
            "Select Complaint ID",
            df["complaint_id"].tolist(),
        )
        detail = fetch_complaint_by_id(selected_id)
        if detail:
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown(f"**Customer:** {detail.get('cust_name', '—')}")
                st.markdown(f"**Email:** {detail.get('cust_email', '—')}")
                st.markdown(f"**Customer ID:** {detail.get('customer_id', '—')}")
                st.markdown(f"**Channel:** {detail.get('channel', '—')}")
                st.markdown(f"**Branch:** {detail.get('branch', '—')}")
                st.markdown(f"**Account Type:** {detail.get('account_type', '—')}")
            with col_b:
                st.markdown(f"**Category:** {detail.get('category', '—')}")
                st.markdown(f"**Priority:** {detail.get('priority', '—')}")
                st.markdown(f"**Team:** {detail.get('team', '—')}")
                st.markdown(f"**Sentiment:** {detail.get('sentiment', '—')}")
                st.markdown(f"**SLA Days:** {detail.get('sla_days', '—')}")
                st.markdown(f"**Created:** {detail.get('created_at', '—')}")
                st.markdown(f"**SLA Deadline:** {detail.get('sla_deadline', '—')}")

            st.markdown("---")
            st.markdown("**Complaint:**")
            st.info(detail.get("complaint", ""))

            if detail.get("summary"):
                st.markdown("**AI Summary:**")
                st.success(detail["summary"])
            if detail.get("reasoning"):
                st.markdown("**AI Reasoning:**")
                st.warning(detail["reasoning"])

            # Status update
            st.markdown("---")
            new_status = st.selectbox(
                "Update Status",
                VALID_STATUSES,
                index=VALID_STATUSES.index(detail.get("status", "open"))
                if detail.get("status") in VALID_STATUSES else 0,
                key=f"status_{selected_id}",
            )
            if st.button("💾 Save Status", key=f"save_{selected_id}"):
                try:
                    update_complaint_status(selected_id, new_status)
                    st.success(f"Status updated to **{new_status}**")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Failed to update: {exc}")


# ── Page: Submit Complaint ────────────────────────────────────
elif page == "➕ Submit Complaint":
    st.title("➕ Submit New Complaint")

    with st.form("complaint_form", clear_on_submit=False):
        st.subheader("Customer Information")
        c1, c2 = st.columns(2)
        with c1:
            cust_name = st.text_input("Customer Name *", max_chars=120)
            customer_id = st.text_input("Customer ID *", max_chars=30)
        with c2:
            cust_email = st.text_input("Customer Email", max_chars=120)
            branch = st.text_input("Branch", max_chars=80)

        st.subheader("Complaint Details")
        complaint_text = st.text_area("Complaint *", height=150, max_chars=2000)

        c3, c4, c5 = st.columns(3)
        with c3:
            channel = st.selectbox("Channel", VALID_CHANNELS)
            account_type = st.selectbox("Account Type", VALID_ACCOUNT_TYPES)
        with c4:
            category = st.selectbox("Category", VALID_CATEGORIES)
            priority = st.selectbox("Priority", VALID_PRIORITIES)
        with c5:
            team = st.selectbox("Assigned Team", VALID_TEAMS)
            sentiment = st.selectbox("Sentiment", VALID_SENTIMENTS)

        sla_days = st.number_input(
            "SLA Days", min_value=1, max_value=30, value=3,
        )

        st.subheader("AI Classification (optional)")
        summary = st.text_area("Summary", height=80, max_chars=500)
        reasoning = st.text_area("Reasoning", height=80, max_chars=1000)

        submitted = st.form_submit_button("🚀 Submit Complaint")

        if submitted:
            # Validation
            errors = []
            if not cust_name.strip():
                errors.append("Customer Name is required.")
            if not customer_id.strip():
                errors.append("Customer ID is required.")
            if not complaint_text.strip():
                errors.append("Complaint text is required.")
            if cust_email and "@" not in cust_email:
                errors.append("Invalid email format.")

            if errors:
                for e in errors:
                    st.error(e)
            else:
                complaint_id = f"CMP-{uuid.uuid4().hex[:8].upper()}"
                record = {
                    "complaint_id": complaint_id,
                    "customer_id": customer_id.strip(),
                    "cust_name": cust_name.strip(),
                    "cust_email": cust_email.strip() or None,
                    "complaint": complaint_text.strip(),
                    "channel": channel,
                    "branch": branch.strip() or None,
                    "account_type": account_type,
                    "category": category,
                    "priority": priority,
                    "team": team,
                    "sentiment": sentiment,
                    "sla_days": int(sla_days),
                    "summary": summary.strip() or None,
                    "reasoning": reasoning.strip() or None,
                    "status": "open",
                }
                try:
                    insert_complaint(record)
                    st.success(f"Complaint **{complaint_id}** created successfully!")
                except Exception as exc:
                    st.error(f"Failed to insert complaint: {exc}")


# ── Page: Classification Log ──────────────────────────────────
elif page == "📜 Classification Log":
    st.title("📜 Classification Log")

    log_limit = st.slider("Rows to display", min_value=10, max_value=500,
                          value=100, step=10)
    try:
        logs = fetch_classification_logs(limit=log_limit)
    except Exception as exc:
        st.error(f"Error loading logs: {exc}")
        st.stop()

    if not logs:
        st.info("No classification logs recorded yet.")
    else:
        df_log = pd.DataFrame(logs)
        st.dataframe(df_log, use_container_width=True, hide_index=True)

        # Metrics
        total_logs = len(df_log)
        success_count = int(df_log["parse_success"].sum()) if "parse_success" in df_log.columns else 0
        avg_latency = (
            df_log["latency_ms"].mean() if "latency_ms" in df_log.columns else 0
        )
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Logs", total_logs)
        m2.metric("Parse Success Rate",
                   f"{success_count / total_logs * 100:.1f}%" if total_logs else "N/A")
        m3.metric("Avg Latency (ms)", f"{avg_latency:.0f}" if total_logs else "N/A")


# ── Page: Data Ingestion ──────────────────────────────────────
elif page == "📥 Data Ingestion":
    st.title("📥 Data Ingestion")

    st.markdown(
        "Load records from a `synthetic_complaints.json` file into the "
        "`synthetic_raw` staging table."
    )

    json_path_input = st.text_input("JSON File Path", value=JSON_PATH)

    if st.button("📂 Load JSON → synthetic_raw"):
        try:
            count = load_json_to_db(json_path_input)
            st.success(f"✅ Loaded **{count}** record(s) from `{json_path_input}`.")
        except FileNotFoundError:
            st.error(f"❌ File not found: `{json_path_input}`")
        except json.JSONDecodeError:
            st.error("❌ File is not valid JSON.")
        except ValueError as ve:
            st.error(f"❌ {ve}")
        except Exception as exc:
            st.error(f"❌ Unexpected error: {exc}")

    st.markdown("---")
    st.subheader("Synthetic Raw Preview")

    try:
        raw_rows = fetch_synthetic_raw(limit=50)
    except Exception as exc:
        st.error(f"Error loading synthetic_raw: {exc}")
        st.stop()

    if not raw_rows:
        st.info("The `synthetic_raw` table is empty. Load data above.")
    else:
        df_raw = pd.DataFrame(raw_rows)
        st.dataframe(df_raw, use_container_width=True, hide_index=True)