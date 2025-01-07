import gradio as gr
import pandas as pd
from keyword_analysis import PromptAnalyzer, analyze_word_differences
from datetime import datetime
import os
import traceback
import logging
import jieba
import time

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
        # 使用每小时更新一次的版本号,而不是每秒
        version = int(time.time() / 3600)
        return f"""
        <style data-version="{version}">
        /* 确保样式作用域限定在gradio应用内 */
        .gradio-app-{version} {{
            /* 深色模式基础变量 */
            --background-base: #000000;          /* 最深的背景色（整体背景） */
            --background-primary: #1a1a1a;       /* 主要背景色（卡片背景） */
            --background-secondary: #2d2d2d;     /* 次要背景色（输入框、表格等） */
            --background-hover: #383838;         /* 悬停状态背景色 */
            --background-hover-light: #454545;   /* 滚动条悬停背景色 */
            --text-primary: #ffffff;             /* 主要文本颜色 */
            --text-secondary: #e0e0e0;          /* 次要文本颜色 */
            --text-disabled: #808080;           /* 禁用状态文本颜色 */
            --border-color: #404040;            /* 边框颜色 */
            --accent-color: #2c8fff;            /* 强调色（按钮、链接等） */
            --accent-hover: #1a7fff;            /* 强调色悬停状态 */
            --error-color: #ff4d4f;             /* 错误状态颜色 */
            --success-color: #52c41a;           /* 成功状态颜色 */
        }}

        /* 所有样式规则需要添加.gradio-app-{version}作为父选择器 */
        .gradio-app-{version} .gradio-container,
        .gradio-app-{version} .gradio-box,
        .gradio-app-{version} .contain {{
            background-color: var(--background-base) !important;
            color: var(--text-primary) !important;
        }}

        /* 其他样式规则同样添加作用域... */
        .gradio-app-{version} .gr-box,
        .gradio-app-{version} .gr-panel,
        .gradio-app-{version} .gr-block,
        .gradio-app-{version} .gr-form,
        .gradio-app-{version} .input-box,
        .gradio-app-{version} .output-box {{
            background-color: var(--background-primary) !important;
            border-color: var(--border-color) !important;
            color: var(--text-primary) !important;
        }}

        /* 修复滚动条样式 */
        .gradio-app-{version} ::-webkit-scrollbar {{
            width: 8px;
            height: 8px;
        }}

        .gradio-app-{version} ::-webkit-scrollbar-track {{
            background: var(--background-secondary);
        }}

        .gradio-app-{version} ::-webkit-scrollbar-thumb {{
            background: var(--border-color);
            border-radius: 4px;
        }}

        .gradio-app-{version} ::-webkit-scrollbar-thumb:hover {{
            background: var(--background-hover-light);  /* 使用新的hover变量 */
        }}

        /* 其他样式保持不变,但都需要添加.gradio-app-{version}作用域... */
        </style>
        """
    
    def generate_prompt_card(self, prompt, prev_prompt=None):
        try:
            # 添加调试日志
            print("\n=== 生成Prompt卡片 ===")
            print(f"时间戳: {prompt.get('timestamp')}")
            print(f"生成来源: {prompt.get('enter_from')}")
            
            # 获取生成来源信息
            enter_from = f'<span class="enter-from" style="color: var(--text-primary);">{prompt.get("enter_from", "")}</span>' if prompt.get("enter_from") else ''
            
            html = f"""
            <div class="prompt-card" style="background-color: var(--background-primary); color: var(--text-primary);">
                <div class="prompt-content">
                    <div class="header-row">
                        <div class="timestamp" style="color: var(--text-secondary);">{prompt['timestamp']}</div>
                        {enter_from}
                    </div>
                    
                    <div class="prompt-row">
                        <!-- 左侧 Prompt 部分 -->
                        <div class="prompt-col">
                            {self.generate_diff_section(prev_prompt, prompt) if prev_prompt else ''}
                            <div class="prompt-text" style="color: var(--text-primary);">{prompt["prompt"]}</div>
                        </div>
                        
                        <!-- 右侧垫图部分 -->
                        {self.generate_reference_section(prompt) if prompt.get('reference_img') and prompt['reference_img'].strip() else ''}
                    </div>
                    
                    <!-- 生成结果展示 -->
                    <div class="section-label" style="color: var(--text-primary);">生成结果：</div>
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
        <div class="diff-section" style="background-color: var(--background-secondary); color: var(--text-primary);">
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
        <div class="reference-section" style="background-color: var(--background-secondary); color: var(--text-primary);">
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
        # 处理预览图URL
        preview_urls = prompt['preview_url']
        if isinstance(preview_urls, str):
            # 如果是单个URL，尝试解析是否包含多个URL
            if ',' in preview_urls:
                preview_urls = [url.strip() for url in preview_urls.split(',')]
            else:
                preview_urls = [preview_urls]
        
        # 处理保存状态
        saved_images = prompt.get('saved_images', [False] * len(preview_urls))
        if not isinstance(saved_images, list):
            if ',' in str(saved_images):
                saved_images = [s.strip().lower() == 'true' for s in str(saved_images).split(',')]
            else:
                saved_images = [saved_images] * len(preview_urls)
        
        # 确保只处理4张图片
        preview_urls = preview_urls[:4]
        saved_images = saved_images[:4]
        
        grid_html = '<div class="image-grid">'
        
        # 生成图片容器
        for url, is_saved in zip(preview_urls, saved_images):
            if pd.notna(url) and url.strip():
                grid_html += f"""
                <div class="image-container">
                    <img src="{url.strip()}" alt="预览图" 
                         onerror="this.parentElement.innerHTML='<div class=\'image-error\'>图片加载失败</div>';">
                    {f'<div class="saved-badge">已保存</div>' if is_saved else ''}
                </div>
                """
        
        # 如果图片不足4张，添加空白占位
        for _ in range(4 - len(preview_urls)):
            grid_html += """
            <div class="image-container">
                <div class="image-error">暂无图片</div>
            </div>
            """
        
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

    def get_enter_from_text(self, enter_from):
        """转换来源代码为可读文本"""
        if not enter_from:  # 如果字段为空或不存在，显示 "-"
            return "-"
        
        source_map = {
            'default': '直接输入',
            'new_user_instruction': '新手引导',
            'modal_click': '模态切换',
            'remix': '做同款',
            'assets': '资产页',
            'generate_result': '重新编辑'
        }
        return source_map.get(enter_from, enter_from)

    def generate_cluster_view(self, prompts):
        """生成聚类详情视图"""
        try:
            html = self.get_style_html()
            html += """
            <style>
            .cluster-container {
                background: #1a1b1e;
                border-radius: 16px;
                padding: 20px;
                margin: 20px 0;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
            }
            
            .prompt-card {
                display: flex;
                gap: 20px;
                padding: 20px;
                margin: 15px 0;
                background: #2c2d30;
                border-radius: 12px;
                border: 1px solid #3a3b3e;
            }
            
            .prompt-main {
                flex: 3;
            }
            
            .prompt-side {
                flex: 1;
                min-width: 200px;
            }
            
            .image-grid {
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 12px;
                margin: 15px 0;
            }
            
            .image-container {
                position: relative;
                aspect-ratio: 1;
                border-radius: 8px;
                overflow: hidden;
                background: #1a1b1e;
            }
            
            .image-container img {
                width: 100%;
                height: 100%;
                object-fit: cover;
                transition: transform 0.3s ease;
            }
            
            .image-container:hover img {
                transform: scale(1.05);
            }
            
            .saved-badge {
                position: absolute;
                top: 8px;
                right: 8px;
                background: rgba(82, 196, 26, 0.9);
                color: white;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 12px;
                z-index: 1;
            }
            
            .prompt-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 15px;
                padding-bottom: 10px;
                border-bottom: 1px solid #3a3b3e;
                color: #e0e0e0;
            }
            
            .timestamp-group {
                display: flex;
                align-items: center;
                gap: 15px;
            }
            
            .timestamp {
                color: #e0e0e0;
            }
            
            .source-tag {
                background: #2a2b2e;
                color: #a0a0a0;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 13px;
                border: 1px solid #3a3b3e;
            }
            
            .image-count {
                background: rgba(82, 196, 26, 0.1);
                color: #52c41a;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 13px;
            }
            
            .diff-section {
                background: #1a1b1e;
                border-radius: 8px;
                padding: 15px;
                margin: 10px 0;
            }
            
            .diff-header {
                color: #a0a0a0;
                font-size: 14px;
                margin-bottom: 10px;
            }
            
            .diff-content {
                display: flex;
                flex-direction: column;
                gap: 10px;
            }
            
            .diff-text {
                line-height: 1.6;
                padding: 10px;
                background: #2c2d30;
                border-radius: 6px;
            }
            
            .word-removed {
                color: #ff4d4f;
                background-color: rgba(255, 77, 79, 0.1);
                padding: 2px 6px;
                border-radius: 4px;
                display: inline-block;
                margin: 0 2px;
            }
            
            .word-added {
                color: #52c41a;
                background-color: rgba(82, 196, 26, 0.1);
                padding: 2px 6px;
                border-radius: 4px;
                display: inline-block;
                margin: 0 2px;
            }
            
            .diff-summary {
                margin-top: 10px;
                padding-top: 10px;
                border-top: 1px solid #3a3b3e;
                display: flex;
                gap: 10px;
                flex-wrap: wrap;
            }
            
            .prompt-text {
                font-size: 15px;
                line-height: 1.6;
                padding: 15px;
                background: #1a1b1e;
                border-radius: 8px;
                color: #e0e0e0;
                margin: 10px 0;
            }
            </style>
            """
            
            # 按时间和Prompt分组
            groups = {}
            for prompt in prompts:
                key = (prompt['timestamp'], prompt['prompt'])
                if key not in groups:
                    groups[key] = {
                        'timestamp': prompt['timestamp'],
                        'prompt': prompt['prompt'],
                        'images': [],
                        'reference_img': prompt.get('reference_img', ''),
                        'enter_from': prompt.get('enter_from', None)  # 使用 get 方法，设置默认值为 None
                    }
                
                # 添加图片和保存状态
                url = prompt['preview_url']
                saved = prompt.get('saved_images', False)
                if url and pd.notna(url):
                    groups[key]['images'].append({
                        'url': url.strip(),
                        'saved': saved
                    })
            
            # 转换为列表并排序
            sorted_groups = sorted(groups.values(), key=lambda x: int(x['timestamp']))
            
            html += '<div class="cluster-details">'
            
            for i, group in enumerate(sorted_groups):
                timestamp = datetime.fromtimestamp(int(group['timestamp'])).strftime('%Y-%m-%d %H:%M:%S')
                source_text = self.get_enter_from_text(group.get('enter_from'))  # 使用 get 方法获取来源
                
                # 生成差异分析
                diff_html = ''
                if i > 0:
                    prev_group = sorted_groups[i-1]
                    diff = analyze_word_differences(prev_group['prompt'], group['prompt'])
                    if diff['prev_unique'] or diff['curr_unique']:
                        removed_words = diff['prev_unique']
                        added_words = diff['curr_unique']
                        
                        if removed_words or added_words:
                            diff_html = f"""
                            <div class="diff-section">
                                <div class="diff-header">与上一条Prompt的差异：</div>
                                <div class="diff-content">
                                    <div class="diff-text">{diff['curr_html']}</div>
                                    <div class="diff-summary">
                                        {f'<div class="word-removed">删除: {", ".join(removed_words)}</div>' if removed_words else ''}
                                        {f'<div class="word-added">新增: {", ".join(added_words)}</div>' if added_words else ''}
                                    </div>
                                </div>
                            </div>
                            """
                
                # 生成图片网格
                grid_html = '<div class="image-grid">'
                for img in group['images'][:4]:  # 限制最多4张图
                    grid_html += f"""
                    <div class="image-container">
                        <img src="{img['url']}" alt="预览图" 
                             onerror="this.parentElement.innerHTML='<div class=\'image-error\'>加载失败</div>';">
                        {f'<div class="saved-badge">已保存</div>' if img['saved'] else ''}
                    </div>
                    """
                grid_html += '</div>'
                
                html += f"""
                <div class="cluster-container">
                    <div class="prompt-header">
                        <div class="timestamp-group">
                            <div class="timestamp">{timestamp}</div>
                            <div class="source-tag">来源：{source_text}</div>
                        </div>
                        <div class="image-count">生成数量：{len(group['images'])}</div>
                    </div>
                    <div class="prompt-card">
                        <div class="prompt-main">
                            {diff_html}
                            <div class="prompt-text">{group['prompt']}</div>
                            <div class="preview-section">
                                {grid_html}
                            </div>
                        </div>
                        <div class="prompt-side">
                            {f'''
                            <div class="reference-image">
                                <div class="image-label">垫图</div>
                                <img src="{group['reference_img']}" alt="垫图"
                                     onerror="this.parentElement.style.display='none';">
                            </div>
                            ''' if group.get('reference_img') else ''}
                        </div>
                    </div>
                </div>
                """
            
            html += "</div>"
            return html
            
        except Exception as e:
            print(f"生成聚类视图失败: {str(e)}")
            traceback.print_exc()
            return f"生成视图失败: {str(e)}"

def create_ui():
    app = PromptAnalysisApp()
    version = int(time.time() / 3600)
    
    with gr.Blocks(
        theme=gr.themes.Base(),
        css=f".gradio-app {{ --app-version: {version}; }}"
    ) as interface:
        # 添加类名到根元素
        gr.HTML(f'<div class="gradio-app-{version}">')
        gr.HTML(app.get_style_html())
        
        gr.Markdown("# Prompt 分析工具")
        
        # 1. 上传和用户选择区域
        with gr.Row():
            file_input = gr.File(
                label="上传CSV文件",
                file_types=[".csv"]
            )
            user_dropdown = gr.Dropdown(  # 改用 Dropdown
                label="选择用户",
                interactive=True,
                choices=[]
            )
            analyze_btn = gr.Button("开始分析")
        
        # 2. 状态提示
        status_text = gr.Textbox(
            label="状态",
            interactive=False
        )
        
        # 3. 垂类表格（初始隐藏）
        category_table = gr.Dataframe(
            headers=["垂类ID", "垂类名称", "数据量"],
            label="垂类列表（点击行查看详情）",
            interactive=True,
            visible=False
        )
        
        # 4. 结果展示
        analysis_result = gr.HTML(label="分析结果")

        # 事件处理函数定义
        def handle_file_upload(file):
            try:
                if file is None:
                    return gr.update(choices=[], value=None), "请先上传CSV文件"
                    
                app.df = pd.read_csv(file.name)
                app.df['用户UID'] = app.df['用户UID'].astype(str)
                unique_users = app.df['用户UID'].unique().tolist()
                
                print(f"成功加载CSV文件，共有 {len(unique_users)} 个用户")
                return (
                    gr.update(
                        choices=unique_users,
                        value=unique_users[0] if unique_users else None
                    ),
                    "文件加载成功，请选择用户并点击分析"
                )
            except Exception as e:
                print(f"文件加载错误: {str(e)}")
                return gr.update(choices=[], value=None), f"文件加载失败: {str(e)}"

        def handle_analyze_click(user_id):
            try:
                if app.df is None:
                    return (
                        gr.update(value=None, visible=False),
                        "请先上传CSV文件"
                    )
                
                if not user_id:
                    return (
                        gr.update(value=None, visible=False),
                        "请选择用户"
                    )
                
                user_data = app.df[app.df['用户UID'].astype(str) == str(user_id)]
                if len(user_data) == 0:
                    return (
                        gr.update(value=None, visible=False),
                        f"未找到用户 {user_id} 的数据"
                    )
                
                # 打印调试信息
                print("DataFrame 列名:", user_data.columns.tolist())
                
                # 准备基础数据
                analysis_data = {
                    'prompt': user_data['prompt'],
                    'timestamp': user_data['生成时间(精确到秒)'],
                    'preview_url': user_data['生成结果预览图'],
                }
                
                # 可选字段处理
                if '是否双端采纳(下载、复制、发布、后编辑、生视频、作为参考图、去画布)' in user_data.columns:
                    analysis_data['saved_images'] = user_data['是否双端采纳(下载、复制、发布、后编辑、生视频、作为参考图、去画布)']
                
                # 来源字段处理 - 只在字段存在时添加
                if '生成来源（埋点enter_from）' in user_data.columns:
                    analysis_data['enter_from'] = user_data['生成来源（埋点enter_from）']
                    
                if '指令编辑垫图' in user_data.columns:
                    analysis_data['reference_img'] = user_data['指令编辑垫图']
                
                # 转换为DataFrame
                analysis_data = pd.DataFrame(analysis_data)
                
                # 分析数据并保存结果
                app.current_results = app.analyzer.analyze_user_prompts(analysis_data, str(user_id))
                if not app.current_results or 'clusters' not in app.current_results:
                    return (
                        gr.update(value=None, visible=False),
                        "分析结果为空"
                    )
                
                # 将聚类结果转换为表格格式
                category_rows = []
                for cluster_id, prompts in app.current_results['clusters'].items():
                    category_rows.append([
                        cluster_id,  # 直接使用数字作为聚类ID
                        f"聚类{cluster_id}",  # 聚类名称
                        len(prompts)  # 该聚类中的数据量
                    ])
                
                # 按数据量排序（可选）
                category_rows.sort(key=lambda x: x[2], reverse=True)
                
                if not category_rows:
                    return (
                        gr.update(value=None, visible=False),
                        f"用户 {user_id} 暂无数据"
                    )
                    
                return (
                    gr.update(value=category_rows, visible=True),
                    f"找到用户 {user_id} 的数据，请点击聚类查看详情"
                )
            except Exception as e:
                print(f"分析错误: {str(e)}")
                traceback.print_exc()
                return (
                    gr.update(value=None, visible=False),
                    f"分析失败: {str(e)}"
                )

        def handle_category_select(evt: gr.SelectData, user_id):
            try:
                if app.df is None:
                    return "请先上传CSV文件"
                
                if not user_id:
                    return "请选择用户"
                
                # 获取选中行的聚类ID
                try:
                    # 如果 evt.value 是列表
                    if isinstance(evt.value, (list, tuple)):
                        cluster_id = int(evt.value[0])
                    # 如果 evt.value 已经是整数
                    elif isinstance(evt.value, (int, float)):
                        cluster_id = int(evt.value)
                    # 如果 evt.value 是字符串
                    elif isinstance(evt.value, str):
                        # 尝试从字符串中提取数字
                        import re
                        match = re.search(r'\d+', evt.value)
                        if match:
                            cluster_id = int(match.group())
                        else:
                            raise ValueError(f"无法从 {evt.value} 中提取聚类ID")
                    else:
                        raise ValueError(f"无法处理的值类型: {type(evt.value)}")
                except Exception as e:
                    print(f"提取聚类ID时出错: {str(e)}")
                    print(f"evt.value: {evt.value}, 类型: {type(evt.value)}")
                    # 尝试使用 evt.index
                    cluster_id = evt.index
                
                print(f"查看用户 {user_id} 的聚类 {cluster_id} 详情")
                
                # 获取当前的聚类结果
                if not hasattr(app, 'current_results') or not app.current_results:
                    return "请先进行聚类分析"
                
                # 生成选中聚类的视图
                if cluster_id not in app.current_results['clusters']:
                    return f"未找到聚类 {cluster_id} 的数据"
                
                cluster_prompts = app.current_results['clusters'][cluster_id]
                return app.generate_cluster_view(cluster_prompts)
                
            except Exception as e:
                print(f"显示聚类详情时出错: {str(e)}")
                traceback.print_exc()
                return f"显示详情失败: {str(e)}"

        # 绑定事件
        file_input.change(
            fn=handle_file_upload,
            inputs=[file_input],
            outputs=[
                user_dropdown,
                status_text
            ]
        )
        
        analyze_btn.click(
            fn=handle_analyze_click,
            inputs=[user_dropdown],
            outputs=[
                category_table,
                status_text
            ]
        )
        
        category_table.select(
            fn=handle_category_select,
            inputs=[user_dropdown],
            outputs=[analysis_result]
        )

        # 关闭根div
        gr.HTML('</div>')

    return interface

if __name__ == "__main__":
    interface = create_ui()
    interface.launch(
        server_name="0.0.0.0",
        server_port=7860,
        show_error=True,
        ssl_verify=False,
    ) 