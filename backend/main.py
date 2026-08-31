import os
import time
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Header, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson.objectid import ObjectId

from backend.database import init_db, get_db
from backend.auth import hash_password, verify_password, create_token, decode_token
from backend.data_loader import resolve_champion_image
from backend.email_service import (
    is_valid_email, generate_otp, send_otp_email, send_welcome_email,
    validate_password_rules, send_password_reset_otp_email, send_password_changed_email
)

app = FastAPI(title="MCOC Full-Stack Nexus API", version="1.0.0")

FRONTEND_ORIGINS = [
    "https://nexus-frontend-virid.vercel.app",
    "https://nexus-frontend.vercel.app",
    "https://mcoc-nexus.vercel.app",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def serialize_mongo(doc):
    if not doc: return None
    doc["id"] = str(doc.pop("_id"))
    return doc

def get_current_user(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split("Bearer ", 1)[1].strip()
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token expired or invalid")
    return payload

def get_admin_user(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user

from backend.mcoc_data_module import MCOC_DATA

@app.get("/api/env-check")
def env_check():
    """Debug endpoint to verify environment variable presence on Render (never shows values)."""
    return {
        "RESEND_API_KEY": "SET ✅" if os.getenv("RESEND_API_KEY") else "NOT SET ❌",
        "SMTP_PASSWORD": "SET ✅" if os.getenv("SMTP_PASSWORD") else "NOT SET ❌",
        "SMTP_EMAIL": os.getenv("SMTP_EMAIL", "not set"),
        "MONGODB_URI": "SET ✅" if os.getenv("MONGODB_URI") else "NOT SET ❌",
    }


@app.get("/api/smtp-test")
def smtp_test():
    import smtplib
    import os
    results = {}
    try:
        s = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10)
        s.login(os.getenv("SMTP_EMAIL", ""), os.getenv("SMTP_PASSWORD", ""))
        s.quit()
        results["ssl_465"] = "SUCCESS"
    except Exception as e:
        results["ssl_465"] = f"ERROR: {str(e)}"
        
    try:
        s = smtplib.SMTP("smtp.gmail.com", 587, timeout=10)
        s.starttls()
        s.login(os.getenv("SMTP_EMAIL", ""), os.getenv("SMTP_PASSWORD", ""))
        s.quit()
        results["tls_587"] = "SUCCESS"
    except Exception as e:
        results["tls_587"] = f"ERROR: {str(e)}"
        
    return results

@app.on_event("startup")
def startup_event():
    print(f"[+] Cached {len(MCOC_DATA.get('champions', []))} champions.")
    try:
        init_db()
        db = get_db()
        adam = db.users.find_one({"username": "BL_ADAM_07"})
        if not adam:
            db.users.insert_one({
                "username": "BL_ADAM_07", "email": "gamingfftamilan@gmail.com",
                "password_hash": hash_password("fftgARMY2"), "role": "admin",
                "created_at": time.time()
            })
            print("[+] Created Primary Admin account")
        
        demo = db.users.find_one({"username": "summoner_alpha"})
        if not demo:
            res = db.users.insert_one({
                "username": "summoner_alpha", "email": "summoner@contest.com",
                "password_hash": hash_password("summoner123"), "role": "user",
                "created_at": time.time()
            })
            demo_id = str(res.inserted_id)
            
            presets = MCOC_DATA.get("upgrade_plan_presets", [])
            for item in presets[:40]:
                r_res = db.user_roster.insert_one({
                    "user_id": demo_id, "champion_name": item["champion_name"],
                    "champion_class": item["class"], "rarity": item["rarity"],
                    "awakened": 1 if item["awakened"] else 0, "current_rank": item["current_rank"],
                    "user_notes": "Key champion", "created_at": time.time(), "signature_level": 0
                })
                db.upgrade_plans.insert_one({
                    "user_id": demo_id, "roster_id": str(r_res.inserted_id),
                    "future_rank": item["future_rank"], "priority": item["priority"],
                    "importance_note": item["importance"], "admin_feedback": "Prioritize ranking up",
                    "is_reviewed": 1, "is_completed": 0, "updated_at": time.time()
                })
            print("[+] Pre-seeded demo user.")
    except Exception as e:
        print(f"[!] MongoDB startup error (non-fatal): {e}")
        print("[!] App will still serve champion data. Auth/roster features require MongoDB.")

class SendOtpRequest(BaseModel): username: str; email: str; password: str
class VerifyOtpRegisterRequest(BaseModel): email: str; otp: str
class ResendOtpRequest(BaseModel): email: str
class RegisterRequest(BaseModel): username: str; email: str; password: str
class LoginRequest(BaseModel): username: str; password: str
class SendResetOtpRequest(BaseModel): email: str

class AdminCreateUserRequest(BaseModel): username: str; email: str; password: str; role: str = "user"
class AdminRoleUpdateRequest(BaseModel): role: str
class AdminPasswordResetRequest(BaseModel): new_password: str
class VerifyResetPasswordRequest(BaseModel): email: str; otp: str; new_password: str
class ChangePasswordRequest(BaseModel): old_password: str; new_password: str
class NodeSolverRequest(BaseModel): debuffs: List[str]

class RosterAddRequest(BaseModel):
    champion_name: str; champion_class: Optional[str] = None; rarity: int = 7; awakened: bool = False
    signature_level: int = 0; current_rank: int = 1; user_notes: Optional[str] = ""

class RosterUpdateRequest(BaseModel):
    rarity: Optional[int] = None; awakened: Optional[bool] = None; signature_level: Optional[int] = None
    current_rank: Optional[int] = None; user_notes: Optional[str] = None

class AdminPlanUpdateRequest(BaseModel):
    user_id: str; roster_id: str; future_rank: int; priority: int = 2; importance_note: str; admin_feedback: Optional[str] = ""

@app.post("/api/auth/send-otp")
def send_registration_otp(req: SendOtpRequest):
    email_clean = req.email.strip().lower()
    username_clean = req.username.strip()
    is_valid_pw, pw_reason = validate_password_rules(req.password)
    if not is_valid_pw: raise HTTPException(status_code=400, detail=pw_reason)
    is_valid, reason = is_valid_email(email_clean)
    if not is_valid: raise HTTPException(status_code=400, detail=reason)
    
    db = get_db()
    if db.users.find_one({"$or": [{"username": username_clean}, {"email": email_clean}]}):
        raise HTTPException(status_code=400, detail="Username or email is already registered.")
        
    otp = generate_otp()
    pw_hash = hash_password(req.password)
    db.email_otps.update_one(
        {"email": email_clean},
        {"$set": {"username": username_clean, "password_hash": pw_hash, "otp_code": otp, "expires_at": time.time() + 600}},
        upsert=True
    )
    sent = send_otp_email(email_clean, username_clean, otp)
    if not sent:
        import backend.email_service as email_service
        error_msg = getattr(email_service, "LAST_EMAIL_ERROR", "Unknown SMTP failure")
        raise HTTPException(status_code=500, detail=f"Failed to send verification email: {error_msg}")
        
    return {"message": f"Verification code sent to {email_clean}", "email": email_clean, "expires_in": 600}


@app.post("/api/auth/verify-otp-register")
def verify_otp_and_register(req: VerifyOtpRegisterRequest):
    db = get_db()
    email_clean = req.email.strip().lower()
    otp_record = db.email_otps.find_one({"email": email_clean})
    if not otp_record: raise HTTPException(status_code=400, detail="No verification pending.")
    if time.time() > otp_record["expires_at"]: raise HTTPException(status_code=400, detail="Code expired.")
    if otp_record["otp_code"] != req.otp.strip(): raise HTTPException(status_code=400, detail="Incorrect code.")
    
    username = otp_record["username"]
    try:
        res = db.users.insert_one({
            "username": username, "email": email_clean,
            "password_hash": otp_record["password_hash"], "role": "user", "created_at": time.time()
        })
        db.email_otps.delete_one({"email": email_clean})
    except Exception:
        raise HTTPException(status_code=400, detail="Account already created.")
        
    send_welcome_email(email_clean, username)
    return {
        "token": create_token(str(res.inserted_id), username, "user"),
        "user": {"id": str(res.inserted_id), "username": username, "email": email_clean, "role": "user"}
    }

@app.post("/api/auth/login")
def login(req: LoginRequest):
    db = get_db()
    user = db.users.find_one({"$or": [{"username": req.username.strip()}, {"email": req.username.strip()}]})
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    user = serialize_mongo(user)
    return {"token": create_token(user["id"], user["username"], user["role"]), "user": user}

@app.get("/api/auth/me")
def get_me(user: Dict[str, Any] = Depends(get_current_user)):
    db = get_db()
    db_user = db.users.find_one({"_id": ObjectId(user["user_id"])})
    if not db_user: raise HTTPException(status_code=404, detail="Not found")
    db_user = serialize_mongo(db_user)
    db_user.pop("password_hash", None)
    return db_user

@app.get("/api/champions")
def get_champions(search: Optional[str] = Query(None), champion_class: Optional[str] = Query(None, alias="class")):
    results = MCOC_DATA.get("champions", [])
    if search: results = [c for c in results if search.lower() in c["name"].lower()]
    if champion_class and champion_class.lower() != "all": results = [c for c in results if c["class"].lower() == champion_class.lower()]
    return results

@app.get("/api/immunities")
def get_immunities(): return MCOC_DATA.get("immunities", [])

@app.get("/api/v1/tier-lists")
async def get_tier_lists():
    return MCOC_DATA.get("tier_data", {})

@app.get("/api/v1/duel-targets")
async def get_duel_targets():
    return MCOC_DATA.get("duel_targets", {})

@app.get("/api/v1/glossary")
async def get_glossary():
    return MCOC_DATA.get("glossary", {})

@app.get("/api/v1/tags")
async def get_tags():
    return {
        "all_tags": MCOC_DATA.get("all_tags", []),
        "all_categories": MCOC_DATA.get("all_categories", []),
        "tags_by_category": MCOC_DATA.get("tags_by_category", {})
    }

@app.get("/api/v1/story-guide")
async def get_story_guide():
    guide_path = os.path.join(os.path.dirname(__file__), "..", "assest", "data", "act8_guide.json")
    if os.path.exists(guide_path):
        with open(guide_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"error": "Story guide data not found"}

@app.post("/api/node-solver")
def solve_node(req: NodeSolverRequest):
    champions = MCOC_DATA.get("champions", [])
    if not req.debuffs:
        return {"matching_champions": []}
    
    matches = []
    for c in champions:
        c_immunities = c.get("immunities", [])
        if all(deb in c_immunities for deb in req.debuffs):
            matches.append(c)
            
    return {"matching_champions": matches}

@app.get("/api/tags")
def get_tags(): return {
    "all_tags": MCOC_DATA.get("all_tags", []), 
    "all_categories": MCOC_DATA.get("all_categories", []), 
    "tags_by_category": MCOC_DATA.get("tags_by_category", {})
}

@app.get("/api/upgrade-plan")
def get_upgrade_plan(user: Dict[str, Any] = Depends(get_current_user)):
    db = get_db()
    plans = list(db.upgrade_plans.find({"user_id": user["user_id"]}))
    roster_ids = [ObjectId(p["roster_id"]) for p in plans if len(p["roster_id"]) == 24]
    rosters = list(db.user_roster.find({"_id": {"$in": roster_ids}}))
    roster_map = {str(r["_id"]): r for r in rosters}
    
    results = []
    for p in plans:
        r = roster_map.get(p["roster_id"])
        if not r: continue
        p = serialize_mongo(p)
        p["champion_name"] = r["champion_name"]
        p["champion_class"] = r["champion_class"]
        p["image"] = resolve_champion_image(r["champion_name"], r["champion_class"])
        p["rarity"] = r["rarity"]
        p["current_rank"] = r["current_rank"]
        results.append(p)
    return results

@app.get("/api/roster")
def get_user_roster(user: Dict[str, Any] = Depends(get_current_user)):
    db = get_db()
    roster = list(db.user_roster.find({"user_id": user["user_id"]}))
    plans = list(db.upgrade_plans.find({"user_id": user["user_id"]}))
    plan_map = {p["roster_id"]: p for p in plans}
    
    results = []
    for r in roster:
        r = serialize_mongo(r)
        r["image"] = resolve_champion_image(r["champion_name"], r["champion_class"])
        r["awakened"] = bool(r.get("awakened", False))
        plan = plan_map.get(r["id"], {})
        r["plan_id"] = str(plan.get("_id")) if "_id" in plan else None
        r["future_rank"] = plan.get("future_rank", 0)
        r["priority"] = plan.get("priority", 2)
        r["importance_note"] = plan.get("importance_note", "")
        r["admin_feedback"] = plan.get("admin_feedback", "")
        r["is_completed"] = bool(plan.get("is_completed", False))
        r["is_reviewed"] = bool(plan.get("is_reviewed", False))
        results.append(r)
    return sorted(results, key=lambda x: (x["rarity"], x["current_rank"]), reverse=True)

@app.post("/api/roster")
def add_to_roster(req: RosterAddRequest, user: Dict[str, Any] = Depends(get_current_user)):
    db = get_db()
    c_class = req.champion_class or "Cosmic"
    res = db.user_roster.insert_one({
        "user_id": user["user_id"], "champion_name": req.champion_name.strip(), "champion_class": c_class,
        "rarity": req.rarity, "awakened": 1 if req.awakened else 0, "signature_level": req.signature_level,
        "current_rank": req.current_rank, "user_notes": req.user_notes, "created_at": time.time()
    })
    db.upgrade_plans.insert_one({
        "user_id": user["user_id"], "roster_id": str(res.inserted_id), "future_rank": 0, "priority": 2,
        "importance_note": "Analysing", "admin_feedback": "Coach is analysing.", "is_reviewed": 0, "is_completed": 0
    })
    return {"message": "Champion added", "id": str(res.inserted_id)}

@app.delete("/api/roster/{roster_id}")
def delete_roster_item(roster_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    db = get_db()
    db.user_roster.delete_one({"_id": ObjectId(roster_id), "user_id": user["user_id"]})
    db.upgrade_plans.delete_many({"roster_id": roster_id, "user_id": user["user_id"]})
    return {"message": "Removed"}

@app.get("/api/admin/users")
def get_all_users_for_admin(admin: Dict[str, Any] = Depends(get_admin_user)):
    db = get_db()
    users = list(db.users.find())
    for u in users:
        u = serialize_mongo(u)
        u.pop("password_hash", None)
        u["is_boss"] = u["username"].upper() == "BL_ADAM_07"
        u["roster_count"] = db.user_roster.count_documents({"user_id": u["id"]})
        u["reviewed_count"] = db.upgrade_plans.count_documents({"user_id": u["id"], "is_reviewed": 1})
    return users

@app.post("/api/admin/users/create")
def admin_create_user(req: AdminCreateUserRequest, admin: Dict[str, Any] = Depends(get_admin_user)):
    db = get_db()
    email_clean = req.email.strip().lower()
    username_clean = req.username.strip()
    if db.users.find_one({"$or": [{"username": username_clean}, {"email": email_clean}]}):
        raise HTTPException(status_code=400, detail="Username or email already exists.")
    pw_hash = hash_password(req.password)
    res = db.users.insert_one({
        "username": username_clean, "email": email_clean,
        "password_hash": pw_hash, "role": req.role, "created_at": time.time()
    })
    return {"message": "User created successfully", "id": str(res.inserted_id)}

@app.put("/api/admin/users/{user_id}/role")
def admin_update_role(user_id: str, req: AdminRoleUpdateRequest, admin: Dict[str, Any] = Depends(get_admin_user)):
    db = get_db()
    target = db.users.find_one({"_id": ObjectId(user_id)})
    if not target: raise HTTPException(status_code=404, detail="User not found.")
    if target.get("username", "").upper() == "BL_ADAM_07":
        raise HTTPException(status_code=403, detail="Cannot modify primary boss admin.")
    db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"role": req.role}})
    return {"message": "Role updated"}

