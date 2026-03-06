# app.py - VibeNet  (SQLAlchemy ORM  |  SQLite locally  |  PostgreSQL on Render)
import os
import uuid
import datetime
import json as _json
from flask import Flask, request, jsonify, send_from_directory, session, render_template_string

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, text
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
_cld_cloud  = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
_cld_key    = os.environ.get("CLOUDINARY_API_KEY", "")
_cld_secret = os.environ.get("CLOUDINARY_API_SECRET", "")
CLOUDINARY_URL = os.environ.get("CLOUDINARY_URL", "")
if _cld_cloud and _cld_key and _cld_secret:
    cloudinary.config(cloud_name=_cld_cloud, api_key=_cld_key, api_secret=_cld_secret, secure=True)
elif CLOUDINARY_URL:
    cloudinary.config(cloudinary_url=CLOUDINARY_URL)

def _cloudinary_ok():
    cfg = cloudinary.config()
    return bool(cfg.cloud_name and cfg.api_key)

# SQLAlchemy: prefer DATABASE_URL env var (Render PostgreSQL), fall back to SQLite
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):          # Render uses legacy scheme
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = (
    DATABASE_URL if DATABASE_URL
    else f"sqlite:///{os.path.join(APP_DIR, 'data', 'vibenet.db')}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 280,
    "pool_pre_ping": True,
    "connect_args": {"connect_timeout": 10} if not os.environ.get("DATABASE_URL", "").startswith("sqlite") else {},
}

os.makedirs(os.path.join(APP_DIR, "data"), exist_ok=True)

db = SQLAlchemy(app)

# ---------- Utilities ----------
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
    verified          = db.Column(db.Integer, default=0)   # 1 = VibeNet Verified
    created_at        = db.Column(db.Text, default=lambda: now_ts())

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "email": self.email,
            "profile_pic": self.profile_pic, "bio": self.bio,
            "watch_hours": self.watch_hours, "earnings": self.earnings,
            "verified": bool(self.verified),
        }


class Follower(db.Model):
    __tablename__ = "followers"
    id             = db.Column(db.Integer, primary_key=True)
    user_email     = db.Column(db.Text, nullable=False)   # the person being followed
    follower_email = db.Column(db.Text, nullable=False)   # the person who follows
    created_at     = db.Column(db.Text, default=lambda: now_ts())
    __table_args__ = (
        db.UniqueConstraint("user_email", "follower_email", name="uq_follow"),
    )


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

    def reactions(self):
        try:
            return _json.loads(self.reactions_json or "{}")
        except Exception:
            return {"👍": 0, "❤️": 0, "😂": 0}

    def to_dict(self, user_reaction=None, author_verified=False):
        return {
            "id": self.id, "author_email": self.author_email,
            "author_name": self.author_name, "profile_pic": self.profile_pic,
            "text": self.text, "file_url": self.file_url,
            "timestamp": self.timestamp, "reactions": self.reactions(),
            "comments_count": self.comments_count,
            "user_reaction": user_reaction,
            "author_verified": author_verified,
        }


class UserReaction(db.Model):
    __tablename__ = "user_reactions"
    id         = db.Column(db.Integer, primary_key=True)
    user_email = db.Column(db.Text, nullable=False)
    post_id    = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=False)
    emoji      = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.Text, default=lambda: now_ts())
    __table_args__ = (
        db.UniqueConstraint("user_email", "post_id", name="uq_reaction"),
    )


class Notification(db.Model):
    __tablename__ = "notifications"
    id         = db.Column(db.Integer, primary_key=True)
    user_email = db.Column(db.Text, nullable=False)
    text       = db.Column(db.Text)
    timestamp  = db.Column(db.Text, default=lambda: now_ts())
    seen       = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {"id": self.id, "text": self.text, "timestamp": self.timestamp, "seen": self.seen}


class Ad(db.Model):
    __tablename__ = "ads"
    id               = db.Column(db.Integer, primary_key=True)
    title            = db.Column(db.Text)
    owner_email      = db.Column(db.Text)
    whatsapp_number  = db.Column(db.Text, default="")
    budget           = db.Column(db.Float, default=0.0)
    impressions      = db.Column(db.Integer, default=0)
    clicks           = db.Column(db.Integer, default=0)
    approved         = db.Column(db.Integer, default=0)
    created_at       = db.Column(db.Text, default=lambda: now_ts())

    def to_dict(self):
        return {
            "id": self.id, "title": self.title, "owner_email": self.owner_email,
            "whatsapp_number": self.whatsapp_number or "",
            "budget": self.budget, "impressions": self.impressions, "clicks": self.clicks,
            "approved": self.approved, "created_at": self.created_at,
        }


