import gradio as gr

def create_dashboard_page():
    with gr.Column(visible=False) as page:
        gr.Markdown("# 📊 Supervisor Dashboard")
        
        # --- KPI Metrics Row ---
        with gr.Row():
            total_complaints = gr.Label(label="Total Complaints", value="0")
            escalated_count = gr.Label(label="Escalated", value="0")
            avg_sla_hours = gr.Label(label="Avg SLA Hours", value="0 hrs")
            
        # --- Visual Breakdown Row ---
        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### Complaints by Category")
                category_plot = gr.BarPlot(x="Category", y="Count", height=300)
            with gr.Column(scale=1):
                gr.Markdown("### Complaints by Priority")
                priority_plot = gr.BarPlot(x="Priority", y="Count", height=300)
        
        gr.Markdown("---")
        
        # --- Professional Filters ---
        gr.Markdown("### 🔍 Filters")
        with gr.Row():
            filter_category = gr.Dropdown(label="Category", allow_custom_value=True, scale=1)
            filter_priority = gr.Dropdown(label="Priority", allow_custom_value=True, scale=1)
            filter_escalate = gr.Dropdown(label="Escalate", choices=["True", "False"], scale=1)
            filter_status = gr.Dropdown(label="Routing Status", allow_custom_value=True, scale=1)
            
        with gr.Row():
            apply_btn = gr.Button("Apply Filters", variant="primary")
            reset_btn = gr.Button("Reset Filters")
            
        gr.Markdown("---")
        
        # --- Detailed Table ---
        gr.Markdown("### 📋 Detailed Routing List")
        # Removed height=400 to fix the TypeError
        dashboard_table = gr.Dataframe(interactive=True, wrap=True)
        
        with gr.Row():
            back_to_list_btn = gr.Button("← View Standard List")
            back_to_login_btn = gr.Button("Logout", variant="stop")

    return (
        page, total_complaints, escalated_count, avg_sla_hours, 
        category_plot, priority_plot, dashboard_table, 
        filter_category, filter_priority, filter_escalate, filter_status, 
        apply_btn, reset_btn, back_to_list_btn, back_to_login_btn
    )