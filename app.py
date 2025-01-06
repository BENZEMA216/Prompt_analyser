import gradio as gr
import pandas as pd
from keyword_analysis import PromptAnalyzer, analyze_word_differences
from datetime import datetime
import os
import traceback
import logging
import jieba

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
            if '生成结果预览图' not in user_data.columns:
                return "CSV文件缺少必要的列: 生成结果预览图"
            
            # 检查数据有效性 - 修改这里，不要过滤掉垫图
            valid_data = user_data.dropna(subset=['prompt', time_column])
            if len(valid_data) == 0:
                return f"用户 {user_id} 没有有效的Prompt数据"
            
            print("\n=== 数据验证 ===")
            print(f"列名: {valid_data.columns.tolist()}")
            print(f"垫图列存在: {'指令编辑垫图' in valid_data.columns}")
            if '指令编辑垫图' in valid_data.columns:
                print(f"有垫图的行数: {valid_data['指令编辑垫图'].notna().sum()}")
            
            print(f"找到 {len(valid_data)} 条有效数据")
            print(f"使用时间字段: {time_column}")
            
            # 添加数据量检查
            print("\n=== 数据统计 ===")
            print(f"原始数据量: {len(user_data)}")
            print(f"有效数据量: {len(valid_data)}")
            
            # 按时间和prompt分组时记录每张图片的保存状态
            grouped_data = {}
            for _, row in valid_data.iterrows():
                key = (row[time_column], row['prompt'])
                preview_url = row.get('生成结果预览图')
                reference_img = row.get('指令编辑垫图') if pd.notna(row.get('指令编辑垫图')) else None
                enter_from = row.get('生成来源（埋点enter_from）') if pd.notna(row.get('生成来源（埋点enter_from）')) else None
                
                print(f"\n处理行: prompt={row['prompt'][:30]}...")
                print(f"垫图: {reference_img}")
                
                if key not in grouped_data:
                    grouped_data[key] = {
                        'timestamp': row[time_column],
                        'prompt': row['prompt'],
                        'preview_url': [preview_url] if pd.notna(preview_url) else [],
                        'reference_img': reference_img,
                        'saved_images': [row['是否双端采纳(下载、复制、发布、后编辑、生视频、作为参考图、去画布)']] if pd.notna(preview_url) else [],
                        'enter_from': enter_from
                    }
                else:
                    if pd.notna(preview_url):
                        grouped_data[key]['preview_url'].append(preview_url)
                        grouped_data[key]['saved_images'].append(row['是否双端采纳(下载、复制、发布、后编辑、生视频、作为参考图、去画布)'])
            
            # 打印分组后的数据
            print("\n=== 分组后的数据 ===")
            for key, data in grouped_data.items():
                print(f"\n时间: {data['timestamp']}")
                print(f"Prompt: {data['prompt']}")
                print(f"垫图: {data['reference_img']}")
                print(f"预览图数量: {len(data['preview_url'])}")
            
            # 转换为DataFrame
            temp_df = pd.DataFrame([{
                'timestamp': v['timestamp'],
                'prompt': v['prompt'],
                'preview_url': v['preview_url'],
                'reference_img': v['reference_img'],
                'saved_images': v['saved_images'],
                'enter_from': v['enter_from']  # 确保包含生成来源
            } for v in grouped_data.values() 
            if v['preview_url']])  # 只保留有图片的数据
            
            if len(temp_df) == 0:
                return "没有找到有效的图片数据"
            
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
        /* 卡片基础样式 */
        .prompt-card {
            background: var(--background-fill-primary);
            border: 1px solid var(--border-color-primary);
            border-radius: 12px;
            padding: 20px;
            margin: 16px 0;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        
        /* 文本和背景样式 */
        .prompt-text {
            color: var(--body-text-color);
            font-size: 15px;
            line-height: 1.6;
            margin: 12px 0;
            padding: 12px;
            background: var(--background-fill-secondary);
            border-radius: 8px;
            border: 1px solid var(--border-color-primary);
        }
        
        /* 差异分析样式 */
        .diff-section {
            background: var(--background-fill-secondary);
            border-radius: 8px;
            padding: 15px;
            margin: 10px 0;
            border-left: 3px solid var(--primary-500);
        }
        
        .version-text {
            margin: 5px 0;
            color: var(--body-text-color);
            line-height: 1.6;
        }
        
        /* 差异文本颜色 */
        .word-removed {
            color: #ff7875;  /* 更亮的红色 */
            background-color: rgba(255, 77, 79, 0.15);
            padding: 0 4px;
            border-radius: 3px;
            font-weight: 500;
        }
        
        .word-added {
            color: #73d13d;  /* 更亮的绿色 */
            background-color: rgba(82, 196, 26, 0.15);
            padding: 0 4px;
            border-radius: 3px;
            font-weight: 500;
        }
        
        /* 变更摘要样式 */
        .change-summary {
            margin-top: 10px;
            padding-top: 10px;
            border-top: 1px solid var(--border-color-primary);
            font-size: 13px;
            line-height: 1.6;
        }
        
        .change-summary .word-removed {
            margin-right: 6px;
        }
        
        .change-summary .word-added {
            margin-left: 6px;
        }
        
        /* 标签样式 */
        .section-label {
            color: var(--body-text-color);
            font-size: 14px;
            font-weight: 500;
            margin: 15px 0 10px;
            opacity: 0.9;
        }
        
        /* 暗色模式特定样式 */
        @media (prefers-color-scheme: dark) {
            .prompt-card {
                background: var(--background-fill-primary);
                border-color: rgba(255, 255, 255, 0.1);
            }
            
            .prompt-text {
                background: rgba(255, 255, 255, 0.05);
                border-color: rgba(255, 255, 255, 0.1);
            }
            
            .diff-section {
                background: rgba(255, 255, 255, 0.05);
                border-left-color: var(--primary-400);
            }
            
            .word-removed {
                color: #ff9c9c;  /* 暗色模式下更亮的红色 */
                background-color: rgba(255, 77, 79, 0.2);
            }
            
            .word-added {
                color: #95eb6a;  /* 暗色模式下更亮的绿色 */
                background-color: rgba(82, 196, 26, 0.2);
            }
            
            .section-label {
                color: rgba(255, 255, 255, 0.9);
            }
            
            .image-error {
                color: rgba(255, 255, 255, 0.7);
                background: rgba(255, 255, 255, 0.1);
            }
            
            .saved-badge {
                background-color: var(--primary-400);
            }
        }
        
        /* 图片网格样式 */
        .image-grid {
            display: flex;
            gap: 16px;
            margin-top: 16px;
            flex-wrap: wrap;
        }
        
        .image-row {
            display: flex;
            gap: 16px;
            width: 100%;
        }
        
        .grid-image {
            position: relative;
            width: calc((100% - 48px) / 4);  /* 4列等宽，减去3个间隔的16px */
            aspect-ratio: 1;
            border-radius: 8px;
            overflow: hidden;
            background: var(--background-fill-secondary);
            border: 1px solid var(--border-color-primary);
        }
        
        .grid-image img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }
        
        .saved-badge {
            position: absolute;
            top: 8px;
            right: 8px;
            background-color: var(--primary-500);
            color: white;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            z-index: 1;
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }
        
        .image-error {
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--body-text-color-subdued);
            font-size: 13px;
            text-align: center;
            padding: 20px;
        }
        
        /* 布局样式 */
        .prompt-row {
            display: flex;
            gap: 20px;
            margin-bottom: 20px;
            align-items: flex-start;
        }
        
        .prompt-col {
            flex: 1;
            min-width: 0;
        }
        
        /* 垫图样式调整 */
        .reference-section {
            width: 120px;
            flex-shrink: 0;
            background: var(--background-fill-secondary);
            border-radius: 8px;
            padding: 10px;
            border: 1px solid var(--border-color-primary);
        }
        
        .reference-image {
            width: 100px;
            height: 100px;
            overflow: hidden;
            border-radius: 4px;
            background: var(--background-fill-primary);
            margin: 0 auto;
        }
        
        .reference-image img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }
        
        /* 头部样式 */
        .header-row {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 12px;
        }
        
        .timestamp {
            color: var(--body-text-color-subdued);
            font-size: 13px;
        }
        
        .enter-from {
            color: var(--body-text-color-subdued);
            font-size: 13px;
            padding: 2px 8px;
            background: var(--background-fill-secondary);
            border-radius: 4px;
            border: 1px solid var(--border-color-primary);
        }
        </style>
        """
    
    def generate_prompt_card(self, prompt, prev_prompt=None):
        try:
            # 添加调试日志
            print("\n=== 生成Prompt卡片 ===")
            print(f"时间戳: {prompt.get('timestamp')}")
            print(f"生成来源: {prompt.get('enter_from')}")
            
            # 获取生成来源信息
            enter_from = f'<span class="enter-from">{prompt.get("enter_from", "")}</span>' if prompt.get("enter_from") else ''
            
            html = f"""
            <div class="prompt-card">
                <div class="prompt-content">
                    <div class="header-row">
                        <div class="timestamp">{prompt['timestamp']}</div>
                        {enter_from}
                    </div>
                    
                    <div class="prompt-row">
                        <!-- 左侧 Prompt 部分 -->
                        <div class="prompt-col">
                            {self.generate_diff_section(prev_prompt, prompt) if prev_prompt else ''}
                            <div class="prompt-text">{prompt["prompt"]}</div>
                        </div>
                        
                        <!-- 右侧垫图部分 -->
                        {self.generate_reference_section(prompt) if prompt.get('reference_img') and prompt['reference_img'].strip() else ''}
                    </div>
                    
                    <!-- 生成结果展示 -->
                    <div class="section-label">生成结果：</div>
                    {self.generate_image_grid(prompt)}
                </div>
            </div>
            """
            return html
        except Exception as e:
            print(f"生成Prompt卡片时出错: {str(e)}")
            return ""

    def generate_diff_section(self, prev_prompt, curr_prompt):
        """生成差异分析部分的HTML"""
        diff = analyze_word_differences(prev_prompt['prompt'], curr_prompt['prompt'])
        if not (diff['prev_unique'] or diff['curr_unique']):
            return ''
        
        return f"""
        <div class="diff-section">
            <div class="version-text">原始版本: {diff["prev_html"]}</div>
            <div class="version-text current">当前版本: {diff["curr_html"]}</div>
            <div class="change-summary">
                {f'<span class="word-removed">删除: {", ".join(diff["prev_unique"])}</span>' if diff['prev_unique'] else ''}
                {' | ' if diff['prev_unique'] and diff['curr_unique'] else ''}
                {f'<span class="word-added">新增: {", ".join(diff["curr_unique"])}</span>' if diff['curr_unique'] else ''}
            </div>
        </div>
        """

    def generate_reference_section(self, prompt):
        """生成垫图部分的HTML"""
        if not (prompt.get('reference_img') and prompt['reference_img'].strip()):
            return ''
        
        return f"""
        <div class="reference-section">
            <div class="section-label">
                <span class="label-icon">📎</span> 参考图
            </div>
            <div class="reference-image">
                <img src="{prompt['reference_img']}" alt="参考图" 
                     onerror="this.parentElement.parentElement.style.display='none';">
            </div>
        </div>
        """

    def generate_image_grid(self, prompt):
        """生成图片网格的HTML，确保1*4排列"""
        preview_urls = prompt['preview_url'] if isinstance(prompt['preview_url'], list) else [prompt['preview_url']]
        saved_images = prompt.get('saved_images', [])
        if not isinstance(saved_images, list):
            saved_images = [saved_images] * len(preview_urls)
        
        grid_html = '<div class="image-grid">'
        
        # 每4张图片一行
        for i in range(0, len(preview_urls), 4):
            grid_html += '<div class="image-row">'
            row_urls = preview_urls[i:i+4]
            row_saved = saved_images[i:i+4]
            
            for url, is_saved in zip(row_urls, row_saved):
                if pd.notna(url) and url.strip():
                    grid_html += f"""
                    <div class="grid-image">
                        {f'<div class="saved-badge">已保存</div>' if is_saved else ''}
                        <img src="{url}" alt="预览图" 
                             onerror="this.parentElement.innerHTML='<div class=\'image-error\'>图片加载失败</div>';">
                    </div>
                    """
            
            grid_html += '</div>'
        
        grid_html += '</div>'
        return grid_html

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