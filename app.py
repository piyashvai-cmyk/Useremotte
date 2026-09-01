import os
import re
import time
import json
import logging
from urllib.parse import quote_plus
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("mpx-panel")

app = Flask(__name__, static_folder="public", static_url_path="")
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Environment Variables & Defaults
MASTER_KEY = os.environ.get("MASTER_KEY", "7XMARUF10XPIYASH")
DEFAULT_BOT_API = "https://maruf-king.onrender.com/app/5050/emote?uid1={uid1}&uid2={uid2}&uid3={uid3}&uid4={uid4}&uid5={uid5}&uid6={uid6}&team_code={team_code}&emote_id={emote_id}"
BOT_API_URL = os.environ.get("BOT_API_URL", DEFAULT_BOT_API)
SPECIAL_TEAM_CODE = os.environ.get("SPECIAL_TEAM_CODE", "1694161")
SPECIAL_TARGET_CODE = os.environ.get("SPECIAL_TARGET_CODE", "3859281")
DEFAULT_EMOTE_ID = os.environ.get("DEFAULT_EMOTE_ID", "909000063")
DEFAULT_UID_COUNT = int(os.environ.get("UID_COUNT", "6"))


@app.route("/")
def serve_index():
    """Serve index.html at root."""
    if os.path.exists("index.html"):
        return send_from_directory(".", "index.html")
    return send_from_directory("public", "index.html")


@app.route("/api/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return jsonify({
        "success": True,
        "service": "MPX PANEL API"
    }), 200


@app.route("/api/config", methods=["GET"])
def get_config():
    """Return safe public configuration for UID fields without exposing backend API URLs."""
    uid_fields = [f"uid{i}" for i in range(1, DEFAULT_UID_COUNT + 1)]
    return jsonify({
        "success": True,
        "uid_count": DEFAULT_UID_COUNT,
        "uid_fields": uid_fields,
        "default_emote_id": DEFAULT_EMOTE_ID
    }), 200


@app.route("/api/login", methods=["POST"])
def verify_login():
    """
    Secure server-side authentication check.
    Validates master key without ever exposing it to client-side code.
    """
    try:
        data = request.get_json(silent=True) or {}
        username = str(data.get("username", "")).strip()
        key = str(data.get("key", "")).strip()
        device_id = str(data.get("device_id", "")).strip()

        if not key:
            return jsonify({
                "success": False,
                "error": "Access Key is required."
            }), 400

        # Check Master Key
        if key == MASTER_KEY:
            logger.info("Master Key authentication successful for user: %s", username or "Master")
            return jsonify({
                "success": True,
                "is_master": True,
                "username": username or "Master Admin",
                "validity_days": 99999,
                "message": "Master Access Granted"
            }), 200

        # Normal key authentication response
        return jsonify({
            "success": True,
            "is_master": False,
            "username": username,
            "device_id": device_id,
            "message": "Proceed with key verification"
        }), 200

    except Exception as e:
        logger.error("Login verification error: %s", str(e))
        return jsonify({
            "success": False,
            "error": "Authentication processing error."
        }), 500


def build_external_api_url(template: str, team_code: str, emote_id: str, uids: dict) -> str:
    """Build external Bot API URL with safe parameter encoding."""
    url = template
    url = re.sub(r"\{team_code\}", quote_plus(team_code), url, flags=re.IGNORECASE)
    url = re.sub(r"\{emote_id\}", quote_plus(emote_id), url, flags=re.IGNORECASE)

    for i in range(1, 100):
        key = f"uid{i}"
        val = uids.get(key, "")
        url = re.sub(rf"\{{{key}\}}", quote_plus(val), url, flags=re.IGNORECASE)

    return url


