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

    def analyze_user(self, user_id):
        """分析用户数据"""
        try:
            if self.df is None:
                return "请先上传CSV文件", "未加载数据"
            if user_id is None:
                return "请选择用户", "未选择用户"

            # 获取用户数据
            user_data = self.df[self.df['用户UID'].astype(str) == str(user_id)]
            
            # 准备数据
            temp_df = pd.DataFrame({
                'prompt': user_data['prompt'],
                'timestamp': user_data['生成时间(精确到秒)'],
                '生成结果预览图': user_data['生成结果预览图'],
                'is_saved': user_data['是否双端采纳(下载、复制、发布、后编辑、生视频、作为参考图、去画布)'].fillna(0).astype(int) == 1
            })

            # 分析数据
            results = self.analyzer.analyze_user_prompts(temp_df, str(user_id))
            if results is None:
                return "分析失败", "分析过程出错"

            # 生成HTML展示
            html_output = self.generate_analysis_view(results)
            return html_output, "分析完成"

        except Exception as e:
            self.logger.error(f"分析用户数据时出错: {str(e)}")
            return f"分析出错: {str(e)}", str(e)

    def generate_analysis_view(self, results):
        """生成分析结果的HTML视图"""
        html = """
        <style>
        .prompt-card {
            border: 1px solid #ddd;
            padding: 15px;
            margin: 10px 0;
            border-radius: 8px;
        }
        .timestamp {
            color: #666;
            font-size: 0.9em;
        }
        .preview-image {
            max-width: 200px;
            margin-top: 10px;
        }
        </style>
        """
        
        for cluster_id, prompts in results['clusters'].items():
            html += f"<h3>聚类 {cluster_id} ({len(prompts)} 条Prompt)</h3>"
            for p in prompts:
                html += f"""
                <div class="prompt-card">
                    <div class="timestamp">{p['timestamp']}</div>
                    <div class="prompt-text">{p['prompt']}</div>
                    <img class="preview-image" src="{p['preview_url']}" alt="预览图">
                </div>
                """
        
        return html

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
        
        analyze_btn.click(
            fn=app.analyze_user,
            inputs=[user_dropdown],
            outputs=[output, debug_output]
        )

    return interface

# 创建界面
interface = create_ui()

# 启动应用（移除密码验证）
if __name__ == "__main__":
    interface.launch(
        server_name="0.0.0.0",
        server_port=7860,
        debug=False
    ) 