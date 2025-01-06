import gradio as gr
import pandas as pd
from app import PromptAnalysisApp

class GradioInterface:
    def __init__(self):
        self.app = PromptAnalysisApp()
        
    def create_interface(self):
        with gr.Blocks() as interface:
            with gr.Row():
                file_upload = gr.File(label="上传CSV文件")
                user_id = gr.Textbox(label="用户ID（可选）")
            
            # 添加垂类表格
            category_data = self.get_category_data()
            category_table = gr.Dataframe(
                value=category_data,
                headers=["垂类ID", "垂类名称", "数据量"],
                row_count=(15, "dynamic"),
                col_count=(3, "fixed"),
                interactive=False,
                label="垂类列表（点击行查看详情）"
            )
            
            # 添加选中垂类的详情展示
            selected_category = gr.Textbox(label="选中的垂类", visible=False)
            analysis_result = gr.HTML(label="分析结果")
            
            # 处理文件上传
            file_upload.upload(
                fn=self.handle_file_upload,
                inputs=[file_upload],
                outputs=[category_table]
            )
            
            # 处理表格选择
            category_table.select(
                fn=self.handle_category_select,
                inputs=[category_table, user_id],
                outputs=[analysis_result, selected_category]
            )
            
        return interface
    
    def get_category_data(self):
        """获取垂类数据"""
        # 这里可以根据实际数据结构调整
        categories = [
            ["7", "卡通形象", ""],
            ["20", "实拍写真", ""],
            ["30", "风景写真", ""],
            ["31", "秋日写真", ""],
            ["46", "毕业写真", ""],
            ["55", "艺术绘画", ""],
            ["63", "人像写真", ""],
            ["77", "服装搭配", ""],
            ["80", "宠物写真", ""],
            ["88", "单手写真", ""],
            ["90", "时钟写真", ""]
        ]
        return categories
    
    def handle_file_upload(self, file):
        """处理文件上传，更新垂类数据量"""
        if file is None:
            return None
            
        try:
            # 读取CSV文件
            df = pd.read_csv(file.name)
            self.app.df = df
            
            # 更新垂类数据量
            categories = self.get_category_data()
            for i, category in enumerate(categories):
                count = len(df[df['聚类ID'] == int(category[0])])
                categories[i][2] = str(count)
            
            return categories
            
        except Exception as e:
            print(f"文件处理错误: {str(e)}")
            return None
    
    def handle_category_select(self, evt: gr.SelectData, user_id):
        """处理垂类选择"""
        try:
            if self.app.df is None:
                return "请先上传CSV文件", None
                
            selected_category = evt.data[0]  # 获取选中行的垂类ID
            print(f"选中垂类: {selected_category}")
            
            # 过滤该垂类的数据
            category_df = self.app.df[self.app.df['聚类ID'] == int(selected_category)]
            
            if user_id:
                category_df = category_df[category_df['用户UID'].astype(str) == str(user_id)]
            
            if len(category_df) == 0:
                return "未找到相关数据", selected_category
            
            # 分析数据
            results = self.app.analyze_user_prompts(category_df)
            if results:
                return results, selected_category
            else:
                return "数据分析失败", selected_category
                
        except Exception as e:
            print(f"处理选择错误: {str(e)}")
            return f"处理错误: {str(e)}", None

if __name__ == "__main__":
    interface = GradioInterface()
    demo = interface.create_interface()
    demo.launch() 