@app.put("/api/admin/users/{user_id}/password")
def admin_reset_password(user_id: str, req: AdminPasswordResetRequest, admin: Dict[str, Any] = Depends(get_admin_user)):
    db = get_db()
    target = db.users.find_one({"_id": ObjectId(user_id)})
    if not target: raise HTTPException(status_code=404, detail="User not found.")
    if target.get("username", "").upper() == "BL_ADAM_07":
        raise HTTPException(status_code=403, detail="Cannot reset password of primary boss admin.")
    db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"password_hash": hash_password(req.new_password)}})
    return {"message": "Password reset"}

@app.delete("/api/admin/users/{user_id}")
def admin_delete_user(user_id: str, admin: Dict[str, Any] = Depends(get_admin_user)):
    db = get_db()
    target = db.users.find_one({"_id": ObjectId(user_id)})
    if not target: raise HTTPException(status_code=404, detail="User not found.")
    if target.get("username", "").upper() == "BL_ADAM_07":
        raise HTTPException(status_code=403, detail="Cannot delete primary boss admin.")
    db.users.delete_one({"_id": ObjectId(user_id)})
    db.user_roster.delete_many({"user_id": user_id})
    db.upgrade_plans.delete_many({"user_id": user_id})
    return {"message": "User deleted"}

