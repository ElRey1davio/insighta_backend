from functools import wraps
from flask import request, jsonify
import jwt
from config import JWT_SECRET
import sqlite3

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
        
        if not token:
            return jsonify({"status": "error", "message": "Authentication required"}), 401
        
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            request.user_id = payload["user_id"]
            request.user_role = payload["role"]
            
            # Check if user is active
            conn = sqlite3.connect("profiles.db")
            cursor = conn.cursor()
            cursor.execute("SELECT is_active FROM users WHERE id = ?", (request.user_id,))
            user = cursor.fetchone()
            conn.close()
            if not user or user[0] == 0:
                return jsonify({"status": "error", "message": "Account deactivated"}), 403
                
        except jwt.ExpiredSignatureError:
            return jsonify({"status": "error", "message": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"status": "error", "message": "Invalid token"}), 401
        
        return f(*args, **kwargs)
    return decorated

def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.user_role != "admin":
            return jsonify({"status": "error", "message": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated

def require_version(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        version = request.headers.get("X-API-Version")
        if not version:
            return jsonify({"status": "error", "message": "API version header required"}), 400
        return f(*args, **kwargs)
    return decorated