import gradio as gr
from db_manager import get_dropdown_choices

def validate_selection(selected_value, valid_choices):
    if not selected_value or selected_value.startswith("Select"):
        return ""
    return "✅ Valid selection" if selected_value in valid_choices else "⚠️ Invalid selection"

def create_details_page():
    user_ids, teams = get_dropdown_choices()
    
    with gr.Column(visible=False) as page:
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

        # Wire up validations within the form
        d_routed_team.change(lambda x: validate_selection(x, teams), inputs=d_routed_team, outputs=routed_team_validation)
        d_escalate_to.change(lambda x: validate_selection(x, user_ids), inputs=d_escalate_to, outputs=escalate_to_validation)

    return (
        page, d_complaint_id, d_routing_id, d_customer_id, d_cust_name, d_complaint,
        d_category, d_priority, d_sentiment, d_original_team, d_confidence,
        d_sla_hours, d_routing_status, d_latency_ms, d_routing_reason_ro, d_team_email_ro,
        d_routed_team, d_escalate, d_escalate_to, d_action, d_routing_reason, d_team_email,
        submit_btn, update_status_msg, back_to_list_btn
    )