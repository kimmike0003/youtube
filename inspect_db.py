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
    cursor = conn.cursor()
    
    print("--- key_mgr columns ---")
    cursor.execute("DESCRIBE key_mgr")
    for row in cursor.fetchall():
        print(row)
        
    print("\n--- voice_actor columns ---")
    cursor.execute("DESCRIBE voice_actor")
    for row in cursor.fetchall():
        print(row)

    cursor.close()
    conn.close()
except Exception as e:
    print(e)
