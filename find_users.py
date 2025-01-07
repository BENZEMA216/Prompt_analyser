import pandas as pd

def find_users_with_multiple_prompts():
    df = pd.read_csv('/home/ubuntu/attachments/transformed_data.csv')
    user_counts = df['用户UID'].value_counts()
    
    print('\nUsers with multiple prompts:')
    print('\nUID : Number of Prompts')
    print('-' * 30)
    for uid, count in user_counts[user_counts > 1].head().items():
        print(f'{uid} : {count}')

if __name__ == '__main__':
    find_users_with_multiple_prompts()
