import pytest
import pandas as pd
import numpy as np
from app.analyzer import VideoPromptAnalyzer

@pytest.fixture
def sample_prompts():
    """Sample prompts for testing"""
    return {
        'prompts': [
            "一个女孩在海边奔跑",  # Similar to prompt 2
            "女孩奔跑在海边",      # Similar to prompt 1
            "城市夜景灯光璀璨",    # Different theme
            "繁华都市夜景",        # Similar to prompt 3
            "山间小屋炊烟袅袅"     # Unique theme
        ],
        'timestamps': [
            "2024-01-01 10:00:00",
            "2024-01-01 10:05:00",
            "2024-01-01 10:10:00",
            "2024-01-01 10:15:00",
            "2024-01-01 10:20:00"
        ],
        'preview_urls': [
            "http://example.com/1.jpg",
            "http://example.com/2.jpg",
            "http://example.com/3.jpg",
            "http://example.com/4.jpg",
            "http://example.com/5.jpg"
        ]
    }

@pytest.fixture
def sample_df():
    """Sample DataFrame for testing"""
    data = {
        '用户UID': ['user1'] * 5,
        'prompt': [
            "一个女孩在海边奔跑",
            "女孩奔跑在海边",
            "城市夜景灯光璀璨",
            "繁华都市夜景",
            "山间小屋炊烟袅袅"
        ],
        'timestamp': [
            "2024-01-01 10:00:00",
            "2024-01-01 10:05:00",
            "2024-01-01 10:10:00",
            "2024-01-01 10:15:00",
            "2024-01-01 10:20:00"
        ],
        '生成结果预览图': [
            "http://example.com/1.jpg",
            "http://example.com/2.jpg",
            "http://example.com/3.jpg",
            "http://example.com/4.jpg",
            "http://example.com/5.jpg"
        ]
    }
    return pd.DataFrame(data)

def test_analyzer_initialization():
    """Test analyzer initialization"""
    analyzer = VideoPromptAnalyzer()
    assert analyzer is not None
    assert analyzer.similarity_threshold == 0.9
    assert analyzer.model is not None

def test_cluster_prompts(sample_prompts):
    """Test prompt clustering with similarity threshold"""
    analyzer = VideoPromptAnalyzer()
    clusters = analyzer.cluster_prompts(sample_prompts['prompts'])
    
    assert clusters is not None
    assert isinstance(clusters, dict)
    
    # Check that similar prompts are clustered together
    for cluster_id, indices in clusters.items():
        prompts = [sample_prompts['prompts'][i] for i in indices]
        # If cluster has multiple prompts, they should be semantically similar
        if len(prompts) > 1:
            embeddings = analyzer.model.encode(prompts)
            similarities = np.inner(embeddings, embeddings)
            # All similarities in cluster should be >= 0.9
            assert np.all(similarities >= 0.9)

def test_analyze_user_prompts(sample_df):
    """Test user prompt analysis"""
    analyzer = VideoPromptAnalyzer()
    results = analyzer.analyze_user_prompts(sample_df, 'user1')
    
    assert results is not None
    assert 'clusters' in results
    
    # Check cluster structure
    for cluster_id, cluster_data in results['clusters'].items():
        assert isinstance(cluster_data, list)
        for prompt_data in cluster_data:
            assert 'prompt' in prompt_data
            assert 'timestamp' in prompt_data
            assert 'preview_url' in prompt_data

def test_similarity_threshold():
    """Test similarity threshold enforcement"""
    analyzer = VideoPromptAnalyzer()
    test_prompts = [
        "一个女孩在海边奔跑",
        "完全不相关的prompt",
        "女孩奔跑在海边"
    ]
    
    clusters = analyzer.cluster_prompts(test_prompts)
    
    # Check that dissimilar prompts are not clustered together
    for cluster_indices in clusters.values():
        prompts = [test_prompts[i] for i in cluster_indices]
        if len(prompts) > 1:
            embeddings = analyzer.model.encode(prompts)
            similarities = np.inner(embeddings, embeddings)
            # All similarities should be >= 0.9
            assert np.all(similarities >= 0.9)

def test_empty_input():
    """Test handling of empty input"""
    analyzer = VideoPromptAnalyzer()
    empty_df = pd.DataFrame({
        '用户UID': [],
        'prompt': [],
        'timestamp': [],
        '生成结果预览图': []
    })
    
    results = analyzer.analyze_user_prompts(empty_df, 'user1')
    assert results is None

def test_invalid_input():
    """Test handling of invalid input"""
    analyzer = VideoPromptAnalyzer()
    invalid_df = pd.DataFrame({
        '用户UID': ['user1'],
        'wrong_column': ['test']
    })
    
    results = analyzer.analyze_user_prompts(invalid_df, 'user1')
    assert results is None