class PayoutRequest(db.Model):
    __tablename__ = "payout_requests"
    id         = db.Column(db.Integer, primary_key=True)
    user_email = db.Column(db.Text, nullable=False)
    user_name  = db.Column(db.Text, default="")
    om_number  = db.Column(db.Text, nullable=False)
    amount     = db.Column(db.Float, nullable=False)
    status     = db.Column(db.Text, default="pending")  # pending | paid | rejected
    created_at = db.Column(db.Text, default=lambda: now_ts())

    def to_dict(self):
        return {
            "id": self.id, "user_email": self.user_email, "user_name": self.user_name,
            "om_number": self.om_number, "amount": self.amount,
            "status": self.status, "created_at": self.created_at,
        }


# ---------- Create tables ----------
with app.app_context():
    try:
        db.create_all()
        print("✅ Database tables created/verified OK", flush=True)
    except Exception as e:
        print(f"⚠️  DB init warning (non-fatal): {e}", flush=True)

    # Safe migrations — add columns that may not exist in older deployments
    migrations = [
        "ALTER TABLE ads ADD COLUMN approved INTEGER DEFAULT 0",
        "ALTER TABLE ads ADD COLUMN whatsapp_number TEXT DEFAULT ''",
        "ALTER TABLE payout_requests ADD COLUMN user_email TEXT DEFAULT ''",
        "ALTER TABLE payout_requests ADD COLUMN user_name TEXT DEFAULT ''",
    ]
    for sql in migrations:
        try:
            db.session.execute(text(sql))
            db.session.commit()
        except Exception:
            db.session.rollback()

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "botsile55@gmail.com")

def require_admin():
    return session.get("user_email") == ADMIN_EMAIL

def hash_password(pw):
    """Simple hash for demo — use bcrypt in production"""
    import hashlib
    return hashlib.sha256(pw.encode()).hexdigest()

# ---------- Auth Routes ----------
@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()
    name = data.get("name", "").strip()
    
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "User already exists"}), 409
    
    user = User(name=name or email, email=email, password=hash_password(password))
    db.session.add(user)
    db.session.commit()
    
    session["user_email"] = email
    return jsonify({"success": True, "user": user.to_dict()})

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()
    
    user = User.query.filter_by(email=email).first()
    if not user or user.password != hash_password(password):
        return jsonify({"error": "Invalid credentials"}), 401
    
    session["user_email"] = email
    return jsonify({"success": True, "user": user.to_dict()})

@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"success": True})

@app.route("/api/me")
def api_me():
    email = session.get("user_email")
    if not email:
        return jsonify({"error": "Not logged in"}), 401
    user = User.query.filter_by(email=email).first()
    return jsonify(user.to_dict() if user else {"error": "User not found"})

# ---------- User Profile Routes ----------
@app.route("/api/user/<email>")
def api_user_profile(email):
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(user.to_dict())

@app.route("/api/user/update", methods=["POST"])
def api_user_update():
    email = session.get("user_email")
    if not email:
        return jsonify({"error": "Not logged in"}), 401
    
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    data = request.get_json() or {}
    if "name" in data:
        user.name = data["name"]
    if "bio" in data:
        user.bio = data["bio"]
    if "profile_pic" in data:
        user.profile_pic = data["profile_pic"]
    
    db.session.commit()
    return jsonify({"success": True, "user": user.to_dict()})

