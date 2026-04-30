import requests
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from datetime import datetime, timezone, timedelta
import sqlite3
import uuid6
import json
from models import init_db, seed_db
from middleware import require_auth, require_admin, require_version
import math
import io
import csv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import time
from config import JWT_SECRET
import jwt


app = Flask(__name__)
CORS(app, supports_credentials=True)
init_db()
seed_db()

from auth import auth_bp
app.register_blueprint(auth_bp)

limiter = Limiter(get_remote_address, app=app, default_limits=["60/minute"])
limiter.limit("10/minute")(auth_bp)


@app.before_request
def log_request_start():
    request.start_time = time.time()


@app.after_request
def log_request(response):
    duration = time.time() - getattr(request, 'start_time', time.time())
    app.logger.info(f"{request.method} {request.path} {response.status_code} {duration:.3f}s")
    return response


COUNTRY_MAP = {
    "nigeria": "NG", "kenya": "KE", "uganda": "UG", "tanzania": "TZ",
    "ghana": "GH", "ethiopia": "ET", "sudan": "SD", "angola": "AO",
    "mozambique": "MZ", "cameroon": "CM", "mali": "ML", "senegal": "SN",
    "benin": "BJ", "rwanda": "RW", "somalia": "SO", "zambia": "ZM",
    "zimbabwe": "ZW", "chad": "TD", "guinea": "GN", "south africa": "ZA",
    "ivory coast": "CI", "niger": "NE", "burkina faso": "BF",
    "malawi": "MW", "togo": "TG", "sierra leone": "SL", "libya": "LY",
    "congo": "CG", "liberia": "LR", "mauritania": "MR", "eritrea": "ER",
    "gambia": "GM", "botswana": "BW", "namibia": "NA", "gabon": "GA",
    "lesotho": "LS", "guinea-bissau": "GW", "equatorial guinea": "GQ",
    "mauritius": "MU", "eswatini": "SZ", "djibouti": "DJ",
    "comoros": "KM", "cape verde": "CV", "sao tome": "ST",
    "seychelles": "SC", "egypt": "EG", "morocco": "MA", "tunisia": "TN",
    "algeria": "DZ", "madagascar": "MG"
}


def parse_natural_query(q):
    words = q.lower().split()
    filters = {}

    if "young" in words:
        filters["min_age"] = 16
        filters["max_age"] = 24
    if "child" in words or "children" in words:
        filters["age_group"] = "child"
    if "teenager" in words or "teenagers" in words:
        filters["age_group"] = "teenager"
    if "adult" in words or "adults" in words:
        filters["age_group"] = "adult"
    if "senior" in words or "seniors" in words:
        filters["age_group"] = "senior"

    for i, word in enumerate(words):
        if word in ("above", "over") and i + 1 < len(words):
            try:
                filters["min_age"] = int(words[i + 1])
            except ValueError:
                pass
        if word in ("below", "under") and i + 1 < len(words):
            try:
                filters["max_age"] = int(words[i + 1])
            except ValueError:
                pass

    if "from" in words:
        from_index = words.index("from")
        remaining = " ".join(words[from_index + 1:])
        for country_name, code in COUNTRY_MAP.items():
            if country_name in remaining:
                filters["country_id"] = code
                break

    has_male = "male" in words or "males" in words
    has_female = "female" in words or "females" in words
    if has_male and not has_female:
        filters["gender"] = "male"
    elif has_female and not has_male:
        filters["gender"] = "female"

    return filters


@app.route("/api/users/me", methods=["GET"])
@require_auth
def get_current_user():
    conn = sqlite3.connect("profiles.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, github_id, username, email, avatar_url, role, is_active, last_login_at, created_at FROM users WHERE id = ?", (request.user_id,))
    user = cursor.fetchone()
    conn.close()
    if not user:
        return jsonify({"status": "error", "message": "User not found"}), 404
    return jsonify({
        "status": "success",
        "data": {
            "id": user[0],
            "github_id": user[1],
            "username": user[2],
            "email": user[3],
            "avatar_url": user[4],
            "role": user[5],
            "is_active": bool(user[6]),
            "last_login_at": user[7],
            "created_at": user[8]
        }
    }), 200


