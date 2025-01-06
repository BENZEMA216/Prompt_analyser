import os
import sys
import pandas as pd

# 添加项目根目录到 Python 路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import PromptAnalysisApp

def test_data_loading():
    """测试数据加载和垫图处理"""
    # 创建应用实例
    app = PromptAnalysisApp()
    
    # 读取测试文件
    test_file = "test.csv"
    encodings = ['utf-8', 'GBK', 'GB18030', 'GB2312', 'BIG5', 'cp936']
    
    df = None
    for encoding in encodings:
        try:
            print(f"\n尝试使用 {encoding} 编码读取文件...")
            df = pd.read_csv(test_file, encoding=encoding)
            print(f"成功使用 {encoding} 编码读取文件")
            break
        except Exception as e:
            print(f"{encoding} 编码读取失败: {str(e)}")
            continue
    
    if df is None:
        print("所有编码尝试均失败")
        return
    
    # 打印列名
    print("\n=== CSV文件列名 ===")
    print(df.columns.tolist())
    
    # 检查垫图列
    print("\n=== 垫图数据检查 ===")
    if '指令编辑垫图' in df.columns:
        print("找到垫图列")
        # 统计非空垫图数量
        non_empty = df['指令编辑垫图'].notna().sum()
        print(f"非空垫图数量: {non_empty}")
        
        # 打印详细的垫图信息
        print("\n垫图详细信息:")
        has_ref_img = df[df['指令编辑垫图'].notna()]
        for idx, row in has_ref_img.head().iterrows():
            print(f"\n行号: {idx}")
            print(f"用户ID: {row['用户UID']}")
            print(f"Prompt: {row['prompt']}")
            print(f"垫图URL: {row['指令编辑垫图']}")
    else:
        print("未找到垫图列")
    
    # 加载数据到应用
    app.df = df
    
    # 获取一个用户ID进行测试
    test_user = df['用户UID'].iloc[0]
    print(f"\n=== 测试用户 {test_user} ===")
    
    # 分析用户数据
    results = app.analyze_user(test_user)
    
    # 检查结果中的垫图数据
    if isinstance(results, dict) and 'clusters' in results:
        print("\n=== 聚类结果中的垫图检查 ===")
        found_ref_imgs = False
        for cluster_id, prompts in results['clusters'].items():
            print(f"\n检查聚类 {cluster_id}:")
            for i, p in enumerate(prompts):
                print(f"  Prompt {i}: {p['prompt'][:50]}...")
                if 'reference_img' in p:
                    found_ref_imgs = True
                    print(f"  找到垫图: {p['reference_img']}")
        if not found_ref_imgs:
            print("未在聚类结果中找到任何垫图")
    else:
        print("分析失败:", results)

if __name__ == "__main__":
    test_data_loading() 