import gradio as gr
import duckdb
import pandas as pd

# --- Database Configuration ---
ROUTING_DB = "routing.duckdb"
COMPLAINTS_DB = "complaints.duckdb"

# --- Database Initialization & Helper Functions ---
def get_routing_conn():
    return duckdb.connect(ROUTING_DB)

def init_dbs():
    # 1. Initialize Routing DB
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
    
    # 2. Initialize User Authentication Table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_authentication (
            UserID    VARCHAR PRIMARY KEY,
            Password  VARCHAR NOT NULL,
            UserType  VARCHAR NOT NULL
        )
    """)
    
    # 3. Seed default users if empty
    user_count = conn.execute("SELECT COUNT(*) FROM user_authentication").fetchone()[0]
    if user_count == 0:
        specific_users = [
            ("Fraud_Member_01", "FM01", "Fraud Response Team"),
            ("Fraud_Member_02", "FM02", "Fraud Response Team"),
            ("Fraud_Supervisor_01", "FMS01", "Fraud Response Team"),
            ("KYC_Member_01", "KYC01", "KYC Team"),
            ("KYC_Supervisor_01", "KYCS01", "KYC Team"),
            ("Admin", "Admin", "Admin")
        ]
        conn.executemany("INSERT OR IGNORE INTO user_authentication (UserID, Password, UserType) VALUES (?, ?, ?)", specific_users)
        
    # 4. Seed sample routing data if empty (for testing purposes)
    route_count = conn.execute("SELECT COUNT(*) FROM routing_decisions").fetchone()[0]
    if route_count == 0:
        sample_routes = [
            ('RT-001', 'CMP-001', 'CUST-001', 'Rahul', 'Fraud transaction', 'fraud', 'P1', 'angry', 'Fraud Response Team', 'Fraud Response Team', False, None, None, 'Suspicious activity', 'High', 'fraud@bank.com', 24, '2025-06-12 10:00:00', 'routed', '2025-06-12 10:05:00', 150, 'vLLM'),
            ('RT-002', 'CMP-002', 'CUST-002', 'Priya', 'KYC pending', 'kyc_onboarding', 'P2', 'frustrated', 'KYC Team', 'KYC Team', False, None, None, 'Document required', 'Medium', 'kyc@bank.com', 48, '2025-06-12 11:00:00', 'routed', '2025-06-12 11:05:00', 120, 'vLLM')
        ]
        conn.executemany("""INSERT OR IGNORE INTO routing_decisions 
                            (routing_id, complaint_id, customer_id, cust_name, complaint, category, priority, sentiment, original_team, routed_team, escalate, escalate_to, action, routing_reason, confidence, team_email, sla_hours, complaint_created_at, routing_status, routed_at, latency_ms, model_used) 
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", sample_routes)
            
    conn.close()
    print("Databases initialised.")

init_dbs()

def authenticate_user(user_id, password):
    """Validates user. Only shows error for incorrect password, not invalid user."""
    conn = get_routing_conn()
    result = conn.execute("SELECT UserType FROM user_authentication WHERE UserID = ? AND Password = ?", [user_id, password]).fetchone()
    conn.close()
    
    if result:
        return True, result[0], ""
    else:
        # Intentionally generic error to prevent UserID enumeration
        return False, "", "❌ Incorrect password. Please try again."

def fetch_requests_list(user_type):
    """Fetches routing_decisions filtered by the logged-in user's UserType."""
    conn = get_routing_conn()
    df = conn.execute("SELECT * FROM routing_decisions WHERE routed_team = ?", [user_type]).fetchdf()
    conn.close()
    return df

def fetch_complaint_details(complaint_id):
    """Fetches single complaint details for the form."""
    conn = get_routing_conn()
    row = conn.execute("SELECT * FROM routing_decisions WHERE complaint_id = ?", [complaint_id]).fetchone()
    cols = [d[0] for d in conn.description]
    conn.close()
    if row:
        return dict(zip(cols, row))
    return {}

def get_dropdown_choices():
    """Fetches dynamic dropdown choices from user_authentication table."""
    conn = get_routing_conn()
    user_ids = [r[0] for r in conn.execute("SELECT UserID FROM user_authentication ORDER BY UserID").fetchall()]
    teams = [r[0] for r in conn.execute("SELECT DISTINCT UserType FROM user_authentication ORDER BY UserType").fetchall()]
    conn.close()
    return user_ids, teams

def validate_dropdown_selection(selected_value, valid_choices):
    """Validates dropdown selections against DB values."""
    if not selected_value or selected_value.startswith("Select"):
        return ""
    if selected_value not in valid_choices:
        return f"⚠️ Invalid selection: {selected_value} not found in database."
    return "✅ Valid selection"

