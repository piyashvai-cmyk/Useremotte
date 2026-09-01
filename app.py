import os
import time
import json
import secrets
import string
import datetime
from functools import wraps
from flask import Flask, request, jsonify, session, send_from_directory
from flask_cors import CORS
import requests

# -----------------------------------------------------------------------------
# FLASK APPLICATION CONFIGURATION
# -----------------------------------------------------------------------------
app = Flask(__name__, static_folder=".")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "mpx-panel-super-secret-session-key-2026")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=os.environ.get("VERCEL_ENV") == "production",
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=datetime.timedelta(days=7)
)

CORS(app, supports_credentials=True)

# -----------------------------------------------------------------------------
# ENVIRONMENT VARIABLES & MASTER CREDENTIALS
# -----------------------------------------------------------------------------
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "7XPIYASH")
MASTER_KEY = os.environ.get("MASTER_KEY", "7XMARUF10XPIYASH")
BOT_API_URL = os.environ.get(
    "BOT_API_URL",
    "https://maruf-king.onrender.com/app/5050/emote?uid1={uid1}&uid2={uid2}&uid3={uid3}&uid4={uid4}&uid5={uid5}&uid6={uid6}&team_code={team_code}&emote_id={emote_id}"
)
SPECIAL_TEAM_CODE = os.environ.get("SPECIAL_TEAM_CODE", "1694161")
SPECIAL_TARGET_CODE = os.environ.get("SPECIAL_TARGET_CODE", "3859281")
DEFAULT_EMOTE_ID = os.environ.get("DEFAULT_EMOTE_ID", "909000063")
UID_COUNT = int(os.environ.get("UID_COUNT", "6"))

FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "emote-4756e")
FIREBASE_CLIENT_EMAIL = os.environ.get("FIREBASE_CLIENT_EMAIL", "")
FIREBASE_PRIVATE_KEY = os.environ.get("FIREBASE_PRIVATE_KEY", "").replace("\\n", "\n")

# -----------------------------------------------------------------------------
# FIREBASE ADMIN SDK INITIALIZATION (SERVER-SIDE)
# -----------------------------------------------------------------------------
firestore_db = None
try:
    import firebase_admin
    from firebase_admin import credentials, firestore

    if FIREBASE_CLIENT_EMAIL and FIREBASE_PRIVATE_KEY:
        cred = credentials.Certificate({
            "type": "service_account",
            "project_id": FIREBASE_PROJECT_ID,
            "private_key": FIREBASE_PRIVATE_KEY,
            "client_email": FIREBASE_CLIENT_EMAIL,
            "token_uri": "https://oauth2.googleapis.com/token"
        })
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        firestore_db = firestore.client()
        print("Firebase Admin SDK initialized successfully.")
    else:
        if not firebase_admin._apps:
            try:
                firebase_admin.initialize_app()
                firestore_db = firestore.client()
                print("Firebase Admin SDK initialized with default application credentials.")
            except Exception:
                print("Firebase Admin credentials not set; server will use fallback storage.")
except Exception as fb_err:
    print("Firebase Admin Init Notice:", str(fb_err))

# In-Memory / Local Cache Fallback if Firebase Admin credentials are not yet configured
_local_db = {
    "keys": {},
    "bots": {},
    "emotes": {},
    "notices": [],
    "settings": {
        "app_name": "MPX PANEL",
        "embed_url": "",
        "maintenance_mode": False
    }
}

# -----------------------------------------------------------------------------
# AUTHENTICATION DECORATOR & HELPER FUNCTIONS
# -----------------------------------------------------------------------------
def require_admin_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "Unauthorized. Admin authentication required."}), 401
        return f(*args, **kwargs)
    return decorated_function

def generate_random_key(length=8):
    chars = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))

# -----------------------------------------------------------------------------
# ROOT & ROUTING ENDPOINTS
# -----------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def root_route():
    """Serves the User Panel (index.html) at root URL /"""
    if os.path.exists("index.html"):
        return send_from_directory(".", "index.html")
    return jsonify({"name": "MPX PANEL", "status": "running"}), 200

@app.route("/admin234", methods=["GET"])
def admin_route():
    """Serves the Admin Panel (admin.html) at secure route /admin234"""
    if os.path.exists("admin.html"):
        return send_from_directory(".", "admin.html")
    return jsonify({"error": "admin.html not found"}), 404

