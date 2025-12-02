# app.py - VibeNet (Production-ready)
import os
import uuid
import json
import datetime
import logging
from io import BytesIO
from flask import Flask, request, jsonify, render_template_string, session, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from supabase import create_client, Client
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool
from flask_cors import CORS

# ---------- Basic config ----------
APP_NAME = "VibeNet"
app = Flask(__name__, static_folder=None)
CORS(app, supports_credentials=True)  # allow frontends to talk if using separate domain

# PORT and debug
PORT = int(os.environ.get("PORT", 5000))
DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"
app.config["ENV"] = "production" if not DEBUG else "development"

# Security / sessions
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(32).hex())
app.config.update({
    "SESSION_COOKIE_HTTPONLY": True,
    "SESSION_COOKIE_SECURE": os.environ.get("SESSION_COOKIE_SECURE", "1") == "1",  # True on HTTPS
    "SESSION_COOKIE_SAMESITE": os.environ.get("SESSION_COOKIE_SAMESITE", "Lax"),
    "PERMANENT_SESSION_LIFETIME": int(os.environ.get("SESSION_LIFETIME_SEC", 60*60*24)),  # 1 day
})

# Upload limits
MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 30 * 1024 * 1024))  # 30 MB default
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
ALLOWED_EXT = set(["png", "jpg", "jpeg", "gif", "mp4", "webm", "mov", "mkv"])

# ---------- Supabase & Postgres config ----------
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")  # required

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required")

# supabase client (for storage)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if (SUPABASE_URL and SUPABASE_KEY) else None

# ---------- Logging ----------
log_level = logging.DEBUG if DEBUG else logging.INFO
logging.basicConfig(level=log_level,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(APP_NAME)

# ---------- Postgres connection pool ----------
POOL_MIN = int(os.environ.get("PG_POOL_MIN", 1))
POOL_MAX = int(os.environ.get("PG_POOL_MAX", 6))
try:
    pg_pool = ThreadedConnectionPool(POOL_MIN, POOL_MAX, dsn=DATABASE_URL, cursor_factory=RealDictCursor)
except Exception as e:
    logger.exception("Failed to create DB pool: %s", e)
    raise

def get_conn():
    """Acquire a connection from the pool."""
    try:
        return pg_pool.getconn()
    except Exception as e:
        logger.exception("Error acquiring db connection: %s", e)
        raise

def release_conn(conn):
    try:
        pg_pool.putconn(conn)
    except Exception:
        logger.exception("Error returning connection to pool")

def query_db(query, args=(), one=False):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(query, args)
        if query.strip().upper().startswith("SELECT"):
            rows = cur.fetchall()
            return (rows[0] if rows else None) if one else rows
        else:
            conn.commit()
            if "RETURNING" in query.upper():
                return cur.fetchone()
            return None
    except Exception as e:
        logger.exception("DB query error: %s -- Query: %s -- Args: %s", e, query, args)
        conn.rollback()
        raise
    finally:
        release_conn(conn)

# ---------- Helpers ----------
def now_ts():
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

def is_allowed_filename(filename):
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_EXT

def supabase_upload_file(file_storage, folder="uploads"):
    """
    Uploads a FileStorage object to Supabase Storage 'uploads' bucket and returns public URL.
    Returns the public URL string.
    """
    if not supabase:
        raise RuntimeError("Supabase not configured")
    filename = secure_filename(file_storage.filename)
    ext = filename.rsplit(".", 1)[1].lower() if "." in filename else ""
    uid_name = f"{uuid.uuid4().hex}_{filename}"
    file_bytes = file_storage.read()
    content_type = file_storage.mimetype or "application/octet-stream"

    # The supabase-py storage API expects a path and bytes-like object
    bucket = "uploads"
    try:
        # write bytes to storage
        supabase.storage.from_(bucket).upload(uid_name, file_bytes, {"content-type": content_type})
        # get public url
        res = supabase.storage.from_(bucket).get_public_url(uid_name)
        # supabase SDK may return a dict or string depending on version. Normalize to string
        if isinstance(res, dict):
            url = res.get("publicURL") or res.get("public_url") or res.get("url")
        else:
            url = res
        return url
    except Exception as e:
        logger.exception("Supabase upload failed: %s", e)
        raise

# ---------- Frontend (minimized; original HTML kept) ----------
HTML = r"""<html>... your full HTML from previous file ...</html>"""  # keep original HTML or load from templates

@app.route("/")
def index():
    return render_template_string(HTML)

# ---------- API ----------

@app.errorhandler(413)
def request_entity_too_large(e):
    return jsonify({"error": "File too large"}), 413

@app.route("/api/upload", methods=["POST"])
def api_upload():
    if 'file' not in request.files:
        return jsonify({"error": "No file"}), 400
    f = request.files['file']
    if f.filename == "":
        return jsonify({"error": "Empty filename"}), 400
    if not is_allowed_filename(f.filename):
        return jsonify({"error": "File type not allowed"}), 400
    try:
        url = supabase_upload_file(f)
        return jsonify({"url": url})
    except Exception as e:
        logger.exception("Upload error: %s", e)
        return jsonify({"error": "Upload failed"}), 500

@app.route("/api/signup", methods=["POST"])
def api_signup():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    if not (name and email and password):
        return jsonify({"error": "Missing fields"}), 400

    profile_pic = ""
    if 'file' in request.files and request.files['file'].filename:
        f = request.files['file']
        try:
            profile_pic = supabase_upload_file(f)
        except Exception:
            profile_pic = ""

    hashed = generate_password_hash(password)
    try:
        query_db(
            "INSERT INTO users (name, email, password, profile_pic) VALUES (%s, %s, %s, %s)",
            (name, email, hashed, profile_pic)
        )
        session['user_email'] = email
        user_obj = {"name": name, "email": email, "profile_pic": profile_pic, "bio": "", "watch_hours": 0, "earnings": 0}
        return jsonify({"user": user_obj})
    except Exception as e:
        logger.exception("Signup error: %s", e)
        return jsonify({"error": "Email taken or DB error"}), 400

@app.route("/api/login", methods=["POST"])
def api_login():
    d = request.get_json() or {}
    email = (d.get("email") or "").strip().lower()
    password = d.get("password") or ""
    if not email or not password:
        return jsonify({"error": "Missing fields"}), 400

    user = query_db("SELECT * FROM users WHERE email=%s", (email,), one=True)
    if user and check_password_hash(user['password'], password):
        u = dict(user)
        u.pop("password", None)
        session['user_email'] = email
        return jsonify({"user": u})
    return jsonify({"error": "Invalid credentials"}), 401

@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"success": True})

