# app.py - VibeNet with Orange Money (Manual Payments - Botswana)
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
APP_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(APP_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 300 * 1024 * 1024
app.config["PORT"] = int(os.environ.get("PORT", 8000))
app.secret_key = os.environ.get("SECRET_KEY", "vibenet_secret_botswana")

# IMPORTANT: Set your Orange Money number here (where ad payments go)
BUSINESS_ORANGE_MONEY = os.environ.get("BUSINESS_ORANGE_MONEY", "+267XXXXXXXX")

# ---------- Cloudinary ----------
CLOUDINARY_URL = os.environ.get("CLOUDINARY_URL", "")
_cld_cloud = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
_cld_key = os.environ.get("CLOUDINARY_API_KEY", "")
_cld_secret = os.environ.get("CLOUDINARY_API_SECRET", "")

if _cld_cloud and _cld_key and _cld_secret:
    cloudinary.config(cloud_name=_cld_cloud, api_key=_cld_key, api_secret=_cld_secret, secure=True)
elif CLOUDINARY_URL:
    cloudinary.config(cloudinary_url=CLOUDINARY_URL)

def _cloudinary_ok():
    cfg = cloudinary.config()
    return bool(cfg.cloud_name and cfg.api_key)

def upload_to_cloudinary(file_storage, folder="vibenet"):
    result = cloudinary.uploader.upload(
        file_storage,
        folder=folder,
        resource_type="auto",
        overwrite=False,
        eager=[{"quality": "auto", "fetch_format": "auto"}],
    )
    return result["secure_url"]

def _optimize_cloudinary_url(url, is_video=False):
    if not url or "cloudinary.com" not in url:
        return url
    t = "q_auto,f_auto,vc_auto" if is_video else "q_auto,f_auto"
    return url.replace("/upload/", f"/upload/{t}/")

# ---------- Database ----------
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = (
    DATABASE_URL if DATABASE_URL
    else f"sqlite:///{os.path.join(APP_DIR, 'data', 'vibenet.db')}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 280,
    "pool_pre_ping": True,
}

os.makedirs(os.path.join(APP_DIR, "data"), exist_ok=True)
db = SQLAlchemy(app)

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
    orange_money = db.Column(db.Text, nullable=True)  # Their Orange Money number
    created_at = db.Column(db.Text, default=lambda: now_ts())

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "email": self.email,
            "profile_pic": self.profile_pic, "bio": self.bio,
            "watch_hours": self.watch_hours, "earnings": self.earnings,
            "verified": bool(self.verified), "orange_money": bool(self.orange_money),
        }

class Follower(db.Model):
    __tablename__ = "followers"
    id = db.Column(db.Integer, primary_key=True)
    user_email = db.Column(db.Text, nullable=False)
    follower_email = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.Text, default=lambda: now_ts())
    __table_args__ = (db.UniqueConstraint("user_email", "follower_email", name="uq_follow"),)

class Post(db.Model):
    __tablename__ = "posts"
    id = db.Column(db.Integer, primary_key=True)
    author_email = db.Column(db.Text, nullable=False)
    author_name = db.Column(db.Text)
    profile_pic = db.Column(db.Text, default="")
    text = db.Column(db.Text, default="")
    file_url = db.Column(db.Text, default="")
    timestamp = db.Column(db.Text, default=lambda: now_ts())
    reactions_json = db.Column(db.Text, default='{"👍":0,"❤️":0,"😂":0}')
    comments_count = db.Column(db.Integer, default=0)

    def reactions(self):
        try:
            return _json.loads(self.reactions_json or "{}")
        except:
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
    id = db.Column(db.Integer, primary_key=True)
    user_email = db.Column(db.Text, nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=False)
    emoji = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.Text, default=lambda: now_ts())
    __table_args__ = (db.UniqueConstraint("user_email", "post_id", name="uq_reaction"),)