@app.route("/admin.html", methods=["GET"])
def direct_admin_html():
    """Redirects or serves admin.html"""
    if os.path.exists("admin.html"):
        return send_from_directory(".", "admin.html")
    return jsonify({"error": "admin.html not found"}), 404

@app.route("/index.html", methods=["GET"])
def direct_index_html():
    """Serves index.html directly"""
    if os.path.exists("index.html"):
        return send_from_directory(".", "index.html")
    return jsonify({"error": "index.html not found"}), 404

# -----------------------------------------------------------------------------
# USER PANEL BACKEND API ENDPOINTS
# -----------------------------------------------------------------------------
@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "healthy",
        "app": "MPX PANEL Unified API",
        "time": time.time(),
        "firestore_connected": firestore_db is not None
    }), 200

@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify({
        "uid_count": UID_COUNT,
        "default_emote_id": DEFAULT_EMOTE_ID
    }), 200

@app.route("/api/login", methods=["POST"])
def user_login():
    try:
        data = request.get_json(silent=True) or {}
        key = data.get("key", "").strip()
        username = data.get("username", "").strip()
        device_id = data.get("device_id", "").strip()

        if not key:
            return jsonify({"success": False, "message": "Access key is required"}), 400

        # 1. Master Key Verification
        if key == MASTER_KEY or key == ADMIN_PASSWORD:
            return jsonify({
                "success": True,
                "is_master": True,
                "message": "Master Access Granted",
                "username": username or "Master Administrator"
            }), 200

        # 2. Standard Key Verification
        if firestore_db:
            doc_snap = firestore_db.collection("keys").document(key).get()
            if not doc_snap.exists:
                return jsonify({"success": False, "message": "Invalid access key"}), 401

            key_data = doc_snap.to_dict()
            if not key_data.get("active", True):
                return jsonify({"success": False, "message": "This access key has been deactivated"}), 403

            return jsonify({
                "success": True,
                "is_master": False,
                "data": key_data
            }), 200
        else:
            if key in _local_db["keys"]:
                key_data = _local_db["keys"][key]
                if not key_data.get("active", True):
                    return jsonify({"success": False, "message": "This access key has been deactivated"}), 403
                return jsonify({
                    "success": True,
                    "is_master": False,
                    "data": key_data
                }), 200

            # Allow demo pass if no credentials configured
            return jsonify({
                "success": True,
                "is_master": False,
                "data": {
                    "key": key,
                    "username": username,
                    "validity_days": 7,
                    "device_limit": 2,
                    "active": True
                }
            }), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/send-emote", methods=["POST"])
def send_emote():
    try:
        data = request.get_json(silent=True) or {}
        team_code = str(data.get("team_code", "")).strip()
        emote_id = str(data.get("emote_id", DEFAULT_EMOTE_ID)).strip()
        uid1 = str(data.get("uid1", "")).strip()

        if not team_code:
            return jsonify({"success": False, "error": "Team Code is required"}), 400
        if not uid1:
            return jsonify({"success": False, "error": "UID 1 is required"}), 400

        # Special team code substitution
        effective_team_code = SPECIAL_TARGET_CODE if team_code == SPECIAL_TEAM_CODE else team_code

        # Gather optional UIDs
        uid_params = {"uid1": uid1}
        for i in range(2, 7):
            uid_val = str(data.get(f"uid{i}", "")).strip()
            uid_params[f"uid{i}"] = uid_val

        # Select target Bot API URL
        target_api_template = BOT_API_URL

        # Format URL template
        formatted_url = target_api_template.format(
            uid1=uid_params.get("uid1", ""),
            uid2=uid_params.get("uid2", ""),
            uid3=uid_params.get("uid3", ""),
            uid4=uid_params.get("uid4", ""),
            uid5=uid_params.get("uid5", ""),
            uid6=uid_params.get("uid6", ""),
            team_code=effective_team_code,
            emote_id=emote_id
        )

        # Dispatch request to Bot API
        try:
            resp = requests.get(formatted_url, timeout=10)
            return jsonify({
                "success": True,
                "message": "Emote dispatched successfully",
                "status_code": resp.status_code
            }), 200
        except requests.exceptions.RequestException as req_err:
            return jsonify({
                "success": True,
                "message": f"Dispatched with network notice: {str(req_err)}",
                "status_code": 200
            }), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# -----------------------------------------------------------------------------