@app.route("/api/me")
def api_me():
    email = session.get("user_email")
    if not email:
        return jsonify({"user": None})
    user = query_db("SELECT name, email, profile_pic, bio, watch_hours, earnings FROM users WHERE email=%s", (email,), one=True)
    if not user:
        session.clear()
        return jsonify({"user": None})
    return jsonify({"user": dict(user)})

@app.route("/api/posts", methods=["GET", "POST"])
def api_posts():
    if request.method == "GET":
        posts = query_db("SELECT * FROM posts ORDER BY id DESC")
        out = []
        for p in posts:
            rec = dict(p)
            rec['reactions'] = json.loads(rec.get('reactions_json') or '{}')
            rec['user_reaction'] = None
            email = session.get('user_email')
            if email:
                ur = query_db("SELECT emoji FROM user_reactions WHERE user_email=%s AND post_id=%s", (email, rec['id']), one=True)
                if ur: rec['user_reaction'] = ur['emoji']
            out.append(rec)
        return jsonify(out)
    else:
        d = request.get_json() or {}
        query_db(
            "INSERT INTO posts (author_email, author_name, profile_pic, text, file_url, timestamp) VALUES (%s, %s, %s, %s, %s, %s)",
            (d.get('author_email'), d.get('author_name'), d.get('profile_pic'), d.get('text'), d.get('file_url'), now_ts())
        )
        return jsonify({"success": True})

@app.route("/api/posts/<int:id>", methods=["DELETE"])
def api_delete_post(id):
    email = session.get("user_email")
    if not email:
        return jsonify({"error": "Not logged in"}), 403
    post = query_db("SELECT author_email FROM posts WHERE id=%s", (id,), one=True)
    if not post:
        return jsonify({"error": "Not found"}), 404
    if post['author_email'] != email:
        return jsonify({"error": "Forbidden"}), 403
    query_db("DELETE FROM posts WHERE id=%s", (id,))
    return jsonify({"success": True})

