"""配置文件"""
import os

# 基础配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "cache")
LOG_DIR = os.path.join(BASE_DIR, "logs")

# 模型配置
MODEL_CONFIG = {
    'sentence_transformer': 'paraphrase-multilingual-MiniLM-L12-v2',
    'similarity_threshold': 0.9,
    'min_prompts': 4
}

# Gradio界面配置
UI_CONFIG = {
    'theme': 'default',
    'auth': ("admin", "password"),
    'server_port': 7860,
    'debug': False
} 