import gradio as gr
import pandas as pd
from login_form import create_login_page
from list_form import create_list_page
from details_form import create_details_page
from dashboard_form import create_dashboard_page
from db import (
    authenticate_user_ui as authenticate_user,
    fetch_requests_list,
    fetch_complaint_details,
    update_complaint_routing as update_complaint,
    get_filter_choices,
    fetch_dashboard_data,
)

css = ".gradio-container label { font-weight: bold; font-family: Arial, sans-serif; }"

with gr.Blocks(title="Bank Routing Portal") as app:

    logged_in_user_type = gr.State("")
    logged_in_uid       = gr.State("")
    logged_in_team      = gr.State("")

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

    # 1. Login — supervisors → dashboard, members → list
    def handle_login(uid, pwd):
        success, user_type, team = authenticate_user(uid, pwd)
        if success:
            is_supervisor = "Supervisor" in uid
            if is_supervisor:
                df, total, esc, sla, cat_df, pri_df = fetch_dashboard_data(user_type)
                cats, pris, stats = get_filter_choices()
                return (
                    gr.update(visible=False), gr.update(visible=False), gr.update(visible=True),
                    user_type, uid, team,
                    total, esc, sla, cat_df, pri_df, df,
                    gr.update(choices=cats), gr.update(choices=pris), gr.update(), gr.update(choices=stats),
                    None, ""
                )
            else:
                df_list = fetch_requests_list(user_type, team)
                return (
                    gr.update(visible=False), gr.update(visible=True), gr.update(visible=False),
                    user_type, uid, team,
                    0, 0, "0 hrs", pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
                    gr.update(), gr.update(), gr.update(), gr.update(),
                    df_list, ""
                )
        return (
            gr.update(visible=True), gr.update(visible=False), gr.update(visible=False),
            "", "", "",
            0, 0, "0 hrs", pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
            gr.update(), gr.update(), gr.update(), gr.update(),
            None, "❌ Incorrect password."
        )

    login_btn.click(
        handle_login, inputs=[uid_in, pwd_in],
        outputs=[
            login_page, list_page, dashboard_page, logged_in_user_type, logged_in_uid, logged_in_team,
            dash_total, dash_escalated, dash_sla, dash_cat_plot, dash_pri_plot, dash_table,
            f_cat, f_pri, f_esc, f_stat,
            req_table, login_err
        ]
    )

    # 2. Dashboard filters
    def apply_dashboard_filters(user_type, category, priority, escalate, status):
        df, total, esc, sla, cat_df, pri_df = fetch_dashboard_data(user_type, category, priority, escalate, status)
        return total, esc, sla, cat_df, pri_df, df

    def reset_dashboard_filters(user_type):
        df, total, esc, sla, cat_df, pri_df = fetch_dashboard_data(user_type)
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

    # 3. List -- row click auto-loads details; View Details button also works

    detail_outputs = [
        list_page, details_page, d_comp_id, d_route_id, d_cust_id, d_name, d_comp,
        d_cat, d_pri, d_sent, d_orig_team, d_conf, d_sla, d_status, d_lat,
        d_reason_ro, d_email_ro, d_route_team, d_escalate, d_escalate_to,
        d_action, d_reason, d_email, update_msg
    ]

    def load_details(comp_id):
        if not comp_id or str(comp_id).strip() == "":
            return [gr.update()] * 23 + ["\u274c No complaint selected."]
        data = fetch_complaint_details(str(comp_id).strip())
        if not data:
            return [gr.update()] * 23 + [f"\u274c Not found: {comp_id}"]
        return (
            gr.update(visible=False), gr.update(visible=True),
            data.get("complaint_id", ""),    data.get("routing_id", ""),
            data.get("customer_id", ""),     data.get("cust_name", ""),
            data.get("complaint", ""),       data.get("category", ""),
            data.get("priority", ""),        data.get("sentiment", ""),
            data.get("original_team", ""),   data.get("confidence", ""),
            str(data.get("sla_hours", "")),  data.get("routing_status", ""),
            str(data.get("latency_ms", "")), data.get("routing_reason", ""),
            data.get("team_email", ""),      data.get("routed_team", "Select team to re-route"),
            bool(data.get("escalate", False)),
            data.get("escalate_to") or "Select ID to re-route",
            data.get("action", ""),          data.get("routing_reason", ""),
            data.get("team_email", ""),      ""
        )

    def row_click(evt: gr.SelectData, df):
        """Auto-load details on row click — always uses complaint_id from the row."""
        import pandas as pd
        try:
            if (evt.index is not None
                    and df is not None
                    and isinstance(df, pd.DataFrame)
                    and not df.empty
                    and "complaint_id" in df.columns):
                comp_id = str(df.iloc[evt.index[0]]["complaint_id"]).strip()
                return [comp_id] + list(load_details(comp_id))
        except Exception as e:
            print(f"[row_click] {e}")
        return [""] + [gr.update()] * 23 + ["\u274c Could not load row."]

    # row click -> update sel_comp_id AND navigate to details automatically
    req_table.select(row_click, inputs=req_table,
                     outputs=[sel_comp_id] + detail_outputs)

    # View Details button as manual fallback
    view_btn.click(load_details, inputs=sel_comp_id, outputs=detail_outputs)

    # 4. Submit update
    def handle_submit(comp_id, routed_team, escalate, escalate_to, action, routing_reason, team_email, user_type, team):
        if not action or not action.strip():
            return "❌ Action field is mandatory.", gr.update(), gr.update()
        success = update_complaint(comp_id, routed_team, escalate, escalate_to, action, routing_reason, team_email)
        if not success:
            return "❌ Update failed — DB is busy. Please try again in a moment.", gr.update(), gr.update()
        df = fetch_requests_list(user_type, team)
        return f"✅ Successfully updated Complaint ID: {comp_id}", gr.update(value=df), gr.update(visible=True)

    submit_btn.click(
        handle_submit,
        inputs=[d_comp_id, d_route_team, d_escalate, d_escalate_to, d_action, d_reason, d_email, logged_in_user_type, logged_in_team],
        outputs=[update_msg, req_table, list_page]
    )

    # 5. Navigation
    back_btn.click(
        lambda: [gr.update(visible=True), gr.update(visible=False)],
        outputs=[list_page, details_page]
    )
    dash_back_list_btn.click(
        lambda user_type, team: [gr.update(visible=True), gr.update(visible=False), fetch_requests_list(user_type, team)],
        inputs=[logged_in_user_type, logged_in_team],
        outputs=[list_page, dashboard_page, req_table]
    )

    def logout():
        return gr.update(visible=True), gr.update(visible=False), gr.update(visible=False), gr.update(visible=False), "", ""

    logout_btn.click(logout, outputs=[login_page, list_page, details_page, dashboard_page, uid_in, pwd_in])
    dash_logout_btn.click(logout, outputs=[login_page, list_page, details_page, dashboard_page, uid_in, pwd_in])


if __name__ == "__main__":
    app.launch(server_port=10000, share=True, css=css)