def get_mock_results():
    """生成测试用的聚类结果数据"""
    return {
        'clusters': {
            '0': [
                {
                    'prompt': '大写意，水墨晕染，湿墨，怪兽，极简主义，大面积留白，毛笔小楷题跋落款文字"愿虫跟持则可圆"',
                    'timestamp': '2025-01-01',
                    'preview_url': 'https://example.com/img1.jpg',
                    'is_saved': True
                },
                {
                    'prompt': '大写意，水墨晕染，湿墨，怪兽，留白，毛笔题跋"愿虫跟持则可圆"',
                    'timestamp': '2025-01-02',
                    'preview_url': 'https://example.com/img2.jpg',
                    'is_saved': False
                }
            ],
            '1': [
                {
                    'prompt': '中国风，水彩，古风人物，仙女，飘带，云雾缭绕',
                    'timestamp': '2025-01-03',
                    'preview_url': 'https://example.com/img3.jpg',
                    'is_saved': True
                }
            ],
            '2': [
                {
                    'prompt': '插画风格，可爱，萌系，小动物，粉色背景',
                    'timestamp': '2025-01-04',
                    'preview_url': 'https://example.com/img4.jpg',
                    'is_saved': False
                },
                {
                    'prompt': '插画，可爱，萌宠，小狗，彩色背景',
                    'timestamp': '2025-01-05',
                    'preview_url': 'https://example.com/img5.jpg',
                    'is_saved': True
                }
            ]
        },
        'changes': []  # 简化起见，暂时不模拟修改历史
    } 