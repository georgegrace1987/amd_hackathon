import gradio as gr
import duckdb
import pandas as pd
from login_form import create_login_page
from list_form import create_list_page
from details_form import create_details_page
from dashboard_form import create_dashboard_page

# --- Database Configuration ---
ROUTING_DB = "routing.duckdb"

def get_routing_conn():
    return duckdb.connect(ROUTING_DB)

# --- Authentication & Query Functions ---
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
    conn.execute("UPDATE routing_decisions SET routed_team=?, escalate=?, escalate_to=?, action=?, routing_reason=?, team_email=? WHERE complaint_id=?",
                 [routed_team, escalate, escalate_to, action, routing_reason, team_email, complaint_id])
    conn.close()

# --- Dashboard Specific Functions ---
def get_filter_choices():
    conn = get_routing_conn()
    categories = [r[0] for r in conn.execute("SELECT DISTINCT category FROM routing_decisions WHERE category IS NOT NULL").fetchall()]
    priorities = [r[0] for r in conn.execute("SELECT DISTINCT priority FROM routing_decisions WHERE priority IS NOT NULL").fetchall()]
    statuses = [r[0] for r in conn.execute("SELECT DISTINCT routing_status FROM routing_decisions WHERE routing_status IS NOT NULL").fetchall()]
    conn.close()
    return categories, priorities, statuses

def fetch_dashboard_data(user_type, category=None, priority=None, escalate=None, status=None):
    conn = get_routing_conn()
    query = "SELECT * FROM routing_decisions WHERE routed_team = ?"
    params = [user_type]
    
    if category: query += " AND category = ?"; params.append(category)
    if priority: query += " AND priority = ?"; params.append(priority)
    if escalate: query += " AND escalate = ?"; params.append(escalate == "True")
    if status: query += " AND routing_status = ?"; params.append(status)
        
    df = conn.execute(query, params).fetchdf()
    conn.close()
    
    if df.empty:
        return df, 0, 0, "0 hrs", pd.DataFrame(columns=['Category', 'Count']), pd.DataFrame(columns=['Priority', 'Count'])
        
    total = len(df)
    escalated = len(df[df['escalate'] == True])
    avg_sla = f"{df['sla_hours'].mean():.1f} hrs"
    
    cat_df = df['category'].value_counts().reset_index()
    cat_df.columns = ['Category', 'Count']
    pri_df = df['priority'].value_counts().reset_index()
    pri_df.columns = ['Priority', 'Count']
    
    return df, total, escalated, avg_sla, cat_df, pri_df

# --- Professional Font CSS ---
css = ".gradio-container label { font-weight: bold; font-family: Arial, sans-serif; }"

