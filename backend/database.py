import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
DB_NAME = "mcoc_nexus"

client = None
db = None

def get_db_connection():
    global client, db
    if client is None:
        client = MongoClient(
            MONGODB_URI,
            tls=True,
            tlsAllowInvalidCertificates=True,
            serverSelectionTimeoutMS=30000,
            connectTimeoutMS=30000,
            socketTimeoutMS=30000,
        )
        db = client[DB_NAME]
    return db

def get_db():
    return get_db_connection()

def init_db():
    database = get_db_connection()
    
    # Users collection indexes
    database.users.create_index("username", unique=True)
    database.users.create_index("email", unique=True)
    
    # Email OTPs
    database.email_otps.create_index("email", unique=True)
    
    # Password resets
    database.password_resets.create_index("email", unique=True)
    
    # Roster indexes
    database.user_roster.create_index("user_id")
    
    # Upgrade plans indexes
    database.upgrade_plans.create_index("user_id")
    database.upgrade_plans.create_index("roster_id")

    print("MongoDB database initialized with indexes.")

if __name__ == "__main__":
    init_db()
