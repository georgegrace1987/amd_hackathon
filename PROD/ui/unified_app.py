"""
unified_app.py — Single Gradio app with Customer and Employee UIs on same page.
Run: python unified_app.py
     or called from run_pipeline.py
"""

import re
import gradio as gr
from datetime import datetime

from config import TIERS_CITIES, COMPLAINT_CHANNELS, COMPLAINT_CATEGORIES, ACCOUNT_TYPES
from pii_redactor import redact_pii
from content_security import check_content_safety
from db import (
    get_conn,
    check_duplicate_complaint,
    check_complaint_status,
    authenticate_user_ui as authenticate_user,
    fetch_requests_list,
    fetch_complaint_details,
    update_complaint_routing as update_complaint,
    get_filter_choices,
    fetch_dashboard_data,
)
from login_form import create_login_page
from list_form import create_list_page
from details_form import create_details_page
from dashboard_form import create_dashboard_page

import pandas as pd


# ── Customer helpers ──────────────────────────────────────────────────────────

def is_valid_email(email: str) -> bool:
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return bool(re.match(pattern, email))


import uuid

def generate_complaint_id(conn) -> str:
    """Generate complaint ID in CMP-XXXXXXXX format, matching classifier.py's
    format so customer-submitted and synthetic/classified complaints share
    the same ID scheme. Retries on the rare UUID collision."""
    for _ in range(5):
        complaint_id = "CMP-" + str(uuid.uuid4())[:8].upper()
        exists = conn.execute(
            "SELECT 1 FROM complaints WHERE complaint_id = ?", [complaint_id]
        ).fetchone()
        if not exists:
            return complaint_id
    # extremely unlikely fallback — full UUID guarantees uniqueness
    return "CMP-" + str(uuid.uuid4()).replace("-", "").upper()[:12]


def submit_complaint(customer_id, cust_name, cust_email, complaint,
                     channel, branch, account_type, category):
    if not all([customer_id, cust_name, cust_email, complaint]):
        return "❌ Customer ID, Name, Email, and Complaint are mandatory."
    if not is_valid_email(cust_email):
        return "❌ Invalid email format. e.g. user@example.com"

    # ── Content security check — reject malicious/injection content outright ─
    safety = check_content_safety(complaint, use_llm=True)
    if not safety["is_safe"]:
        return (f"❌ Your complaint could not be submitted because it contains "
                 f"content that was flagged as unsafe ({', '.join(safety['threats_found'])}). "
                 f"Please rephrase your complaint using plain language describing your issue.")

    # ── Exact duplicate check (same customer, same complaint, same metadata) ─
    # Runs on the ORIGINAL text — redaction happens after, so two different
    # customers' PII can never coincidentally collide into a false duplicate.
    dup = check_duplicate_complaint(
        customer_id, complaint,
        channel=channel, branch=branch,
        account_type=account_type, category=category,
    )
    if dup:
        return (f"❌ This exact complaint already exists "
                 f"(Complaint ID: **{dup['complaint_id']}**, status: {dup['status']}). "
                 f"Please do not resubmit the same complaint.")

    # ── PII redaction — strip Aadhaar/PAN/card/CVV before this ever touches disk ─
    redaction = redact_pii(complaint, use_llm=True)
    complaint_to_store = redaction["redacted_text"]
    pii_notice = ""
    if redaction["pii_found"]:
        pii_notice = (f" ⚠️ We detected and masked sensitive information "
                       f"({', '.join(redaction['types_found'])}) in your complaint "
                       f"for your protection.")

    try:
        conn         = get_conn()
        complaint_id = generate_complaint_id(conn)
        conn.execute("""
            INSERT INTO complaints (
                complaint_id, customer_id, cust_name, cust_email, complaint,
                channel, branch, account_type, category,
                priority, team, sentiment, sla_days, summary, reasoning,
                status, created_at, sla_deadline
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      current_timestamp, ?)
        """, [
            complaint_id, customer_id.strip(), cust_name.strip(),
            cust_email.strip(), complaint_to_store.strip(),
            channel, branch if branch else None, account_type, category,
            None, None, None, None, None, None, "New", None
        ])
        conn.close()
        return f"✅ Complaint registered. Your Complaint ID: **{complaint_id}**{pii_notice}"
    except Exception as e:
        return f"❌ Database Error: {str(e)}"


# ── Build unified app ─────────────────────────────────────────────────────────

