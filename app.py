import os
import time
import json
import base64
import secrets
import string
import datetime
import traceback
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

FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "mpxpanel")
FIREBASE_API_KEY = os.environ.get("FIREBASE_API_KEY", "AIzaSyAkAqyxA9sPjd7Dlr82LmWBYKO0WHi5KLI")
FIREBASE_CLIENT_EMAIL = os.environ.get("FIREBASE_CLIENT_EMAIL", "")
FIREBASE_PRIVATE_KEY = os.environ.get("FIREBASE_PRIVATE_KEY", "")
FIREBASE_SERVICE_ACCOUNT_KEY = os.environ.get("FIREBASE_SERVICE_ACCOUNT_KEY", "")

# -----------------------------------------------------------------------------
# FIRESTORE REST API CLIENT (FALLBACK & ZERO-CONFIG ENGINE)
# -----------------------------------------------------------------------------
FIRESTORE_REST_BASE = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/databases/(default)/documents"

def val_to_firestore_field(v):
    if v is None:
        return {"nullValue": None}
    elif isinstance(v, bool):
        return {"booleanValue": v}
    elif isinstance(v, int):
        return {"integerValue": str(v)}
    elif isinstance(v, float):
        return {"doubleValue": v}
    elif isinstance(v, str):
        return {"stringValue": v}
    elif isinstance(v, list):
        return {"arrayValue": {"values": [val_to_firestore_field(item) for item in v]}}
    elif isinstance(v, dict):
        return {"mapValue": {"fields": dict_to_firestore_fields(v)}}
    else:
        return {"stringValue": str(v)}

def dict_to_firestore_fields(d):
    fields = {}
    for k, v in d.items():
        fields[k] = val_to_firestore_field(v)
    return fields

def firestore_field_to_val(v):
    if "stringValue" in v:
        return v["stringValue"]
    if "integerValue" in v:
        return int(v["integerValue"])
    if "doubleValue" in v:
        return float(v["doubleValue"])
    if "booleanValue" in v:
        return v["booleanValue"]
    if "nullValue" in v:
        return None
    if "arrayValue" in v:
        return [firestore_field_to_val(item) for item in v["arrayValue"].get("values", [])]
    if "mapValue" in v:
        return firestore_fields_to_dict(v["mapValue"].get("fields", {}))
    if "timestampValue" in v:
        return v["timestampValue"]
    return None

def firestore_fields_to_dict(fields):
    res = {}
    for k, v in fields.items():
        res[k] = firestore_field_to_val(v)
    return res

def rest_get_doc(collection, doc_id):
    url = f"{FIRESTORE_REST_BASE}/{collection}/{doc_id}"
    params = {"key": FIREBASE_API_KEY} if FIREBASE_API_KEY else {}
    resp = requests.get(url, params=params, timeout=8)
    if resp.status_code == 200:
        data = resp.json()
        return firestore_fields_to_dict(data.get("fields", {}))
    return None

def rest_set_doc(collection, doc_id, data):
    url = f"{FIRESTORE_REST_BASE}/{collection}/{doc_id}"
    params = {"key": FIREBASE_API_KEY} if FIREBASE_API_KEY else {}
    payload = {"fields": dict_to_firestore_fields(data)}
    resp = requests.patch(url, params=params, json=payload, timeout=8)
    if resp.status_code not in [200, 201]:
        err_msg = ""
        try:
            err_msg = resp.json().get("error", {}).get("message", resp.text)
        except Exception:
            err_msg = resp.text
        print(f"Firestore REST PATCH Error ({resp.status_code}): {err_msg}")
        if resp.status_code == 403:
            raise Exception("Firebase Permission Denied (403). Please update your Firebase Console Security Rules to: allow read, write: if true;")
        raise Exception(f"Firebase Error ({resp.status_code}): {err_msg}")
    return True

def rest_add_doc(collection, data):
    url = f"{FIRESTORE_REST_BASE}/{collection}"
    params = {"key": FIREBASE_API_KEY} if FIREBASE_API_KEY else {}
    payload = {"fields": dict_to_firestore_fields(data)}
    resp = requests.post(url, params=params, json=payload, timeout=8)
    if resp.status_code not in [200, 201]:
        err_msg = ""
        try:
            err_msg = resp.json().get("error", {}).get("message", resp.text)
        except Exception:
            err_msg = resp.text
        print(f"Firestore REST POST Error ({resp.status_code}): {err_msg}")
        if resp.status_code == 403:
            raise Exception("Firebase Permission Denied (403). Please update your Firebase Console Security Rules to: allow read, write: if true;")
        raise Exception(f"Firebase Error ({resp.status_code}): {err_msg}")
    res_json = resp.json()
    doc_name = res_json.get("name", "")
    return doc_name.split("/")[-1] if "/" in doc_name else "doc"