def update_complaint(complaint_id, routed_team, escalate, escalate_to, action, routing_reason, team_email):
    """Updates the database with edited values."""
    if not action or not action.strip():
        return "❌ Action field is mandatory."
    
    conn = get_routing_conn()
    conn.execute("""
        UPDATE routing_decisions 
        SET routed_team=?, escalate=?, escalate_to=?, action=?, routing_reason=?, team_email=?
        WHERE complaint_id=?
    """, [routed_team, escalate, escalate_to, action, routing_reason, team_email, complaint_id])
    conn.close()
    return f"✅ Successfully updated Complaint ID: {complaint_id}"


# --- Gradio UI ---
user_ids, teams = get_dropdown_choices()

with gr.Blocks(title="Bank Routing Portal", css="label { font-weight: bold; font-family: Arial, sans-serif; }") as app:
    # State variables
    logged_in_user_type = gr.State("")
    current_df_state = gr.State(pd.DataFrame())
    
    # ==========================================
    # PAGE 1: LOGIN
    # ==========================================
    with gr.Column(visible=True, scale=1) as login_page:
        gr.Markdown("# 🏦 Bank Employee Login")
        with gr.Group():
            user_id_input = gr.Textbox(label="UserID", placeholder="Enter your UserID")
            password_input = gr.Textbox(label="Password", type="password", placeholder="Enter your password")
            login_btn = gr.Button("Login", variant="primary")
            login_error = gr.Markdown("", visible=True)

    # ==========================================
    # PAGE 2: REQUEST LIST
    # ==========================================
    with gr.Column(visible=False, scale=1) as list_page:
        gr.Markdown("# 📋 Request List")
        gr.Markdown("Click on any row to view and edit the complaint details.")
        
        requests_table = gr.Dataframe(
            value=pd.DataFrame(), 
            interactive=True, # Enables sorting and filtering natively
            wrap=True
        )
        
        with gr.Row():
            back_to_login_btn = gr.Button("Logout", variant="stop")
            selected_complaint_id = gr.Textbox(label="Selected Complaint ID", interactive=False)
            view_details_btn = gr.Button("View Details", variant="primary")

    # ==========================================
    # PAGE 3: COMPLAINT DETAILS
    # ==========================================
    with gr.Column(visible=False, scale=1) as details_page:
        gr.Markdown("# 📝 Complaint Details")
        
        with gr.Group():
            gr.Markdown("### Read-Only Information")
            with gr.Row():
                d_routing_id = gr.Textbox(label="Routing ID", interactive=False)
                d_complaint_id = gr.Textbox(label="Complaint ID", interactive=False)
                d_customer_id = gr.Textbox(label="Customer ID", interactive=False)
                d_cust_name = gr.Textbox(label="Customer Name", interactive=False)
            
            d_complaint = gr.Textbox(label="Complaint", interactive=False, lines=3)
            
            with gr.Row():
                d_category = gr.Textbox(label="Category", interactive=False)
                d_priority = gr.Textbox(label="Priority", interactive=False)
                d_sentiment = gr.Textbox(label="Sentiment", interactive=False)
                d_original_team = gr.Textbox(label="Original Team", interactive=False)
            
            with gr.Row():
                d_confidence = gr.Textbox(label="Confidence", interactive=False)
                d_sla_hours = gr.Textbox(label="SLA Hours", interactive=False)
                d_routing_status = gr.Textbox(label="Routing Status", interactive=False)
                d_latency_ms = gr.Textbox(label="Latency (ms)", interactive=False)
                
            d_routing_reason_ro = gr.Textbox(label="Routing Reason (Original)", interactive=False)
            d_team_email_ro = gr.Textbox(label="Team Email (Original)", interactive=False)

        with gr.Group():
            gr.Markdown("### Editable Fields")
            d_routed_team = gr.Dropdown(choices=teams, label="Routed Team", value="Select team to re-route", allow_custom_value=True)
            routed_team_validation = gr.Markdown("")
            
            d_escalate = gr.Checkbox(label="Escalate", value=False)
            d_escalate_to = gr.Dropdown(choices=user_ids, label="Escalate To", value="Select ID to re-route", allow_custom_value=True)
            escalate_to_validation = gr.Markdown("")
            
            d_action = gr.Textbox(label="Action *", placeholder="Mandatory: Enter action taken", lines=2)
            d_routing_reason = gr.Textbox(label="Routing Reason", placeholder="Update routing reason if changed", lines=2)
            d_team_email = gr.Textbox(label="Team Email", placeholder="Update team email if changed")
            
            submit_btn = gr.Button("Submit Update", variant="primary")
            update_status_msg = gr.Markdown("")
            
        back_to_list_btn = gr.Button("← Back to List")

    # --- UI Logic / Events ---

    # Login Logic
    def handle_login(uid, pwd):
        success, user_type, err = authenticate_user(uid, pwd)
        if success:
            df = fetch_requests_list(user_type)
            return (
                gr.update(visible=False),  # login page
                gr.update(visible=True),   # list page
                gr.update(visible=False),  # details page
                user_type,                 # state
                df,                        # state
                gr.update(value=df),       # dataframe
                ""                         # clear error
            )
        else:
            return (
                gr.update(visible=True), 
                gr.update(visible=False), 
                gr.update(visible=False), 
                "", 
                pd.DataFrame(), 
                gr.update(value=pd.DataFrame()), 
                err
            )

    login_btn.click(
        handle_login, 
        inputs=[user_id_input, password_input], 
        outputs=[login_page, list_page, details_page, logged_in_user_type, current_df_state, requests_table, login_error]
    )

    # Select Row from Dataframe Logic
    def select_row_from_table(evt: gr.SelectData, df_state):
        if evt.row is not None and 'complaint_id' in df_state.columns:
            selected_id = df_state.iloc[evt.row]['complaint_id']
            return str(selected_id)
        return ""

    requests_table.select(
        select_row_from_table, 
        inputs=[current_df_state], 
        outputs=[selected_complaint_id]
    )

    # View Details Logic
    def load_details(comp_id, user_type):
        if not comp_id:
            return [gr.update()] * 20 + ["❌ No Complaint ID selected."]
        
        data = fetch_complaint_details(comp_id)
        if not data:
            return [gr.update()] * 20 + ["❌ Complaint not found."]
            
        return (
            data.get('routing_id', ''),
            data.get('complaint_id', ''),
            data.get('customer_id', ''),
            data.get('cust_name', ''),
            data.get('complaint', ''),
            data.get('category', ''),
            data.get('priority', ''),
            data.get('sentiment', ''),
            data.get('original_team', ''),
            data.get('confidence', ''),
            str(data.get('sla_hours', '')),
            data.get('routing_status', ''),
            str(data.get('latency_ms', '')),
            data.get('routing_reason', ''),
            data.get('team_email', ''),
            data.get('routed_team', 'Select team to re-route'),
            bool(data.get('escalate', False)),
            data.get('escalate_to', 'Select ID to re-route') or 'Select ID to re-route',
            data.get('action', ''),
            data.get('routing_reason', ''), # Editable
            data.get('team_email', ''),     # Editable
            ""
        )

    view_details_btn.click(
        load_details,
        inputs=[selected_complaint_id, logged_in_user_type],
        outputs=[
            d_routing_id, d_complaint_id, d_customer_id, d_cust_name, d_complaint,
            d_category, d_priority, d_sentiment, d_original_team, d_confidence,
            d_sla_hours, d_routing_status, d_latency_ms, d_routing_reason_ro, d_team_email_ro,
            d_routed_team, d_escalate, d_escalate_to, d_action, d_routing_reason, d_team_email,
            update_status_msg
        ]
    )

    # Dynamic Dropdown Validation
    def validate_routed_team(selection):
        _, teams = get_dropdown_choices()
        return validate_dropdown_selection(selection, teams)

    def validate_escalate_to(selection):
        user_ids, _ = get_dropdown_choices()
        return validate_dropdown_selection(selection, user_ids)

    d_routed_team.change(validate_routed_team, inputs=d_routed_team, outputs=routed_team_validation)
    d_escalate_to.change(validate_escalate_to, inputs=d_escalate_to, outputs=escalate_to_validation)

    # Submit Update Logic
    def handle_submit(comp_id, routed_team, escalate, escalate_to, action, routing_reason, team_email, user_type):
        msg = update_complaint(comp_id, routed_team, escalate, escalate_to, action, routing_reason, team_email)
        # Refresh the list after update
        df = fetch_requests_list(user_type)
        return msg, gr.update(value=df), df

    submit_btn.click(
        handle_submit,
        inputs=[d_complaint_id, d_routed_team, d_escalate, d_escalate_to, d_action, d_routing_reason, d_team_email, logged_in_user_type],
        outputs=[update_status_msg, requests_table, current_df_state]
    )

    # Navigation Logic
    def go_to_list_page(user_type):
        df = fetch_requests_list(user_type)
        return gr.update(visible=False), gr.update(visible=True), gr.update(value=df), df

    back_to_list_btn.click(
        go_to_list_page,
        inputs=[logged_in_user_type],
        outputs=[details_page, list_page, requests_table, current_df_state]
    )

    def logout():
        return gr.update(visible=True), gr.update(visible=False), gr.update(visible=False), "", ""

    back_to_login_btn.click(
        logout,
        outputs=[login_page, list_page, details_page, user_id_input, password_input]
    )


if __name__ == "__main__":
    app.launch(server_port=10000, share=True)