@app.route("/api/profiles", methods=["POST"])
@require_auth
@require_admin
@require_version
def check():
    data = request.get_json()
    if not data or "name" not in data:
        return jsonify({"status": "error", "message": "Missing or empty name"}), 400

    name = data.get("name")

    if not isinstance(name, str):
        return jsonify({"status": "error", "message": "Invalid type"}), 422

    if not name.strip():
        return jsonify({"status": "error", "message": "Missing or empty name"}), 400

    conn = sqlite3.connect("profiles.db")
    c = conn.cursor()
    c.execute("SELECT * FROM profiles WHERE name = ?", (name.lower(),))
    existing = c.fetchone()
    if existing:
        conn.close()
        return jsonify({"status": "success", "message": "Profile already exists", "data": format_row(existing)}), 200

    try:
        gender_response = requests.get(f"https://api.genderize.io/?name={name}", timeout=10)
        age_response = requests.get(f"https://api.agify.io/?name={name}", timeout=10)
        nation_response = requests.get(f"https://api.nationalize.io/?name={name}", timeout=10)

        if gender_response.status_code != 200:
            conn.close()
            return jsonify({"status": "error", "message": "Genderize returned an invalid response"}), 502
        if age_response.status_code != 200:
            conn.close()
            return jsonify({"status": "error", "message": "Agify returned an invalid response"}), 502
        if nation_response.status_code != 200:
            conn.close()
            return jsonify({"status": "error", "message": "Nationalize returned an invalid response"}), 502

        genderize = gender_response.json()
        agify = age_response.json()
        nationalize = nation_response.json()
    except Exception:
        conn.close()
        return jsonify({"status": "error", "message": "Upstream server failure"}), 502

    if genderize.get("gender") is None or genderize.get("count") == 0:
        conn.close()
        return jsonify({"status": "error", "message": "Genderize returned an invalid response"}), 502
    if agify.get("age") is None:
        conn.close()
        return jsonify({"status": "error", "message": "Agify returned an invalid response"}), 502
    if not nationalize.get("country") or len(nationalize.get("country")) == 0:
        conn.close()
        return jsonify({"status": "error", "message": "Nationalize returned an invalid response"}), 502

    age = agify["age"]
    if age <= 12:
        age_group = "child"
    elif age <= 19:
        age_group = "teenager"
    elif age <= 59:
        age_group = "adult"
    else:
        age_group = "senior"

    top_country = max(nationalize["country"], key=lambda x: x["probability"])

    profile_id = str(uuid6.uuid7())
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    c.execute('''
        INSERT INTO profiles (id, name, gender, gender_probability, age, age_group, country_id, country_name, country_probability, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (profile_id, name.lower(), genderize["gender"], genderize["probability"], age, age_group, top_country["country_id"], top_country["country_name"], top_country["probability"], created_at))

    conn.commit()
    conn.close()

    return jsonify({
        "status": "success",
        "data": {
            "id": profile_id,
            "name": name.lower(),
            "gender": genderize["gender"],
            "gender_probability": genderize["probability"],
            "age": age,
            "age_group": age_group,
            "country_id": top_country["country_id"],
            "country_name": top_country["country_name"],
            "country_probability": top_country["probability"],
            "created_at": created_at
        }
    }), 201


@app.route("/api/profiles/search", methods=["GET"])
@require_auth
@require_version
def search_profiles():
    q = request.args.get('q')
    if not q:
        return jsonify({"status": "error", "message": "Missing or empty query"}), 400

    filters = parse_natural_query(q)
    if not filters:
        return jsonify({"status": "error", "message": "Unable to interpret query"}), 400

    conn = sqlite3.connect("profiles.db")
    c = conn.cursor()
    query = "SELECT * FROM profiles WHERE 1=1"
    params = []

    try:
        if "gender" in filters:
            query += " AND gender = ?"
            params.append(filters["gender"])
        if "min_age" in filters:
            query += " AND age >= ?"
            params.append(filters["min_age"])
        if "max_age" in filters:
            query += " AND age <= ?"
            params.append(filters["max_age"])
        if "age_group" in filters:
            query += " AND age_group = ?"
            params.append(filters["age_group"])
        if "country_id" in filters:
            query += " AND country_id = ?"
            params.append(filters["country_id"])
    except ValueError:
        conn.close()
        return jsonify({"status": "error", "message": "Invalid query parameters"}), 422

    count_query = query.replace("SELECT *", "SELECT COUNT(*)")
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
    except ValueError:
        conn.close()
        return jsonify({"status": "error", "message": "Invalid query parameters"}), 422

    if page < 1 or limit < 1:
        conn.close()
        return jsonify({"status": "error", "message": "Invalid query parameters"}), 422
    if limit > 50:
        limit = 50

    offset = (page - 1) * limit

    c.execute(count_query, params)
    total = c.fetchone()[0]

    query += " LIMIT ? OFFSET ?"
    params.append(limit)
    params.append(offset)

    c.execute(query, params)
    rows = c.fetchall()
    conn.close()

    profiles_list = [format_row(row) for row in rows]
    total_pages = math.ceil(total / limit)

    return jsonify({
        "status": "success",
        "page": page,
        "limit": limit,
        "total": total,
        "total_pages": total_pages,
        "links": {
            "self": f"/api/profiles/search?page={page}&limit={limit}",
            "next": f"/api/profiles/search?page={page+1}&limit={limit}" if page < total_pages else None,
            "prev": f"/api/profiles/search?page={page-1}&limit={limit}" if page > 1 else None
        },
        "data": profiles_list
    }), 200


@app.route("/api/profiles/export", methods=["GET"])
@require_auth
@require_version
def export_profiles():
    conn = sqlite3.connect("profiles.db")
    c = conn.cursor()
    query = "SELECT * FROM profiles WHERE 1=1"
    params = []

    gender = request.args.get('gender')
    country_id = request.args.get('country_id')
    age_group = request.args.get('age_group')
    min_age = request.args.get('min_age')
    max_age = request.args.get('max_age')

    if gender:
        query += " AND gender = ?"
        params.append(gender.lower())
    if country_id:
        query += " AND country_id = ?"
        params.append(country_id.upper())
    if age_group:
        query += " AND age_group = ?"
        params.append(age_group.lower())
    if min_age:
        query += " AND age >= ?"
        params.append(int(min_age))
    if max_age:
        query += " AND age <= ?"
        params.append(int(max_age))

    sort_by = request.args.get('sort_by')
    order = request.args.get('order', 'asc')
    allowed_sort = ['age', 'created_at', 'gender_probability']
    if sort_by and sort_by in allowed_sort:
        if order not in ['asc', 'desc']:
            order = 'asc'
        query += f" ORDER BY {sort_by} {order}"

    c.execute(query, params)
    rows = c.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "name", "gender", "gender_probability", "age", "age_group", "country_id", "country_name", "country_probability", "created_at"])
    for row in rows:
        writer.writerow(row)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=profiles_{timestamp}.csv"}
    )


@app.route("/api/profiles/<id>", methods=["GET"])
@require_auth
@require_version
def get_profile(id):
    conn = sqlite3.connect("profiles.db")
    c = conn.cursor()
    c.execute("SELECT * FROM profiles WHERE id = ?", (id,))
    row = c.fetchone()
    conn.close()

    if not row:
        return jsonify({"status": "error", "message": "Profile not found"}), 404

    return jsonify({"status": "success", "data": format_row(row)}), 200


@app.route("/api/profiles", methods=["GET"])
@require_auth
@require_version
def get_all_profiles():
    gender = request.args.get('gender')
    country_id = request.args.get('country_id')
    age_group = request.args.get('age_group')
    min_age = request.args.get('min_age')
    max_age = request.args.get('max_age')
    min_gender_probability = request.args.get('min_gender_probability')
    min_country_probability = request.args.get('min_country_probability')

    conn = sqlite3.connect("profiles.db")
    c = conn.cursor()
    query = "SELECT * FROM profiles WHERE 1=1"
    params = []

    try:
        if gender:
            query += " AND gender = ?"
            params.append(gender.lower())
        if country_id:
            query += " AND country_id = ?"
            params.append(country_id.upper())
        if age_group:
            query += " AND age_group = ?"
            params.append(age_group.lower())
        if min_age:
            query += " AND age >= ?"
            params.append(int(min_age))
        if max_age:
            query += " AND age <= ?"
            params.append(int(max_age))
        if min_gender_probability:
            query += " AND gender_probability >= ?"
            params.append(float(min_gender_probability))
        if min_country_probability:
            query += " AND country_probability >= ?"
            params.append(float(min_country_probability))
    except ValueError:
        conn.close()
        return jsonify({"status": "error", "message": "Invalid query parameters"}), 422

    count_query = query.replace("SELECT *", "SELECT COUNT(*)")
    sort_by = request.args.get('sort_by')
    order = request.args.get('order', 'asc')

    allowed_sort = ['age', 'created_at', 'gender_probability']
    allowed_order = ['asc', 'desc']

    if sort_by:
        if sort_by not in allowed_sort:
            conn.close()
            return jsonify({"status": "error", "message": "Invalid query parameters"}), 422
        if order not in allowed_order:
            order = 'asc'
        query += f" ORDER BY {sort_by} {order}"

    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
    except ValueError:
        conn.close()
        return jsonify({"status": "error", "message": "Invalid query parameters"}), 422

    if page < 1 or limit < 1:
        conn.close()
        return jsonify({"status": "error", "message": "Invalid query parameters"}), 422
    if limit > 50:
        limit = 50

    offset = (page - 1) * limit

    c.execute(count_query, params)
    total = c.fetchone()[0]

    query += " LIMIT ? OFFSET ?"
    params.append(limit)
    params.append(offset)

    c.execute(query, params)
    rows = c.fetchall()
    conn.close()

    profiles_list = [format_row(row) for row in rows]
    total_pages = math.ceil(total / limit)

    return jsonify({
        "status": "success",
        "page": page,
        "limit": limit,
        "total": total,
        "total_pages": total_pages,
        "links": {
            "self": f"/api/profiles?page={page}&limit={limit}",
            "next": f"/api/profiles?page={page+1}&limit={limit}" if page < total_pages else None,
            "prev": f"/api/profiles?page={page-1}&limit={limit}" if page > 1 else None
        },
        "data": profiles_list
    }), 200


@app.route("/api/profiles/<id>", methods=["DELETE"])
@require_auth
@require_admin
@require_version
def delete_profile(id):
    conn = sqlite3.connect("profiles.db")
    c = conn.cursor()
    c.execute("SELECT id FROM profiles WHERE id = ?", (id,))
    if not c.fetchone():
        conn.close()
        return jsonify({"status": "error", "message": "Profile not found"}), 404
    c.execute("DELETE FROM profiles WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return '', 204


def format_row(row):
    return {
        "id": row[0], "name": row[1], "gender": row[2], "gender_probability": row[3],
        "age": row[4], "age_group": row[5], "country_id": row[6],
        "country_name": row[7], "country_probability": row[8], "created_at": row[9]
    }


if __name__ == "__main__":
    app.run(debug=True)