def rest_delete_doc(collection, doc_id):
    url = f"{FIRESTORE_REST_BASE}/{collection}/{doc_id}"
    params = {"key": FIREBASE_API_KEY} if FIREBASE_API_KEY else {}
    resp = requests.delete(url, params=params, timeout=8)
    if resp.status_code not in [200, 204]:
        err_msg = ""
        try:
            err_msg = resp.json().get("error", {}).get("message", resp.text)
        except Exception:
            err_msg = resp.text
        print(f"Firestore REST DELETE Error ({resp.status_code}): {err_msg}")
        if resp.status_code == 403:
            raise Exception("Firebase Permission Denied (403). Please update your Firebase Console Security Rules to: allow read, write: if true;")
        raise Exception(f"Firebase Error ({resp.status_code}): {err_msg}")
    return True

def rest_get_collection(collection):
    url = f"{FIRESTORE_REST_BASE}/{collection}"
    params = {"key": FIREBASE_API_KEY} if FIREBASE_API_KEY else {}
    try:
        resp = requests.get(url, params=params, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            docs = []
            for doc_item in data.get("documents", []):
                doc_id = doc_item.get("name", "").split("/")[-1]
                fields = firestore_fields_to_dict(doc_item.get("fields", {}))
                fields["id"] = doc_id
                docs.append(fields)
            return docs
    except Exception as e:
        print(f"rest_get_collection error for {collection}:", e)
    return []

def format_bot_api_url(template, uid_params):
    import urllib.parse
    url = template
    for k, v in uid_params.items():
        url = url.replace(f"{{{k}}}", str(v))
        url = url.replace(f"{{{k.upper()}}}", str(v))

    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    managed_keys = ["uid1", "uid2", "uid3", "uid4", "uid5", "uid6", "team_code", "emote_id"]

    if qs:
        new_qs = {}
        for k, v_list in qs.items():
            k_lower = k.lower()
            if k_lower in uid_params:
                new_qs[k] = uid_params[k_lower]
            else:
                new_qs[k] = v_list[0] if v_list else ""
        for mk in managed_keys:
            if mk not in [k.lower() for k in new_qs.keys()]:
                new_qs[mk] = uid_params.get(mk, "")
        new_query = urllib.parse.urlencode(new_qs)
        return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
    else:
        query_parts = {mk: uid_params.get(mk, "") for mk in managed_keys}
        new_query = urllib.parse.urlencode(query_parts)
        return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))

# -----------------------------------------------------------------------------
# FIREBASE ADMIN SDK INITIALIZATION (SERVER-SIDE)
# -----------------------------------------------------------------------------
firestore_db = None

def initialize_firebase():
    global firestore_db
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        if firebase_admin._apps:
            firestore_db = firestore.client()
            return firestore_db

        cred = None

        # Strategy 1: Full JSON Service Account
        if FIREBASE_SERVICE_ACCOUNT_KEY:
            raw_json = FIREBASE_SERVICE_ACCOUNT_KEY.strip()
            if not raw_json.startswith("{"):
                try:
                    raw_json = base64.b64decode(raw_json).decode("utf-8")
                except Exception:
                    pass
            cert_dict = json.loads(raw_json)
            cred = credentials.Certificate(cert_dict)

        # Strategy 2: Client Email + Private Key
        elif FIREBASE_CLIENT_EMAIL and FIREBASE_PRIVATE_KEY:
            cleaned_key = FIREBASE_PRIVATE_KEY.strip()
            if cleaned_key.startswith('"') and cleaned_key.endswith('"'):
                cleaned_key = cleaned_key[1:-1]
            if cleaned_key.startswith("'") and cleaned_key.endswith("'"):
                cleaned_key = cleaned_key[1:-1]
            cleaned_key = cleaned_key.replace("\\n", "\n")

            cred = credentials.Certificate({
                "type": "service_account",
                "project_id": FIREBASE_PROJECT_ID,
                "private_key": cleaned_key,
                "client_email": FIREBASE_CLIENT_EMAIL,
                "token_uri": "https://oauth2.googleapis.com/token"
            })

        # Strategy 3: Local file
        elif os.path.exists("service-account.json"):
            cred = credentials.Certificate("service-account.json")

        if cred:
            firebase_admin.initialize_app(cred, {
                "projectId": FIREBASE_PROJECT_ID
            })
            firestore_db = firestore.client()
            print("Firebase Admin SDK initialized successfully with service credentials.")
        else:
            try:
                firebase_admin.initialize_app(options={"projectId": FIREBASE_PROJECT_ID})
                firestore_db = firestore.client()
                print("Firebase Admin SDK initialized with Application Default Credentials.")
            except Exception:
                firestore_db = None
                print("Firebase Admin credentials not set; using direct Firestore REST engine.")
    except Exception as e:
        firestore_db = None
        print("Firebase Admin SDK init notice (using REST engine):", str(e))

    return firestore_db

