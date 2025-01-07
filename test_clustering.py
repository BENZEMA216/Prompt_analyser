import pandas as pd
from app.analyzer import VideoPromptAnalyzer

def test_user_clustering():
    # Load transformed data
    df = pd.read_csv('data/transformed_data.csv')

    # Initialize analyzer
    analyzer = VideoPromptAnalyzer()

    # Test with specific user
    user_id = 1805846196787177
    user_prompts = df[df['user_id'] == user_id]
    print(f'\nAnalyzing prompts for user {user_id}:')
    print(f'Found {len(user_prompts)} prompts')
    print('\nPrompts:')
    print(user_prompts[['prompt', 'timestamp']].to_string())

    # Get clusters
    results = analyzer.analyze_user_prompts(user_id, df)
    print('\nClusters:')
    if results and 'clusters' in results:
        for cluster_id, cluster_data in results['clusters'].items():
            print(f'\nCluster {cluster_id + 1}:')
            items = cluster_data['items']
            similarities = cluster_data['similarities']
            print(f'Cluster size: {len(items)}')
            
            for i, item in enumerate(items):
                print(f'- Prompt: {item["prompt"]}')
                print(f'  Timestamp: {item["timestamp"]}')
                print(f'  Preview URL: {item["preview_url"]}')
                
                if len(items) > 1:
                    print('  Similarities to other prompts in cluster:')
                    for j, other_item in enumerate(items):
                        if i != j:
                            sim_score = similarities[i][j]
                            print(f'    - {sim_score:.3f} with: {other_item["prompt"]}')

if __name__ == '__main__':
    test_user_clustering()
