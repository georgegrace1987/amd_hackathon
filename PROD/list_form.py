import gradio as gr

def create_list_page():
    with gr.Column(visible=False) as page:
        gr.Markdown("# 📋 Request List")
        gr.Markdown("Click on a **complaint_id** value in the table to view details.")
        
        requests_table = gr.Dataframe(
            value=None, 
            interactive=True, # Enables native sorting and filtering
            wrap=True
        )
        
        with gr.Row():
            back_to_login_btn = gr.Button("Logout", variant="stop")
            selected_complaint_id = gr.Textbox(label="Selected Complaint ID", interactive=False)
            view_details_btn = gr.Button("View Details", variant="primary")

    return page, requests_table, back_to_login_btn, selected_complaint_id, view_details_btn