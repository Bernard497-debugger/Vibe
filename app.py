# VibeNet - Clean Minimal Version
import os
import uuid
import datetime
import json as _json
from flask import Flask, request, jsonify, session, render_template_string

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
import requests

# ---------- Config ----------
app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024
app.config["PORT"] = int(os.environ.get("PORT", 5000))
app.secret_key = os.environ.get("SECRET_KEY", "vibenet_secret_dev")

# Database
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL or f"sqlite:///vibenet.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_size": 5,
    "max_overflow": 10,
    "pool_recycle": 300,
    "pool_pre_ping": True,
    "connect_args": {
        "connect_timeout": 30,
        "application_name": "vibenet_app",
    } if not DATABASE_URL.startswith("sqlite") else {},
}

db = SQLAlchemy(app)

# ---------- Models ----------
def now_ts():
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

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
    created_at = db.Column(db.Text, default=lambda: now_ts())

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "profile_pic": self.profile_pic,
            "bio": self.bio,
            "watch_hours": self.watch_hours,
            "earnings": self.earnings,
            "verified": bool(self.verified),
            "banned": bool(self.banned),
            "email_verified": bool(self.email_verified),
        }

class Post(db.Model):
    __tablename__ = "posts"
    id = db.Column(db.Integer, primary_key=True)
    author_email = db.Column(db.Text, nullable=False)
    author_name = db.Column(db.Text)
    profile_pic = db.Column(db.Text, default="")
    text = db.Column(db.Text, default="")
    file_url = db.Column(db.Text, default="")
    file_mime = db.Column(db.Text, default="")
    timestamp = db.Column(db.Text, default=lambda: now_ts())
    reactions_json = db.Column(db.Text, default='{"👍":0,"❤️":0,"😂":0}')
    comments_count = db.Column(db.Integer, default=0)

    def reactions(self):
        try:
            return _json.loads(self.reactions_json or "{}")
        except:
            return {"👍": 0, "❤️": 0, "😂": 0}

    def to_dict(self):
        return {
            "id": self.id,
            "author_email": self.author_email,
            "author_name": self.author_name,
            "profile_pic": self.profile_pic,
            "text": self.text,
            "file_url": self.file_url,
            "file_mime": self.file_mime,
            "timestamp": self.timestamp,
            "reactions": self.reactions(),
            "comments_count": self.comments_count,
        }

# ---------- Routes ----------
@app.route("/")
def index():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>VibeNet</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                background: #0d1117;
                color: #c8d8f0;
                padding: 20px;
            }
            .container {
                max-width: 400px;
                margin: 0 auto;
                background: #161b22;
                border-radius: 12px;
                padding: 30px;
                border: 1px solid #30363d;
            }
            h1 {
                text-align: center;
                margin-bottom: 30px;
                color: #4DF0C0;
            }
            .tabs {
                display: flex;
                gap: 10px;
                margin-bottom: 20px;
            }
            .tab-btn {
                flex: 1;
                padding: 12px;
                border: none;
                border-radius: 8px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 600;
                background: transparent;
                color: #8899b4;
                transition: all 0.2s;
            }
            .tab-btn.active {
                background: #4DF0C0;
                color: #0d1117;
            }
            .form {
                display: none;
            }
            .form.active {
                display: block;
            }
            .field {
                margin-bottom: 15px;
            }
            label {
                display: block;
                font-size: 12px;
                color: #8899b4;
                margin-bottom: 5px;
                font-weight: 600;
            }
            input {
                width: 100%;
                padding: 10px;
                border: 1px solid #30363d;
                border-radius: 8px;
                background: #0d1117;
                color: #c8d8f0;
                font-size: 14px;
            }
            input:focus {
                outline: none;
                border-color: #4DF0C0;
            }
            button {
                width: 100%;
                padding: 12px;
                background: #4DF0C0;
                color: #0d1117;
                border: none;
                border-radius: 8px;
                font-weight: 700;
                cursor: pointer;
                font-size: 14px;
            }
            button:hover {
                opacity: 0.9;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>VibeNet</h1>
            
            <div class="tabs">
                <button class="tab-btn active" onclick="switchTab('signup')">Create Account</button>
                <button class="tab-btn" onclick="switchTab('login')">Sign In</button>
            </div>

            <form id="signup-form" class="form active">
                <div class="field">
                    <label>Full Name</label>
                    <input type="text" id="signup-name" placeholder="Your name">
                </div>
                <div class="field">
                    <label>Email</label>
                    <input type="email" id="signup-email" placeholder="you@email.com">
                </div>
                <div class="field">
                    <label>Password</label>
                    <input type="password" id="signup-password" placeholder="••••••••">
                </div>
                <button type="button" onclick="signup()">Create Account →</button>
            </form>

            <form id="login-form" class="form">
                <div class="field">
                    <label>Email</label>
                    <input type="email" id="login-email" placeholder="you@email.com">
                </div>
                <div class="field">
                    <label>Password</label>
                    <input type="password" id="login-password" placeholder="••••••••">
                </div>
                <button type="button" onclick="login()">Sign In →</button>
            </form>
        </div>

        <script>
        const API = '/api';
        
        function switchTab(tab) {
            document.querySelectorAll('.form').forEach(f => f.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            
            if (tab === 'signup') {
                document.getElementById('signup-form').classList.add('active');
                document.querySelectorAll('.tab-btn')[0].classList.add('active');
            } else {
                document.getElementById('login-form').classList.add('active');
                document.querySelectorAll('.tab-btn')[1].classList.add('active');
            }
        }

        async function signup() {
            const name = document.getElementById('signup-name').value.trim();
            const email = document.getElementById('signup-email').value.trim().toLowerCase();
            const password = document.getElementById('signup-password').value;
            
            if (!name || !email || !password) {
                alert('Fill all fields');
                return;
            }
            
            const res = await fetch(API + '/signup', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({name, email, password, profile_pic: ''})
            });
            const j = await res.json();
            if (j.user) {
                alert('Account created! Now sign in.');
                switchTab('login');
                document.getElementById('login-email').value = email;
            } else {
                alert('Error: ' + (j.error || 'Failed'));
            }
        }

        async function login() {
            const email = document.getElementById('login-email').value.trim().toLowerCase();
            const password = document.getElementById('login-password').value;
            
            if (!email || !password) {
                alert('Fill all fields');
                return;
            }
            
            const res = await fetch(API + '/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email, password})
            });
            const j = await res.json();
            if (j.user) {
                alert('Logged in!');
                window.location.href = '/feed';
            } else {
                alert('Invalid credentials');
            }
        }
        </script>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route("/favicon.ico")
def favicon():
    return "", 204

@app.route("/api/signup", methods=["POST"])
def api_signup():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    
    if not email or not password:
        return jsonify({"error": "email + password required"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "User already exists"}), 400
    
    user = User(name=name, email=email, password=password)
    db.session.add(user)
    db.session.commit()
    session["user_email"] = email
    return jsonify({"user": user.to_dict()})

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    
    user = User.query.filter_by(email=email, password=password).first()
    if not user:
        return jsonify({"error": "Invalid credentials"}), 401
    
    session["user_email"] = email
    return jsonify({"user": user.to_dict()})

@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"status": "logged out"})

@app.route("/api/me")
def api_me():
    email = session.get("user_email")
    if not email:
        return jsonify({"user": None})
    user = User.query.filter_by(email=email).first()
    return jsonify({"user": user.to_dict() if user else None})

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=app.config["PORT"], debug=False)