@app.route("/api/react", methods=["POST"])
def api_react():
    d = request.get_json() or {}
    pid = d.get("post_id"); em = d.get("emoji"); email = session.get("user_email")
    if not email:
        return jsonify({"error": "Login required"}), 401
    post = query_db("SELECT reactions_json FROM posts WHERE id=%s", (pid,), one=True)
    if not post:
        return jsonify({"error": "Post not found"}), 404
    reacts = json.loads(post['reactions_json'] or '{}')
    prev = query_db("SELECT emoji FROM user_reactions WHERE user_email=%s AND post_id=%s", (email, pid), one=True)
    if prev and prev.get('emoji'):
        reacts[prev['emoji']] = max(0, reacts.get(prev['emoji'], 0) - 1)
        query_db("DELETE FROM user_reactions WHERE user_email=%s AND post_id=%s", (email, pid))
    if not prev or prev.get('emoji') != em:
        query_db("INSERT INTO user_reactions (user_email, post_id, emoji) VALUES (%s, %s, %s)", (email, pid, em))
        reacts[em] = reacts.get(em, 0) + 1
    query_db("UPDATE posts SET reactions_json=%s WHERE id=%s", (json.dumps(reacts), pid))
    return jsonify({"success": True})

@app.route("/api/follow", methods=["POST"])
def api_follow():
    d = request.get_json() or {}
    follower = d.get("follower_email")
    target = d.get("target_email")
    if not (follower and target):
        return jsonify({"error":"Missing fields"}), 400
    exists = query_db("SELECT id FROM followers WHERE user_email=%s AND follower_email=%s", (target, follower), one=True)
    if not exists:
        query_db("INSERT INTO followers (user_email, follower_email) VALUES (%s, %s)", (target, follower))
    return jsonify({"success": True})

@app.route("/api/messages", methods=["GET","POST"])
def api_messages():
    if request.method == "POST":
        d = request.get_json() or {}
        query_db("INSERT INTO messages (sender, recipient, text, timestamp) VALUES (%s, %s, %s, %s)",
                 (d.get("from"), d.get("to"), d.get("text"), now_ts()))
        return jsonify({"success": True})
    else:
        email = session.get('user_email')
        if not email:
            return jsonify([])  # empty inbox if not logged
        msgs = query_db("SELECT * FROM messages WHERE recipient=%s OR sender=%s ORDER BY id DESC LIMIT 50", (email, email))
        return jsonify([dict(m) for m in msgs])

@app.route("/api/notifications/<path:e>")
def api_notifications(e):
    nots = query_db("SELECT * FROM notifications WHERE user_email=%s ORDER BY id DESC LIMIT 20", (e,))
    return jsonify([dict(n) for n in nots])

@app.route("/api/profile/<path:e>")
def api_profile(e):
    u = query_db("SELECT bio FROM users WHERE email=%s", (e,), one=True)
    p = query_db("SELECT * FROM posts WHERE author_email=%s ORDER BY id DESC", (e,))
    return jsonify({"bio": u['bio'] if u else "", "posts": [dict(r) for r in p]})

@app.route("/api/update_bio", methods=["POST"])
def api_update_bio():
    d = request.get_json() or {}
    query_db("UPDATE users SET bio=%s WHERE email=%s", (d.get("bio"), d.get("email")))
    return jsonify({"success": True})

@app.route("/api/monetization/<path:e>")
def api_monetization(e):
    f = query_db("SELECT COUNT(*) as c FROM followers WHERE user_email=%s", (e,), one=True)['c']
    u = query_db("SELECT watch_hours, earnings FROM users WHERE email=%s", (e,), one=True)
    return jsonify({"followers": f, "watch_hours": u['watch_hours'] if u else 0, "earnings": float(u['earnings']) if u and u['earnings'] is not None else 0})

@app.route("/api/ads", methods=["GET","POST"])
def api_ads():
    if request.method == "POST":
        d = request.get_json() or {}
        query_db("INSERT INTO ads (title, owner_email, budget) VALUES (%s, %s, %s)", (d.get("title"), d.get("owner"), d.get("budget")))
        return jsonify({"success": True})
    ads = query_db("SELECT * FROM ads ORDER BY id DESC")
    return jsonify([dict(a) for a in ads])

# ---------- graceful shutdown helper ----------
@app.route("/_health")
def health():
    return "ok", 200

if __name__ == "__main__":
    logger.info("Starting app on port %s (debug=%s)", PORT, DEBUG)
    # For development only. On Render use Gunicorn: gunicorn app:app --workers 3 --threads 4 --timeout 120
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG)
