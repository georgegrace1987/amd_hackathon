import gradio as gr
import pandas as pd
from db_manager import authenticate_user, fetch_requests_list, fetch_complaint_details, update_complaint
from login_form import create_login_page
from list_form import create_list_page
from details_form import create_details_page

# Professional Font CSS
css = ".gradio-container label { font-weight: bold; font-family: Arial, sans-serif; }"

with gr.Blocks(title="Bank Routing Portal", css=css) as app:
    # App State Variables
    logged_in_user_type = gr.State("")
    
    # --- Load Form Modules ---
    login_page, uid_in, pwd_in, login_btn, login_err = create_login_page()
    list_page, req_table, logout_btn, sel_comp_id, view_btn = create_list_page()
    (
        details_page, d_comp_id, d_route_id, d_cust_id, d_name, d_comp, d_cat, d_pri, 
        d_sent, d_orig_team, d_conf, d_sla, d_status, d_lat, d_reason_ro, d_email_ro,
        d_route_team, d_escalate, d_escalate_to, d_action, d_reason, d_email, 
        submit_btn, update_msg, back_btn
    ) = create_details_page()

    # --- Logic & Event Wiring ---

    # 1. Login Action
    def handle_login(uid, pwd):
        success, user_type = authenticate_user(uid, pwd)
        if success:
            df = fetch_requests_list(user_type)
            return gr.update(visible=False), gr.update(visible=True), user_type, df, ""
        return gr.update(visible=True), gr.update(visible=False), "", None, "❌ Incorrect password."

    login_btn.click(
        handle_login, 
        inputs=[uid_in, pwd_in], 
        outputs=[login_page, list_page, logged_in_user_type, req_table, login_err]
    )

    # 2. Table Selection Action
    def select_row(evt: gr.SelectData):
        if evt.value:
            return str(evt.value)
        return ""

    req_table.select(select_row, outputs=sel_comp_id)

    # 3. View Details Navigation
    def load_details(comp_id):
        if not comp_id:
            return [gr.update()] * 21 + ["❌ No Complaint ID selected."]
        data = fetch_complaint_details(comp_id)
        if not data:
            return [gr.update()] * 21 + ["❌ Complaint not found."]
            
        return (
            gr.update(visible=False), gr.update(visible=True),  # Page navigation
            data.get('complaint_id', ''), data.get('routing_id', ''), 
            data.get('customer_id', ''), data.get('cust_name', ''), 
            data.get('complaint', ''), data.get('category', ''), 
            data.get('priority', ''), data.get('sentiment', ''), 
            data.get('original_team', ''), data.get('confidence', ''), 
            str(data.get('sla_hours', '')), data.get('routing_status', ''), 
            str(data.get('latency_ms', '')), data.get('routing_reason', ''), 
            data.get('team_email', ''), data.get('routed_team', 'Select team to re-route'), 
            bool(data.get('escalate', False)), 
            data.get('escalate_to', 'Select ID to re-route') or 'Select ID to re-route',
            data.get('action', ''), data.get('routing_reason', ''), 
            data.get('team_email', ''), ""
        )

    view_btn.click(
        load_details, inputs=sel_comp_id, 
        outputs=[
            list_page, details_page, d_comp_id, d_route_id, d_cust_id, d_name, d_comp,
            d_cat, d_pri, d_sent, d_orig_team, d_conf, d_sla, d_status, d_lat,
            d_reason_ro, d_email_ro, d_route_team, d_escalate, d_escalate_to,
            d_action, d_reason, d_email, update_msg
        ]
    )

    # 4. Submit Update Action
    def handle_submit(comp_id, routed_team, escalate, escalate_to, action, routing_reason, team_email, user_type):
        if not action or not action.strip():
            return "❌ Action field is mandatory.", gr.update(), gr.update()
        update_complaint(comp_id, routed_team, escalate, escalate_to, action, routing_reason, team_email)
        df = fetch_requests_list(user_type)
        return f"✅ Successfully updated Complaint ID: {comp_id}", gr.update(value=df), gr.update(visible=True)

    submit_btn.click(
        handle_submit, 
        inputs=[d_comp_id, d_route_team, d_escalate, d_escalate_to, d_action, d_reason, d_email, logged_in_user_type],
        outputs=[update_msg, req_table, list_page]  # Navigates back to list on success
    )

    # 5. Navigation Buttons
    back_btn.click(
        lambda: [gr.update(visible=True), gr.update(visible=False)],
        outputs=[list_page, details_page]
    )

    logout_btn.click(
        lambda: [gr.update(visible=True), gr.update(visible=False), gr.update(visible=False), "", ""],
        outputs=[login_page, list_page, details_page, uid_in, pwd_in]
    )

if __name__ == "__main__":
    app.launch(server_port=10000, share=True)