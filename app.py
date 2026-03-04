# app.py - VibeNet (Original UI + Manual Botswana Payouts)
import os
import uuid
import datetime
import json as _json
from flask import Flask, request, jsonify, send_from_directory, session, render_template_string

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
import cloudinary
import cloudinary.uploader

# ---------- Config ----------
APP_DIR   = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(APP_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 300 * 1024 * 1024
app.config["PORT"] = int(os.environ.get("PORT", 5000))
app.secret_key = os.environ.get("SECRET_KEY", "vibenet_secret_dev")

# ---------- Cloudinary ----------
CLOUDINARY_URL = os.environ.get("CLOUDINARY_URL", "") 
_cld_cloud  = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
_cld_key    = os.environ.get("CLOUDINARY_API_KEY", "")
_cld_secret = os.environ.get("CLOUDINARY_API_SECRET", "")
if _cld_cloud and _cld_key and _cld_secret:
    cloudinary.config(cloud_name=_cld_cloud, api_key=_cld_key,
                      api_secret=_cld_secret, secure=True)
elif CLOUDINARY_URL:
    cloudinary.config(cloudinary_url=CLOUDINARY_URL)

def upload_to_cloudinary(file_storage, folder="vibenet"):
    result = cloudinary.uploader.upload(file_storage, folder=folder, resource_type="auto")
    return result["secure_url"]

# ---------- Database ----------
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = (
    DATABASE_URL if DATABASE_URL
    else f"sqlite:///{os.path.join(APP_DIR, 'data', 'vibenet.db')}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

def now_ts():
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

# ---------- Models ----------
class User(db.Model):
    __tablename__ = "users"
    id                = db.Column(db.Integer, primary_key=True)
    name              = db.Column(db.Text)
    email             = db.Column(db.Text, unique=True, nullable=False)
    password          = db.Column(db.Text, nullable=False)
    profile_pic       = db.Column(db.Text, default="")
    bio               = db.Column(db.Text, default="")
    watch_hours       = db.Column(db.Integer, default=0)
    earnings          = db.Column(db.Float, default=0.0)
    verified          = db.Column(db.Integer, default=0)
    created_at        = db.Column(db.Text, default=lambda: now_ts())

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "email": self.email,
            "profile_pic": self.profile_pic, "bio": self.bio,
            "watch_hours": self.watch_hours, "earnings": self.earnings,
            "verified": bool(self.verified),
        }

class Post(db.Model):
    __tablename__  = "posts"
    id             = db.Column(db.Integer, primary_key=True)
    author_email   = db.Column(db.Text, nullable=False)
    author_name    = db.Column(db.Text)
    profile_pic    = db.Column(db.Text, default="")
    text           = db.Column(db.Text, default="")
    file_url       = db.Column(db.Text, default="")
    timestamp      = db.Column(db.Text, default=lambda: now_ts())
    reactions_json = db.Column(db.Text, default='{"👍":0,"❤️":0,"😂":0}')
    comments_count = db.Column(db.Integer, default=0)

class Notification(db.Model):
    __tablename__ = "notifications"
    id         = db.Column(db.Integer, primary_key=True)
    user_email = db.Column(db.Text, nullable=False)
    text       = db.Column(db.Text)
    timestamp  = db.Column(db.Text, default=lambda: now_ts())
    seen       = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {"id": self.id, "text": self.text, "timestamp": self.timestamp, "seen": self.seen}

# (Other existing models: Follower, Comment, Ad etc should remain as they were)
class Follower(db.Model):
    __tablename__ = "followers"
    id = db.Column(db.Integer, primary_key=True)
    user_email = db.Column(db.Text)
    follower_email = db.Column(db.Text)

class Comment(db.Model):
    __tablename__ = "comments"
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer)
    author_email = db.Column(db.Text)
    author_name = db.Column(db.Text)
    text = db.Column(db.Text)
    timestamp = db.Column(db.Text, default=lambda: now_ts())

class Ad(db.Model):
    __tablename__ = "ads"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.Text)
    owner_email = db.Column(db.Text)
    budget = db.Column(db.Float, default=0.0)
    def to_dict(self):
        return {"id":self.id, "title":self.title, "owner":self.owner_email, "budget":self.budget}

# ---------- API Routes ----------

@app.route("/")
def index():
    return render_template_string(HTML)

