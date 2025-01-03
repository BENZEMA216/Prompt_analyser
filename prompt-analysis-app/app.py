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
        
        # 添加模型加载状态检查
        try:
            self.analyzer.check_models()
        except Exception as e:
            self.logger.error(f"模型加载失败: {str(e)}")
            raise
        
    def load_data(self, csv_file):
        """加载CSV数据"""
        try:
            if csv_file is None:
                return gr.Dropdown(choices=[], value=None, label="请先上传CSV文件")
            
            self.df = pd.read_csv(csv_file.name)
            # 确保用户ID为字符串类型
            self.df['用户UID'] = self.df['用户UID'].astype(str)
            unique_users = self.df['用户UID'].unique().tolist()
            
            print(f"成功加载CSV文件，共有 {len(unique_users)} 个用户")
            return gr.Dropdown(
                choices=unique_users,
                label=f"选择用户 (共{len(unique_users)}个)",
                value=unique_users[0] if unique_users else None
            )
        except Exception as e:
            print(f"加载CSV文件时出错: {str(e)}")
            return gr.Dropdown(choices=[], value=None, label="加载文件失败")
    
    def analyze_user(self, user_id):
        """分析单个用户的Prompts"""
        try:
            if self.df is None:
                return "请先上传CSV文件"
            if user_id is None:
                return "请选择用户"
            
            print(f"开始分析用户: {user_id}")
            
            # 确保用户ID为字符串类型并获取用户数据
            user_data = self.df[self.df['用户UID'].astype(str) == str(user_id)]
            
            if user_data.empty:
                return f"未找到用户 {user_id} 的数据"
            
            # 检查时间字段
            time_column = None
            if '生成时间(精确到秒)' in user_data.columns:
                time_column = '生成时间(精确到秒)'
            elif 'p_date' in user_data.columns:
                time_column = 'p_date'
            else:
                return "CSV文件缺少时间字段: 需要 'p_date' 或 '生成时间(精确到秒)'"
            
            # 检查必要的列是否存在
            required_columns = ['prompt', '生成结果预览图']
            missing_columns = [col for col in required_columns if col not in user_data.columns]
            if missing_columns:
                return f"CSV文件缺少必要的列: {', '.join(missing_columns)}"
            
            # 检查数据有效性
            valid_data = user_data.dropna(subset=['prompt', time_column, '生成结果预览图'])
            if len(valid_data) == 0:
                return f"用户 {user_id} 没有有效的Prompt数据"
            
            print(f"找到 {len(valid_data)} 条有效数据")
            print(f"使用时间字段: {time_column}")
            
            # 添加数据量检查
            print("\n=== 数据统计 ===")
            print(f"原始数据量: {len(user_data)}")
            print(f"有效数据量: {len(valid_data)}")
            
            # 创建临时DataFrame
            temp_df = pd.DataFrame({
                '用户UID': valid_data['用户UID'],
                'prompt': valid_data['prompt'],
                'timestamp': valid_data[time_column],  # 使用检测到的时间字段
                '生成结果预览图': valid_data['生成结果预览图'],
                'is_saved': valid_data['是否双端采纳(下载、复制、发布、后编辑、生视频、作为参考图、去画布)'].fillna(0).astype(int) == 1
            })
            
            # 标准化时间格式
            try:
                if time_column == '生成时间(精确到秒)':
                    # 将 Unix timestamp 转换为 datetime
                    temp_df['timestamp'] = pd.to_datetime(temp_df['timestamp'].astype(int), unit='s')
                else:
                    # 处理 p_date 格式
                    temp_df['timestamp'] = pd.to_datetime(temp_df['timestamp'])
                
                # 转换为统一的字符串格式
                temp_df['timestamp'] = temp_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
                
            except Exception as e:
                print(f"时间格式转换出错: {str(e)}")
                return f"时间格式转换失败: {str(e)}"
            
            # 调用聚类分析前打印信息
            print("\n=== 开始聚类 ===")
            print(f"待聚类数据量: {len(temp_df)}")
            
            # 调用聚类分析
            results = self.analyzer.analyze_user_prompts(temp_df, str(user_id))
            
            # 检查聚类结果
            if results is None:
                return "聚类分析返回空结果"
            
            if not isinstance(results, dict) or 'clusters' not in results:
                return "聚类结果格式错误"
            
            clusters = results['clusters']
            print("\n=== 聚类结果统计 ===")
            print(f"聚类总数: {len(clusters)}")
            print(f"各聚类大小: {[len(prompts) for prompts in clusters.values()]}")
            
            self.current_results = results
            return results  # 返回原始结果而不是视图
            
        except Exception as e:
            print(f"分析用户时出错: {str(e)}")
            import traceback
            traceback.print_exc()
            return f"分析出错: {str(e)}"
    
    def generate_analysis_view(self, results):
        """生成分析视图HTML"""
        try:
            if not results.get('clusters'):
                return "没有找到可分析的数据"
                
            # 对聚类按大小排序
            sorted_clusters = sorted(
                results['clusters'].items(),
                key=lambda x: len(x[1]),
                reverse=True
            )
            
            html = self.get_style_html()
            
            # 添加统计信息
            total_prompts = sum(len(prompts) for _, prompts in sorted_clusters)
            html += f"""
            <div class="section-title">
                分析结果 (共 {total_prompts} 条Prompt，{len(sorted_clusters)} 个聚类)
            </div>
            """
            
            # 时间轴视图（只显示最新的50条）
            html += '<div class="section-title">Prompt 时间轴（最新50条）</div>'
            all_prompts = []
            for cluster in results['clusters'].values():
                all_prompts.extend(cluster)
            
            # 按时间排序并限制显示数量
            all_prompts.sort(key=lambda x: x['timestamp'], reverse=True)
            display_prompts = all_prompts[:50]
            
            for i, prompt in enumerate(display_prompts):
                html += self.generate_prompt_card(
                    prompt, 
                    prev_prompt=display_prompts[i-1] if i > 0 else None
                )
            
            # 聚类视图
            html += f'<div class="section-title">Prompt 聚类分析</div>'
            for cluster_id, prompts in sorted_clusters:
                # 对每个聚类的显示也限制数量
                display_prompts = sorted(prompts, key=lambda x: x['timestamp'], reverse=True)[:50]
                
                html += f"""
                <div class="cluster-section">
                    <div class="cluster-header">
                        <span class="cluster-title">聚类 {cluster_id}</span>
                        <span class="cluster-count">共 {len(prompts)} 条Prompt {f'(显示最新50条)' if len(prompts) > 50 else ''}</span>
                    </div>
                """
                
                for p in display_prompts:
                    html += self.generate_prompt_card(p)
                
                html += "</div>"
            
            return html
            
        except Exception as e:
            print(f"生成分析视图时出错: {str(e)}")
            return f"生成视图失败: {str(e)}"
    
    def get_style_html(self):
        """返回样式HTML"""
        return """
        <style>
        /* 全局文本颜色设置 */
        .gradio-container,
        .gradio-container * {
            color: #000000 !important;
        }
        
        /* Prompt 卡片样式 */
        .gradio-container .prompt-card {
            background: #ffffff !important;
            border: 1px solid #e1e4e8 !important;
            padding: 20px !important;
        }
        
        /* Prompt 文本样式 */
        .gradio-container .prompt-card .prompt-text,
        .gradio-container .prompt-content .prompt-text {
            color: #000000 !important;
            font-size: 14px !important;
            line-height: 1.6 !important;
            font-weight: normal !important;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
            white-space: pre-wrap !important;
            margin: 8px 0 !important;
        }
        
        /* 时间戳样式 */
        .gradio-container .prompt-card .timestamp {
            color: #666666 !important;
            font-size: 12px !important;
        }
        
        /* 差异部分文本样式 */
        .gradio-container .diff-section {
            color: #000000 !important;
        }
        
        .gradio-container .word-removed {
            color: #b31d28 !important;
        }
        
        .gradio-container .word-added {
            color: #22863a !important;
        }
        
        /* 标题样式 */
        .gradio-container .section-title,
        .gradio-container .cluster-title {
            color: #000000 !important;
            font-weight: 600 !important;
        }
        
        .gradio-container .cluster-header {
            color: #000000 !important;
        }
        
        .gradio-container .cluster-count {
            color: #0366d6 !important;  /* 聚类数量用蓝色 */
        }
        
        /* 使用更高优先级的选择器 */
        .gradio-container .prompt-card {
            background: #ffffff !important;
            border: 1px solid #e1e4e8;
            border-radius: 8px;
            padding: 20px;
            margin: 16px 0;
            display: flex;
            gap: 20px;
        }
        
        .gradio-container .prompt-content {
            flex: 3;
            display: flex;
            flex-direction: column;
        }
        
        .gradio-container .prompt-image {
            flex: 1;
            max-width: 200px;
            min-width: 150px;
        }
        
        .gradio-container .prompt-image img {
            width: 100%;
            height: auto;
            border-radius: 4px;
            object-fit: cover;
        }
        
        .gradio-container .diff-section {
            margin-top: 12px;
            padding: 12px;
            background: #f8f9fa;
            border-radius: 6px;
            border-left: 3px solid #0366d6;
            color: #24292e;  /* 差异文本颜色 */
        }
        
        .gradio-container .word-removed {
            background-color: #ffeef0;  /* 浅粉红色背景，表示删除 */
            color: #b31d28;  /* 深红色文字 */
            border: 1px solid #f9d0d5;  /* 粉红色边框 */
        }
        
        .gradio-container .word-added {
            background-color: #e6ffed;  /* 浅绿色背景，表示新增 */
            color: #22863a;  /* 深绿色文字 */
            border: 1px solid #bef5cb;  /* 浅绿色边框 */
        }
        
        .gradio-container .saved-badge {
            background: #28a745;  /* 绿色背景，表示已保存状态 */
            color: #ffffff;  /* 白色文字 */
        }
        
        .gradio-container .nav-button {
            display: inline-block;
            padding: 8px 16px;
            margin: 8px;
            background: #ffffff;
            border: 1px solid #e1e4e8;
            border-radius: 6px;
            color: #24292e;
            text-decoration: none;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .gradio-container .nav-button:hover {
            background: #f6f8fa;
            border-color: #0366d6;
        }
        
        .gradio-container .cluster-filter {
            margin: 20px 0;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 8px;
        }
        
        .gradio-container .filter-active {
            background: #f1f8ff;
            border-left: 3px solid #0366d6;
        }
        
        .gradio-container .saved-card {
            border: 2px solid #28a745 !important;  /* 加重保存状态的边框 */
        }
        
        .gradio-container .saved-badge {
            position: absolute;
            top: 10px;
            right: 10px;
            background: #28a745;
            color: white;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.9em;
            z-index: 1;
        }
        
        .gradio-container .stat-item.saved {
            color: #28a745;
            font-weight: 500;
        }
        
        /* 调试边框 */
        .debug-border * {
            border: 1px solid red;
        }
        
        /* 下拉框样式 */
        .gradio-dropdown {
            width: 100% !important;
            max-width: none !important;
        }
        
        /* 选项样式 */
        .gradio-dropdown select {
            width: 100% !important;
            padding: 8px !important;
            font-size: 14px !important;
        }
        
        /* 确保选项可见 */
        .gradio-dropdown option {
            padding: 8px !important;
            white-space: normal !important;
            word-wrap: break-word !important;
        }
        </style>
        """
    
    def generate_prompt_card(self, prompt, prev_prompt=None):
        """生成单个Prompt卡片的HTML"""
        try:
            is_saved = prompt.get('is_saved', False)
            saved_class = 'saved-card' if is_saved else ''
            
            html = f"""
            <div class="prompt-card {saved_class}" style="position: relative;">
                {f'<div class="saved-badge">已保存</div>' if is_saved else ''}
                <div class="prompt-content">
                    <div class="timestamp">{prompt['timestamp']}</div>
                    <div class="prompt-text">{prompt['prompt']}</div>
            """
            
            # 添加差异分析
            if prev_prompt:
                diff = analyze_word_differences(prev_prompt['prompt'], prompt['prompt'])
                if diff['prev_unique'] or diff['curr_unique']:
                    html += '<div class="diff-section">'
                    if diff['prev_unique']:
                        html += f'<div style="margin-bottom:8px">删除: {", ".join(diff["prev_unique"])}</div>'
                    if diff['curr_unique']:
                        html += f'<div style="margin-bottom:8px">新增: {", ".join(diff["curr_unique"])}</div>'
                    html += f'<div>当前版本: {diff["curr_html"]}</div>'
                    html += '</div>'
            
            html += f"""
                    <div class="prompt-stats">
                        <div class="stat-item">
                            <span>创建时间:</span>
                            <span>{prompt['timestamp']}</span>
                        </div>
            """
            
            if is_saved:
                html += """
                        <div class="stat-item saved">
                            <span>✓ 用户已保存</span>
                        </div>
                """
            
            html += f"""
                    </div>
                </div>
                <div class="prompt-image">
                    <img src="{prompt['preview_url']}" alt="预览图">
                </div>
            </div>
            """
            return html
        except Exception as e:
            print(f"生成Prompt卡片时出错: {str(e)}")
            return ""

    def generate_cluster_section(self, cluster_id, prompts):
        """生成聚类部分的HTML"""
        try:
            html = f"""
            <div class="cluster-section">
                <h4>聚类 {cluster_id} ({len(prompts)} 条Prompt)</h4>
            """
            
            for p in prompts:
                html += self.generate_prompt_card(p)
            
            html += "</div>"
            return html
        except Exception as e:
            print(f"生成聚类部分时出错: {str(e)}")
            return ""

    def generate_cluster_view(self, cluster_id):
        """生成单个聚类的视图"""
        try:
            # 确保cluster_id是整数
            cluster_id = int(cluster_id) if not isinstance(cluster_id, int) else cluster_id
            
            if not self.current_results or cluster_id not in self.current_results['clusters']:
                print(f"未找到聚类 {cluster_id}")
                print(f"可用的聚类: {list(self.current_results['clusters'].keys()) if self.current_results else 'None'}")
                return "未找到聚类数据"
            
            prompts = self.current_results['clusters'][cluster_id]
            html = self.get_style_html()
            
            html += f"""
            <div class="section-title">
                聚类 {cluster_id} ({len(prompts)} 条Prompt)
            </div>
            """
            
            # 按时间排序显示
            sorted_prompts = sorted(prompts, key=lambda x: x['timestamp'])
            for i, prompt in enumerate(sorted_prompts):
                html += self.generate_prompt_card(
                    prompt,
                    prev_prompt=sorted_prompts[i-1] if i > 0 else None
                )
            
            return html
        except Exception as e:
            print(f"生成聚类视图时出错: {str(e)}")
            traceback.print_exc()
            return f"生成视图失败: {str(e)}"

