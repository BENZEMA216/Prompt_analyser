from keybert import KeyBERT
from sentence_transformers import SentenceTransformer
from sklearn.cluster import DBSCAN
import numpy as np
import pandas as pd
from difflib import SequenceMatcher
import json
from datetime import datetime
import os
import warnings
import os
import jieba

# 设置环境变量以避免tokenizers警告
os.environ["TOKENIZERS_PARALLELISM"] = "false"

class PromptAnalyzer:
    def __init__(self):
        # 禁用警告
        warnings.filterwarnings('ignore')
        try:
            self.kw_model = KeyBERT()
            self.st_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        except Exception as e:
            print(f"初始化模型时出错: {str(e)}")
            raise
        
    def extract_keywords(self, prompt):
        """提取关键词及其权重"""
        keywords = self.kw_model.extract_keywords(prompt)
        return keywords
    
    def cluster_prompts(self, prompts, similarity_threshold=0.9):
        """基于相似度阈值对prompts进行聚类"""
        try:
            print(f"开始对 {len(prompts)} 条prompt进行聚类，相似度阈值: {similarity_threshold}")
            
            # 计算embeddings
            embeddings = self.st_model.encode(prompts)
            print("Embeddings计算完成")
            
            # 计算相似度矩阵
            from sklearn.metrics.pairwise import cosine_similarity
            similarity_matrix = cosine_similarity(embeddings)
            
            # 基于相似度阈值进行聚类
            clusters = {}
            used_indices = set()
            
            for i in range(len(prompts)):
                if i in used_indices:
                    continue
                    
                # 找到与当前prompt相似度高于阈值的所有prompts
                similar_indices = set([i])
                for j in range(len(prompts)):
                    if j != i and j not in used_indices:
                        similarity = similarity_matrix[i][j]
                        if similarity >= similarity_threshold:
                            print(f"找到相似Prompt: {i} 和 {j} 的相似度为 {similarity:.3f}")
                            similar_indices.add(j)
                
                # 如果找到相似的prompts，创建新的聚类
                if similar_indices:
                    cluster_id = len(clusters)
                    clusters[cluster_id] = list(similar_indices)
                    used_indices.update(similar_indices)
                    print(f"创建聚类 {cluster_id}，包含 {len(similar_indices)} 条Prompt")
            
            print(f"聚类完成，共有 {len(clusters)} 个聚类")
            return clusters
            
        except Exception as e:
            print(f"聚类过程出错: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def track_prompt_changes(self, prompts, timestamps):
        """追踪prompt的修改历史"""
        changes = []
        for i in range(1, len(prompts)):
            prev_prompt = prompts[i-1]
            curr_prompt = prompts[i]
            
            # 计算差异
            s = SequenceMatcher(None, prev_prompt, curr_prompt)
            diff = []
            for tag, i1, i2, j1, j2 in s.get_opcodes():
                if tag == 'replace':
                    diff.append({
                        'type': 'replace',
                        'old': prev_prompt[i1:i2],
                        'new': curr_prompt[j1:j2]
                    })
                elif tag == 'delete':
                    diff.append({
                        'type': 'delete',
                        'content': prev_prompt[i1:i2]
                    })
                elif tag == 'insert':
                    diff.append({
                        'type': 'insert',
                        'content': curr_prompt[j1:j2]
                    })
            
            if diff:
                changes.append({
                    'timestamp': timestamps[i],
                    'prev_prompt': prev_prompt,
                    'curr_prompt': curr_prompt,
                    'changes': diff
                })
                
        return changes

    def analyze_user_prompts(self, df, user_id):
        """分析用户的prompts"""
        try:
            print(f"开始分析用户 {user_id} 的 {len(df)} 条prompt")
            print(f"DataFrame 列名: {df.columns.tolist()}")
            
            # 验证必要的列
            required_columns = ['prompt', 'timestamp', 'preview_url']
            if not all(col in df.columns for col in required_columns):
                missing = [col for col in required_columns if col not in df.columns]
                print(f"缺少必要的列: {missing}")
                return None
            
            # 获取有效的prompts
            valid_prompts = df['prompt'].tolist()
            if not valid_prompts:
                print("没有有效的prompts")
                return None
            
            # 执行聚类
            cluster_indices = self.cluster_prompts(valid_prompts)
            if cluster_indices is None:
                return None
            
            # 构建聚类结果
            clusters = {}
            for cluster_id, indices in cluster_indices.items():
                clusters[cluster_id] = []
                for idx in indices:
                    prompt_data = df.iloc[idx]
                    cluster_item = {
                        'prompt': prompt_data['prompt'],
                        'timestamp': prompt_data['timestamp'],
                        'preview_url': prompt_data['preview_url'],
                        'saved_images': prompt_data.get('saved_images', False),
                    }
                    
                    # 只在字段存在时添加
                    if 'enter_from' in prompt_data:
                        cluster_item['enter_from'] = prompt_data['enter_from']
                        
                    if 'reference_img' in prompt_data and pd.notna(prompt_data['reference_img']):
                        cluster_item['reference_img'] = prompt_data['reference_img']
                    
                    clusters[cluster_id].append(cluster_item)
            
            return {
                'clusters': clusters,
                'changes': self.track_prompt_changes(
                    df['prompt'].tolist(),
                    df['timestamp'].tolist()
                )
            }
        except Exception as e:
            print(f"分析用户prompts时出错: {str(e)}")
            traceback.print_exc()
            return None

    def check_models(self):
        """检查模型是否正确加载"""
        return self.kw_model is not None and self.st_model is not None

def generate_html_report(analysis_results, output_dir):
    """生成可视化HTML报告"""
    os.makedirs(output_dir, exist_ok=True)
    
    # 生成主页面
    index_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Prompt分析报告</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                background: #f5f5f5;
                margin: 0;
                padding: 20px;
            }
            
            .prompt {
                background: white;
                border-radius: 12px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                overflow: hidden;
                margin: 20px 0;
                transition: transform 0.2s;
            }
            
            .prompt:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            }
            
            .prompt-content {
                padding: 20px;
                flex: 3;
            }
            
            .prompt-image {
                flex: 1;
                min-width: 200px;
                position: relative;
                overflow: hidden;
                background: #f8f9fa;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            
            .preview-image {
                width: 100%;
                height: 100%;
                object-fit: cover;
                transition: transform 0.3s;
            }
            
            .prompt:hover .preview-image {
                transform: scale(1.05);
            }
            
            .timestamp {
                color: #666;
                font-size: 0.9em;
                margin-bottom: 12px;
            }
            
            .prompt-text {
                font-size: 1.1em;
                margin: 12px 0;
                line-height: 1.6;
                color: #1a1a1a;
            }
            
            .diff-view {
                margin: 15px 0;
                padding: 15px;
                background: #f8f9fa;
                border-radius: 8px;
                border-left: 4px solid #e0e0e0;
            }
            
            .word-removed {
                background-color: #ffeef0;
                color: #b31d28;
                padding: 2px 4px;
                border-radius: 3px;
                margin: 0 2px;
            }
            
            .word-added {
                background-color: #e6ffed;
                color: #22863a;
                padding: 2px 4px;
                border-radius: 3px;
                margin: 0 2px;
            }
            
            .word-diff-summary {
                font-size: 0.9em;
                padding: 10px;
                background: #fff;
                border-radius: 6px;
                margin: 10px 0;
                border: 1px solid #e1e4e8;
            }
            
            .prompts-container {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(700px, 1fr));
                gap: 25px;
                max-width: 1600px;
                margin: 0 auto;
            }
            
            .nav-buttons {
                position: sticky;
                top: 0;
                background: rgba(255,255,255,0.95);
                padding: 15px;
                border-radius: 8px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                margin-bottom: 25px;
                backdrop-filter: blur(10px);
                z-index: 100;
            }
            
            .nav-button {
                display: inline-block;
                padding: 8px 16px;
                margin: 0 8px;
                background: #fff;
                border: 1px solid #e1e4e8;
                border-radius: 6px;
                color: #24292e;
                text-decoration: none;
                font-size: 0.9em;
                transition: all 0.2s;
            }
            
            .nav-button:hover {
                background: #f6f8fa;
                border-color: #959da5;
            }
            
            .cluster-info {
                display: inline-block;
                padding: 2px 6px;
                background: #f1f8ff;
                border-radius: 12px;
                font-size: 0.8em;
                color: #0366d6;
                margin-left: 6px;
            }
            
            h2, h3, h4 {
                color: #24292e;
                margin: 30px 0 20px;
            }
            
            .cluster {
                background: white;
                border-radius: 12px;
                padding: 20px;
                margin: 25px 0;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }
        </style>
    </head>
    <body>
        <h1>Prompt分析报告</h1>
        <div id="user-list">
    """
    
    # 为每个用户生成单独的页面
    for user_id, results in analysis_results.items():
        # 对聚类按照包含的prompt数量排序
        sorted_clusters = sorted(
            results['clusters'].items(), 
            key=lambda x: len(x[1]), 
            reverse=True
        )
        
        user_html = f"""
        <div class="user-report">
            <h2>用户 {user_id} 的Prompt分析</h2>
            
            <!-- 添加导航按钮 -->
            <div class="nav-buttons">
                <a href="#timeline" class="nav-button">时间轴视图</a>
                <a href="#clusters" class="nav-button">聚类视图</a>
                {' '.join(f'<a href="#cluster_{cid}" class="nav-button">聚类 {cid} <span class="cluster-info">({len(prompts)} 条)</span></a>' 
                         for cid, prompts in sorted_clusters)}
            </div>
            
            <h3 id="timeline">按时间顺序的Prompt变化</h3>
        """
        
        # 获取按时间排序的prompts
        all_prompts = []
        for cluster in results['clusters'].values():
            all_prompts.extend(cluster)
        all_prompts.sort(key=lambda x: x['timestamp'])
        
        # 显示按时间顺序的prompts及其差异
        user_html += '<div class="prompts-container">'
        for i, curr_prompt in enumerate(all_prompts):
            # 计算差异（如果不是第一个prompt）
            diff_html = ''
            if i > 0:
                prev_prompt = all_prompts[i-1]
                word_diff = analyze_word_differences(prev_prompt['prompt'], curr_prompt['prompt'])
                
                diff_html = '<div class="diff-view"><b>与上一条Prompt的差异：</b><br>'
                if prev_prompt['prompt'] == curr_prompt['prompt']:
                    diff_html += '<div class="diff-line">与上一条Prompt完全相同</div>'
                else:
                    if word_diff['prev_unique'] or word_diff['curr_unique']:
                        diff_html += '<div class="word-diff-summary">'
                        if word_diff['prev_unique']:
                            diff_html += f'<div>删除的词语: {", ".join(word_diff["prev_unique"])}</div>'
                        if word_diff['curr_unique']:
                            diff_html += f'<div>新增的词语: {", ".join(word_diff["curr_unique"])}</div>'
                        diff_html += '</div>'
                    
                    diff_html += f'<div class="diff-line">修改前: {word_diff["prev_html"]}</div>'
                    diff_html += f'<div class="diff-line">修改后: {word_diff["curr_html"]}</div>'
                diff_html += '</div>'

            # 使用 f-string 确保变量被正确替换
            user_html += f"""
            <div class="prompt">
                <div class="prompt-content">
                    <div class="timestamp">{curr_prompt['timestamp']}</div>
                    <div class="prompt-text">{curr_prompt['prompt']}</div>
                    {diff_html}
                </div>
                <div class="prompt-image">
                    <img class="preview-image" src="{curr_prompt['preview_url']}" alt="预览图">
                </div>
            </div>
            """
        
        user_html += "</div>"
        
        # 修改聚类视图部分，使用排序后的聚类
        user_html += '<h3 id="clusters">Prompt聚类（按数量排序）</h3>'
        for cluster_id, prompts in sorted_clusters:
            user_html += f"""
            <div class="cluster" id="cluster_{cluster_id}">
                <h4>聚类 {cluster_id} ({len(prompts)} 条Prompt)</h4>
                <div class="prompts-container">
            """
            
            for p in prompts:
                user_html += f"""
                <div class="prompt">
                    <div class="prompt-content">
                        <div class="timestamp">{p['timestamp']}</div>
                        <div class="prompt-text">{p['prompt']}</div>
                    </div>
                    <div class="prompt-image">
                        <img class="preview-image" src="{p['preview_url']}" alt="预览图">
                    </div>
                </div>
                """
            user_html += "</div></div>"
        
        # 添加返回顶部按钮
        user_html += """
            <div style="position: fixed; bottom: 20px; right: 20px;">
                <a href="#" class="nav-button" style="background: #333; color: white;">返回顶部</a>
            </div>
        """
        
        user_html += "</div>"
        
        # 保存用户页面
        user_file = os.path.join(output_dir, f'user_{user_id}.html')
        with open(user_file, 'w', encoding='utf-8') as f:
            f.write(user_html)
        
        # 添加到主页面
        index_html += f'<p><a href="user_{user_id}.html">用户 {user_id} 的分析报告</a></p>'
    
    index_html += """
        </div>
    </body>
    </html>
    """
    
    # 保存主页面
    with open(os.path.join(output_dir, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(index_html)

def compute_prompt_diff(prev_prompt, curr_prompt):
    """计算两个prompt之间的具体差异"""
    s = SequenceMatcher(None, prev_prompt, curr_prompt)
    
    # 初始化差异信息
    diff_info = {
        'is_identical': prev_prompt == curr_prompt,
        'changes': [],
        'diff_text': {
            'prev': '',
            'curr': ''
        }
    }
    
    if diff_info['is_identical']:
        return diff_info
        
    # 计算具体差异
    last_prev_pos = 0
    last_curr_pos = 0
    
    for tag, i1, i2, j1, j2 in s.get_opcodes():
        # 处理相同部分
        if tag == 'equal':
            diff_info['diff_text']['prev'] += prev_prompt[i1:i2]
            diff_info['diff_text']['curr'] += curr_prompt[j1:j2]
            
        # 处理删除
        elif tag == 'delete':
            deleted_text = prev_prompt[i1:i2]
            diff_info['changes'].append({
                'type': 'delete',
                'text': deleted_text,
                'position': i1
            })
            diff_info['diff_text']['prev'] += f'[DELETE]{deleted_text}[/DELETE]'
            
        # 处理插入
        elif tag == 'insert':
            inserted_text = curr_prompt[j1:j2]
            diff_info['changes'].append({
                'type': 'insert',
                'text': inserted_text,
                'position': j1
            })
            diff_info['diff_text']['curr'] += f'[INSERT]{inserted_text}[/INSERT]'
            
        # 处理替换
        elif tag == 'replace':
            old_text = prev_prompt[i1:i2]
            new_text = curr_prompt[j1:j2]
            diff_info['changes'].append({
                'type': 'replace',
                'old_text': old_text,
                'new_text': new_text,
                'position': i1
            })
            diff_info['diff_text']['prev'] += f'[DELETE]{old_text}[/DELETE]'
            diff_info['diff_text']['curr'] += f'[INSERT]{new_text}[/INSERT]'
    
    return diff_info

def analyze_word_differences(prev_prompt, curr_prompt):
    """分析两个prompt之间的词语差异"""
    # 分词
    prev_words = set(jieba.cut(prev_prompt))
    curr_words = set(jieba.cut(curr_prompt))
    
    # 找出独特的词语
    prev_unique = prev_words - curr_words  # 在前一个prompt中独有的词
    curr_unique = curr_words - prev_words  # 在当前prompt中独有的词
    
    # 构建带标记的HTML文本
    curr_html = ''
    for word in jieba.cut(curr_prompt):
        if word in curr_unique:
            curr_html += f'<span class="word-added">{word}</span>'
        elif word in prev_unique:
            curr_html += f'<span class="word-removed">{word}</span>'
        else:
            curr_html += word
    
    return {
        'curr_html': curr_html,
        'prev_unique': list(prev_unique),
        'curr_unique': list(curr_unique)
    }

def main(csv_path, target_user_id="2012521685064170"):
    try:
        # 读取CSV
        print("正在读取CSV文件...")
        df = pd.read_csv(csv_path)
        print(f"CSV文件中共有 {len(df)} 条数据")
        
        # 检查用户ID是否存在
        df['用户UID'] = df['用户UID'].astype(str)  # 将所有用户ID转换为字符串
        unique_users = df['用户UID'].unique()
        print(f"CSV文件中共有 {len(unique_users)} 个用户")
        
        # 打印一些用户ID示例
        print("用户ID示例:", unique_users[:5])
        print("目标用户ID类型:", type(target_user_id))
        print("目标用户ID:", target_user_id)
        
        if str(target_user_id) not in unique_users:
            print(f"未找到用户 {target_user_id}")
            print("可用的用户ID:", unique_users[:5], "...")
            return
        
        # 初始化分析器
        print("正在初始化分析器...")
        analyzer = PromptAnalyzer()
        
        # 只分析目标用户
        results = {}
        print(f"\n开始分析用户 {target_user_id} 的prompt...")
        
        try:
            # 确保在分析时也使用字符串类型的用户ID
            user_results = analyzer.analyze_user_prompts(df, str(target_user_id))
            if user_results is not None:
                results[target_user_id] = user_results
                print(f"用户分析完成")
                
                # 生成报告
                output_dir = f'prompt_analysis_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
                print(f"\n正在生成分析报告...")
                generate_html_report(results, output_dir)
                print(f"分析报告已生成到: {output_dir}")
            else:
                print("用户分析失败，跳过报告生成")
                
        except Exception as e:
            print(f"分析用户时出错: {str(e)}")
            raise
        
    except Exception as e:
        print(f"发生错误: {str(e)}")
        raise

if __name__ == "__main__":
    csv_path = "path/to/your/csv"  # 替换为实际的CSV路径
    main(csv_path) 