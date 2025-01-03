from typing import List, Dict, Any
import pandas as pd

def validate_csv_data(df: pd.DataFrame) -> tuple[bool, str]:
    """验证CSV数据的格式和内容"""
    required_columns = ['用户UID', 'prompt', '生成结果预览图']
    time_columns = ['p_date', '生成时间(精确到秒)']
    
    # 检查必要列
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        return False, f"缺少必要列: {', '.join(missing)}"
    
    # 检查时间列
    if not any(col in df.columns for col in time_columns):
        return False, f"缺少时间列: 需要 {' 或 '.join(time_columns)}"
    
    # 检查数据有效性
    if df['prompt'].isna().any():
        return False, "存在空的prompt"
        
    return True, "数据验证通过" 