def build_unified_app() -> gr.Blocks:
    with gr.Blocks(title="BFSI Portal") as app:

        gr.Markdown("# 🏦 BFSI Complaint Portal")

        with gr.Tabs():

            # ── Tab 1: Customer Complaint Intake ─────────────────────────────
            with gr.TabItem("📝 Lodge Complaint"):
                gr.Markdown("Fill in the details below to lodge your complaint.")

                with gr.Row():
                    customer_id  = gr.Textbox(label="Customer ID *", placeholder="Enter Customer ID")
                    cust_name    = gr.Textbox(label="Customer Name *", placeholder="Enter Full Name")

                with gr.Row():
                    cust_email   = gr.Textbox(label="Email *", placeholder="name@domain.com")
                    account_type = gr.Dropdown(choices=ACCOUNT_TYPES, label="Account Type *")

                with gr.Row():
                    channel  = gr.Dropdown(choices=COMPLAINT_CHANNELS, label="Channel *")
                    category = gr.Dropdown(choices=COMPLAINT_CATEGORIES, label="Category *")

                branch     = gr.Dropdown(choices=TIERS_CITIES, label="Branch", interactive=True)
                complaint  = gr.Textbox(label="Complaint *", lines=5,
                                        placeholder="Describe your issue in detail...")
                submit_btn = gr.Button("Submit Complaint", variant="primary")
                output_msg = gr.Textbox(label="Status", interactive=False)

                submit_btn.click(
                    fn=submit_complaint,
                    inputs=[customer_id, cust_name, cust_email, complaint,
                            channel, branch, account_type, category],
                    outputs=output_msg,
                )

                gr.Markdown("---")
                gr.Markdown("### 🔍 Check Complaint Status")
                gr.Markdown("Enter either your Complaint ID or Customer ID to check status.")

                with gr.Row():
                    status_complaint_id = gr.Textbox(label="Complaint ID", placeholder="e.g. CMP-8C723406")
                    status_customer_id  = gr.Textbox(label="Customer ID", placeholder="Enter your Customer ID")

                status_check_btn = gr.Button("Check Status")
                status_table = gr.Dataframe(
                    headers=["Complaint ID", "Status", "Assigned Team", "SLA Deadline", "Submitted On"],
                    interactive=False,
                )
                status_msg = gr.Markdown("")

                def handle_status_check(comp_id, cust_id):
                    comp_id = (comp_id or "").strip()
                    cust_id = (cust_id or "").strip()
                    if not comp_id and not cust_id:
                        return pd.DataFrame(), "❌ Please enter a Complaint ID or Customer ID."

                    results = check_complaint_status(complaint_id=comp_id, customer_id=cust_id)
                    if not results:
                        return pd.DataFrame(), "❌ No complaint found matching that ID."

                    df = pd.DataFrame([
                        {
                            "Complaint ID":   r["complaint_id"],
                            "Status":         r["status"],
                            "Assigned Team":  r["routed_team"],
                            "SLA Deadline":   r["sla"],
                            "Submitted On":   r["created_at"],
                        }
                        for r in results
                    ])
                    return df, f"✅ Found {len(results)} complaint(s)."

                status_check_btn.click(
                    handle_status_check,
                    inputs=[status_complaint_id, status_customer_id],
                    outputs=[status_table, status_msg],
                )

            # ── Tab 2: Employee Login + Portal ───────────────────────────────
            with gr.TabItem("🏦 Employee Portal"):

                logged_in_user_type = gr.State("")
                logged_in_uid       = gr.State("")
                logged_in_team      = gr.State("")

                login_page, uid_in, pwd_in, login_btn, login_err = create_login_page()

                list_page, req_table, logout_btn, sel_comp_id, view_btn = create_list_page()

                (
                    details_page,
                    d_comp_id, d_route_id, d_cust_id, d_name, d_comp,
                    d_cat, d_pri, d_sent, d_orig_team, d_conf,
                    d_sla, d_status, d_lat, d_reason_ro, d_email_ro,
                    d_route_team, d_escalate, d_escalate_to,
                    d_action, d_reason, d_email,
                    emp_submit_btn, update_msg, back_btn,
                ) = create_details_page()

                (
                    dashboard_page, dash_total, dash_escalated, dash_sla,
                    dash_cat_plot, dash_pri_plot, dash_table,
                    f_cat, f_pri, f_esc, f_stat,
                    dash_apply_btn, dash_reset_btn, dash_back_list_btn, dash_logout_btn
                ) = create_dashboard_page()

                # ── Login ─────────────────────────────────────────────────────
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
                                gr.update(choices=cats), gr.update(choices=pris),
                                gr.update(), gr.update(choices=stats),
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
                        None, "❌ Incorrect UserID or password."
                    )

                login_btn.click(
                    handle_login, inputs=[uid_in, pwd_in],
                    outputs=[
                        login_page, list_page, dashboard_page,
                        logged_in_user_type, logged_in_uid, logged_in_team,
                        dash_total, dash_escalated, dash_sla,
                        dash_cat_plot, dash_pri_plot, dash_table,
                        f_cat, f_pri, f_esc, f_stat,
                        req_table, login_err
                    ]
                )

                # ── Dashboard filters ─────────────────────────────────────────
                def apply_filters(user_type, cat, pri, esc, stat):
                    df, total, e, sla, cdf, pdf = fetch_dashboard_data(user_type, cat, pri, esc, stat)
                    return total, e, sla, cdf, pdf, df

                def reset_filters(user_type):
                    df, total, e, sla, cdf, pdf = fetch_dashboard_data(user_type)
                    return total, e, sla, cdf, pdf, df, None, None, None, None

                dash_apply_btn.click(apply_filters,
                    inputs=[logged_in_user_type, f_cat, f_pri, f_esc, f_stat],
                    outputs=[dash_total, dash_escalated, dash_sla, dash_cat_plot, dash_pri_plot, dash_table])

                dash_reset_btn.click(reset_filters,
                    inputs=[logged_in_user_type],
                    outputs=[dash_total, dash_escalated, dash_sla, dash_cat_plot,
                             dash_pri_plot, dash_table, f_cat, f_pri, f_esc, f_stat])

                # ── Row click → load details ──────────────────────────────────
                detail_outputs = [
                    list_page, details_page,
                    d_comp_id, d_route_id, d_cust_id, d_name, d_comp,
                    d_cat, d_pri, d_sent, d_orig_team, d_conf,
                    d_sla, d_status, d_lat, d_reason_ro, d_email_ro,
                    d_route_team, d_escalate, d_escalate_to,
                    d_action, d_reason, d_email, update_msg
                ]

                def load_details(comp_id):
                    if not comp_id or str(comp_id).strip() == "":
                        return [gr.update()] * 23 + ["❌ No complaint selected."]
                    data = fetch_complaint_details(str(comp_id).strip())
                    if not data:
                        return [gr.update()] * 23 + [f"❌ Not found: {comp_id}"]
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
                    try:
                        if (evt.index is not None and df is not None
                                and isinstance(df, pd.DataFrame)
                                and not df.empty
                                and "complaint_id" in df.columns):
                            comp_id = str(df.iloc[evt.index[0]]["complaint_id"]).strip()
                            return [comp_id] + list(load_details(comp_id))
                    except Exception as e:
                        print(f"[row_click] {e}")
                    return [""] + [gr.update()] * 23 + ["❌ Could not load row."]

                req_table.select(row_click, inputs=req_table,
                                 outputs=[sel_comp_id] + detail_outputs)
                view_btn.click(load_details, inputs=sel_comp_id, outputs=detail_outputs)

                # ── Submit update ─────────────────────────────────────────────
                def handle_submit(comp_id, routed_team, escalate, escalate_to,
                                  action, routing_reason, team_email, user_type, team):
                    if not action or not action.strip():
                        return "❌ Action field is mandatory.", gr.update(), gr.update()
                    success = update_complaint(comp_id, routed_team, escalate, escalate_to,
                                              action, routing_reason, team_email)
                    if not success:
                        return "❌ DB busy — try again.", gr.update(), gr.update()
                    df = fetch_requests_list(user_type, team)
                    return f"✅ Updated: {comp_id}", gr.update(value=df), gr.update(visible=True)

                emp_submit_btn.click(
                    handle_submit,
                    inputs=[d_comp_id, d_route_team, d_escalate, d_escalate_to,
                            d_action, d_reason, d_email,
                            logged_in_user_type, logged_in_team],
                    outputs=[update_msg, req_table, list_page]
                )

                # ── Navigation ────────────────────────────────────────────────
                back_btn.click(
                    lambda: [gr.update(visible=True), gr.update(visible=False)],
                    outputs=[list_page, details_page]
                )
                dash_back_list_btn.click(
                    lambda user_type, team: [
                        gr.update(visible=True), gr.update(visible=False),
                        fetch_requests_list(user_type, team)
                    ],
                    inputs=[logged_in_user_type, logged_in_team],
                    outputs=[list_page, dashboard_page, req_table]
                )

                def logout():
                    return (gr.update(visible=True), gr.update(visible=False),
                            gr.update(visible=False), gr.update(visible=False), "", "")

                logout_btn.click(logout,
                    outputs=[login_page, list_page, details_page, dashboard_page, uid_in, pwd_in])
                dash_logout_btn.click(logout,
                    outputs=[login_page, list_page, details_page, dashboard_page, uid_in, pwd_in])

    return app


def launch_unified(port: int = 10000, share: bool = True) -> None:
    app = build_unified_app()
    app.launch(server_port=port, share=share)


if __name__ == "__main__":
    launch_unified()