# ---------- Post Routes ----------
@app.route("/api/post/create", methods=["POST"])
def api_post_create():
    email = session.get("user_email")
    if not email:
        return jsonify({"error": "Not logged in"}), 401
    
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    text = request.form.get("text", "").strip()
    file = request.files.get("file")
    file_url = ""
    
    if file:
        try:
            if _cloudinary_ok():
                result = cloudinary.uploader.upload(file, folder="vibenet_posts")
                file_url = result.get("secure_url", "")
            else:
                # Fallback: save locally
                filename = f"{uuid.uuid4()}_{file.filename}"
                filepath = os.path.join(UPLOAD_DIR, filename)
                file.save(filepath)
                file_url = f"/uploads/{filename}"
        except Exception as e:
            print(f"Upload error: {e}")
            return jsonify({"error": f"Upload failed: {e}"}), 500
    
    if not text and not file_url:
        return jsonify({"error": "Post must have text or media"}), 400
    
    post = Post(
        author_email=email,
        author_name=user.name,
        profile_pic=user.profile_pic,
        text=text,
        file_url=file_url
    )
    db.session.add(post)
    db.session.commit()
    
    return jsonify({"success": True, "post": post.to_dict()})

@app.route("/api/posts")
def api_posts():
    email = session.get("user_email")
    posts = Post.query.order_by(Post.id.desc()).all()
    result = []
    for post in posts:
        author = User.query.filter_by(email=post.author_email).first()
        user_reaction = None
        if email:
            ur = UserReaction.query.filter_by(user_email=email, post_id=post.id).first()
            user_reaction = ur.emoji if ur else None
        result.append(post.to_dict(user_reaction=user_reaction, author_verified=bool(author and author.verified)))
    return jsonify(result)

@app.route("/api/posts/<email>")
def api_posts_by_user(email):
    current_email = session.get("user_email")
    posts = Post.query.filter_by(author_email=email).order_by(Post.id.desc()).all()
    result = []
    for post in posts:
        author = User.query.filter_by(email=post.author_email).first()
        user_reaction = None
        if current_email:
            ur = UserReaction.query.filter_by(user_email=current_email, post_id=post.id).first()
            user_reaction = ur.emoji if ur else None
        result.append(post.to_dict(user_reaction=user_reaction, author_verified=bool(author and author.verified)))
    return jsonify(result)

# ---------- Reaction Routes ----------
@app.route("/api/react/<int:post_id>", methods=["POST"])
def api_react(post_id):
    email = session.get("user_email")
    if not email:
        return jsonify({"error": "Not logged in"}), 401
    
    data = request.get_json() or {}
    emoji = data.get("emoji", "").strip()
    
    post = Post.query.get_or_404(post_id)
    existing = UserReaction.query.filter_by(user_email=email, post_id=post_id).first()
    
    if existing:
        if existing.emoji == emoji:
            db.session.delete(existing)
        else:
            existing.emoji = emoji
    else:
        ur = UserReaction(user_email=email, post_id=post_id, emoji=emoji)
        db.session.add(ur)
    
    db.session.commit()
    
    # Recalc reactions
    reactions = {"👍": 0, "❤️": 0, "😂": 0}
    for ur in UserReaction.query.filter_by(post_id=post_id).all():
        if ur.emoji in reactions:
            reactions[ur.emoji] += 1
    post.reactions_json = _json.dumps(reactions)
    db.session.commit()
    
    return jsonify({"success": True, "reactions": reactions})

# ---------- Follow Routes ----------
@app.route("/api/follow/<user_email>", methods=["POST"])
def api_follow(user_email):
    email = session.get("user_email")
    if not email:
        return jsonify({"error": "Not logged in"}), 401
    if email == user_email:
        return jsonify({"error": "Cannot follow yourself"}), 400
    
    existing = Follower.query.filter_by(user_email=user_email, follower_email=email).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({"success": True, "following": False})
    
    follower = Follower(user_email=user_email, follower_email=email)
    db.session.add(follower)
    db.session.commit()
    
    # Notify
    notif = Notification(user_email=user_email, text=f"{email} started following you")
    db.session.add(notif)
    db.session.commit()
    
    return jsonify({"success": True, "following": True})

@app.route("/api/followers/<email>")
def api_followers(email):
    followers = Follower.query.filter_by(user_email=email).all()
    return jsonify([{"email": f.follower_email} for f in followers])

@app.route("/api/following/<email>")
def api_following(email):
    following = Follower.query.filter_by(follower_email=email).all()
    return jsonify([{"email": f.user_email} for f in following])

# ---------- Notification Routes ----------
@app.route("/api/notifications")
def api_notifications():
    email = session.get("user_email")
    if not email:
        return jsonify({"error": "Not logged in"}), 401
    notifs = Notification.query.filter_by(user_email=email).order_by(Notification.id.desc()).all()
    return jsonify([n.to_dict() for n in notifs])

