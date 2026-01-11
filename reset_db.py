import libsql_experimental as libsql
import os
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("TURSO_DATABASE_URL", "libsql://plumfinder-jowes.aws-us-west-2.turso.io")
token = os.getenv("TURSO_AUTH_TOKEN")

if token:
    conn = libsql.connect(url, auth_token=token)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM seen_items")
    cursor.execute("DELETE FROM email_history")
    conn.commit()
    print("Database reset successfully")
else:
    print("No auth token found")