initialize_firebase()

def get_db():
    global firestore_db
    if firestore_db is None and (FIREBASE_CLIENT_EMAIL or FIREBASE_SERVICE_ACCOUNT_KEY):
        initialize_firebase()
    return firestore_db

# -----------------------------------------------------------------------------
# AUTHENTICATION DECORATOR & HELPER FUNCTIONS
# -----------------------------------------------------------------------------
def require_admin_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return jsonify({
                "success": False,
                "error": "Unauthorized",
                "message": "Unauthorized. Admin authentication required."
            }), 401
        return f(*args, **kwargs)
    return decorated_function

def generate_random_key(length=8):
    chars = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))

def get_timestamp():
    return int(time.time() * 1000)

# -----------------------------------------------------------------------------
# ROOT & ROUTING ENDPOINTS
# -----------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def root_route():
    if os.path.exists("index.html"):
        return send_from_directory(".", "index.html")
    return jsonify({"name": "MPX PANEL", "status": "running"}), 200

@app.route("/admin234", methods=["GET"])
def admin_route():
    if os.path.exists("admin.html"):
        return send_from_directory(".", "admin.html")
    return jsonify({"error": "admin.html not found"}), 404

@app.route("/admin.html", methods=["GET"])
def direct_admin_html():
    if os.path.exists("admin.html"):
        return send_from_directory(".", "admin.html")
    return jsonify({"error": "admin.html not found"}), 404

@app.route("/index.html", methods=["GET"])
def direct_index_html():
    if os.path.exists("index.html"):
        return send_from_directory(".", "index.html")
    return jsonify({"error": "index.html not found"}), 404

# -----------------------------------------------------------------------------
# USER PANEL BACKEND API ENDPOINTS
# -----------------------------------------------------------------------------
@app.route("/api/health", methods=["GET"])
def health_check():
    db = get_db()
    return jsonify({
        "status": "healthy",
        "app": "MPX PANEL Unified API",
        "time": time.time(),
        "firebase_project": FIREBASE_PROJECT_ID,
        "firebase_admin_sdk": db is not None,
        "firestore_rest_active": True
    }), 200

@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify({
        "uid_count": UID_COUNT,
        "default_emote_id": DEFAULT_EMOTE_ID,
        "uid_fields": [f"uid{i}" for i in range(1, UID_COUNT + 1)]
    }), 200

@app.route("/api/login", methods=["POST"])
def user_login():
    try:
        data = request.get_json(silent=True) or {}
        key = data.get("key", "").strip()
        username = data.get("username", "").strip()

        if not key:
            return jsonify({"success": False, "error": "Access key is required", "message": "Access key is required"}), 400

        # 1. Master Key Verification
        if key == MASTER_KEY or key == ADMIN_PASSWORD:
            return jsonify({
                "success": True,
                "is_master": True,
                "message": "Master Access Granted",
                "username": username or "Master Administrator"
            }), 200

        # 2. Database Key Verification (Admin SDK or REST)
        db = get_db()
        key_data = None
        if db is not None:
            doc_snap = db.collection("keys").document(key).get()
            if doc_snap.exists:
                key_data = doc_snap.to_dict()
        else:
            key_data = rest_get_doc("keys", key)

        if not key_data:
            return jsonify({"success": False, "error": "Invalid access key", "message": "Invalid access key"}), 401

        if not key_data.get("active", True):
            return jsonify({"success": False, "error": "Key deactivated", "message": "This access key has been deactivated"}), 403

        return jsonify({
            "success": True,
            "is_master": False,
            "data": key_data
        }), 200
    except Exception as e:
        print("Login Error:", str(e))
        return jsonify({"success": False, "error": str(e), "message": str(e)}), 500

