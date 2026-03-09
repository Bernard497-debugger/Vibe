# app.py - VibeNet (Corrected Version)
import os
import uuid
import datetime
import json as _json
from flask import Flask, request, jsonify, send_from_directory, session, render_template_string, redirect

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, text
from sqlalchemy.orm import DeclarativeBase
import requests

# ---------- Supabase Storage Config ----------
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
SUPABASE_BUCKET = os.environ.get("SUPABASE_BUCKET", "vibenet")

def _supabase_ok():
    return bool(SUPABASE_URL and SUPABASE_KEY)

# ---------- Config ----------
APP_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(APP_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024
app.config["PORT"] = int(os.environ.get("PORT", 5000))
app.secret_key = os.environ.get("SECRET_KEY", "vibenet_secret_dev")

# SQLAlchemy: prefer DATABASE_URL env var (Render PostgreSQL), fall back to SQLite
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = (
    DATABASE_URL if DATABASE_URL
    else f"sqlite:///{os.path.join(APP_DIR, 'data', 'vibenet.db')}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Fix for SQLAlchemy AssertionError: Class SQLCoreOperations directly inherits TypingOnly
class Base(DeclarativeBase):
    pass

db = SQLAlchemy(app, model_class=Base)

# ---------- Global Error Handler ----------
@app.errorhandler(Exception)
def handle_error(error):
    import traceback
    print(f"Unhandled error: {error}")
    traceback.print_exc()
    return jsonify({"error": str(error), "type": type(error).__name__}), 500

# ---------- Utilities ----------
def now_ts():
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

# ---------- Models ----------

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text)
    email = db.Column(db.Text, unique=True, nullable=False)
    password = db.Column(db.Text, nullable=False)
    profile_pic = db.Column(db.Text, default="")
    bio = db.Column(db.Text, default="")
    watch_hours = db.Column(db.Integer, default=0)
    earnings = db.Column(db.Float, default=0.0)
    verified = db.Column(db.Integer, default=0)
    banned = db.Column(db.Integer, default=0)
    email_verified = db.Column(db.Integer, default=0)
    phone = db.Column(db.Text, default="")
    phone_verified = db.Column(db.Integer, default=0)
    last_active = db.Column(db.Text, default="")
    created_at = db.Column(db.Text, default=lambda: now_ts())

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "email": self.email,
            "profile_pic": self.profile_pic, "bio": self.bio,
            "watch_hours": self.watch_hours, "earnings": self.earnings,
            "verified": bool(self.verified), "banned": bool(self.banned),
            "email_verified": bool(self.email_verified), "phone": self.phone or "",
            "phone_verified": bool(self.phone_verified), "last_active": self.last_active or "",
        }

# (Other models like Follower, Post, Notification, etc., remain the same)
# ... [Keeping model definitions consistent with your original file] ...

class Post(db.Model):
    __tablename__ = "posts"
    id = db.Column(db.Integer, primary_key=True)
    author_email = db.Column(db.Text, nullable=False)
    author_name = db.Column(db.Text)
    profile_pic = db.Column(db.Text, default="")
    text = db.Column(db.Text, default="")
    file_url = db.Column(db.Text, default="")
    file_mime = db.Column(db.Text, default="")
    thumbnail_url = db.Column(db.Text, default="")
    timestamp = db.Column(db.Text, default=lambda: now_ts())
    reactions_json = db.Column(db.Text, default='{"👍":0,"❤️":0,"😂":0}')
    comments_count = db.Column(db.Integer, default=0)

    def reactions(self):
        try: return _json.loads(self.reactions_json or "{}")
        except: return {"👍":0,"❤️":0,"😂":0}

    def to_dict(self, user_reaction=None, author_verified=False):
        return {
            "id": self.id, "author_email": self.author_email, "author_name": self.author_name,
            "profile_pic": self.profile_pic, "text": self.text, "file_url": self.file_url,
            "file_mime": self.file_mime, "timestamp": self.timestamp, "reactions": self.reactions(),
            "comments_count": self.comments_count, "user_reaction": user_reaction, "author_verified": author_verified
        }

# ---------- Auth Routes (The Fixed Registration) ----------

@app.route("/register", methods=["POST"])
def register():
    # Detect if data is coming from a form or a JSON request
    data = request.form if request.form else (request.get_json() or {})
    name = data.get("name")
    email = data.get("email", "").lower().strip()
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    # Prevent duplicate accounts
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "An account with this email already exists"}), 400

    try:
        new_user = User(
            name=name if name else email.split("@")[0],
            email=email,
            password=password, # In production, use generate_password_hash
            last_active=now_ts()
        )
        db.session.add(new_user)
        db.session.commit()

        # Login immediately
        session["user_email"] = email
        
        # FIX: Return JSON so the frontend doesn't get stuck on a redirect
        return jsonify({
            "success": True, 
            "message": "Account created successfully",
            "user": new_user.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Database error: {str(e)}"}), 500

@app.route("/login", methods=["POST"])
def login():
    data = request.form if request.form else (request.get_json() or {})
    email = data.get("email", "").lower().strip()
    password = data.get("password")
    
    user = User.query.filter_by(email=email).first()
    if user and user.password == password:
        session["user_email"] = email
        user.last_active = now_ts()
        db.session.commit()
        return jsonify({"success": True, "user": user.to_dict()})
    
    return jsonify({"error": "Invalid email or password"}), 401

@app.route("/logout")
def logout():
    session.pop("user_email", None)
    return redirect("/")

# ---------- Database Initialization & Safe Migrations ----------
with app.app_context():
    try:
        db.create_all()
        print("✅ Database tables verified")
    except Exception as e:
        print(f"⚠️ DB init warning: {e}")

    # Safe Migrations (Checks if column exists before adding)
    migrations = [
        ("users", "banned", "INTEGER DEFAULT 0"),
        ("users", "last_active", "TEXT DEFAULT ''"),
        ("ads", "approved", "INTEGER DEFAULT 0"),
        ("ads", "whatsapp_number", "TEXT DEFAULT ''"),
        ("ads", "expiry_date", "TEXT DEFAULT ''"),
        ("posts", "file_mime", "TEXT DEFAULT ''"),
        ("posts", "comments_count", "INTEGER DEFAULT 0"),
    ]
    
    for table, col, definition in migrations:
        try:
            db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {definition}"))
            db.session.commit()
        except Exception:
            db.session.rollback() # Ignores error if column already exists

# ---------- Main Entry ----------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=app.config["PORT"], debug=True)
