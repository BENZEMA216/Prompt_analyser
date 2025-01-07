import pytest
import gradio as gr
from app.main import VideoPromptAnalysisApp
import pandas as pd

@pytest.fixture
def sample_csv(tmp_path):
    """Create a sample CSV file for testing"""
    data = {
        '用户UID': ['user1', 'user1', 'user2'],
        'prompt': [
            "一个女孩在海边奔跑",
            "女孩奔跑在海边",
            "城市夜景灯光璀璨"
        ],
        'timestamp': [
            "2024-01-01 10:00:00",
            "2024-01-01 10:05:00",
            "2024-01-01 10:10:00"
        ],
        '生成结果预览图': [
            "http://example.com/1.jpg",
            "http://example.com/2.jpg",
            "http://example.com/3.jpg"
        ]
    }
    df = pd.DataFrame(data)
    csv_path = tmp_path / "test.csv"
    df.to_csv(csv_path, index=False)
    return csv_path

@pytest.fixture
def app():
    """Create app instance for testing"""
    return VideoPromptAnalysisApp()

def test_app_initialization(app):
    """Test app initialization"""
    assert app is not None
    assert app.analyzer is not None
    assert app.df is None
    assert isinstance(app.current_results, dict)

def test_load_data(app, sample_csv):
    """Test data loading"""
    class MockFile:
        def __init__(self, path):
            self.name = str(path)
    
    result = app.load_data(MockFile(sample_csv))
    assert isinstance(result, gr.Dropdown)
    assert len(result.choices) == 2  # user1 and user2
    # Gradio internally uses tuples for choices
    assert any(choice[0] == 'user1' for choice in result.choices)
    assert any(choice[0] == 'user2' for choice in result.choices)

def test_analyze_user(app, sample_csv):
    """Test user analysis"""
    class MockFile:
        def __init__(self, path):
            self.name = str(path)
    
    app.load_data(MockFile(sample_csv))
    result = app.analyze_user('user1')
    
    assert isinstance(result, str)
    assert 'Cluster' in result
    assert 'prompt-card' in result

def test_generate_analysis_view(app):
    """Test analysis view generation"""
    test_results = {
        'clusters': {
            0: [
                {
                    'prompt': "测试prompt",
                    'timestamp': "2024-01-01 10:00:00",
                    'preview_url': "http://example.com/test.jpg"
                }
            ]
        }
    }
    
    result = app.generate_analysis_view(test_results)
    assert isinstance(result, str)
    assert 'Cluster' in result
    assert 'prompt-card' in result
    assert 'timestamp' in result
    assert 'preview_url' in result

def test_empty_analysis(app):
    """Test analysis with no data"""
    result = app.analyze_user(None)
    assert "Please select a user" in result

def test_invalid_user(app, sample_csv):
    """Test analysis with invalid user"""
    class MockFile:
        def __init__(self, path):
            self.name = str(path)
    
    app.load_data(MockFile(sample_csv))
    result = app.analyze_user('nonexistent_user')
    assert "No data found for user" in result
