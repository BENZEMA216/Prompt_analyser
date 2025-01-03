import seaborn as sns
import matplotlib.pyplot as plt

def plot_similarity_matrix(similarity_matrix, prompts):
    plt.figure(figsize=(10, 8))
    sns.heatmap(similarity_matrix, 
                xticklabels=prompts,
                yticklabels=prompts,
                cmap='YlOrRd')
    plt.title('Prompt相似度热力图')
    plt.show() 

def plot_user_similarities(results, uid, save_path=None):
    if uid not in results:
        print(f"未找到用户 {uid} 的数据")
        return
        
    user_data = results[uid]
    plt.figure(figsize=(10, 8))
    sns.heatmap(user_data['similarity_matrix'], 
                xticklabels=[f"Prompt {i+1}" for i in range(len(user_data['prompts']))],
                yticklabels=[f"Prompt {i+1}" for i in range(len(user_data['prompts']))],
                cmap='YlOrRd')
    plt.title(f'用户 {uid} 的Prompt相似度热力图')
    
    if save_path:
        plt.savefig(save_path)
        plt.close()
    else:
        plt.show() 