@app.route("/api/send-emote", methods=["POST"])
def send_emote():
    try:
        data = request.get_json(silent=True) or {}
        team_code = str(data.get("team_code", "")).strip()
        emote_id = str(data.get("emote_id", DEFAULT_EMOTE_ID)).strip()
        bot_url_param = str(data.get("bot_url", "")).strip()
        bot_id_param = str(data.get("bot_id", "")).strip()

        if not team_code:
            return jsonify({"success": False, "error": "Team Code is required", "message": "Team Code is required"}), 400

        # Collect all 6 UIDs from request
        uid_list = []
        uid_dict = {}
        for i in range(1, 7):
            val = str(data.get(f"uid{i}", "")).strip()
            uid_dict[f"uid{i}"] = val
            if val:
                uid_list.append(val)

        if not uid_list:
            return jsonify({"success": False, "error": "At least one UID must be provided in any box", "message": "At least one UID must be provided in any box"}), 400

        primary_uid = uid_list[0]
        # Guarantee uid1 is populated with primary_uid if box 1 was left blank
        uid_params = {
            "uid1": uid_dict["uid1"] if uid_dict["uid1"] else primary_uid,
            "uid2": uid_dict["uid2"],
            "uid3": uid_dict["uid3"],
            "uid4": uid_dict["uid4"],
            "uid5": uid_dict["uid5"],
            "uid6": uid_dict["uid6"],
            "team_code": SPECIAL_TARGET_CODE if team_code == SPECIAL_TEAM_CODE else team_code,
            "emote_id": emote_id
        }

        # Select target BOT template URL
        target_template = BOT_API_URL
        if bot_url_param:
            target_template = bot_url_param
        elif bot_id_param and bot_id_param != "BOT-1":
            # Lookup custom bot URL from DB if available
            db = get_db()
            bot_doc = None
            if db is not None:
                snap = db.collection("bots").document(bot_id_param).get()
                if snap.exists:
                    bot_doc = snap.to_dict()
            else:
                bot_doc = rest_get_doc("bots", bot_id_param)

            if bot_doc and (bot_doc.get("api_url") or bot_doc.get("url")):
                target_template = bot_doc.get("api_url") or bot_doc.get("url")

        formatted_url = format_bot_api_url(target_template, uid_params)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        try:
            resp = requests.get(formatted_url, headers=headers, timeout=12)
            return jsonify({
                "success": True,
                "message": "Emote dispatched successfully",
                "status_code": resp.status_code,
                "bot_url_used": formatted_url
            }), 200
        except requests.exceptions.RequestException as req_err:
            return jsonify({
                "success": True,
                "message": f"Dispatched with network notice: {str(req_err)}",
                "status_code": 200,
                "bot_url_used": formatted_url
            }), 200

    except Exception as e:
        print("Send Emote Error:", str(e))
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e), "message": str(e)}), 500

# -----------------------------------------------------------------------------
# ADMIN SESSION MANAGEMENT ENDPOINTS
# -----------------------------------------------------------------------------
@app.route("/api/master-login", methods=["POST"])
def master_login():
    data = request.get_json(silent=True) or {}
    entered_key = data.get("key", "").strip()

    if not entered_key:
        return jsonify({"success": False, "error": "Master password is required", "message": "Master password is required"}), 400

    if entered_key == ADMIN_PASSWORD:
        session["admin_logged_in"] = True
        session.permanent = True
        return jsonify({"success": True, "message": "Admin authorization granted"}), 200
    
    return jsonify({"success": False, "error": "Invalid master password", "message": "Invalid master admin password"}), 401

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
            "created_at": get_timestamp()
        }

        db = get_db()
        success = False
        if db is not None:
            db.collection("keys").document(key_value).set(key_doc)
            success = True
        else:
            success = rest_set_doc("keys", key_value, key_doc)

        if not success:
            return jsonify({"success": False, "error": "Failed to write key to Firestore", "message": "Database write failed"}), 500

        return jsonify({
            "success": True,
            "message": "Key created successfully in Firestore",
            "key": key_value,
            "data": key_doc
        }), 200
    except Exception as e:
        print("Generate Key Error:", str(e))
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e), "message": str(e)}), 500

