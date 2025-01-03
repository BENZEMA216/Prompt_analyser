import os
import json
from datetime import datetime

class ResultsCache:
    def __init__(self, cache_dir="cache"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
    
    def save(self, user_id: str, results: dict):
        """保存分析结果到缓存"""
        cache_file = os.path.join(self.cache_dir, f"{user_id}.json")
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'results': results
            }, f, ensure_ascii=False)
    
    def load(self, user_id: str) -> dict:
        """从缓存加载分析结果"""
        cache_file = os.path.join(self.cache_dir, f"{user_id}.json")
        if os.path.exists(cache_file):
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None 