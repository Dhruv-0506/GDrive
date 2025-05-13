from flask import Flask, request, jsonify, redirect
import logging
import requests
import time
from urllib.parse import urlencode
from google.oauth2.credentials import Credentials as OAuthCredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import mimetypes
import os

app = Flask(__name__)

# --- Logging ---
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# --- OAuth Config ---
CLIENT_ID = "26763482887-coiufpukc1l69aaulaiov5o0u3en2del.apps.googleusercontent.com"
CLIENT_SECRET = "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"
REDIRECT_URI = "https://serverless.on-demand.io/apps/googlesheets/auth/callback"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REQUEST_TIMEOUT = 30

# --- Start OAuth Flow ---
@app.route("/auth")
def auth():
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent"
    }
    return redirect(f"{AUTH_URL}?{urlencode(params)}")

# --- Handle OAuth Callback ---
@app.route("/auth/callback")
def auth_callback():
    code = request.args.get("code")
    if not code:
        return jsonify({"error": "Missing authorization code"}), 400

    payload = {
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code"
    }

    try:
        res = requests.post(TOKEN_URL, data=payload, timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        return jsonify(res.json())  # access_token + refresh_token
    except requests.RequestException as e:
        logger.error(f"Token exchange failed: {str(e)}")
        return jsonify({"error": "Token exchange failed"}), 500

# --- Refresh Access Token ---
def get_access_token(refresh_token):
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token"
    }
    res = requests.post(TOKEN_URL, data=payload, timeout=REQUEST_TIMEOUT)
    res.raise_for_status()
    return res.json()["access_token"]

# --- Drive Service ---
def get_drive_service(access_token):
    creds = OAuthCredentials(token=access_token)
    return build('drive', 'v3', credentials=creds)

# --- Create Folder ---
@app.route("/drive/create-folder", methods=["POST"])
def create_folder():
    data = request.json
    refresh_token = data.get("refresh_token")
    folder_name = data.get("name")

    if not refresh_token or not folder_name:
        return jsonify({"error": "Missing fields"}), 400

    try:
        access_token = get_access_token(refresh_token)
        service = get_drive_service(access_token)

        file_metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder"
        }
        folder = service.files().create(body=file_metadata, fields="id, name").execute()
        return jsonify(folder)
    except Exception as e:
        logger.error(str(e))
        return jsonify({"error": "Failed to create folder"}), 500

# --- Upload File to Folder ---
@app.route("/drive/upload", methods=["POST"])
def upload_file():
    refresh_token = request.form.get("refresh_token")
    folder_id = request.form.get("folder_id")
    file = request.files.get("file")

    if not refresh_token or not folder_id or not file:
        return jsonify({"error": "Missing fields"}), 400

    try:
        access_token = get_access_token(refresh_token)
        service = get_drive_service(access_token)

        mime_type = mimetypes.guess_type(file.filename)[0] or "application/octet-stream"
        file_metadata = {
            "name": file.filename,
            "parents": [folder_id]
        }

        media = {
            "body": file.stream,
            "mimeType": mime_type
        }

        uploaded_file = service.files().create(
            body=file_metadata,
            media_body=file,
            fields="id, name, parents"
        ).execute()
        return jsonify(uploaded_file)
    except Exception as e:
        logger.error(str(e))
        return jsonify({"error": "Failed to upload file"}), 500

# --- Rename File ---
@app.route("/drive/rename", methods=["POST"])
def rename_file():
    data = request.json
    refresh_token = data.get("refresh_token")
    file_id = data.get("file_id")
    new_name = data.get("new_name")

    if not refresh_token or not file_id or not new_name:
        return jsonify({"error": "Missing fields"}), 400

    try:
        access_token = get_access_token(refresh_token)
        service = get_drive_service(access_token)

        updated_file = service.files().update(
            fileId=file_id,
            body={"name": new_name},
            fields="id, name"
        ).execute()
        return jsonify(updated_file)
    except Exception as e:
        logger.error(str(e))
        return jsonify({"error": "Failed to rename file"}), 500

# --- Main ---
if __name__ == "__main__":
    app.run(debug=True)