@app.get("/api/admin/user-roster/{user_id}")
def get_user_roster_for_admin(user_id: str, admin: Dict[str, Any] = Depends(get_admin_user)):
    db = get_db()
    target = db.users.find_one({"_id": ObjectId(user_id)})
    if not target: raise HTTPException(status_code=404)
    target = serialize_mongo(target)
    
    roster = list(db.user_roster.find({"user_id": user_id}))
    plans = list(db.upgrade_plans.find({"user_id": user_id}))
    plan_map = {p["roster_id"]: p for p in plans}
    
    r_list = []
    for r in roster:
        r = serialize_mongo(r)
        r["image"] = resolve_champion_image(r["champion_name"], r["champion_class"])
        plan = plan_map.get(r["id"], {})
        r["plan_id"] = str(plan.get("_id")) if "_id" in plan else None
        r["future_rank"] = plan.get("future_rank", r["current_rank"]+1)
        r["priority"] = plan.get("priority", 2)
        r["importance_note"] = plan.get("importance_note", "Recommended Rankup")
        r["admin_feedback"] = plan.get("admin_feedback", "")
        r["is_reviewed"] = bool(plan.get("is_reviewed", 0))
        r_list.append(r)
    return {"user": target, "roster": r_list}

@app.post("/api/admin/upgrade-plan")
def save_admin_upgrade_plan(req: AdminPlanUpdateRequest, admin: Dict[str, Any] = Depends(get_admin_user)):
    db = get_db()
    db.upgrade_plans.update_one(
        {"user_id": req.user_id, "roster_id": req.roster_id},
        {"$set": {
            "future_rank": req.future_rank, "priority": req.priority,
            "importance_note": req.importance_note or "Recommended Rankup",
            "admin_feedback": req.admin_feedback, "is_reviewed": 1, "updated_at": time.time()
        }},
        upsert=True
    )
    return {"message": "Plan saved"}

