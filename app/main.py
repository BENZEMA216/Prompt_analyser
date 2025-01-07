import gradio as gr
import pandas as pd
from .analyzer import VideoPromptAnalyzer
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class VideoPromptAnalysisApp:
    def __init__(self):
        self.analyzer = VideoPromptAnalyzer()
        self.df = None
        self.current_results = {}
        self.logger = logging.getLogger(__name__)
        
        try:
            self.analyzer.check_models()
        except Exception as e:
            self.logger.error(f"Model loading failed: {str(e)}")
            raise

    def load_data(self, csv_file):
        """Load CSV data"""
        try:
            if csv_file is None:
                return gr.Dropdown(choices=[], value=None, label="Please upload a CSV file first")
            
            self.df = pd.read_csv(csv_file.name)
            self.df['用户UID'] = self.df['用户UID'].astype(str)
            unique_users = self.df['用户UID'].unique().tolist()
            
            print(f"Successfully loaded CSV file with {len(unique_users)} users")
            # Create dropdown with tuples for choices as per Gradio's internal format
            return gr.Dropdown(
                choices=[(user, user) for user in unique_users],
                label=f"Select User (Total: {len(unique_users)})",
                value=unique_users[0] if unique_users else None
            )
        except Exception as e:
            print(f"Error loading CSV file: {str(e)}")
            return gr.Dropdown(choices=[], value=None, label="File loading failed")

    def analyze_user(self, user_id):
        """Analyze prompts for a single user"""
        try:
            if self.df is None or user_id is None:
                return "Please select a user"
            
            user_data = self.df[self.df['用户UID'].astype(str) == str(user_id)]
            if user_data.empty:
                return f"No data found for user {user_id}"
            
            # Analyze prompts with 0.9 similarity threshold
            results = self.analyzer.analyze_user_prompts(self.df, user_id)
            if not results:
                return "No clusters found"
            
            return self.generate_analysis_view(results)
            
        except Exception as e:
            self.logger.error(f"Analysis error: {str(e)}")
            return f"Analysis failed: {str(e)}"

    def generate_analysis_view(self, results):
        """Generate HTML view of analysis results"""
        html = self._get_style()
        
        # Add summary
        total_prompts = sum(len(cluster) for cluster in results['clusters'].values())
        html += f"""
        <div class="summary">
            <h2>Cluster Analysis Results</h2>
            <p>Total Prompts: {total_prompts}</p>
            <p>Number of Clusters: {len(results['clusters'])}</p>
            <p>Similarity Threshold: 0.9</p>
        </div>
        """
        
        # Display clusters
        for cluster_id, prompts in results['clusters'].items():
            html += f"""
            <div class="cluster">
                <h3>Cluster {cluster_id + 1} ({len(prompts)} prompts)</h3>
                <div class="prompt-grid">
            """
            
            for prompt_data in prompts:
                html += f"""
                <div class="prompt-card">
                    <img src="{prompt_data['preview_url']}" alt="Video preview">
                    <div class="prompt-info">
                        <p class="timestamp">{prompt_data['timestamp']}</p>
                        <p class="prompt-text">{prompt_data['prompt']}</p>
                        <p class="preview_url">{prompt_data['preview_url']}</p>
                    </div>
                </div>
                """
            
            html += "</div></div>"
        
        return html

    def _get_style(self):
        """Return CSS styles for the interface"""
        return """
        <style>
        .summary {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        
        .cluster {
            margin: 30px 0;
            padding: 20px;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        .prompt-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
            margin-top: 15px;
        }
        
        .prompt-card {
            border: 1px solid #e1e4e8;
            border-radius: 8px;
            overflow: hidden;
        }
        
        .prompt-card img {
            width: 100%;
            height: 200px;
            object-fit: cover;
        }
        
        .prompt-info {
            padding: 15px;
        }
        
        .timestamp {
            color: #666;
            font-size: 0.9em;
            margin: 0;
        }
        
        .prompt-text {
            margin: 10px 0 0;
            font-size: 0.95em;
            line-height: 1.5;
        }
        </style>
        """

def create_ui():
    """Create Gradio interface"""
    app = VideoPromptAnalysisApp()
    
    with gr.Blocks(title="Video Prompt Analysis") as interface:
        gr.Markdown("# Video Prompt Analysis")
        gr.Markdown("Analyze and cluster video generation prompts by semantic similarity")
        
        with gr.Row():
            file_input = gr.File(label="Upload CSV File")
            user_dropdown = gr.Dropdown(choices=[], label="Select User")
        
        analyze_button = gr.Button("Analyze Prompts")
        results_display = gr.HTML()
        
        file_input.change(
            fn=app.load_data,
            inputs=[file_input],
            outputs=[user_dropdown]
        )
        
        analyze_button.click(
            fn=app.analyze_user,
            inputs=[user_dropdown],
            outputs=[results_display]
        )
    
    return interface

if __name__ == "__main__":
    interface = create_ui()
    interface.launch()