class Notification(db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    user_email = db.Column(db.Text, nullable=False)
    text = db.Column(db.Text)
    timestamp = db.Column(db.Text, default=lambda: now_ts())
    seen = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {"id": self.id, "text": self.text, "timestamp": self.timestamp, "seen": self.seen}

class Ad(db.Model):
    __tablename__ = "ads"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.Text)
    owner_email = db.Column(db.Text)
    budget = db.Column(db.Float, default=0.0)
    impressions = db.Column(db.Integer, default=0)
    clicks = db.Column(db.Integer, default=0)
    created_at = db.Column(db.Text, default=lambda: now_ts())
    payment_status = db.Column(db.Text, default="pending")  # pending, received
    payment_date = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            "id": self.id, "title": self.title, "owner_email": self.owner_email,
            "budget": self.budget, "impressions": self.impressions, "clicks": self.clicks,
            "payment_status": self.payment_status, "payment_date": self.payment_date,
        }

class PayoutRequest(db.Model):
    __tablename__ = "payout_requests"
    id = db.Column(db.Integer, primary_key=True)
    creator_email = db.Column(db.Text, nullable=False)
    orange_money = db.Column(db.Text, nullable=False)
    amount = db.Column(db.Float)
    status = db.Column(db.Text, default="pending")  # pending, sent, cancelled
    requested_at = db.Column(db.Text, default=lambda: now_ts())
    sent_at = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            "id": self.id, "creator_email": self.creator_email,
            "orange_money": self.orange_money, "amount": self.amount,
            "status": self.status, "requested_at": self.requested_at,
            "sent_at": self.sent_at,
        }

# Create tables
with app.app_context():
    db.create_all()

# ---------- Static uploads ----------
@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)

