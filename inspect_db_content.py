import mysql.connector

config = {
    'user': 'youtubedev',
    'password': 'youtube2122',
    'host': 'devlab.pics',
    'database': 'youtubedevdb',
    'port': 3306
}

try:
    conn = mysql.connector.connect(**config)
    cursor = conn.cursor(dictionary=True)
    
    print("\n--- key_mgr sample (kind='AUDIO') ---")
    cursor.execute("SELECT kind, api_key, name FROM key_mgr WHERE kind='AUDIO' AND use_yn='Y' AND user_id='admin' LIMIT 1")
    print(cursor.fetchone())
        
    print("\n--- voice_actor sample ---")
    cursor.execute("SELECT voice_name, model_id FROM voice_actor LIMIT 1")
    print(cursor.fetchone())

    cursor.close()
    conn.close()
except Exception as e:
    print(e)