# Removed css=css from here to fix Gradio 6.0 Warning
with gr.Blocks(title="Bank Routing Portal") as app:
    # App State Variables
    logged_in_user_type = gr.State("")
    logged_in_uid = gr.State("")
    
    # --- Load Form Modules ---
    login_page, uid_in, pwd_in, login_btn, login_err = create_login_page()
    list_page, req_table, logout_btn, sel_comp_id, view_btn = create_list_page()
    (
        details_page, d_comp_id, d_route_id, d_cust_id, d_name, d_comp, d_cat, d_pri, 
        d_sent, d_orig_team, d_conf, d_sla, d_status, d_lat, d_reason_ro, d_email_ro,
        d_route_team, d_escalate, d_escalate_to, d_action, d_reason, d_email, 
        submit_btn, update_msg, back_btn
    ) = create_details_page()
    
    (
        dashboard_page, dash_total, dash_escalated, dash_sla, dash_cat_plot, dash_pri_plot, dash_table,
        f_cat, f_pri, f_esc, f_stat, dash_apply_btn, dash_reset_btn, dash_back_list_btn, dash_logout_btn
    ) = create_dashboard_page()

    # --- Logic & Event Wiring ---

    # 1. Login Action (Routing Supervisors to Dashboard, others to List)
    def handle_login(uid, pwd):
        success, user_type = authenticate_user(uid, pwd)
        if success:
            is_supervisor = "Supervisor" in uid  # Access control check
            
            if is_supervisor:
                df, total, esc, sla, cat_df, pri_df = fetch_dashboard_data(user_type)
                cats, pris, stats = get_filter_choices()
                return (
                    gr.update(visible=False), gr.update(visible=False), gr.update(visible=True), # Pages
                    user_type, uid, # States
                    total, esc, sla, cat_df, pri_df, df, # Dashboard components
                    gr.update(choices=cats), gr.update(choices=pris), gr.update(), gr.update(choices=stats), # Filters
                    None, "" # List components, login error
                )
            else:
                df_list = fetch_requests_list(user_type)
                return (
                    gr.update(visible=False), gr.update(visible=True), gr.update(visible=False), 
                    user_type, uid,
                    0, 0, "0 hrs", pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), 
                    gr.update(), gr.update(), gr.update(), gr.update(),
                    df_list, ""
                )
        return (
            gr.update(visible=True), gr.update(visible=False), gr.update(visible=False), 
            "", "",
            0, 0, "0 hrs", pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
            gr.update(), gr.update(), gr.update(), gr.update(),
            None, "❌ Incorrect password."
        )

    login_btn.click(
        handle_login, inputs=[uid_in, pwd_in], 
        outputs=[
            login_page, list_page, dashboard_page, logged_in_user_type, logged_in_uid,
            dash_total, dash_escalated, dash_sla, dash_cat_plot, dash_pri_plot, dash_table,
            f_cat, f_pri, f_esc, f_stat,
            req_table, login_err
        ]
    )

    # 2. Dashboard Filter Actions
    def apply_dashboard_filters(user_type, category, priority, escalate, status):
        df, total, esc, sla, cat_df, pri_df = fetch_dashboard_data(user_type, category, priority, escalate, status)
        return total, esc, sla, cat_df, pri_df, df

    def reset_dashboard_filters(user_type):
        df, total, esc, sla, cat_df, pri_df = fetch_dashboard_data(user_type)
        cats, pris, stats = get_filter_choices()
        return total, esc, sla, cat_df, pri_df, df, gr.update(value=None), gr.update(value=None), gr.update(value=None), gr.update(value=None)

    dash_apply_btn.click(
        apply_dashboard_filters, 
        inputs=[logged_in_user_type, f_cat, f_pri, f_esc, f_stat], 
        outputs=[dash_total, dash_escalated, dash_sla, dash_cat_plot, dash_pri_plot, dash_table]
    )

    dash_reset_btn.click(
        reset_dashboard_filters, 
        inputs=[logged_in_user_type], 
        outputs=[dash_total, dash_escalated, dash_sla, dash_cat_plot, dash_pri_plot, dash_table, f_cat, f_pri, f_esc, f_stat]
    )

    # 3. Standard List Actions
    def select_row(evt: gr.SelectData):
        if evt.value: return str(evt.value)
        return ""

    req_table.select(select_row, outputs=sel_comp_id)

    def load_details(comp_id):
        if not comp_id: return [gr.update()] * 21 + ["❌ No Complaint ID selected."]
        data = fetch_complaint_details(comp_id)
        if not data: return [gr.update()] * 21 + ["❌ Complaint not found."]
        return (
            gr.update(visible=False), gr.update(visible=True), 
            data.get('complaint_id', ''), data.get('routing_id', ''), data.get('customer_id', ''), 
            data.get('cust_name', ''), data.get('complaint', ''), data.get('category', ''), 
            data.get('priority', ''), data.get('sentiment', ''), data.get('original_team', ''), 
            data.get('confidence', ''), str(data.get('sla_hours', '')), data.get('routing_status', ''), 
            str(data.get('latency_ms', '')), data.get('routing_reason', ''), data.get('team_email', ''), 
            data.get('routed_team', 'Select team to re-route'), bool(data.get('escalate', False)), 
            data.get('escalate_to', 'Select ID to re-route') or 'Select ID to re-route',
            data.get('action', ''), data.get('routing_reason', ''), data.get('team_email', ''), ""
        )

    view_btn.click(load_details, inputs=sel_comp_id, outputs=[
        list_page, details_page, d_comp_id, d_route_id, d_cust_id, d_name, d_comp, d_cat, d_pri, 
        d_sent, d_orig_team, d_conf, d_sla, d_status, d_lat, d_reason_ro, d_email_ro, d_route_team, 
        d_escalate, d_escalate_to, d_action, d_reason, d_email, update_msg
    ])

    def handle_submit(comp_id, routed_team, escalate, escalate_to, action, routing_reason, team_email, user_type):
        if not action or not action.strip(): return "❌ Action field is mandatory.", gr.update(), gr.update()
        update_complaint(comp_id, routed_team, escalate, escalate_to, action, routing_reason, team_email)
        df = fetch_requests_list(user_type)
        return f"✅ Successfully updated Complaint ID: {comp_id}", gr.update(value=df), gr.update(visible=True)

    submit_btn.click(handle_submit, inputs=[d_comp_id, d_route_team, d_escalate, d_escalate_to, d_action, d_reason, d_email, logged_in_user_type], outputs=[update_msg, req_table, list_page])

    # 4. Navigation Buttons
    back_btn.click(lambda: [gr.update(visible=True), gr.update(visible=False)], outputs=[list_page, details_page])
    
    dash_back_list_btn.click(lambda user_type: [gr.update(visible=True), gr.update(visible=False), fetch_requests_list(user_type)], inputs=logged_in_user_type, outputs=[list_page, dashboard_page, req_table])

    def logout():
        return gr.update(visible=True), gr.update(visible=False), gr.update(visible=False), gr.update(visible=False), "", ""

    logout_btn.click(logout, outputs=[login_page, list_page, details_page, dashboard_page, uid_in, pwd_in])
    dash_logout_btn.click(logout, outputs=[login_page, list_page, details_page, dashboard_page, uid_in, pwd_in])

if __name__ == "__main__":
    # Moved css=css here to fix Gradio 6.0 Warning
    app.launch(server_port=10000, share=True, css=css)