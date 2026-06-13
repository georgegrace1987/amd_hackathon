import gradio as gr
import duckdb
import re
from datetime import datetime

DB_PATH = "complaints.duckdb"

# --- Tier 1 and Tier 2 Cities in India (Sorted Ascending) ---
TIERS_CITIES = [
    "Agra", "Ahmedabad", "Ajmer", "Aligarh", "Allahabad", "Amravati", "Amritsar", 
    "Asansol", "Bangalore", "Bhopal", "Bhubaneswar", "Chandigarh", "Chennai", 
    "Coimbatore", "Dehradun", "Delhi", "Dhanbad", "Durg-Bhilai", "Erode", "Faridabad", 
    "Ghaziabad", "Gwalior", "Hubli-Dharwad", "Hyderabad", "Indore", "Jabalpur", 
    "Jaipur", "Jalandhar", "Jodhpur", "Kannur", "Kanpur", "Kochi", "Kolhapur", 
    "Kollam", "Kolkata", "Kozhikode", "Lucknow", "Ludhiana", "Madurai", "Meerut", 
    "Moradabad", "Mumbai", "Nagpur", "Nanded", "Nashik", "Nellore", "Noida", 
    "Puducherry", "Pune", "Raipur", "Rajkot", "Ranchi", "Salem", "Shillong", 
    "Shimla", "Siliguri", "Solapur", "Srinagar", "Surat", "Thiruvananthapuram", 
    "Thrissur", "Tiruchirappalli", "Tirunelveli", "Tiruppur", "Udaipur", "Ujjain", 
    "Vadodara", "Varanasi", "Vijayawada", "Visakhapatnam", "Warangal"
]

def is_valid_email(email):
    """Validate email format using regex."""
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return re.match(pattern, email) is not None

def generate_complaint_id():
    """Generate complaint ID in yyyymmdd-xxxxx format with an incremental counter."""
    today_str = datetime.now().strftime("%Y%m%d")
    prefix = today_str + "-"
    
    conn = duckdb.connect(DB_PATH)
    # Fetch the latest complaint_id for today
    result = conn.execute(
        "SELECT complaint_id FROM complaints WHERE complaint_id LIKE ? ORDER BY complaint_id DESC LIMIT 1",
        [prefix + "%"]
    ).fetchone()
    conn.close()
    
    if result:
        last_counter = int(result[0].split("-")[1])
        new_counter = last_counter + 1
    else:
        new_counter = 1
        
    return f"{prefix}{new_counter:05d}"

def submit_complaint(customer_id, cust_name, cust_email, complaint, channel, branch, account_type, category):
    # --- Validations ---
    if not customer_id or not cust_name or not cust_email or not complaint:
        return "❌ Error: Customer ID, Name, Email, and Complaint are mandatory."
    
    if not is_valid_email(cust_email):
        return "❌ Error: Invalid Email ID format. Please enter a valid email (e.g., user@example.com)."
    
    # --- Generate Auto Fields ---
    complaint_id = generate_complaint_id()
    
    # Hidden / Default fields based on requirements
    status = "New"       # Override default 'open' to meet "New" requirement
    priority = None      # Blank
    team = None          # Blank
    sentiment = None     # Blank
    sla_days = None      # Blank
    summary = None       # Blank
    reasoning = None     # Blank
    sla_deadline = None  # Blank

    # --- Database Insert ---
    try:
        conn = duckdb.connect(DB_PATH)
        conn.execute("""
            INSERT INTO complaints (
                complaint_id, customer_id, cust_name, cust_email, complaint, 
                channel, branch, account_type, category, 
                priority, team, sentiment, sla_days, summary, reasoning, 
                status, created_at, sla_deadline
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp, ?)
        """, [
            complaint_id, customer_id, cust_name, cust_email, complaint, 
            channel, branch, account_type, category, 
            priority, team, sentiment, sla_days, summary, reasoning, 
            status, sla_deadline
        ])
        conn.close()
        return f"✅ Success! Complaint registered. Your Complaint ID: **{complaint_id}**"
    except Exception as e:
        return f"❌ Database Error: {str(e)}"

# --- Gradio UI ---
with gr.Blocks(title="Bank Complaint Registration") as demo:
    gr.Markdown("# Bank Complaint Registration Portal")
    gr.Markdown("Please fill in the details below to lodge your complaint.")
    
    with gr.Row():
        customer_id = gr.Textbox(label="Customer ID *", placeholder="Enter Customer ID")
        cust_name = gr.Textbox(label="Customer Name *", placeholder="Enter Full Name")
        
    with gr.Row():
        cust_email = gr.Textbox(label="Customer Email *", placeholder="Enter Email ID (e.g., name@domain.com)")
        account_type = gr.Dropdown(
            choices=["Consumer Banking", "Corporate Banking"], 
            label="Account Type *"
        )
        
    with gr.Row():
        channel = gr.Dropdown(
            choices=["Fraud", "Cards", "KYC", "Loans", "Digital Banking", "Branch Support", "Insurance", "General Support"], 
            label="Channel *"
        )
        category = gr.Dropdown(
            choices=["Savings", "Credit Card", "Personal Loan", "Insurance", "Corporate Banking", "Corporate Credit Card"], 
            label="Category *"
        )
        
    branch = gr.Dropdown(
        choices=TIERS_CITIES, 
        label="Branch *",
        interactive=True
    )
    
    complaint = gr.Textbox(label="Complaint *", lines=5, placeholder="Describe your issue in detail...")
    
    submit_btn = gr.Button("Submit Complaint", variant="primary")
    
    # Replaced gr.Textbox with gr.Markdown to hide the empty field container
    output_msg = gr.Markdown()
    
    submit_btn.click(
        fn=submit_complaint, 
        inputs=[customer_id, cust_name, cust_email, complaint, channel, branch, account_type, category], 
        outputs=output_msg
    )

if __name__ == "__main__":
    demo.launch(server_port=10000, share=True)