"""
Admin Management CLI for MCOC Nexus
Usage:
  python manage_admin.py list
  python manage_admin.py create <username> <password> <email>
  python manage_admin.py promote <username>
"""
import sys
import time
from backend.database import get_db
from backend.auth import hash_password
from bson.objectid import ObjectId

def serialize_mongo(doc):
    if not doc: return None
    doc["id"] = str(doc.pop("_id"))
    return doc

def list_admins():
    db = get_db()
    admins = list(db.users.find({"role": "admin"}))
    print("\n[+] CURRENT ADMINISTRATORS:")
    print("--------------------------------------------------")
    for a in admins:
        a = serialize_mongo(a)
        print(f"ID: {a['id']} | Username: {a['username']:<16} | Email: {a['email']}")
    print("--------------------------------------------------\n")

def create_admin(username, password, email):
    db = get_db()
    try:
        db.users.insert_one({
            "username": username.strip(),
            "email": email.strip(),
            "password_hash": hash_password(password),
            "role": "admin",
            "created_at": time.time()
        })
        print(f"\n[+] Successfully created Admin account: '{username}' ({email})")
    except Exception:
        print(f"\n[!] Error: Username '{username}' or email '{email}' already exists.")

def promote_user(username):
    db = get_db()
    result = db.users.update_one(
        {"username": username.strip()},
        {"$set": {"role": "admin"}}
    )
    if result.modified_count > 0:
        print(f"\n[+] Successfully promoted user '{username}' to Admin!")
    else:
        print(f"\n[!] Error: User '{username}' not found or already an admin.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
        
    cmd = sys.argv[1].lower()
    if cmd == "list":
        list_admins()
    elif cmd == "create":
        if len(sys.argv) < 5:
            print("Usage: python manage_admin.py create <username> <password> <email>")
        else:
            create_admin(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == "promote":
        if len(sys.argv) < 3:
            print("Usage: python manage_admin.py promote <username>")
        else:
            promote_user(sys.argv[2])
    else:
        print(__doc__)
