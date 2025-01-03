def get_style_html(self):
    """返回样式HTML"""
    return """
    <style>
    .gradio-container * {
        color: #000000 !important;
    }
    
    .prompt-card {
        background: #ffffff !important;
        border: 1px solid #e1e4e8;
        border-radius: 8px;
        padding: 20px;
        margin: 16px 0;
        display: flex;
        gap: 20px;
    }
    
    .prompt-content {
        flex: 3;
        display: flex;
        flex-direction: column;
    }
    
    .prompt-image {
        flex: 1;
        max-width: 200px;
        min-width: 150px;
    }
    
    .prompt-image img {
        width: 100%;
        height: auto;
        border-radius: 4px;
        object-fit: cover;
    }
    
    .timestamp {
        color: #666666 !important;
        font-size: 12px;
    }
    
    .prompt-text {
        font-size: 14px;
        line-height: 1.6;
        margin: 8px 0;
    }
    
    .section-title {
        font-size: 18px;
        font-weight: 600;
        margin: 24px 0 16px;
    }
    
    .cluster-header {
        margin: 16px 0;
    }
    
    .cluster-title {
        font-weight: 600;
    }
    
    .cluster-count {
        color: #0366d6;
        margin-left: 8px;
    }
    
    .saved-badge {
        background: #28a745;
        color: white;
        padding: 4px 8px;
        border-radius: 4px;
        position: absolute;
        top: 10px;
        right: 10px;
    }
    
    .diff-section {
        margin-top: 12px;
        padding: 12px;
        background: #f8f9fa;
        border-radius: 6px;
        border-left: 3px solid #0366d6;
    }
    </style>
    """ 