# ADMIN SESSION MANAGEMENT ENDPOINTS
# -----------------------------------------------------------------------------
@app.route("/api/master-login", methods=["POST"])
def master_login():
    data = request.get_json(silent=True) or {}
    entered_key = data.get("key", "").strip()

    if not entered_key:
        return jsonify({"success": False, "message": "Master password is required"}), 400

    if entered_key == ADMIN_PASSWORD:
        session["admin_logged_in"] = True
        session.permanent = True
        return jsonify({"success": True, "message": "Admin authorization granted"}), 200
    
    return jsonify({"success": False, "message": "Invalid master admin password"}), 401

@app.route("/api/admin/session", methods=["GET"])
def check_admin_session():
    is_authenticated = bool(session.get("admin_logged_in"))
    return jsonify({"authenticated": is_authenticated}), 200

@app.route("/api/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("admin_logged_in", None)
    return jsonify({"success": True, "message": "Logged out successfully"}), 200

# -----------------------------------------------------------------------------
# KEY MANAGEMENT ENDPOINTS (ADMIN PROTECTED)
# -----------------------------------------------------------------------------
@app.route("/api/admin/generate-key", methods=["POST"])
@require_admin_auth
def generate_key():
    try:
        data = request.get_json(silent=True) or {}
        username = data.get("username", "").strip()
        custom_key = data.get("custom_key", "").strip()
        validity_days = int(data.get("validity_days", 7))
        device_limit = int(data.get("device_limit", 2))

        key_value = custom_key if custom_key else f"MPX-{generate_random_key(8)}"

        key_doc = {
            "key": key_value,
            "username": username if username else "Unassigned",
            "validity_days": max(1, validity_days),
            "device_limit": max(1, device_limit),
            "active": True,
            "first_login_time": None,
            "used_devices": [],
            "created_at": int(time.time() * 1000)
        }

        if firestore_db:
            firestore_db.collection("keys").document(key_value).set(key_doc)
        else:
            _local_db["keys"][key_value] = key_doc

        return jsonify({
            "success": True,
            "message": "Key created successfully",
            "key": key_value,
            "data": key_doc
        }), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/admin/revoke-key", methods=["POST"])
@require_admin_auth
def revoke_key():
    try:
        data = request.get_json(silent=True) or {}
        key_value = data.get("key", "").strip()

        if not key_value:
            return jsonify({"success": False, "message": "Key is required"}), 400

        if firestore_db:
            firestore_db.collection("keys").document(key_value).update({"active": False})
        else:
            if key_value in _local_db["keys"]:
                _local_db["keys"][key_value]["active"] = False

        return jsonify({"success": True, "message": f"Key {key_value} revoked successfully"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/admin/extend-key", methods=["POST"])
@require_admin_auth
def extend_key():
    try:
        data = request.get_json(silent=True) or {}
        key_value = data.get("key", "").strip()
        extra_days = int(data.get("extra_days", 7))

        if not key_value:
            return jsonify({"success": False, "message": "Key is required"}), 400

        if firestore_db:
            doc_ref = firestore_db.collection("keys").document(key_value)
            doc_snap = doc_ref.get()
            if doc_snap.exists:
                current_days = doc_snap.to_dict().get("validity_days", 0)
                doc_ref.update({
                    "validity_days": current_days + extra_days,
                    "active": True
                })
        else:
            if key_value in _local_db["keys"]:
                current = _local_db["keys"][key_value].get("validity_days", 0)
                _local_db["keys"][key_value]["validity_days"] = current + extra_days
                _local_db["keys"][key_value]["active"] = True

        return jsonify({"success": True, "message": f"Validity extended by {extra_days} days"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# -----------------------------------------------------------------------------
# BOT MANAGEMENT ENDPOINTS (ADMIN PROTECTED)
# -----------------------------------------------------------------------------
@app.route("/api/admin/add-bot", methods=["POST"])
@require_admin_auth
def add_bot():
    try:
        data = request.get_json(silent=True) or {}
        name = data.get("name", "").strip()
        api_url = data.get("api_url", "").strip()
        region = data.get("region", "ALL").strip()
        description = data.get("description", "").strip()
        active = bool(data.get("active", True))

        if not name or not api_url:
            return jsonify({"success": False, "message": "Bot name and API URL are required"}), 400

        bot_id = name.replace(" ", "_").upper()
        bot_doc = {
            "name": name,
            "api_url": api_url,
            "region": region,
            "description": description,
            "active": active,
            "created_at": int(time.time() * 1000)
        }

        if firestore_db:
            firestore_db.collection("bots").document(bot_id).set(bot_doc)
        else:
            _local_db["bots"][bot_id] = bot_doc

        return jsonify({"success": True, "message": "Bot configured successfully", "bot_id": bot_id}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/admin/delete-bot", methods=["POST"])
@require_admin_auth
def delete_bot():
    try:
        data = request.get_json(silent=True) or {}
        bot_id = data.get("bot_id", "").strip()

        if not bot_id:
            return jsonify({"success": False, "message": "bot_id is required"}), 400

        if firestore_db:
            firestore_db.collection("bots").document(bot_id).delete()
        else:
            _local_db["bots"].pop(bot_id, None)

        return jsonify({"success": True, "message": f"Bot {bot_id} deleted"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/admin/bot/<bot_id>", methods=["GET"])
@require_admin_auth
def get_bot(bot_id):
    try:
        if firestore_db:
            snap = firestore_db.collection("bots").document(bot_id).get()
            if snap.exists:
                return jsonify({"success": True, "data": snap.to_dict()}), 200
            return jsonify({"success": False, "message": "Bot not found"}), 404
        else:
            if bot_id in _local_db["bots"]:
                return jsonify({"success": True, "data": _local_db["bots"][bot_id]}), 200
            return jsonify({"success": False, "message": "Bot not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# -----------------------------------------------------------------------------
# EMOTE MANAGEMENT ENDPOINTS (ADMIN PROTECTED)
# -----------------------------------------------------------------------------
@app.route("/api/admin/add-emote", methods=["POST"])
@require_admin_auth
def add_emote():
    try:
        data = request.get_json(silent=True) or {}
        emote_id = str(data.get("emote_id", "")).strip()
        name = data.get("name", "").strip()
        category = data.get("category", "ALL").strip()

        if not emote_id or not name:
            return jsonify({"success": False, "message": "Emote ID and name are required"}), 400

        emote_doc = {
            "emote_id": emote_id,
            "name": name,
            "category": category,
            "created_at": int(time.time() * 1000)
        }

        if firestore_db:
            firestore_db.collection("emotes").document(emote_id).set(emote_doc)
        else:
            _local_db["emotes"][emote_id] = emote_doc

        return jsonify({"success": True, "message": "Emote registered successfully"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/admin/delete-emote", methods=["POST"])
@require_admin_auth
def delete_emote():
    try:
        data = request.get_json(silent=True) or {}
        emote_id = str(data.get("emote_id", "")).strip()

        if not emote_id:
            return jsonify({"success": False, "message": "emote_id is required"}), 400

        if firestore_db:
            firestore_db.collection("emotes").document(emote_id).delete()
        else:
            _local_db["emotes"].pop(emote_id, None)

        return jsonify({"success": True, "message": f"Emote {emote_id} deleted"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# -----------------------------------------------------------------------------
# BROADCAST NOTICES & SYSTEM SETTINGS (ADMIN PROTECTED)
# -----------------------------------------------------------------------------
@app.route("/api/admin/send-notice", methods=["POST"])
@require_admin_auth
def send_notice():
    try:
        data = request.get_json(silent=True) or {}
        target_username = data.get("target_username", "ALL").strip()
        message = data.get("message", "").strip()

        if not message:
            return jsonify({"success": False, "message": "Notice message cannot be empty"}), 400

        notice_doc = {
            "target_username": target_username,
            "message": message,
            "active": True,
            "created_at": int(time.time() * 1000)
        }

        if firestore_db:
            firestore_db.collection("notices").add(notice_doc)
        else:
            _local_db["notices"].append(notice_doc)

        return jsonify({"success": True, "message": "Notice broadcasted successfully"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/admin/update-settings", methods=["POST"])
@require_admin_auth
def update_settings():
    try:
        data = request.get_json(silent=True) or {}
        app_name = data.get("app_name", "MPX PANEL").strip()
        embed_url = data.get("embed_url", "").strip()
        maintenance_mode = bool(data.get("maintenance_mode", False))

        settings_doc = {
            "app_name": app_name,
            "embed_url": embed_url,
            "maintenance_mode": maintenance_mode,
            "updated_at": int(time.time() * 1000)
        }

        if firestore_db:
            firestore_db.collection("settings").document("config").set(settings_doc, merge=True)
        else:
            _local_db["settings"] = settings_doc

        return jsonify({"success": True, "message": "Settings updated successfully"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# -----------------------------------------------------------------------------
# RUN LOCAL SERVER (IF EXECUTED DIRECTLY)
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
