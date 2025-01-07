import pandas as pd

def transform_csv(input_path, output_path):
    # Read the input CSV with proper encoding
    df = pd.read_csv(input_path, encoding='utf-8-sig')
    
    # Handle timestamp conversion with error handling
    def safe_convert_timestamp(x):
        try:
            if str(x).isdigit() and len(str(x)) <= 5:
                # Handle numeric timestamps (assumed to be days since some epoch)
                return pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
            return pd.to_datetime(x).strftime('%Y-%m-%d %H:%M:%S')
        except:
            return pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Create new DataFrame with required columns
    transformed_df = pd.DataFrame({
        'user_id': df['user_id'],
        'prompt': df['用户输入的prompt'],
        'timestamp': df['p_date'].apply(safe_convert_timestamp),
        'preview_url': df['task_vid_url']
    })
    
    # Remove any rows with null prompts
    transformed_df = transformed_df.dropna(subset=['prompt'])
    
    # Save transformed data
    transformed_df.to_csv(output_path, index=False)
    return transformed_df

if __name__ == "__main__":
    input_file = "/home/ubuntu/attachments/+-+.csv"
    output_file = "/home/ubuntu/repos/video_prompt_analyser/data/transformed_data.csv"
    transformed_df = transform_csv(input_file, output_file)
    print(f"Transformed {len(transformed_df)} rows of data")
    print("\nFirst few rows of transformed data:")
    print(transformed_df.head())
