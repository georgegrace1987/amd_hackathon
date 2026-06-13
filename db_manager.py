import duckdb
import pandas as pd

ROUTING_DB = "routing.duckdb"

def get_routing_conn():
    return duckdb.connect(ROUTING_DB)

def init_dbs():
    conn = get_routing_conn()
    # 1. Create routing_decisions table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS routing_decisions (
            routing_id VARCHAR PRIMARY KEY, complaint_id VARCHAR NOT NULL,
            customer_id VARCHAR, cust_name VARCHAR, complaint TEXT,
            category VARCHAR, priority VARCHAR, sentiment VARCHAR,
            original_team VARCHAR, routed_team VARCHAR, escalate BOOLEAN,
            escalate_to VARCHAR, action TEXT, routing_reason TEXT,
            confidence VARCHAR, team_email VARCHAR, sla_hours INTEGER,
            complaint_created_at TIMESTAMP, routing_status VARCHAR DEFAULT 'routed',
            routed_at TIMESTAMP DEFAULT current_timestamp, latency_ms INTEGER, model_used VARCHAR
        )
    """)
    # 2. Create user_authentication table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_authentication (
            UserID VARCHAR PRIMARY KEY, Password VARCHAR NOT NULL, UserType VARCHAR NOT NULL
        )
    """)
    # 3. Seed Users if empty
    if conn.execute("SELECT COUNT(*) FROM user_authentication").fetchone()[0] == 0:
        users = [
            ("Fraud_Member_01", "FM01", "Fraud Response Team"), ("Fraud_Member_02", "FM02", "Fraud Response Team"),
            ("Fraud_Supervisor_01", "FMS01", "Fraud Response Team"), ("KYC_Member_01", "KYC01", "KYC Team"),
            ("KYC_Supervisor_01", "KYCS01", "KYC Team"), ("Admin", "Admin", "Admin")
        ]
        conn.executemany("INSERT OR IGNORE INTO user_authentication VALUES (?, ?, ?)", users)
    # 4. Seed Routing Data if empty
    if conn.execute("SELECT COUNT(*) FROM routing_decisions").fetchone()[0] == 0:
        routes = [
            ('RT-001', 'CMP-001', 'CUST-001', 'Rahul', 'Fraud transaction', 'fraud', 'P1', 'angry', 'Fraud Response Team', 'Fraud Response Team', False, None, None, 'Suspicious activity', 'High', 'fraud@bank.com', 24, '2025-06-12 10:00:00', 'routed', '2025-06-12 10:05:00', 150, 'vLLM'),
            ('RT-002', 'CMP-002', 'CUST-002', 'Priya', 'KYC pending', 'kyc_onboarding', 'P2', 'frustrated', 'KYC Team', 'KYC Team', False, None, None, 'Document required', 'Medium', 'kyc@bank.com', 48, '2025-06-12 11:00:00', 'routed', '2025-06-12 11:05:00', 120, 'vLLM')
        ]
        conn.executemany("""INSERT OR IGNORE INTO routing_decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", routes)
    conn.close()

def authenticate_user(user_id, password):
    conn = get_routing_conn()
    result = conn.execute("SELECT UserType FROM user_authentication WHERE UserID = ? AND Password = ?", [user_id, password]).fetchone()
    conn.close()
    if result: return True, result[0]
    return False, None

def fetch_requests_list(user_type):
    conn = get_routing_conn()
    df = conn.execute("SELECT * FROM routing_decisions WHERE routed_team = ?", [user_type]).fetchdf()
    conn.close()
    return df

def fetch_complaint_details(complaint_id):
    conn = get_routing_conn()
    row = conn.execute("SELECT * FROM routing_decisions WHERE complaint_id = ?", [complaint_id]).fetchone()
    cols = [d[0] for d in conn.description]
    conn.close()
    return dict(zip(cols, row)) if row else {}

def get_dropdown_choices():
    conn = get_routing_conn()
    user_ids = [r[0] for r in conn.execute("SELECT UserID FROM user_authentication ORDER BY UserID").fetchall()]
    teams = [r[0] for r in conn.execute("SELECT DISTINCT UserType FROM user_authentication ORDER BY UserType").fetchall()]
    conn.close()
    return user_ids, teams

def update_complaint(complaint_id, routed_team, escalate, escalate_to, action, routing_reason, team_email):
    conn = get_routing_conn()
    conn.execute("""
        UPDATE routing_decisions 
        SET routed_team=?, escalate=?, escalate_to=?, action=?, routing_reason=?, team_email=?
        WHERE complaint_id=?
    """, [routed_team, escalate, escalate_to, action, routing_reason, team_email, complaint_id])
    conn.close()

# Initialize on import
init_dbs()