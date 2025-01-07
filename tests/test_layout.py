import os
import sys

# 添加项目根目录到 Python 路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from app import PromptAnalysisApp

def create_mock_data():
    """创建模拟数据"""
    # 创建基础数据
    now = datetime.now()
    base_timestamp = int(now.timestamp())
    
    # 创建测试数据
    data = []
    
    # 第一组：4张相同的图片
    prompt1 = "Design a minimalist Chinese style logo with coffee cup"
    for i in range(4):
        data.append({
            '用户UID': '12345',
            'prompt': prompt1,
            '生成时间(精确到秒)': base_timestamp,
            '生成结果预览图': f'https://example.com/group1_image_{i}.jpg',
            '是否双端采纳(下载、复制、发布、后编辑、生视频、作为参考图、去画布)': 1
        })
    
    # 第二组：3张相同的图片
    prompt2 = "Create a traditional Chinese painting style tea cup"
    for i in range(3):
        data.append({
            '用户UID': '12345',
            'prompt': prompt2,
            '生成时间(精确到秒)': base_timestamp + 3600,  # 1小时后
            '生成结果预览图': f'https://example.com/group2_image_{i}.jpg',
            '是否双端采纳(下载、复制、发布、后编辑、生视频、作为参考图、去画布)': 0
        })
    
    # 第三组：单张图片
    data.append({
        '用户UID': '12345',
        'prompt': "Single minimalist logo design",
        '生成时间(精确到秒)': base_timestamp + 7200,  # 2小时后
        '生成结果预览图': 'https://example.com/single_image.jpg',
        '是否双端采纳(下载、复制、发布、后编辑、生视频、作为参考图、去画布)': 1
    })
    
    # 创建DataFrame
    df = pd.DataFrame(data)
    print("\n=== 测试数据统计 ===")
    print(f"总记录数: {len(df)}")
    print(f"唯一Prompt数: {df['prompt'].nunique()}")
    print(f"时间范围: {datetime.fromtimestamp(df['生成时间(精确到秒)'].min())} - {datetime.fromtimestamp(df['生成时间(精确到秒)'].max())}")
    
    return df

def test_layout():
    """测试布局渲染"""
    # 创建应用实例
    app = PromptAnalysisApp()
    
    # 加载模拟数据
    print("\n=== 加载测试数据 ===")
    mock_df = create_mock_data()
    app.df = mock_df
    
    # 测试分析
    print("\n=== 开始分析 ===")
    results = app.analyze_user('12345')
    
    # 生成HTML并保存到文件
    if isinstance(results, dict) and 'clusters' in results:
        print("\n=== 生成HTML ===")
        html = app.generate_analysis_view(results)
        with open('test_layout.html', 'w', encoding='utf-8') as f:
            f.write("""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <title>Layout Test</title>
                <style>
                    body { 
                        max-width: 1200px;
                        margin: 0 auto;
                        padding: 20px;
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    }
                </style>
                        margin: 0 auto;
                        padding: 20px;
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    }
                </style>
            </head>
            <body>
            """)
            f.write(html)
            f.write("</body></html>")
        print("测试HTML已生成到 test_layout.html")
    else:
        print("分析失败:", results)

if __name__ == "__main__":
    test_layout() 