@app.get("/api/upgrade-plan")
def get_user_upgrade_plan(user: Dict[str, Any] = Depends(get_current_user)):
    db = get_db()
    roster = list(db.user_roster.find({"user_id": user["user_id"]}))
    plans = list(db.upgrade_plans.find({"user_id": user["user_id"]}))
    plan_map = {p["roster_id"]: p for p in plans}
    
    items = []
    for r in roster:
        r = serialize_mongo(r)
        plan = plan_map.get(r["id"], {})
        r["plan_id"] = str(plan.get("_id")) if "_id" in plan else None
        r["is_reviewed"] = bool(plan.get("is_reviewed", 0))
        r["future_rank"] = plan.get("future_rank")
        r["status"] = "RECOMMENDED" if r["is_reviewed"] else "ANALYSING"
        r["costs"] = {"t6b":0, "t3a":0, "t5cc":0, "gold":0, "gold_str":"Analysing" if not r["is_reviewed"] else "0 Gold"}
        r["is_completed"] = bool(plan.get("is_completed", 0))
        items.append(r)
    return {"items": items, "summary": {"total_items": len(items)}}

@app.post("/api/upgrade-plan/toggle-complete/{plan_id}")
def toggle_upgrade_complete(plan_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    db = get_db()
    plan = db.upgrade_plans.find_one({"_id": ObjectId(plan_id), "user_id": user["user_id"]})
    if not plan: raise HTTPException(status_code=404)
    new_state = 0 if plan.get("is_completed", 0) else 1
    db.upgrade_plans.update_one({"_id": ObjectId(plan_id)}, {"$set": {"is_completed": new_state}})
    if new_state == 1:
        db.user_roster.update_one({"_id": ObjectId(plan["roster_id"])}, {"$set": {"current_rank": plan["future_rank"]}})
    return {"is_completed": bool(new_state)}

@app.get("/api/health")
def health_check(): return {"status": "ok", "version": "1.0.0 (MongoDB)"}