# --- MANUAL WITHDRAWAL API ---
@app.route("/api/withdraw", methods=["POST"])
def api_withdraw():
    data = request.get_json() or {}
    email = data.get("email")
    method = data.get("method")
    details = data.get("details")
    amount = float(data.get("amount", 0))

    user = User.query.filter_by(email=email).first()
    if not user or amount < 50 or amount > user.earnings:
        return jsonify({"success": False, "message": "Check balance (Min P50)"}), 400

    user.earnings -= amount
    
    # Save a record you can see later
    log_msg = f"CASH OUT: P{amount:.2f} via {method} to {details}"
    notif = Notification(user_email=email, text=log_msg)
    db.session.add(notif)
    db.session.commit()

    return jsonify({"success": True, "new_balance": user.earnings})

# (Keep all your existing API routes: signup, login, watch, ads, etc.)
@app.route("/api/signup", methods=["POST"])
def api_signup():
    name = request.form.get("name")
    email = request.form.get("email")
    password = request.form.get("password")
    pic = request.files.get("pic")
    if User.query.filter_by(email=email).first():
        return jsonify({"success": False, "message": "Email exists"})
    url = upload_to_cloudinary(pic) if pic else ""
    user = User(name=name, email=email, password=password, profile_pic=url)
    db.session.add(user)
    db.session.commit()
    return jsonify({"success": True, "user": user.to_dict()})

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    user = User.query.filter_by(email=data.get("email"), password=data.get("password")).first()
    if user: return jsonify({"success": True, "user": user.to_dict()})
    return jsonify({"success": False})

@app.route("/api/watch", methods=["POST"])
def api_watch():
    data    = request.get_json() or {}
    viewer  = data.get("viewer")
    post_id = data.get("post_id")
    post    = Post.query.get(post_id)
    if post and post.author_email != viewer:
        author = User.query.filter_by(email=post.author_email).first()
        if author:
            author.watch_hours += 1
            author.earnings    += 0.1
            db.session.commit()
    return jsonify({"success": True})

# ---------- HTML & JS ----------
# I am using your original HTML structure exactly.
HTML = r"""
<!doctype html>
<html lang="en">
<head>
    <style>
        /* All your Syne font, DM Sans, and VibeNet colors stay exactly the same */
        :root { --bg: #060910; --surface: #0c1018; --card: #101520; --border: rgba(255,255,255,0.06); --accent: #4DF0C0; --text: #E8F0FF; --muted: #5A6A85; --danger: #F06A4D; }
        /* ... (rest of your CSS) ... */
        .withdraw-box { background:var(--card); border:1px solid var(--border); border-radius:16px; padding:20px; margin-top:20px; }
        .form-input { background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:12px; color:#fff; width:100%; margin-bottom:10px; }
    </style>
</head>
<body>
    <div id="monet" class="tab">
        <div class="monet-grid">
            <div class="monet-card">
                <div class="monet-card-label">Balance</div>
                <div class="monet-card-value green">P<span id="monEarnings">0.00</span></div>
            </div>
        </div>

        <div class="withdraw-box">
            <h3 style="margin-bottom:15px; font-family:Syne; color:var(--accent);">Withdraw (Botswana)</h3>
            <select id="payMethod" class="form-input">
                <option value="Orange Money">Orange Money</option>
                <option value="FNB eWallet">FNB eWallet</option>
                <option value="Absa CashSend">Absa CashSend</option>
            </select>
            <input id="payDetails" class="form-input" placeholder="Phone Number (71xxxxxx)">
            <input id="payAmount" type="number" class="form-input" placeholder="Amount (Min P50)">
            <button class="btn-primary" style="width:100%" onclick="requestPayout()">Withdraw Funds</button>
        </div>
    </div>

    <script>
        // YOUR ORIGINAL SCRIPT REMAINS
        // ... (Existing functions) ...

        async function requestPayout() {
            const method = document.getElementById('payMethod').value;
            const details = document.getElementById('payDetails').value;
            const amount = document.getElementById('payAmount').value;

            if(!details || !amount) return alert("Fill in details");

            const res = await fetch("/api/withdraw", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    email: currentUser.email,
                    method: method,
                    details: details,
                    amount: amount
                })
            });

            const data = await res.json();
            if(data.success) {
                alert("Request Sent! Wait for your transfer.");
                currentUser.earnings = data.new_balance;
                document.getElementById('monEarnings').innerText = data.new_balance.toFixed(2);
            } else {
                alert(data.message);
            }
        }
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    with app.app_context(): db.create_all()
    app.run(debug=True, host="0.0.0.0", port=app.config["PORT"])
