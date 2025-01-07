# Video Prompt Analyser

A specialized tool for analyzing video generation prompts, focusing on semantic similarity clustering and visualization.

## Features

- Load and analyze video generation prompts by user UID
- Calculate pairwise embedding similarities between prompts
- Cluster similar prompts (similarity threshold > 0.9)
- Visualize clusters with video preview images
- Interactive web interface using Gradio

## Project Structure

- `app/main.py`: Main application with Gradio interface
- `app/analyzer.py`: Core prompt analysis and clustering logic
- `app/__init__.py`: Package initialization
- `requirements.txt`: Project dependencies

## Requirements

```
torch>=1.9.0
sentence-transformers>=2.2.0
pandas>=1.3.0
scikit-learn>=0.24.2
numpy>=1.21.0
gradio>=3.50.0
```

## Usage

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python -m app.main
```

3. Upload a CSV file containing video prompts with the following columns:
   - 用户UID: User identifier
   - prompt: Video generation prompt text
   - timestamp: Generation timestamp
   - 生成结果预览图: Preview image URL for the generated video

4. Select a user from the dropdown menu to analyze their prompts

5. View the clustering results, where prompts with similarity > 0.9 are grouped together

## Input Data Format

The input CSV file should contain the following columns:
- 用户UID (string): User identifier
- prompt (string): Video generation prompt text
- timestamp (datetime): Generation timestamp
- 生成结果预览图 (string): URL to the video preview image

## Analysis Process

1. Loads user prompts from CSV file
2. Generates embeddings using SentenceTransformer
3. Calculates pairwise similarities between prompts
4. Clusters prompts with similarity > 0.9
5. Displays clusters with preview images and timestamps
