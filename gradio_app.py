import gradio as gr
import pandas as pd
from app import PromptAnalysisApp
import traceback
import time

class GradioInterface:
    def __init__(self):
        self.app = PromptAnalysisApp()
    
    def create_interface(self):
        with gr.Blocks(theme=gr.themes.Base()) as interface:
            gr.HTML(self.get_dark_theme_style())
            
            gr.Markdown("# Prompt 分析工具")
            
            # 1. 上传和用户选择区域
            with gr.Row():
                file_input = gr.File(
                    label="上传CSV文件",
                    file_types=[".csv"]
                )
                user_id = gr.Textbox(
                    label="用户ID（可选）"
                )
                analyze_btn = gr.Button("开始分析")
            
            # 添加文件上传状态显示
            upload_status = gr.Textbox(
                label="文件上传状态",
                interactive=False,
                visible=True
            )
            
            # 2. 垂类表格（初始隐藏）
            category_table = gr.Dataframe(
                headers=["垂类ID", "垂类名称", "数据量"],
                label="垂类列表（点击行查看详情）",
                interactive=True,
                visible=False
            )
            
            # 3. 结果展示
            analysis_result = gr.HTML(label="分析结果")
            
            # 事件处理
            def handle_file_upload(file):
                try:
                    self.app.load_data(file)
                    return "文件加载成功，请输入用户ID并点击分析"
                except Exception as e:
                    print(f"文件加载错误: {str(e)}")
                    return f"文件加载失败: {str(e)}"

            def handle_analyze_click(user_id):
                try:
                    if self.app.df is None:
                        return gr.Dataframe.update(value=None, visible=False), "请先上传CSV文件"
                    
                    if not user_id or not user_id.strip():
                        return gr.Dataframe.update(value=None, visible=False), "请输入用户ID"
                    
                    user_id = str(user_id).strip()
                    print(f"正在分析用户: {user_id}")
                    
                    user_data = self.app.df[self.app.df['用户UID'].astype(str) == user_id]
                    if len(user_data) == 0:
                        return gr.Dataframe.update(value=None, visible=False), f"未找到用户 {user_id} 的数据"
                    
                    print(f"找到用户数据 {len(user_data)} 条")
                    
                    # 获取用户的垂类数据
                    category_data = user_data.groupby('聚类ID').size().reset_index()
                    category_data.columns = ['聚类ID', '数据量']
                    
                    # 转换为列表格式
                    category_rows = []
                    for _, row in category_data.iterrows():
                        category_rows.append([
                            str(row['聚类ID']),
                            "垂类" + str(row['聚类ID']),
                            str(row['数据量'])
                        ])
                    
                    if not category_rows:
                        return gr.Dataframe.update(value=None, visible=False), f"用户 {user_id} 暂无数据"
                        
                    # 只返回两个值：表格更新和状态消息
                    return gr.Dataframe.update(value=category_rows, visible=True), f"找到用户 {user_id} 的数据"
                except Exception as e:
                    print(f"分析错误: {str(e)}")
                    traceback.print_exc()
                    return gr.Dataframe.update(value=None, visible=False), f"分析失败: {str(e)}"

            def handle_category_select(evt: gr.SelectData, user_id):
                try:
                    if self.app.df is None:
                        return (
                            gr.update(value=None),  # 保持表格不变
                            "请先上传CSV文件"  # 状态消息
                        )
                    
                    if not user_id or not user_id.strip():
                        return (
                            gr.update(value=None),
                            "请先输入用户ID"
                        )
                    
                    user_id = str(user_id).strip()
                    
                    # 从选中行获取垂类ID
                    selected_id = evt.index[0]  # 使用 index 获取选中行的索引
                    category_id = evt.data[0]  # 获取该行第一列的值（垂类ID）
                    
                    print(f"分析用户 {user_id} 的垂类 {category_id}")
                    
                    category_df = self.app.df[
                        (self.app.df['聚类ID'] == int(category_id)) & 
                        (self.app.df['用户UID'].astype(str) == user_id)
                    ]
                    
                    print(f"找到 {len(category_df)} 条数据")
                    
                    if len(category_df) == 0:
                        return (
                            gr.update(value=None),
                            f"用户 {user_id} 在垂类 {category_id} 下暂无数据"
                        )
                    
                    results = self.app.analyze_user_prompts(category_df)
                    if not results:
                        return (
                            gr.update(value=None),
                            "分析结果为空"
                        )
                        
                    analysis_view = self.app.generate_analysis_view(results)
                    return (
                        gr.update(value=None),  # 保持表格不变
                        analysis_view  # 显示分析结果
                    )
                    
                except Exception as e:
                    print(f"分析错误: {str(e)}")
                    traceback.print_exc()
                    return (
                        gr.update(value=None),
                        f"分析失败: {str(e)}"
                    )

            # 绑定事件
            file_input.change(
                fn=handle_file_upload,
                inputs=[file_input],
                outputs=[upload_status]  # 改为使用新的状态文本组件
            )
            
            analyze_btn.click(
                fn=handle_analyze_click,
                inputs=[user_id],
                outputs=[
                    category_table,
                    analysis_result  # 用于显示状态消息
                ]
            )
            
            category_table.select(
                fn=handle_category_select,
                inputs=[category_table, user_id],
                outputs=[
                    category_table,  # 保持表格状态
                    analysis_result  # 显示分析结果或错误消息
                ]
            )

        return interface

    def get_dark_theme_style(self):
        # 添加时间戳作为版本号
        version = int(time.time())
        return f"""
        <style data-version="{version}">
        :root {{
            --background-base: #000000;
            --background-primary: #1a1a1a;
            --background-secondary: #2d2d2d;
            --text-primary: #ffffff;
            --text-secondary: #e0e0e0;
            --border-color: #404040;
        }}

        /* 添加命名空间避免样式冲突 */
        .gradio-app-{version} {{
            background-color: var(--background-base) !important;
        }}

        .gradio-app-{version} .gr-box {{
            background-color: var(--background-primary) !important;
            border-color: var(--border-color) !important;
        }}

        .gradio-app-{version} table {{
            background-color: var(--background-primary) !important;
        }}

        .gradio-app-{version} th {{
            background-color: var(--background-secondary) !important;
            color: var(--text-primary) !important;
        }}

        .gradio-app-{version} td {{
            color: var(--text-secondary) !important;
        }}

        .gradio-app-{version} label, 
        .gradio-app-{version} .gr-text {{
            color: var(--text-primary) !important;
        }}
        </style>

        <script>
        // 强制刷新样式
        document.addEventListener('DOMContentLoaded', function() {{
            document.querySelector('.gradio-container').classList.add('gradio-app-{version}');
        }});
        </script>
        """

if __name__ == "__main__":
    interface = GradioInterface()
    demo = interface.create_interface()
    demo.launch(
        server_name="0.0.0.0", 
        server_port=7860,
        show_error=True
    ) 