@app.route("/api/notification/<int:notif_id>/read", methods=["POST"])
def api_notification_read(notif_id):
    notif = Notification.query.get_or_404(notif_id)
    notif.seen = 1
    db.session.commit()
    return jsonify({"success": True})

# ---------- Ad Campaign Routes ----------
@app.route("/api/ad/create", methods=["POST"])
def api_ad_create():
    email = session.get("user_email")
    if not email:
        return jsonify({"error": "Not logged in"}), 401
    
    data = request.get_json() or {}
    title = data.get("title", "").strip()
    whatsapp = data.get("whatsapp_number", "").strip()
    budget = float(data.get("budget", 0))
    
    if not title or budget <= 0 or not whatsapp:
        return jsonify({"error": "Missing fields"}), 400
    
    ad = Ad(title=title, owner_email=email, whatsapp_number=whatsapp, budget=budget, approved=0)
    db.session.add(ad)
    db.session.commit()
    
    return jsonify({"success": True, "ad": ad.to_dict()})

@app.route("/api/ads")
def api_ads():
    ads = Ad.query.filter_by(approved=1).order_by(Ad.id.desc()).all()
    return jsonify([a.to_dict() for a in ads])

@app.route("/api/ads/my")
def api_my_ads():
    email = session.get("user_email")
    if not email:
        return jsonify({"error": "Not logged in"}), 401
    ads = Ad.query.filter_by(owner_email=email).order_by(Ad.id.desc()).all()
    return jsonify([a.to_dict() for a in ads])

@app.route("/api/ad/<int:ad_id>/click", methods=["POST"])
def api_ad_click(ad_id):
    ad = Ad.query.get_or_404(ad_id)
    ad.clicks += 1
    db.session.commit()
    return jsonify({"success": True})

# ---------- Watch Hours / Earnings Routes ----------
@app.route("/api/watch", methods=["POST"])
def api_watch():
    data = request.get_json() or {}
    creator_email = data.get("creator_email", "").strip()
    duration_seconds = int(data.get("duration_seconds", 0))
    
    if duration_seconds < 1:
        return jsonify({"error": "Invalid duration"}), 400
    
    watch_hours = duration_seconds / 3600.0
    user = User.query.filter_by(email=creator_email).first()
    if not user:
        return jsonify({"error": "Creator not found"}), 404
    
    user.watch_hours = int(user.watch_hours + watch_hours)
    # Earnings: 0.10 per watch hour
    user.earnings += watch_hours * 0.10
    db.session.commit()
    
    return jsonify({"success": True, "watch_hours": user.watch_hours, "earnings": round(user.earnings, 2)})

