from sentence_transformers import SentenceTransformer
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from keybert import KeyBERT
import jieba
import jieba.analyse
import difflib
from tqdm import tqdm
import os
import json
from datetime import datetime
from visualization import plot_user_similarities

def analyze_and_save_user(uid, user_data, output_dir):
    """实时保存单个用户的分析结果"""
    user_dir = os.path.join(output_dir, f"user_{uid}")
    os.makedirs(user_dir, exist_ok=True)
    
    # 保存相似对分析
    pairs_file = os.path.join(user_dir, "similar_pairs.txt")
    with open(pairs_file, "w", encoding="utf-8") as f:
        f.write(f"用户 {uid} 的Prompt分析\n")
        f.write(f"总共有 {user_data['prompt_count']} 个Prompt\n")
        f.write(f"完全相同的prompt对数量: {user_data['identical_count']}\n\n")
        
        if user_data['identical_pairs']:
            f.write("\n完全相同的Prompt对:\n")
            f.write("="*50 + "\n")
            for idx, pair in enumerate(user_data['identical_pairs'], 1):
                f.write(f"\n重复 {idx}:\n")
                f.write(f"索引: {pair['index1']} vs {pair['index2']}\n")
                f.write(f"Prompt: {pair['prompt']}\n")
                f.write(f"预览链接1: {pair['preview_url1']}\n")
                f.write(f"预览链接2: {pair['preview_url2']}\n")
                f.write("-"*50 + "\n")
        
        # 相似对分析
        sorted_pairs = sorted(user_data["similar_pairs"], 
                            key=lambda x: x["similarity"], 
                            reverse=True)
        
        for idx, pair in enumerate(sorted_pairs, 1):
            f.write(f"\n分析 {idx}\n")
            f.write("="*50 + "\n")
            f.write(f"相似度: {pair['similarity']:.3f}\n")
            f.write(f"Prompt索引: {pair['prompt1_index']} vs {pair['prompt2_index']}\n\n")
            
            f.write(f"Prompt 1: {pair['prompt1']}\n")
            f.write(f"预览链接1: {pair['preview_url1']}\n\n")
            
            f.write(f"Prompt 2: {pair['prompt2']}\n")
            f.write(f"预览链接2: {pair['preview_url2']}\n\n")
            
            if pair["unique_to_1"] or pair["unique_to_2"]:
                f.write("\n差异分析:\n")
                if pair["unique_to_1"]:
                    f.write(f"Prompt 1 独有词: {', '.join(pair['unique_to_1'])}\n")
                if pair["unique_to_2"]:
                    f.write(f"Prompt 2 独有词: {', '.join(pair['unique_to_2'])}\n")
            f.write("\n" + "-"*50 + "\n")
    
    try:
        # 保存相似度矩阵图
        plot_file = os.path.join(user_dir, "similarity_matrix.png")
        plot_user_similarities({'temp_uid': user_data}, 'temp_uid', save_path=plot_file)
    except Exception as e:
        print(f"保存用户 {uid} 的相似度矩阵图时出错: {str(e)}")
    
    return user_dir