def execute_bot_request(target_url: str):
    """Execute GET request to external bot API with timeout and safe response parsing."""
    headers = {
        "User-Agent": "MPX-PANEL-Proxy/2.5 (HighSpeed Engine)"
    }
    response = requests.get(target_url, headers=headers, timeout=30)
    response.raise_for_status()

    # Try parsing JSON
    try:
        json_data = response.json()
        return json_data
    except Exception:
        # Fallback text parsing
        raw_text = response.text.strip()
        if "success" in raw_text.lower() and "true" in raw_text.lower():
            return {"success": True, "raw": raw_text}
        return {"success": True, "message": raw_text}


@app.route("/api/send-emote", methods=["POST"])
def send_emote():
    """
    Proxy endpoint for sending emotes.
    Solves browser CORS issues and protects backend Bot API secrets.
    """
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({
                "success": False,
                "error": "Invalid JSON payload."
            }), 400

        team_code = str(data.get("team_code", "")).strip()
        emote_id = str(data.get("emote_id", "")).strip() or DEFAULT_EMOTE_ID

        # Validation: Team Code
        if not team_code:
            return jsonify({
                "success": False,
                "error": "Team Code is required"
            }), 400

        # Validation: Emote ID
        if not emote_id:
            return jsonify({
                "success": False,
                "error": "Emote ID is required"
            }), 400

        # Collect UIDs
        uids = {}
        has_uid = False
        for i in range(1, 100):
            key = f"uid{i}"
            val = str(data.get(key, "")).strip()
            uids[key] = val
            if val:
                has_uid = True

        # Validation: At least one UID required
        if not has_uid:
            return jsonify({
                "success": False,
                "error": "At least one UID required (uid1, uid2, ...)"
            }), 400

        # UID1 specific check if provided in data
        if "uid1" in data and not uids.get("uid1"):
            return jsonify({
                "success": False,
                "error": "UID 1 is required."
            }), 400

        # Special Team Code Handling
        if team_code == SPECIAL_TEAM_CODE:
            logger.info("Executing special team sequence for code %s", SPECIAL_TEAM_CODE)
            
            # Step 1: First request with SPECIAL_TEAM_CODE
            first_url = build_external_api_url(BOT_API_URL, SPECIAL_TEAM_CODE, emote_id, uids)
            result1 = execute_bot_request(first_url)

            # Wait 2 seconds
            time.sleep(2)

            # Step 2: Second request with SPECIAL_TARGET_CODE
            second_url = build_external_api_url(BOT_API_URL, SPECIAL_TARGET_CODE, emote_id, uids)
            result2 = execute_bot_request(second_url)

            return jsonify({
                "success": True,
                "emote_id": emote_id,
                "team_code": team_code,
                "special_sequence": True,
                "results": result2.get("results", result1.get("results", []))
            }), 200

        # Standard Single Request
        final_url = build_external_api_url(BOT_API_URL, team_code, emote_id, uids)
        result = execute_bot_request(final_url)

        # Check if the external bot returned an explicit error
        if isinstance(result, dict):
            if result.get("success") is False or "error" in result:
                error_msg = result.get("error") or result.get("message") or "Emote send failed on Bot server."
                return jsonify({
                    "success": False,
                    "error": error_msg
                }), 400

            return jsonify({
                "success": True,
                "emote_id": emote_id,
                "team_code": team_code,
                "results": result.get("results", [])
            }), 200

        return jsonify({
            "success": True,
            "emote_id": emote_id,
            "team_code": team_code,
            "results": []
        }), 200

    except requests.exceptions.Timeout:
        logger.error("Bot API timed out")
        return jsonify({
            "success": False,
            "error": "Bot API request timed out. Please try again."
        }), 504

    except requests.exceptions.RequestException as req_err:
        logger.error("Bot API request error: %s", str(req_err))
        return jsonify({
            "success": False,
            "error": "Unable to connect to Bot API service."
        }), 502

    except Exception as e:
        logger.error("Unexpected server error in send_emote: %s", str(e))
        return jsonify({
            "success": False,
            "error": "Internal server error occurred."
        }), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