# ---------- Frontend ----------
@app.route("/")
def index():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>VibeNet - Botswana Creator Platform</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #060910; color: #fff; margin: 0; padding: 20px; }
            .container { max-width: 800px; margin: 0 auto; }
            h1 { color: #4DF0C0; text-align: center; }
            .status { background: #1a1f2e; padding: 20px; border-radius: 10px; margin: 20px 0; }
            .success { color: #4DF0C0; }
            .info { color: #8899B4; font-size: 14px; }
            .highlight { background: rgba(77,240,192,0.1); padding: 15px; border-left: 3px solid #4DF0C0; margin: 10px 0; border-radius: 5px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>✅ VibeNet - Orange Money Edition</h1>
            <div class="status">
                <h2>Status: <span class="success">LIVE</span></h2>
                <p class="info">🎉 VibeNet is running with Orange Money integration!</p>
                <p class="info">🤖 Manual Orange Money payments (Botswana)</p>
                <p class="info">💰 Advertisers pay to: <strong>{{BUSINESS_ORANGE_MONEY}}</strong></p>
                <p class="info">🚀 Creators withdraw to their Orange Money</p>
            </div>
            <div class="highlight">
                <strong>How it works:</strong><br>
                1️⃣ Advertisers create ad campaigns<br>
                2️⃣ You send them a payment request to your Orange Money<br>
                3️⃣ They pay via Orange Money<br>
                4️⃣ You mark payment as received<br>
                5️⃣ Creators request payout with their Orange Money number<br>
                6️⃣ You send them money via Orange Money
            </div>
        </div>
    </body>
    </html>
    """.replace("{{BUSINESS_ORANGE_MONEY}}", BUSINESS_ORANGE_MONEY)

# ========== API ROUTES ==========

# Auth
@app.route("/api/signup", methods=["POST"])
def api_signup():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    
    if not email or not password:
        return jsonify({"error": "email + password required"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "User already exists"}), 400

    profile_pic = ""
    if "file" in request.files:
        f = request.files["file"]
        if f and f.filename:
            if _cloudinary_ok():
                try:
                    profile_pic = upload_to_cloudinary(f, folder="vibenet/avatars")
                except:
                    pass
            else:
                fn = f"{uuid.uuid4().hex}_{f.filename}"
                f.save(os.path.join(UPLOAD_DIR, fn))
                profile_pic = f"/uploads/{fn}"

    user = User(name=name, email=email, password=password, profile_pic=profile_pic)
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

# Upload
@app.route("/api/upload", methods=["POST"])
def api_upload():
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "No filename"}), 400
    fn = f"{uuid.uuid4().hex}_{f.filename}"
    f.save(os.path.join(UPLOAD_DIR, fn))
    return jsonify({"url": f"/uploads/{fn}"})

@app.route("/api/sign-upload", methods=["POST"])
def api_sign_upload():
    if not _cloudinary_ok():
        return jsonify({"error": "Cloudinary not configured"}), 503
    import time, hashlib
    data = request.get_json() or {}
    folder = data.get("folder", "vibenet/posts")
    timestamp = int(time.time())
    param_str = f"folder={folder}&timestamp={timestamp}"
    sig_input = param_str + cloudinary.config().api_secret
    signature = hashlib.sha1(sig_input.encode()).hexdigest()
    return jsonify({
        "signature": signature,
        "timestamp": timestamp,
        "api_key": cloudinary.config().api_key,
        "cloud_name": cloudinary.config().cloud_name,
        "folder": folder,
    })

# Posts
@app.route("/api/posts", methods=["GET", "POST"])
def api_posts():
    if request.method == "GET":
        posts = Post.query.order_by(Post.id.desc()).all()
        emails = list({p.author_email for p in posts})
        verified_map = {}
        if emails:
            users = User.query.filter(User.email.in_(emails)).all()
            verified_map = {u.email: bool(u.verified) for u in users}
        return jsonify([p.to_dict(author_verified=verified_map.get(p.author_email, False)) for p in posts])

    data = request.get_json() or {}
    post = Post(
        author_email=data.get("author_email"),
        author_name=data.get("author_name"),
        profile_pic=data.get("profile_pic", ""),
        text=data.get("text", ""),
        file_url=data.get("file_url", ""),
    )
    db.session.add(post)
    db.session.commit()
    return jsonify(post.to_dict())

@app.route("/api/posts/<int:post_id>", methods=["DELETE", "PATCH"])
def api_post_modify(post_id):
    data = request.get_json() or {}
    email = data.get("email")
    post = Post.query.get_or_404(post_id)
    if post.author_email != email:
        return jsonify({"error": "Unauthorized"}), 403

    if request.method == "DELETE":
        UserReaction.query.filter_by(post_id=post_id).delete()
        db.session.delete(post)
        db.session.commit()
        return jsonify({"success": True})

    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "Text required"}), 400
    post.text = text
    db.session.commit()
    return jsonify({"success": True})

# React
@app.route("/api/react", methods=["POST"])
def api_react_post():
    data = request.get_json() or {}
    post_id = data.get("post_id")
    emoji = data.get("emoji")
    user_email = data.get("user_email")

    post = Post.query.get(post_id)
    if not post:
        return jsonify({"error": "Post not found"}), 404

    reactions = post.reactions()
    prev_react = UserReaction.query.filter_by(user_email=user_email, post_id=post_id).first()
    prev_emoji = prev_react.emoji if prev_react else None

    if prev_emoji == emoji:
        return jsonify({"success": True, "reactions": reactions})

    if prev_react:
        reactions[prev_emoji] = max(0, reactions.get(prev_emoji, 0) - 1)
        db.session.delete(prev_react)

    new_react = UserReaction(user_email=user_email, post_id=post_id, emoji=emoji)
    db.session.add(new_react)
    reactions[emoji] = reactions.get(emoji, 0) + 1
    post.reactions_json = _json.dumps(reactions)

    if post.author_email != user_email:
        notif = Notification(user_email=post.author_email, text=f"{emoji} reaction on your post")
        db.session.add(notif)

    db.session.commit()
    return jsonify({"success": True, "reactions": reactions})

# Notifications
@app.route("/api/notifications/<email>")
def api_notifications_get(email):
    notifs = Notification.query.filter_by(user_email=email).order_by(Notification.id.desc()).all()
    return jsonify([n.to_dict() for n in notifs])

# Monetization
@app.route("/api/monetization/<email>")
def api_monetization_get(email):
    followers = Follower.query.filter_by(user_email=email).count()
    user = User.query.filter_by(email=email).first()
    if user:
        return jsonify({"followers": followers, "watch_hours": user.watch_hours, "earnings": user.earnings})
    return jsonify({"followers": 0, "watch_hours": 0, "earnings": 0})

@app.route("/api/profile/<email>")
def api_profile_get(email):
    user = User.query.filter_by(email=email).first()
    posts = Post.query.filter_by(author_email=email).order_by(Post.id.desc()).all()
    return jsonify({
        "bio": user.bio if user else "",
        "posts": [p.to_dict() for p in posts],
    })

@app.route("/api/update_bio", methods=["POST"])
def api_update_bio():
    data = request.get_json() or {}
    user = User.query.filter_by(email=data.get("email")).first()
    if user:
        user.bio = data.get("bio", "")
        db.session.commit()
    return jsonify({"success": True})

# Follow
@app.route("/api/follow", methods=["POST"])
def api_follow():
    data = request.get_json() or {}
    follower = data.get("follower_email")
    target = data.get("target_email")

    existing = Follower.query.filter_by(user_email=target, follower_email=follower).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({"success": True, "status": "unfollowed"})

    db.session.add(Follower(user_email=target, follower_email=follower))
    db.session.add(Notification(user_email=target, text=f"{follower} followed you"))
    db.session.commit()
    return jsonify({"success": True, "status": "followed"})

@app.route("/api/is_following")
def api_is_following():
    f = request.args.get("f")
    t = request.args.get("t")
    exists = Follower.query.filter_by(user_email=t, follower_email=f).first() is not None
    return jsonify({"following": exists})

# Watch & Ads
@app.route("/api/watch", methods=["POST"])
def api_watch():
    data = request.get_json() or {}
    viewer = data.get("viewer")
    post_id = data.get("post_id")
    post = Post.query.get(post_id)
    if post and post.author_email != viewer:
        author = User.query.filter_by(email=post.author_email).first()
        if author:
            author.watch_hours += 1
            author.earnings += 0.10
            db.session.commit()
    return jsonify({"success": True})

@app.route("/api/ads", methods=["GET", "POST"])
def api_ads():
    if request.method == "POST":
        data = request.get_json() or {}
        ad = Ad(title=data.get("title"), owner_email=data.get("owner"), budget=data.get("budget", 0))
        db.session.add(ad)
        db.session.commit()
        return jsonify({"message": "Ad created", "id": ad.id})
    ads = Ad.query.order_by(Ad.id.desc()).all()
    return jsonify([a.to_dict() for a in ads])

@app.route("/api/ads/impression", methods=["POST"])
def api_ads_impression():
    return jsonify({"success": True})

# ========== ORANGE MONEY ROUTES ==========

# Get business Orange Money number
@app.route("/api/orange-money/business-number")
def get_business_number():
    return jsonify({"orange_money": BUSINESS_ORANGE_MONEY})

# Create ad and return payment instructions
@app.route("/api/orange-money/create-ad", methods=["POST"])
def orange_create_ad():
    """Create ad and show payment instructions"""
    data = request.get_json() or {}
    title = data.get("title", "").strip()
    budget = float(data.get("budget", 0))
    owner_email = data.get("owner_email")
    
    if not title or budget <= 0:
        return jsonify({"error": "Invalid title or budget"}), 400
    
    # Create ad
    ad = Ad(title=title, owner_email=owner_email, budget=budget, payment_status="pending")
    db.session.add(ad)
    db.session.commit()
    
    return jsonify({
        "success": True,
        "ad_id": ad.id,
        "message": f"Send P{budget} to {BUSINESS_ORANGE_MONEY}",
        "instructions": f"Please send P{budget} via Orange Money to {BUSINESS_ORANGE_MONEY} with reference: AD-{ad.id}",
        "business_orange_money": BUSINESS_ORANGE_MONEY,
    })

# Mark ad payment as received
@app.route("/api/orange-money/payment-received/<int:ad_id>", methods=["POST"])
def mark_payment_received(ad_id):
    """Mark ad payment as received (admin only)"""
    data = request.get_json() or {}
    admin_password = data.get("admin_password")
    
    # Simple auth (replace with proper auth)
    if admin_password != os.environ.get("ADMIN_PASSWORD", "admin123"):
        return jsonify({"error": "Unauthorized"}), 401
    
    ad = Ad.query.get_or_404(ad_id)
    ad.payment_status = "received"
    ad.payment_date = now_ts()
    db.session.commit()
    
    return jsonify({
        "success": True,
        "message": f"Payment received for {ad.title}",
        "ad_id": ad.id,
    })

# Creator requests payout
@app.route("/api/orange-money/request-payout", methods=["POST"])
def request_payout():
    """Creator requests payout to their Orange Money"""
    data = request.get_json() or {}
    creator_email = data.get("creator_email")
    orange_money = data.get("orange_money", "").strip()
    
    if not creator_email or not orange_money:
        return jsonify({"error": "Email and Orange Money required"}), 400
    
    user = User.query.filter_by(email=creator_email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    if user.earnings < 10:
        return jsonify({
            "error": f"Minimum payout is P10. Your balance: P{user.earnings:.2f}"
        }), 400
    
    # Validate Orange Money format
    if not orange_money.startswith("+267") and not orange_money.startswith("267"):
        return jsonify({"error": "Invalid Orange Money number format"}), 400
    
    # Create payout request
    payout = PayoutRequest(
        creator_email=creator_email,
        orange_money=orange_money,
        amount=user.earnings,
    )
    db.session.add(payout)
    
    # Save Orange Money for future reference
    user.orange_money = orange_money
    db.session.commit()
    
    return jsonify({
        "success": True,
        "payout_id": payout.id,
        "amount": payout.amount,
        "message": f"Payout request submitted. We'll send P{payout.amount:.2f} to {orange_money}",
        "instructions": "You will receive the money within 24 hours. Check your Orange Money balance.",
    })

# Get payout requests (admin)
@app.route("/api/orange-money/payout-requests")
def get_payout_requests():
    """Get pending payout requests (admin)"""
    admin_password = request.args.get("admin_password")
    
    if admin_password != os.environ.get("ADMIN_PASSWORD", "admin123"):
        return jsonify({"error": "Unauthorized"}), 401
    
    pending = PayoutRequest.query.filter_by(status="pending").order_by(PayoutRequest.requested_at.desc()).all()
    return jsonify([p.to_dict() for p in pending])

# Mark payout as sent (admin)
@app.route("/api/orange-money/payout-sent/<int:payout_id>", methods=["POST"])
def mark_payout_sent(payout_id):
    """Mark payout as sent (admin)"""
    data = request.get_json() or {}
    admin_password = data.get("admin_password")
    
    if admin_password != os.environ.get("ADMIN_PASSWORD", "admin123"):
        return jsonify({"error": "Unauthorized"}), 401
    
    payout = PayoutRequest.query.get_or_404(payout_id)
    payout.status = "sent"
    payout.sent_at = now_ts()
    
    # Reset creator earnings
    user = User.query.filter_by(email=payout.creator_email).first()
    if user:
        user.earnings = 0
        db.session.add(user)
    
    db.session.commit()
    
    return jsonify({
        "success": True,
        "message": f"Payout sent to {payout.orange_money}",
        "amount": payout.amount,
    })

# ========== RUN ==========

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🚀 VibeNet - Orange Money Edition (Botswana)")
    print("="*60)
    print(f"💰 Business Orange Money: {BUSINESS_ORANGE_MONEY}")
    print(f"📊 Database: {('PostgreSQL' if os.environ.get('DATABASE_URL') else 'SQLite')}")
    print(f"📍 Port: {app.config['PORT']}")
    print("="*60 + "\n")
    
    app.run(host="0.0.0.0", port=app.config["PORT"], debug=False)
