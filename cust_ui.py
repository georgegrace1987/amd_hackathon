"""
cust_ui.py — Gradio customer complaint intake form.
Collects customer data and saves to complaints.duckdb.
Classification and routing run separately via classifier.py and router.py.

Run:  python cust_ui.py
      or call launch_ui() from main.py
"""

import re
import gradio as gr
from datetime import datetime
from config import TIERS_CITIES, COMPLAINT_CHANNELS, COMPLAINT_CATEGORIES, ACCOUNT_TYPES
from db import get_conn, insert_complaint


def is_valid_email(email: str) -> bool:
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return bool(re.match(pattern, email))


def generate_complaint_id(conn) -> str:
    """Generate complaint ID in yyyymmdd-xxxxx format. Reuses existing connection."""
    today_str = datetime.now().strftime("%Y%m%d")
    prefix    = today_str + "-"
    result    = conn.execute(
        "SELECT complaint_id FROM complaints WHERE complaint_id LIKE ? ORDER BY complaint_id DESC LIMIT 1",
        [prefix + "%"]
    ).fetchone()
    new_counter = int(result[0].split("-")[1]) + 1 if result else 1
    return f"{prefix}{new_counter:05d}"


def submit_complaint(
    customer_id: str,
    cust_name:   str,
    cust_email:  str,
    complaint:   str,
    channel:     str,
    branch:      str,
    account_type:str,
    category:    str,
) -> str:
    """Validate inputs, save complaint to DB, return status message."""

    # ── Validation ────────────────────────────────────────────────────────────
    if not all([customer_id, cust_name, cust_email, complaint]):
        return "❌ Customer ID, Name, Email, and Complaint are mandatory."
    if not is_valid_email(cust_email):
        return "❌ Invalid email format. e.g. user@example.com"

    # ── Insert ────────────────────────────────────────────────────────────────
    try:
        conn         = get_conn()
        complaint_id = generate_complaint_id(conn)
        record = {
            "complaint_id": complaint_id,
            "customer_id":  customer_id.strip(),
            "cust_name":    cust_name.strip(),
            "cust_email":   cust_email.strip(),
            "complaint":    complaint.strip(),
            "channel":      channel,
            "branch":       branch if branch else None,
            "account_type": account_type,
            "category":     category,
            "priority":     None,
            "team":         None,
            "sentiment":    None,
            "sla_days":     None,
            "summary":      None,
            "reasoning":    None,
            "status":       "New",
        }
        # use raw insert to avoid sla_deadline calculation (no sla_days yet)
        conn.execute("""
            INSERT INTO complaints (
                complaint_id, customer_id, cust_name, cust_email, complaint,
                channel, branch, account_type, category,
                priority, team, sentiment, sla_days, summary, reasoning,
                status, created_at, sla_deadline
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      current_timestamp, ?)
        """, [
            record["complaint_id"], record["customer_id"], record["cust_name"],
            record["cust_email"], record["complaint"],
            record["channel"], record["branch"], record["account_type"], record["category"],
            None, None, None, None, None, None,
            "New", None
        ])
        conn.close()
        return f"✅ Complaint registered. Complaint ID: **{complaint_id}**"
    except Exception as e:
        return f"❌ Database Error: {str(e)}"


def build_ui() -> gr.Blocks:
    """Build and return the Gradio Blocks UI."""
    with gr.Blocks(title="BFSI Complaint Registration") as demo:
        gr.Markdown("# 🏦 BFSI Complaint Registration Portal")
        gr.Markdown(
            "Fill in the details below to lodge your complaint. "
            "Classification and routing will be handled automatically."
        )

        with gr.Row():
            customer_id = gr.Textbox(label="Customer ID *", placeholder="Enter Customer ID")
            cust_name   = gr.Textbox(label="Customer Name *", placeholder="Enter Full Name")

        with gr.Row():
            cust_email   = gr.Textbox(label="Customer Email *", placeholder="name@domain.com")
            account_type = gr.Dropdown(choices=ACCOUNT_TYPES, label="Account Type *")

        with gr.Row():
            channel  = gr.Dropdown(choices=COMPLAINT_CHANNELS, label="Channel *")
            category = gr.Dropdown(choices=COMPLAINT_CATEGORIES, label="Category *")

        branch = gr.Dropdown(choices=TIERS_CITIES, label="Branch *", interactive=True)

        complaint  = gr.Textbox(label="Complaint *", lines=5, placeholder="Describe your issue in detail...")
        submit_btn = gr.Button("Submit Complaint", variant="primary")
        output_msg = gr.Textbox(label="Status", interactive=False)

        submit_btn.click(
            fn=submit_complaint,
            inputs=[customer_id, cust_name, cust_email, complaint,
                    channel, branch, account_type, category],
            outputs=output_msg,
        )

    return demo


def launch_ui(port: int = 10001, share: bool = True) -> None:
    """Launch the Gradio UI."""
    demo = build_ui()
    demo.launch(server_port=port, share=share)


if __name__ == "__main__":
    launch_ui()