def create_ui():
    app = PromptAnalysisApp()
    
    def analyze_and_show_clusters(user_id):
        try:
            print("\n=== 开始分析聚类 ===")
            print(f"用户ID: {user_id}")
            
            results = app.analyze_user(user_id)
            
            if isinstance(results, str):
                print(f"返回错误信息: {results}")
                return [[], gr.update(choices=["全部"]), results, "分析失败"]
            
            # 准备数据
            clusters_data = []
            cluster_choices = ["全部"]
            
            # 按聚类大小排序并限制数量
            sorted_clusters = sorted(
                app.current_results['clusters'].items(),
                key=lambda x: len(x[1]),
                reverse=True
            )[:50]  # 限制最多显示50个聚类
            
            print(f"\n找到 {len(sorted_clusters)} 个聚类 (限制显示前50个)")
            
            # 处理每个聚类
            for cluster_id, prompts in sorted_clusters:
                # 确保cluster_id是字符串类型
                cluster_id = str(cluster_id)
                
                latest_prompt = sorted(prompts, key=lambda x: x['timestamp'])[-1]
                prompt_preview = latest_prompt['prompt'][:100] + "..." if len(latest_prompt['prompt']) > 100 else latest_prompt['prompt']
                
                # 使用一致的格式
                cluster_label = f"聚类 {cluster_id}"
                
                clusters_data.append([
                    cluster_label,
                    f"{len(prompts)}条",
                    prompt_preview
                ])
                cluster_choices.append(cluster_label)
                
                print(f"添加选项: {cluster_label}")
            
            print("\n=== 最终数据 ===")
            print(f"表格数据: {len(clusters_data)} 行")
            print(f"选项列表: {cluster_choices}")
            
            return [
                clusters_data,  # 表格数据
                gr.update(choices=cluster_choices, value="全部"),  # 下拉选项
                "",  # 清空输出
                f"找到 {len(app.current_results['clusters'])} 个聚类，显示前 {len(sorted_clusters)} 个"  # 调试信息
            ]
        except Exception as e:
            print(f"\n=== 发生错误 ===")
            print(f"错误信息: {str(e)}")
            traceback.print_exc()
            return [[], gr.update(choices=["全部"]), str(e), str(e)]
    
    def show_cluster_details(selected_cluster):
        print(f"选择的聚类: {selected_cluster}")
        
        if not app.current_results:
            return ["请先进行分析", "未选择聚类"]
        
        try:
            if selected_cluster == "全部":
                return [app.generate_analysis_view(app.current_results), "显示所有聚类"]
            
            try:
                # 从 "聚类 X" 格式中提取数字
                cluster_id = int(selected_cluster.split()[1])  # 转换为整数
                print(f"提取的聚类ID: {cluster_id}")
                print(f"可用的聚类: {list(app.current_results['clusters'].keys())}")
                
                # 直接检查整数ID是否存在
                if cluster_id not in app.current_results['clusters']:
                    print(f"未找到聚类 {cluster_id}")
                    return [f"未找到聚类 {cluster_id}", "无效的聚类ID"]
                
                # 生成视图
                result = app.generate_cluster_view(cluster_id)
                print(f"生成视图成功，长度: {len(result) if result else 0}")
                return [result, f"显示聚类 {cluster_id} 的详细信息"]
                
            except ValueError as e:
                print(f"聚类ID转换错误: {str(e)}")
                return ["无效的聚类ID格式", "格式错误"]
            except Exception as e:
                print(f"处理聚类ID时出错: {str(e)}")
                traceback.print_exc()
                return ["处理聚类ID时出错", str(e)]
            
        except Exception as e:
            print(f"显示聚类详情时出错: {str(e)}")
            traceback.print_exc()
            return [str(e), "出错"]
    
    # 创建界面
    with gr.Blocks(title="Prompt分析工具", css="""
        :root {
            --primary-color: #8B9DA5;  /* 莫兰迪蓝灰色 */
            --background-color: #F5F4F2;  /* 莫兰迪米白色 */
            --text-color: #4A4A4A;  /* 深灰色文字 */
            --border-color: #D6D3CC;  /* 莫兰迪灰棕色边框 */
            --hover-color: #A4B0B9;  /* 浅蓝灰色悬停 */
            --accent-color: #B5A9A1;  /* 莫兰迪褐色强调 */
            --success-color: #9CAF88;  /* 莫兰迪绿色成功提示 */
        }
        
        .container { 
            max-width: 1200px; 
            margin: 0 auto; 
            padding: 20px; 
            background-color: var(--background-color); 
            color: var(--text-color);
        }
        .overview-section, .selector-section, .output-section, .debug-section {
            background-color: var(--background-color);
            color: var(--text-color);
            margin-bottom: 20px;
            padding: 15px;
            border-radius: 8px;
        }
        .fixed-table, .fixed-selector {
            width: 100%; 
            margin-bottom: 20px; 
            background-color: #FFFFFF;
            color: var(--text-color);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }
        .prompt-card {
            background-color: #FFFFFF;
            color: var(--text-color);
            border: 1px solid var(--border-color);
            margin-bottom: 15px;
            padding: 15px;
            border-radius: 6px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }
        .prompt-card .saved-badge {
            background-color: var(--success-color);
            color: #FFFFFF;
            padding: 5px 10px;
            border-radius: 4px;
            font-size: 0.9em;
        }
        button, .gr-button {
            background-color: var(--primary-color);
            color: #FFFFFF;
            border: none;
            padding: 10px 20px;
            cursor: pointer;
            transition: all 0.3s ease;
            border-radius: 6px;
            font-weight: 500;
        }
        button:hover, .gr-button:hover {
            background-color: var(--hover-color);
            transform: translateY(-1px);
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .gr-dropdown {
            background-color: #FFFFFF;
            color: var(--text-color);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            transition: all 0.3s ease;
        }
        .gr-dropdown:hover {
            border-color: var(--accent-color);
        }
        .section-title {
            color: var(--accent-color);
            font-size: 1.2em;
            margin-bottom: 15px;
            font-weight: 500;
        }
        .cluster-header {
            color: var(--primary-color);
            padding: 10px 0;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: 15px;
        }
    """) as interface:
        with gr.Column(elem_classes="container"):
            gr.Markdown("# Prompt 分析工具")
            
            # 1. 上传和选择区域
            with gr.Row():
                file_input = gr.File(label="上传CSV文件", file_types=[".csv"])
                user_dropdown = gr.Dropdown(label="选择用户", interactive=True)
                analyze_btn = gr.Button("开始分析", variant="primary")
            
            # 2. 聚类概览区域
            with gr.Row(elem_classes="overview-section"):
                cluster_overview = gr.Dataframe(
                    headers=["聚类ID", "Prompt数量", "示例Prompt"],
                    label="聚类概览",
                    wrap=True,
                    elem_classes=["fixed-table"]  # 添加固定样式类
                )
            
            # 3. 聚类选择区域
            with gr.Row(elem_classes="selector-section"):
                cluster_selector = gr.Dropdown(
                    label="选择聚类查看详情",
                    choices=["全部"],
                    value="全部",
                    interactive=True,
                    elem_classes=["fixed-selector"]  # 添加固定样式类
                )
            
            # 4. 结果展示区域
            with gr.Row(elem_classes="output-section"):
                output = gr.HTML(elem_classes=["fixed-output"])  # 添加固定样式类
            
            # 5. 调试信息区域
            with gr.Row(elem_classes="debug-section"):
                debug_output = gr.Textbox(label="调试信息", lines=3)

        # 绑定事件
        file_input.change(
            fn=app.load_data,
            inputs=[file_input],
            outputs=[user_dropdown]
        )
        
        analyze_btn.click(
            fn=analyze_and_show_clusters,
            inputs=[user_dropdown],
            outputs=[
                cluster_overview,
                cluster_selector,
                output,
                debug_output
            ]
        )
        
        # 修改选择事件，只更新输出和调试信息
        cluster_selector.change(
            fn=show_cluster_details,
            inputs=[cluster_selector],
            outputs=[output, debug_output]
        ).then(  # 添加回调以保持选择器状态
            fn=lambda x: x,
            inputs=[cluster_selector],
            outputs=[cluster_selector]
        )
    
    return interface

if __name__ == "__main__":
    interface = create_ui()
    interface.launch(
        share=True,
        server_name="0.0.0.0",
        server_port=7860,
        debug=True
    ) 