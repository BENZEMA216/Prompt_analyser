from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import logging

logger = logging.getLogger(__name__)

class VideoPromptAnalyzer:
    def __init__(self):
        self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        self.similarity_threshold = 0.9  # Restored to original threshold
    
    def check_models(self):
        """Verify model is loaded correctly"""
        return self.model is not None
    
    def cluster_prompts(self, prompts):
        """Cluster prompts based on similarity threshold"""
        try:
            if not prompts:
                return None
            
            # Calculate embeddings
            embeddings = self.model.encode(prompts)
            
            # Calculate pairwise similarities
            similarities = cosine_similarity(embeddings)
            
            # Find clusters
            clusters = {}
            used_indices = set()
            
            for i in range(len(prompts)):
                if i in used_indices:
                    continue
                
                # Find all prompts similar to current prompt
                cluster = [i]  # Start with current prompt
                for j in range(len(prompts)):
                    if j != i and j not in used_indices and similarities[i][j] >= self.similarity_threshold:
                        cluster.append(j)
                
                if len(cluster) > 0:  # Always create a cluster, even for single prompts
                    clusters[len(clusters)] = cluster
                    used_indices.update(cluster)
            
            # Sort clusters by size
            sorted_clusters = {}
            for idx, (_, cluster) in enumerate(sorted(clusters.items(), key=lambda x: len(x[1]), reverse=True)):
                sorted_clusters[idx] = cluster
            
            return sorted_clusters
            
        except Exception as e:
            logger.error(f"Error in prompt clustering: {str(e)}")
            return None
            
    def analyze_user_prompts(self, user_id, df):
        """Analyze prompts for a specific user"""
        try:
            if df is None or user_id is None:
                return None
                
            # Convert user_id to int for comparison
            user_id = int(user_id)
            user_data = df[df['user_id'] == user_id]
            
            if user_data.empty:
                logger.error(f"No data found for user {user_id}")
                return None
            
            prompts = user_data['prompt'].tolist()
            logger.info(f"Found {len(prompts)} prompts for user {user_id}")
            clusters = self.cluster_prompts(prompts)
            
            if not clusters:
                return None
                
            # Calculate embeddings and similarities
            prompts = user_data['prompt'].tolist()
            timestamps = user_data['timestamp'].tolist()
            preview_urls = user_data['preview_url'].tolist()
            
            embeddings = self.model.encode(prompts)
            similarities = cosine_similarity(embeddings)
            
            # Format results
            results = {'clusters': {}}
            for cluster_id, indices in clusters.items():
                results['clusters'][cluster_id] = {
                    'items': [],
                    'similarities': []
                }
                
                # Add items
                for idx in indices:
                    results['clusters'][cluster_id]['items'].append({
                        'prompt': prompts[idx],
                        'timestamp': timestamps[idx],
                        'preview_url': preview_urls[idx]
                    })
                
                # Add similarity matrix for this cluster
                cluster_similarities = []
                for i in indices:
                    row = []
                    for j in indices:
                        row.append(float(similarities[i][j]))
                    cluster_similarities.append(row)
                results['clusters'][cluster_id]['similarities'] = cluster_similarities
            
            return results
            
        except Exception as e:
            logger.error(f"Error in user prompt analysis: {str(e)}")
            return None
    
    def _cluster_by_similarity(self, similarities, prompts, timestamps, preview_urls):
        """Cluster prompts based on similarity threshold"""
        clusters = []
        used_indices = set()
        
        for i in range(len(prompts)):
            if i in used_indices:
                continue
            
            # Find all prompts similar to current prompt
            cluster_indices = {i}
            for j in range(len(prompts)):
                if j != i and j not in used_indices and similarities[i][j] >= self.similarity_threshold:
                    cluster_indices.add(j)
            
            # If we found similar prompts, create a cluster
            if len(cluster_indices) > 0:
                cluster = {
                    'prompts': [prompts[idx] for idx in cluster_indices],
                    'timestamps': [timestamps[idx] for idx in cluster_indices],
                    'preview_urls': [preview_urls[idx] for idx in cluster_indices],
                    'similarities': [[similarities[i][j] for j in cluster_indices] for i in cluster_indices]
                }
                clusters.append(cluster)
                used_indices.update(cluster_indices)
        
        # Sort clusters by size
        clusters.sort(key=lambda x: len(x['prompts']), reverse=True)
        return clusters
