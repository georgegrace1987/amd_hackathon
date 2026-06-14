import gradio as gr

def create_login_page():
    with gr.Column(visible=True) as page:
        gr.Markdown("# 🏦 Bank Employee Login")
        with gr.Group():
            user_id_input = gr.Textbox(label="UserID", placeholder="Enter your UserID")
            password_input = gr.Textbox(label="Password", type="password", placeholder="Enter your password")
            login_btn = gr.Button("Login", variant="primary")
            login_error = gr.Markdown("")
            
    return page, user_id_input, password_input, login_btn, login_error