def analyze_prompts(csv_path, similarity_threshold=0.9, min_prompts=4, batch_size=32):
    # 创建输出目录
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"analysis_results_{timestamp}"
    os.makedirs(output_dir, exist_ok=True)
    
    # 读取CSV文件
    df = pd.read_csv(csv_path)
    print("CSV文件的列名:", df.columns.tolist())
    
    # 检查预览URL的列名
    preview_column = '生成结果预览图'  # 使用正确的列名
    if preview_column not in df.columns:
        print(f"警告: 未找到'{preview_column}'列，将使用空字符串代替")
        df[preview_column] = ''
    else:
        print(f"找到预览图列: '{preview_column}'")
    
    # 筛选2024年12月27日的数据
    df['p_date'] = pd.to_datetime(df['p_date'])
    df = df[df['p_date'].dt.strftime('%Y-%m-%d') == '2024-12-27']
    print(f"\n筛选出 {len(df)} 条2024年12月27日的数据")
    
    uid_column = '用户UID'
    model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
    jieba.initialize()
    
    results = {}
    # 筛选有足够prompt数量的用户
    valid_users = df.groupby(uid_column).filter(lambda x: len(x) >= min_prompts)[uid_column].unique()
    print(f"\n找到 {len(valid_users)} 个符合条件的用户（2024年12月27日至少有 {min_prompts} 个prompt）")
    
    for uid in tqdm(valid_users, desc="分析用户"):
        try:
            group = df[df[uid_column] == uid]
            prompts = group['prompt'].tolist()
            preview_urls = group[preview_column].tolist()  # 使用找到的列名
            
            print(f"\n\n{'='*80}")
            print(f"正在分析用户 {uid}")
            print(f"该用户共有 {len(prompts)} 个prompt")
            
            # 统计完全相同的prompt对
            identical_pairs = []
            similar_pairs = []
            
            # 计算embeddings
            embeddings = []
            for i in range(0, len(prompts), batch_size):
                batch = prompts[i:i + batch_size]
                batch_embeddings = model.encode(batch, show_progress_bar=False)
                embeddings.extend(batch_embeddings)
            embeddings = np.array(embeddings)
            
            similarity_matrix = cosine_similarity(embeddings)
            
            # 使用tqdm显示比较进度
            total_comparisons = len(prompts) * (len(prompts) - 1) // 2
            with tqdm(total=total_comparisons, desc=f"比较用户 {uid} 的prompts", leave=False) as pbar:
                for i in range(len(prompts)):
                    for j in range(i+1, len(prompts)):
                        if prompts[i] == prompts[j]:
                            identical_pairs.append({
                                'index1': i,
                                'index2': j,
                                'prompt': prompts[i],
                                'preview_url1': preview_urls[i],
                                'preview_url2': preview_urls[j]
                            })
                        else:
                            similarity = similarity_matrix[i][j]
                            if similarity >= similarity_threshold:
                                try:
                                    keywords1 = jieba.analyse.extract_tags(prompts[i], topK=10, withWeight=True)
                                    keywords2 = jieba.analyse.extract_tags(prompts[j], topK=10, withWeight=True)
                                    
                                    words1 = jieba.lcut(prompts[i])
                                    words2 = jieba.lcut(prompts[j])
                                    
                                    set1 = set(words1)
                                    set2 = set(words2)
                                    
                                    similar_pairs.append({
                                        'prompt1': prompts[i],
                                        'prompt2': prompts[j],
                                        'prompt1_index': i,
                                        'prompt2_index': j,
                                        'preview_url1': preview_urls[i],
                                        'preview_url2': preview_urls[j],
                                        'similarity': similarity,
                                        'keywords1': dict(keywords1),
                                        'keywords2': dict(keywords2),
                                        'unique_to_1': list(set1 - set2),
                                        'unique_to_2': list(set2 - set1),
                                        'common_words': list(set1 & set2),
                                        'detailed_diff': list(difflib.ndiff(words1, words2))
                                    })
                                except Exception as e:
                                    print(f"\n处理prompt对 {i}, {j} 时出错: {str(e)}")
                        pbar.update(1)
            
            if similar_pairs or identical_pairs:
                user_data = {
                    'similar_pairs': similar_pairs,
                    'identical_pairs': identical_pairs,
                    'identical_count': len(identical_pairs),
                    'similarity_matrix': similarity_matrix,
                    'prompts': prompts,
                    'prompt_count': len(prompts)
                }
                results[uid] = user_data
                
                # 打印分析结果
                print(f"\n用户 {uid} 分析完成:")
                print(f"完全相同的prompt对数量: {len(identical_pairs)}")
                print(f"相似的prompt对数量: {len(similar_pairs)}")
                
                # 立即保存该用户的分析结果
                user_dir = analyze_and_save_user(uid, user_data, output_dir)
                
                # 打印分析结果
                print(f"\n用户 {uid} 分析完成:")
                print(f"找到 {len(similar_pairs)} 对相似prompt")
                print(f"结果已保存到: {user_dir}")
                print("\n详细分析结果:")
                
                # 打印详细结果
                sorted_pairs = sorted(similar_pairs, key=lambda x: x['similarity'], reverse=True)
                for idx, pair in enumerate(sorted_pairs, 1):
                    print(f"\n分析 {idx}")
                    print("-" * 50)
                    print(f"相似度: {pair['similarity']:.3f}")
                    print(f"Prompt索引: {pair['prompt1_index']} vs {pair['prompt2_index']}")
                    print(f"\nPrompt 1: {pair['prompt1']}")
                    print(f"Prompt 2: {pair['prompt2']}")
                    
                    if pair['unique_to_1'] or pair['unique_to_2']:
                        print("\n主要差异:")
                        if pair['unique_to_1']:
                            print(f"Prompt 1 独有词: {', '.join(pair['unique_to_1'])}")
                        if pair['unique_to_2']:
                            print(f"Prompt 2 独有词: {', '.join(pair['unique_to_2'])}")
                    print(f"\n{'='*80}\n")
                
            else:
                print(f"\n用户 {uid} 没有找到相似度大于 {similarity_threshold} 的prompt对")
                
        except Exception as e:
            print(f"\n处理用户 {uid} 时出错: {str(e)}")
            continue
    
    # 保存总体统计信息
    summary = {
        "total_users": len(results),
        "analysis_time": timestamp,
        "user_statistics": {
            uid: {
                "total_prompts": data["prompt_count"],
                "similar_pairs": len(data["similar_pairs"])
            } for uid, data in results.items()
        }
    }
    
    summary_file = os.path.join(output_dir, "analysis_summary.json")
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    print(f"\n分析完成，找到 {len(results)} 个有相似prompt的用户")
    print(f"所有结果已保存到: {output_dir}")
    return results, output_dir

