from prompt_analysis import analyze_prompts, print_analysis_results, save_analysis_results
from visualization import plot_user_similarities
from keyword_analysis import main as analyze_prompts_changes
import os
import pandas as pd

# 设置环境变量
os.environ["TOKENIZERS_PARALLELISM"] = "false"

def main():
    # 文件路径
    csv_path = "/Users/bytedance/Desktop/优质创作者分析_副本/Good User Case Jan 3 2025-1.csv"
    
    # 读取CSV查看可用的用户ID
    df = pd.read_csv(csv_path)
    print("可用的用户ID示例:")
    print(df['用户UID'].unique()[:5])
    
    # 使用实际存在的用户ID
    target_user_id = df['用户UID'].iloc[0]  # 使用第一个用户ID
    print(f"将分析用户: {target_user_id}")
    
    try:
        # 运行prompt变化分析
        print("开始分析prompt变化...")
        analyze_prompts_changes(csv_path, str(target_user_id))
        
        print("\n分析完成")
        
    except Exception as e:
        print(f"发生错误: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 