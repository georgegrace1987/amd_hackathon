import gradio as gr
import duckdb, uuid

def save_complaint(customer_id, cust_name, cust_email, channel, account_type, branch, complaint):
    if len(customer_id) != 16 or not customer_id.isdigit():
        return "❌ Customer ID must be 16 digits"
    if not cust_name or not complaint:
        return "❌ Name and complaint are required"

    conn = duckdb.connect("complaints.duckdb")
    complaint_id = "CMP-" + str(uuid.uuid4())[:8].upper()
    conn.execute("""
        INSERT INTO complaints
            (complaint_id, customer_id, cust_name, cust_email,
             complaint, channel, branch, account_type, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', current_timestamp)
    """, [complaint_id, customer_id, cust_name, cust_email or None,
          complaint, channel, branch or None, account_type])
    conn.close()
    return f"✅ Saved — {complaint_id}"

demo = gr.Interface(
    fn=save_complaint,
    inputs=[
        gr.Textbox(label="Customer ID *", max_lines=1, placeholder="16-digit"),
        gr.Textbox(label="Full Name *",   max_lines=1),
        gr.Textbox(label="Email",         max_lines=1),
        gr.Dropdown(["web", "branch", "mobile_app"], label="Channel *"),
        gr.Dropdown(["savings","current","credit_card","loan","demat","insurance"], label="Account Type *"),
        gr.Dropdown(["— None —","Andheri West","Bandra East","Borivali","Dadar",
                     "Thane","Kurla","Powai","Malad","Goregaon","Vashi"], label="Branch"),
        gr.Textbox(label="Complaint *", lines=4),
    ],
    outputs=gr.Textbox(label="Status"),
    title="BFSI Complaint Intake",
)

demo.launch(server_port=10000, share=True)   # share=True gives a public URL instantly