@app.route("/api/admin/revoke-key", methods=["POST"])
@require_admin_auth
def revoke_key():
    try:
        data = request.get_json(silent=True) or {}
        key_value = data.get("key", "").strip()

        if not key_value:
            return jsonify({"success": False, "error": "Key is required", "message": "Key is required"}), 400

        db = get_db()
        if db is not None:
            db.collection("keys").document(key_value).update({"active": False})
        else:
            existing = rest_get_doc("keys", key_value) or {"key": key_value}
            existing["active"] = False
            rest_set_doc("keys", key_value, existing)

        return jsonify({"success": True, "message": f"Key {key_value} revoked successfully"}), 200
    except Exception as e:
        print("Revoke Key Error:", str(e))
        return jsonify({"success": False, "error": str(e), "message": str(e)}), 500

@app.route("/api/admin/ban-key", methods=["POST"])
@require_admin_auth
def ban_key():
    try:
        data = request.get_json(silent=True) or {}
        key_value = data.get("key", "").strip()

        if not key_value:
            return jsonify({"success": False, "error": "Key is required", "message": "Key is required"}), 400

        db = get_db()
        if db is not None:
            db.collection("keys").document(key_value).update({"active": False})
        else:
            existing = rest_get_doc("keys", key_value) or {"key": key_value}
            existing["active"] = False
            rest_set_doc("keys", key_value, existing)

        return jsonify({"success": True, "message": f"User/Key {key_value} banned successfully"}), 200
    except Exception as e:
        print("Ban Key Error:", str(e))
        return jsonify({"success": False, "error": str(e), "message": str(e)}), 500

@app.route("/api/admin/unban-key", methods=["POST"])
@require_admin_auth
def unban_key():
    try:
        data = request.get_json(silent=True) or {}
        key_value = data.get("key", "").strip()

        if not key_value:
            return jsonify({"success": False, "error": "Key is required", "message": "Key is required"}), 400

        db = get_db()
        if db is not None:
            db.collection("keys").document(key_value).update({"active": True})
        else:
            existing = rest_get_doc("keys", key_value) or {"key": key_value}
            existing["active"] = True
            rest_set_doc("keys", key_value, existing)

        return jsonify({"success": True, "message": f"User/Key {key_value} unbanned successfully"}), 200
    except Exception as e:
        print("Unban Key Error:", str(e))
        return jsonify({"success": False, "error": str(e), "message": str(e)}), 500

@app.route("/api/admin/extend-key", methods=["POST"])
@require_admin_auth
def extend_key():
    try:
        data = request.get_json(silent=True) or {}
        key_value = data.get("key", "").strip()
        extra_days = int(data.get("extra_days", 7))

        if not key_value:
            return jsonify({"success": False, "error": "Key is required", "message": "Key is required"}), 400
        if extra_days <= 0:
            return jsonify({"success": False, "error": "Extra days must be greater than 0", "message": "Invalid extra days"}), 400

        db = get_db()
        new_days = extra_days
        if db is not None:
            doc_ref = db.collection("keys").document(key_value)
            doc_snap = doc_ref.get()
            if doc_snap.exists:
                current_days = int(doc_snap.to_dict().get("validity_days", 0))
                new_days = current_days + extra_days
                doc_ref.update({"validity_days": new_days, "active": True})
        else:
            existing = rest_get_doc("keys", key_value) or {}
            current_days = int(existing.get("validity_days", 0))
            new_days = current_days + extra_days
            existing["validity_days"] = new_days
            existing["active"] = True
            rest_set_doc("keys", key_value, existing)

        return jsonify({
            "success": True,
            "message": f"Validity extended by {extra_days} days (New Total: {new_days} days)",
            "validity_days": new_days
        }), 200
    except Exception as e:
        print("Extend Key Error:", str(e))
        return jsonify({"success": False, "error": str(e), "message": str(e)}), 500

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
            return jsonify({"success": False, "error": "Bot name and API URL are required", "message": "Bot name and API URL are required"}), 400

        bot_id = name.replace(" ", "_").upper()
        bot_doc = {
            "name": name,
            "api_url": api_url,
            "region": region,
            "description": description,
            "active": active,
            "created_at": get_timestamp()
        }

        db = get_db()
        if db is not None:
            db.collection("bots").document(bot_id).set(bot_doc)
        else:
            rest_set_doc("bots", bot_id, bot_doc)

        return jsonify({"success": True, "message": "Bot configured successfully", "bot_id": bot_id}), 200
    except Exception as e:
        print("Add Bot Error:", str(e))
        return jsonify({"success": False, "error": str(e), "message": str(e)}), 500

