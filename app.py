import gradio as gr
import pandas as pd
from keyword_analysis import PromptAnalyzer, analyze_word_differences
from datetime import datetime
import os
import traceback
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class PromptAnalysisApp:
    def __init__(self):
        self.analyzer = PromptAnalyzer()
        self.df = None
        self.current_results = {}
        self.logger = logging.getLogger(__name__)
        
    def load_data(self, csv_file):
        """加载CSV数据"""
        try:
            if csv_file is None:
                return gr.Dropdown(choices=[], value=None, label="请先上传CSV文件")
            
            self.df = pd.read_csv(csv_file.name)
            self.df['用户UID'] = self.df['用户UID'].astype(str)
            unique_users = self.df['用户UID'].unique().tolist()
            
            return gr.Dropdown(
                choices=unique_users,
                label=f"选择用户 (共{len(unique_users)}个)",
                value=unique_users[0] if unique_users else None
            )
        except Exception as e:
            self.logger.error(f"加载CSV文件时出错: {str(e)}")
            return gr.Dropdown(choices=[], value=None, label="加载文件失败")

def create_ui():
    app = PromptAnalysisApp()
    
    with gr.Blocks(title="Prompt分析工具") as interface:
        with gr.Column():
            gr.Markdown("# Prompt 分析工具")
            
            with gr.Row():
                file_input = gr.File(label="上传CSV文件", file_types=[".csv"])
                user_dropdown = gr.Dropdown(label="选择用户", interactive=True)
                analyze_btn = gr.Button("开始分析", variant="primary")
            
            with gr.Row():
                output = gr.HTML()
            
            with gr.Row():
                debug_output = gr.Textbox(label="调试信息", lines=3)

        file_input.change(
            fn=app.load_data,
            inputs=[file_input],
            outputs=[user_dropdown]
        )

    return interface

# 创建界面
interface = create_ui()

# 启动应用
if __name__ == "__main__":
    interface.launch(
        server_name="0.0.0.0",
        server_port=7860,
        auth=("admin", "password"),
        debug=False
    ) 