def print_analysis_results(results):
    for uid, user_data in results.items():
        print(f"\n用户 {uid} 的相似Prompt分析:")
        print(f"该用户共有 {user_data['prompt_count']} 个Prompt")
        
        # 按相似度降序排列
        sorted_pairs = sorted(user_data['similar_pairs'], 
                            key=lambda x: x['similarity'], 
                            reverse=True)
        
        for pair in sorted_pairs:
            print("\n" + "="*50)
            print(f"相似度: {pair['similarity']:.3f}")
            print(f"Prompt索引: {pair['prompt1_index']} vs {pair['prompt2_index']}")
            
            print(f"\nPrompt 1: {pair['prompt1']}")
            print("关键词 1 (带权重):")
            for word, weight in pair['keywords1'].items():
                print(f"  {word}: {weight:.3f}")
            
            print(f"\nPrompt 2: {pair['prompt2']}")
            print("关键词 2 (带权重):")
            for word, weight in pair['keywords2'].items():
                print(f"  {word}: {weight:.3f}")
            
            if pair['unique_to_1'] or pair['unique_to_2']:
                print("\n差异分析:")
                if pair['unique_to_1']:
                    print(f"Prompt 1 独有词: {', '.join(pair['unique_to_1'])}")
                if pair['unique_to_2']:
                    print(f"Prompt 2 独有词: {', '.join(pair['unique_to_2'])}")
            
            print("\n详细差异:")
            for d in pair['detailed_diff']:
                if d[0] != ' ':  # 只显示有变化的部分
                    print(d)

def save_analysis_results(results, output_dir="analysis_results"):
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 保存总体统计信息
    summary = {
        "total_users": len(results),
        "analysis_time": timestamp,
        "user_statistics": {}
    }
    
    # 为每个用户创建详细报告
    for uid, user_data in results.items():
        user_dir = os.path.join(output_dir, f"user_{uid}")
        os.makedirs(user_dir, exist_ok=True)
        
        # 用户统计信息
        user_stats = {
            "total_prompts": user_data["prompt_count"],
            "similar_pairs": len(user_data["similar_pairs"]),
            "prompts": user_data["prompts"],
            "similarity_matrix": user_data["similarity_matrix"].tolist()
        }
        summary["user_statistics"][uid] = user_stats
        
        # 保存相似对分析
        pairs_file = os.path.join(user_dir, "similar_pairs.txt")
        with open(pairs_file, "w", encoding="utf-8") as f:
            f.write(f"用户 {uid} 的Prompt分析\n")
            f.write(f"总共有 {user_data['prompt_count']} 个Prompt\n")
            f.write(f"完全相同的prompt对数量: {user_data['identical_count']}\n\n")
            
            if user_data['identical_pairs']:
                f.write("\n完全相同的Prompt对:\n")
                f.write("="*50 + "\n")
                for idx, pair in enumerate(user_data['identical_pairs'], 1):
                    f.write(f"\n重复 {idx}:\n")
                    f.write(f"索引: {pair['index1']} vs {pair['index2']}\n")
                    f.write(f"Prompt: {pair['prompt']}\n")
                    f.write(f"预览链接1: {pair['preview_url1']}\n")
                    f.write(f"预览链接2: {pair['preview_url2']}\n")
                    f.write("-"*50 + "\n")
            
            # 按相似度降序排列
            sorted_pairs = sorted(user_data["similar_pairs"], 
                                key=lambda x: x["similarity"], 
                                reverse=True)
            
            for idx, pair in enumerate(sorted_pairs, 1):
                f.write(f"\n分析 {idx}\n")
                f.write("="*50 + "\n")
                f.write(f"相似度: {pair['similarity']:.3f}\n")
                f.write(f"Prompt索引: {pair['prompt1_index']} vs {pair['prompt2_index']}\n\n")
                
                f.write(f"Prompt 1: {pair['prompt1']}\n")
                f.write(f"预览链接1: {pair['preview_url1']}\n\n")
                
                f.write(f"\nPrompt 2: {pair['prompt2']}\n")
                f.write(f"预览链接2: {pair['preview_url2']}\n\n")
                
                if pair["unique_to_1"] or pair["unique_to_2"]:
                    f.write("\n差异分析:\n")
                    if pair["unique_to_1"]:
                        f.write(f"Prompt 1 独有词: {', '.join(pair['unique_to_1'])}\n")
                    if pair["unique_to_2"]:
                        f.write(f"Prompt 2 独有词: {', '.join(pair['unique_to_2'])}\n")
                
                f.write("\n详细差异:\n")
                for d in pair["detailed_diff"]:
                    if d[0] != " ":
                        f.write(f"{d}\n")
                f.write("\n" + "-"*50 + "\n")
        
        # 保存相似度矩阵图
        plot_file = os.path.join(user_dir, "similarity_matrix.png")
        plot_user_similarities(results, uid, save_path=plot_file)
    
    # 保存总体统计信息
    summary_file = os.path.join(output_dir, f"analysis_summary_{timestamp}.json")
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    return output_dir