# ---------- Admin Routes ----------
@app.route("/")
def admin_dashboard():
    if not require_admin():
        return "Access denied", 403
    
    users = User.query.all()
    posts = Post.query.all()
    payouts = PayoutRequest.query.filter_by(status="pending").all()
    ads = Ad.query.filter_by(approved=0).all()
    
    rows_users = "".join([f"<tr><td>{u.id}</td><td>{u.email}</td><td>{u.name}</td><td>{u.watch_hours}</td><td>P{u.earnings:.2f}</td><td>{'✓' if u.verified else 'X'}</td><td><button onclick=\"verifyUser('{u.email}', {1 if not u.verified else 0})\">{'Unverify' if u.verified else 'Verify'}</button><button onclick=\"banUser('{u.email}', {1 if not u.banned else 0})\">{'Unban' if u.banned else 'Ban'}</button><button onclick=\"deleteUser('{u.email}')\">Delete</button></td></tr>" for u in users])
    rows_posts = "".join([f"<tr><td>{p.id}</td><td>{p.author_email}</td><td>{p.text[:50]}</td><td>{p.timestamp}</td></tr>" for p in posts])
    rows_ads = "".join([f"<tr><td>{a.id}</td><td>{a.title}</td><td>{a.owner_email}</td><td>P{a.budget}</td><td>{a.impressions}</td><td>{'Approved' if a.approved else 'Pending'}</td><td><button onclick=\"approveAd({a.id}, {1 if not a.approved else 0})\">{'Reject' if a.approved else 'Approve'}</button></td></tr>" for a in ads])
    rows_payouts = "".join([f"<tr><td>{pr.id}</td><td>{pr.user_email}</td><td>{pr.om_number}</td><td>P{pr.amount:.2f}</td><td>{pr.created_at}</td><td>{pr.status}</td><td><button onclick=\"markPaid({pr.id})\">Mark Paid</button></td></tr>" for pr in payouts])
    
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>VibeNet Admin</title>
<style>
body {{ font-family: Segoe UI, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
h1 {{ color: #333; text-align: center; }}
.section {{ background: white; padding: 20px; margin: 20px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
th {{ background: #4CAF50; color: white; }}
button {{ background: #4CAF50; color: white; padding: 6px 12px; border: none; border-radius: 4px; cursor: pointer; }}
button:hover {{ background: #45a049; }}
</style></head><body>
<h1>🎬 VibeNet Admin Dashboard</h1>

<div class="section">
  <h2>👥 Users</h2>
  <table><tr><th>ID</th><th>Email</th><th>Name</th><th>Watch Hours</th><th>Earnings</th><th>Verified</th><th>Actions</th></tr>
  {rows_users}</table>
</div>

<div class="section">
  <h2>📝 Posts</h2>
  <table><tr><th>ID</th><th>Author</th><th>Text</th><th>Timestamp</th></tr>
  {rows_posts}</table>
</div>

<div class="section">
  <h2>📣 Ad Campaigns</h2>
  <table><tr><th>ID</th><th>Title</th><th>Owner</th><th>Budget</th><th>Impressions</th><th>Status</th><th>Actions</th></tr>
  {rows_ads}</table>
</div>

<div class="section">
  <h2>💸 Payout Requests</h2>
  <table><tr><th>ID</th><th>User</th><th>OM Number</th><th>Amount</th><th>Date</th><th>Status</th></tr>
  {rows_payouts}</table>
</div>

<script>
async function approveAd(id, status){{
  const r = await fetch('/api/admin/ads/'+id+'/approve',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{status}})}});
  const j = await r.json();
  if(j.success) location.reload(); else alert(j.error||'Failed');
}}
async function markPaid(id){{
  const r = await fetch('/api/admin/payout/'+id+'/mark-paid',{{method:'POST'}});
  const j = await r.json();
  if(j.success) location.reload(); else alert(j.error||'Failed');
}}
async function banUser(email, val){{
  if(val && !confirm('Ban '+email+'?')) return;
  const r = await fetch('/api/admin/user/ban',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{email,val}})}});
  const j = await r.json();
  if(j.success) location.reload(); else alert(j.error||'Failed');
}}
async function verifyUser(email, val){{
  const r = await fetch('/api/admin/user/verify',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{email,val}})}});
  const j = await r.json();
  if(j.success) location.reload(); else alert(j.error||'Failed');
}}
async function deleteUser(email){{
  if(!confirm('Permanently delete '+email+' and all their content?')) return;
  const r = await fetch('/api/admin/user/delete',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{email}})}});
  const j = await r.json();
  if(j.success) location.reload(); else alert(j.error||'Failed');
}}
</script></body></html>"""
    
    return render_template_string(html)


@app.route("/api/admin/ads/<int:ad_id>/approve", methods=["POST"])
def api_admin_approve_ad(ad_id):
    if not require_admin():
        return jsonify({"error": "Unauthorized"}), 403
    data = request.get_json() or {}
    ad   = Ad.query.get_or_404(ad_id)
    ad.approved = data.get("status", 1)
    db.session.commit()
    return jsonify({"success": True})


@app.route("/api/admin/payout/<int:payout_id>/mark-paid", methods=["POST"])
def api_admin_mark_paid(payout_id):
    if not require_admin():
        return jsonify({"error": "Unauthorized"}), 403
    pr = PayoutRequest.query.get_or_404(payout_id)
    pr.status = "paid"
    db.session.commit()
    return jsonify({"success": True})


@app.route("/api/admin/user/ban", methods=["POST"])
def api_admin_ban_user():
    if not require_admin():
        return jsonify({"error": "Unauthorized"}), 403
    data  = request.get_json() or {}
    email = data.get("email", "").strip()
    val   = int(data.get("val", 1))
    user  = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404
    user.banned = val
    db.session.commit()
    return jsonify({"success": True})


@app.route("/api/admin/user/verify", methods=["POST"])
def api_admin_verify_user():
    if not require_admin():
        return jsonify({"error": "Unauthorized"}), 403
    data  = request.get_json() or {}
    email = data.get("email", "").strip()
    val   = int(data.get("val", 1))
    user  = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404
    user.verified = val
    db.session.commit()
    return jsonify({"success": True})


@app.route("/api/admin/user/delete", methods=["POST"])
def api_admin_delete_user():
    if not require_admin():
        return jsonify({"error": "Unauthorized"}), 403
    data  = request.get_json() or {}
    email = data.get("email", "").strip()
    if email == ADMIN_EMAIL:
        return jsonify({"error": "Cannot delete admin account"}), 403
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404
    # Delete all user content
    post_ids = [p.id for p in Post.query.filter_by(author_email=email).all()]
    if post_ids:
        UserReaction.query.filter(UserReaction.post_id.in_(post_ids)).delete(synchronize_session=False)
    Post.query.filter_by(author_email=email).delete()
    Follower.query.filter_by(user_email=email).delete()
    Follower.query.filter_by(follower_email=email).delete()
    Notification.query.filter_by(user_email=email).delete()
    PayoutRequest.query.filter_by(user_email=email).delete()
    db.session.delete(user)
    db.session.commit()
    return jsonify({"success": True})


# ---------- Admin Management (API) ----------
@app.route("/api/admin/stats")
def api_admin_stats():
    if not require_admin():
        return jsonify({"error": "Unauthorized"}), 403
    return jsonify({
        "users":                  User.query.count(),
        "posts":                  Post.query.count(),
        "pending_payouts":        PayoutRequest.query.filter_by(status="pending").count(),
        "platform_earnings_hold": round(db.session.query(func.sum(User.earnings)).scalar() or 0, 2),
        "pending_ads":            Ad.query.filter_by(approved=0).count(),
    })


@app.route("/api/admin/users")
def api_admin_users():
    if not require_admin():
        return jsonify({"error": "Unauthorized"}), 403
    users = User.query.order_by(User.id.desc()).all()
    return jsonify([u.to_dict() for u in users])


@app.route("/api/admin/user/<int:user_id>/action", methods=["POST"])
def api_admin_user_action(user_id):
    if not require_admin():
        return jsonify({"error": "Unauthorized"}), 403
    data   = request.get_json() or {}
    action = data.get("action")  # verify | unverify | ban | unban
    user   = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    if action == "verify":     user.verified = 1
    elif action == "unverify": user.verified = 0
    elif action == "ban":      user.banned = 1
    elif action == "unban":    user.banned = 0
    else: return jsonify({"error": "Unknown action"}), 400
    db.session.commit()
    return jsonify({"success": True, "message": f"User {action}ed successfully"})


# ---------- Payout Requests ----------
@app.route("/api/payout", methods=["POST"])
def api_payout_request():
    data      = request.get_json() or {}
    email     = data.get("email", "").strip()
    om_number = data.get("om_number", "").strip()
    amount    = float(data.get("amount", 0))
    if not email or not om_number or amount <= 0:
        return jsonify({"error": "Missing fields"}), 400
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404
    # Must be eligible: 1K followers + 4K watch hours
    followers = Follower.query.filter_by(user_email=email).count()
    if followers < 1000 or user.watch_hours < 4000:
        return jsonify({"error": f"You need 1,000 followers and 4,000 watch hours to request a payout. You have {followers} followers and {user.watch_hours} watch hours."}), 403
    if user.earnings < amount:
        return jsonify({"error": f"Insufficient balance. Your earnings are P{user.earnings:.2f}"}), 400
    user.earnings -= amount
    pr = PayoutRequest(user_email=email, user_name=user.name or "",
                       om_number=om_number, amount=amount, status="pending")
    db.session.add(pr)
    db.session.commit()
    return jsonify({"success": True, "message": f"Payout of P{amount:.2f} requested. You'll receive it on {om_number} within 24–48hrs."})


@app.route("/api/payout/history/<email>")
def api_payout_history(email):
    items = PayoutRequest.query.filter_by(user_email=email).order_by(PayoutRequest.id.desc()).all()
    return jsonify([r.to_dict() for r in items])




# ══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=app.config["PORT"], debug=True)