@app.route("/api/admin/delete-bot", methods=["POST"])
@require_admin_auth
def delete_bot():
    try:
        data = request.get_json(silent=True) or {}
        bot_id = data.get("bot_id", "").strip()

        if not bot_id:
            return jsonify({"success": False, "error": "bot_id is required", "message": "bot_id is required"}), 400

        db = get_db()
        if db is not None:
            db.collection("bots").document(bot_id).delete()
        else:
            rest_delete_doc("bots", bot_id)

        return jsonify({"success": True, "message": f"Bot {bot_id} deleted successfully"}), 200
    except Exception as e:
        print("Delete Bot Error:", str(e))
        return jsonify({"success": False, "error": str(e), "message": str(e)}), 500

@app.route("/api/admin/bot/<bot_id>", methods=["GET"])
@require_admin_auth
def get_bot(bot_id):
    try:
        db = get_db()
        if db is not None:
            snap = db.collection("bots").document(bot_id).get()
            if snap.exists:
                return jsonify({"success": True, "data": snap.to_dict()}), 200
        else:
            data = rest_get_doc("bots", bot_id)
            if data:
                return jsonify({"success": True, "data": data}), 200
        return jsonify({"success": False, "error": "Bot not found", "message": "Bot not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "message": str(e)}), 500

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
        image_url = data.get("image_url", "").strip()

        if not emote_id or not name:
            return jsonify({"success": False, "error": "Emote ID and name are required", "message": "Emote ID and name are required"}), 400

        if not image_url:
            image_url = f"https://cdn.jsdelivr.net/gh/ShahGCreator/icon@main/PNG/{emote_id}.png"

        emote_doc = {
            "emote_id": emote_id,
            "name": name,
            "category": category,
            "image_url": image_url,
            "created_at": get_timestamp()
        }

        db = get_db()
        if db is not None:
            db.collection("emotes").document(emote_id).set(emote_doc)
        else:
            rest_set_doc("emotes", emote_id, emote_doc)

        return jsonify({"success": True, "message": "Emote registered successfully", "emote_id": emote_id}), 200
    except Exception as e:
        print("Add Emote Error:", str(e))
        return jsonify({"success": False, "error": str(e), "message": str(e)}), 500

@app.route("/api/admin/delete-emote", methods=["POST"])
@require_admin_auth
def delete_emote():
    try:
        data = request.get_json(silent=True) or {}
        emote_id = str(data.get("emote_id", "")).strip()

        if not emote_id:
            return jsonify({"success": False, "error": "emote_id is required", "message": "emote_id is required"}), 400

        db = get_db()
        if db is not None:
            db.collection("emotes").document(emote_id).delete()
        else:
            rest_delete_doc("emotes", emote_id)

        return jsonify({"success": True, "message": f"Emote {emote_id} deleted successfully"}), 200
    except Exception as e:
        print("Delete Emote Error:", str(e))
        return jsonify({"success": False, "error": str(e), "message": str(e)}), 500

@app.route("/api/admin/update-emote", methods=["POST"])
@require_admin_auth
def update_emote():
    try:
        data = request.get_json(silent=True) or {}
        old_emote_id = str(data.get("old_emote_id", "")).strip()
        emote_id = str(data.get("emote_id", "")).strip()
        name = data.get("name", "").strip()
        category = data.get("category", "ALL").strip()
        image_url = data.get("image_url", "").strip()

        if not emote_id or not name:
            return jsonify({"success": False, "error": "Emote ID and name are required", "message": "Emote ID and name are required"}), 400

        if not image_url:
            image_url = f"https://cdn.jsdelivr.net/gh/ShahGCreator/icon@main/PNG/{emote_id}.png"

        emote_doc = {
            "emote_id": emote_id,
            "name": name,
            "category": category,
            "image_url": image_url,
            "updated_at": get_timestamp()
        }

        db = get_db()
        if db is not None:
            if old_emote_id and old_emote_id != emote_id:
                try:
                    db.collection("emotes").document(old_emote_id).delete()
                except Exception:
                    pass
            db.collection("emotes").document(emote_id).set(emote_doc, merge=True)
        else:
            if old_emote_id and old_emote_id != emote_id:
                try:
                    rest_delete_doc("emotes", old_emote_id)
                except Exception:
                    pass
            rest_set_doc("emotes", emote_id, emote_doc)

        return jsonify({"success": True, "message": "Emote updated successfully", "emote_id": emote_id}), 200
    except Exception as e:
        print("Update Emote Error:", str(e))
        return jsonify({"success": False, "error": str(e), "message": str(e)}), 500

@app.route("/api/admin/update-bot", methods=["POST"])
@require_admin_auth
def update_bot():
    try:
        data = request.get_json(silent=True) or {}
        old_bot_id = data.get("old_bot_id", "").strip()
        name = data.get("name", "").strip()
        api_url = data.get("api_url", "").strip()
        region = data.get("region", "ALL").strip()
        description = data.get("description", "").strip()
        active = bool(data.get("active", True))

        if not name or not api_url:
            return jsonify({"success": False, "error": "Bot name and API URL are required", "message": "Bot name and API URL are required"}), 400

        bot_id = name.replace(" ", "_").upper()
        bot_doc = {
            "name": name,
            "api_url": api_url,
            "region": region,
            "description": description,
            "active": active,
            "updated_at": get_timestamp()
        }

        db = get_db()
        if db is not None:
            if old_bot_id and old_bot_id != bot_id:
                try:
                    db.collection("bots").document(old_bot_id).delete()
                except Exception:
                    pass
            db.collection("bots").document(bot_id).set(bot_doc, merge=True)
        else:
            if old_bot_id and old_bot_id != bot_id:
                try:
                    rest_delete_doc("bots", old_bot_id)
                except Exception:
                    pass
            rest_set_doc("bots", bot_id, bot_doc)

        return jsonify({"success": True, "message": "Bot updated successfully", "bot_id": bot_id}), 200
    except Exception as e:
        print("Update Bot Error:", str(e))
        return jsonify({"success": False, "error": str(e), "message": str(e)}), 500

# -----------------------------------------------------------------------------
# CATEGORIES & REGIONS MANAGEMENT ENDPOINTS
# -----------------------------------------------------------------------------
@app.route("/api/categories", methods=["GET"])
def get_categories():
    try:
        db = get_db()
        categories = []
        if db is not None:
            docs = db.collection("categories").stream()
            for doc in docs:
                categories.append(doc.id)
        else:
            docs = rest_get_collection("categories")
            for doc in docs:
                categories.append(doc.get("id", doc.get("name", "")))
        if not categories:
            categories = ["ALL", "EVO", "OLD", "RARE", "POPULAR", "SPECIAL"]
        return jsonify({"success": True, "categories": sorted(list(set(categories)))}), 200
    except Exception as e:
        return jsonify({"success": True, "categories": ["ALL", "EVO", "OLD", "RARE", "POPULAR", "SPECIAL"]}), 200

@app.route("/api/admin/add-category", methods=["POST"])
@require_admin_auth
def add_category():
    try:
        data = request.get_json(silent=True) or {}
        name = data.get("name", "").strip().upper()
        if not name:
            return jsonify({"success": False, "error": "Category name required"}), 400

        db = get_db()
        if db is not None:
            db.collection("categories").document(name).set({"name": name, "created_at": get_timestamp()})
        else:
            rest_set_doc("categories", name, {"name": name, "created_at": get_timestamp()})
        return jsonify({"success": True, "message": f"Category {name} added", "name": name}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/admin/update-category", methods=["POST"])
@require_admin_auth
def update_category():
    try:
        data = request.get_json(silent=True) or {}
        old_name = data.get("old_name", "").strip().upper()
        new_name = data.get("new_name", "").strip().upper()
        if not old_name or not new_name:
            return jsonify({"success": False, "error": "Both old and new category name required"}), 400

        db = get_db()
        if db is not None:
            db.collection("categories").document(old_name).delete()
            db.collection("categories").document(new_name).set({"name": new_name, "created_at": get_timestamp()})
        else:
            rest_delete_doc("categories", old_name)
            rest_set_doc("categories", new_name, {"name": new_name, "created_at": get_timestamp()})
        return jsonify({"success": True, "message": f"Category renamed to {new_name}", "name": new_name}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/admin/delete-category", methods=["POST"])
@require_admin_auth
def delete_category():
    try:
        data = request.get_json(silent=True) or {}
        name = data.get("name", "").strip().upper()
        if not name:
            return jsonify({"success": False, "error": "Category name required"}), 400

        db = get_db()
        if db is not None:
            db.collection("categories").document(name).delete()
        else:
            rest_delete_doc("categories", name)
        return jsonify({"success": True, "message": f"Category {name} deleted"}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/regions", methods=["GET"])
def get_regions():
    try:
        db = get_db()
        regions = []
        if db is not None:
            docs = db.collection("regions").stream()
            for doc in docs:
                regions.append(doc.id)
        else:
            docs = rest_get_collection("regions")
            for doc in docs:
                regions.append(doc.get("id", doc.get("name", "")))
        if not regions:
            regions = ["BD", "IND", "Sylhet", "PK", "BR", "US", "Other"]
        return jsonify({"success": True, "regions": sorted(list(set(regions)))}), 200
    except Exception as e:
        return jsonify({"success": True, "regions": ["BD", "IND", "Sylhet", "PK", "BR", "US", "Other"]}), 200

@app.route("/api/admin/add-region", methods=["POST"])
@require_admin_auth
def add_region():
    try:
        data = request.get_json(silent=True) or {}
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"success": False, "error": "Region name required"}), 400

        db = get_db()
        if db is not None:
            db.collection("regions").document(name).set({"name": name, "created_at": get_timestamp()})
        else:
            rest_set_doc("regions", name, {"name": name, "created_at": get_timestamp()})
        return jsonify({"success": True, "message": f"Region {name} added", "name": name}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/admin/update-region", methods=["POST"])
@require_admin_auth
def update_region():
    try:
        data = request.get_json(silent=True) or {}
        old_name = data.get("old_name", "").strip()
        new_name = data.get("new_name", "").strip()
        if not old_name or not new_name:
            return jsonify({"success": False, "error": "Both old and new region name required"}), 400

        db = get_db()
        if db is not None:
            db.collection("regions").document(old_name).delete()
            db.collection("regions").document(new_name).set({"name": new_name, "created_at": get_timestamp()})
        else:
            rest_delete_doc("regions", old_name)
            rest_set_doc("regions", new_name, {"name": new_name, "created_at": get_timestamp()})
        return jsonify({"success": True, "message": f"Region renamed to {new_name}", "name": new_name}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/admin/delete-region", methods=["POST"])
@require_admin_auth
def delete_region():
    try:
        data = request.get_json(silent=True) or {}
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"success": False, "error": "Region name required"}), 400

        db = get_db()
        if db is not None:
            db.collection("regions").document(name).delete()
        else:
            rest_delete_doc("regions", name)
        return jsonify({"success": True, "message": f"Region {name} deleted"}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

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
            return jsonify({"success": False, "error": "Notice message cannot be empty", "message": "Notice message cannot be empty"}), 400

        notice_doc = {
            "target_username": target_username,
            "message": message,
            "active": True,
            "created_at": get_timestamp()
        }

        db = get_db()
        notice_id = "notice_" + generate_random_key(6)
        if db is not None:
            _, doc_ref = db.collection("notices").add(notice_doc)
            notice_id = doc_ref.id
        else:
            rest_add_doc("notices", notice_doc)

        return jsonify({"success": True, "message": "Notice broadcasted successfully", "notice_id": notice_id}), 200
    except Exception as e:
        print("Send Notice Error:", str(e))
        return jsonify({"success": False, "error": str(e), "message": str(e)}), 500

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
            "updated_at": get_timestamp()
        }

        db = get_db()
        if db is not None:
            db.collection("settings").document("config").set(settings_doc, merge=True)
        else:
            rest_set_doc("settings", "config", settings_doc)

        return jsonify({"success": True, "message": "Settings updated successfully"}), 200
    except Exception as e:
        print("Update Settings Error:", str(e))
        return jsonify({"success": False, "error": str(e), "message": str(e)}), 500

# -----------------------------------------------------------------------------
# RUN LOCAL SERVER (IF EXECUTED DIRECTLY)
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
