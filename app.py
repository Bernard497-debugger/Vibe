# app.py - VibeNet  (SQLAlchemy ORM  |  SQLite locally  |  PostgreSQL on Render)
import os
import uuid
import datetime
import json as _json
from flask import Flask, request, jsonify, send_from_directory, session, render_template_string

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
import cloudinary

# ---------- Config ----------
APP_DIR   = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(APP_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 300 * 1024 * 1024
app.config["PORT"] = int(os.environ.get("PORT", 5000))
app.secret_key = os.environ.get("SECRET_KEY", "vibenet_secret_dev")

# ---------- Cloudinary ----------
CLOUDINARY_URL = os.environ.get("CLOUDINARY_URL", "")  # set this on Render
# CLOUDINARY_URL format: cloudinary://API_KEY:API_SECRET@CLOUD_NAME
# Cloudinary SDK auto-parses CLOUDINARY_URL env var, but we configure explicitly too:
_cld_cloud  = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
_cld_key    = os.environ.get("CLOUDINARY_API_KEY", "")
_cld_secret = os.environ.get("CLOUDINARY_API_SECRET", "")
if _cld_cloud and _cld_key and _cld_secret:
    cloudinary.config(cloud_name=_cld_cloud, api_key=_cld_key,
                      api_secret=_cld_secret, secure=True)
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
    "pool_recycle": 280,   # keep Render/Postgres connections alive
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
    id          = db.Column(db.Integer, primary_key=True)
    title       = db.Column(db.Text)
    owner_email = db.Column(db.Text)
    budget      = db.Column(db.Float, default=0.0)
    impressions = db.Column(db.Integer, default=0)
    clicks      = db.Column(db.Integer, default=0)
    created_at  = db.Column(db.Text, default=lambda: now_ts())

    def to_dict(self):
        return {
            "id": self.id, "title": self.title, "owner_email": self.owner_email,
            "budget": self.budget, "impressions": self.impressions, "clicks": self.clicks,
        }


class PayoutRequest(db.Model):
    __tablename__ = "payout_requests"
    id            = db.Column(db.Integer, primary_key=True)
    user_email    = db.Column(db.Text, nullable=False)
    user_name     = db.Column(db.Text, default="")
    om_number     = db.Column(db.Text, nullable=False)   # creator's Orange Money number
    amount        = db.Column(db.Float, nullable=False)  # amount in BWP
    status        = db.Column(db.Text, default="pending")  # pending | paid | rejected
    created_at    = db.Column(db.Text, default=lambda: now_ts())

    def to_dict(self):
        return {
            "id": self.id, "user_email": self.user_email, "user_name": self.user_name,
            "om_number": self.om_number, "amount": self.amount,
            "status": self.status, "created_at": self.created_at,
        }


# ---------- Create tables ----------
with app.app_context():
    db.create_all()

# ---------- Static uploads ----------
@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


# ---------- Frontend ----------
HTML = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>VibeNet</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;500;600;700;800&family=DM+Sans:ital,wght@0,300;0,400;0,500;1,300&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #060910;
  --surface: #0c1018;
  --card: #101520;
  --card2: #131925;
  --border: rgba(255,255,255,0.06);
  --accent: #4DF0C0;
  --accent2: #7B6EF6;
  --accent3: #F06A4D;
  --text: #E8F0FF;
  --muted: #5A6A85;
  --muted2: #8899B4;
  --danger: #F06A4D;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: var(--bg);
  font-family: 'DM Sans', sans-serif;
  color: var(--text);
  min-height: 100vh;
  overflow-x: hidden;
}

body::before {
  content: '';
  position: fixed;
  top: -40%;
  left: -20%;
  width: 70%;
  height: 70%;
  background: radial-gradient(ellipse, rgba(77,240,192,0.04) 0%, transparent 70%);
  pointer-events: none;
  z-index: 0;
}
body::after {
  content: '';
  position: fixed;
  bottom: -30%;
  right: -10%;
  width: 60%;
  height: 60%;
  background: radial-gradient(ellipse, rgba(123,110,246,0.05) 0%, transparent 70%);
  pointer-events: none;
  z-index: 0;
}

/* ===== AUTH SCREEN ===== */
#authScreen {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  background: var(--bg);
  padding: 20px;
}

.auth-wrap {
  width: 100%;
  max-width: 900px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2px;
  background: var(--border);
  border-radius: 20px;
  overflow: hidden;
  box-shadow: 0 40px 120px rgba(0,0,0,0.8);
  animation: fadeUp 0.5s ease both;
}

@keyframes fadeUp {
  from { opacity: 0; transform: translateY(24px); }
  to   { opacity: 1; transform: translateY(0); }
}

.auth-brand {
  background: linear-gradient(145deg, #0d1826, #080f1a);
  padding: 52px 44px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  position: relative;
  overflow: hidden;
}

.auth-brand::before {
  content: 'VN';
  position: absolute;
  bottom: -30px;
  right: -20px;
  font-family: 'Syne', sans-serif;
  font-size: 160px;
  font-weight: 800;
  color: rgba(77,240,192,0.04);
  line-height: 1;
  letter-spacing: -8px;
}

.brand-logo {
  font-family: 'Syne', sans-serif;
  font-size: 38px;
  font-weight: 800;
  color: var(--accent);
  letter-spacing: -1px;
  margin-bottom: 16px;
}

.brand-tag {
  font-size: 15px;
  color: var(--muted2);
  line-height: 1.6;
  max-width: 240px;
}

.brand-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 32px;
}

.pill {
  background: rgba(77,240,192,0.08);
  border: 1px solid rgba(77,240,192,0.15);
  color: var(--accent);
  padding: 5px 12px;
  border-radius: 100px;
  font-size: 12px;
  font-weight: 500;
}

.auth-forms {
  background: var(--card);
  padding: 44px;
  display: flex;
  flex-direction: column;
  gap: 32px;
}

.auth-section h3 {
  font-family: 'Syne', sans-serif;
  font-size: 17px;
  font-weight: 700;
  margin-bottom: 16px;
  color: var(--text);
  letter-spacing: -0.3px;
}

.field {
  margin-bottom: 10px;
}

.field input {
  width: 100%;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 11px 14px;
  color: var(--text);
  font-family: 'DM Sans', sans-serif;
  font-size: 14px;
  transition: border-color 0.2s;
  outline: none;
}

.field input:focus {
  border-color: rgba(77,240,192,0.4);
}

.field input::placeholder { color: var(--muted); }

.field-label {
  font-size: 12px;
  color: var(--muted2);
  margin-bottom: 6px;
  font-weight: 500;
  letter-spacing: 0.3px;
  text-transform: uppercase;
}

.divider {
  height: 1px;
  background: var(--border);
}

/* Buttons */
.btn-primary {
  background: var(--accent);
  color: #030a0e;
  border: none;
  padding: 11px 22px;
  border-radius: 10px;
  font-family: 'Syne', sans-serif;
  font-weight: 700;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
  letter-spacing: 0.2px;
}
.btn-primary:hover { background: #6bf5d0; transform: translateY(-1px); }

.btn-ghost {
  background: transparent;
  color: var(--muted2);
  border: 1px solid var(--border);
  padding: 10px 20px;
  border-radius: 10px;
  font-family: 'DM Sans', sans-serif;
  font-weight: 500;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-ghost:hover { border-color: rgba(255,255,255,0.2); color: var(--text); }

.btn-icon {
  background: var(--card2);
  border: 1px solid var(--border);
  color: var(--muted2);
  width: 38px;
  height: 38px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 16px;
  transition: all 0.2s;
}
.btn-icon:hover { border-color: var(--accent); color: var(--accent); }

/* ===== MAIN APP ===== */
#mainApp {
  display: none;
  min-height: 100vh;
  position: relative;
  z-index: 1;
}

/* Top Nav */
.topnav {
  position: sticky;
  top: 0;
  z-index: 50;
  background: rgba(6,9,16,0.92);
  backdrop-filter: blur(20px);
  border-bottom: 1px solid var(--border);
  padding: 0 20px;
  height: 58px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.nav-brand {
  font-family: 'Syne', sans-serif;
  font-size: 20px;
  font-weight: 800;
  color: var(--accent);
  letter-spacing: -0.5px;
  flex-shrink: 0;
}

.nav-tabs {
  display: flex;
  gap: 2px;
  background: var(--surface);
  padding: 4px;
  border-radius: 12px;
  border: 1px solid var(--border);
  flex-shrink: 0;
}

.nav-tab {
  background: transparent;
  border: none;
  color: var(--muted2);
  padding: 7px 14px;
  border-radius: 9px;
  font-family: 'DM Sans', sans-serif;
  font-weight: 500;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 5px;
  white-space: nowrap;
  position: relative;
}

.nav-tab:hover { color: var(--text); background: rgba(255,255,255,0.04); }
.nav-tab.active { background: var(--card2); color: var(--text); }
.nav-tab.active::after {
  content: '';
  position: absolute;
  bottom: -1px;
  left: 50%;
  transform: translateX(-50%);
  width: 16px;
  height: 2px;
  background: var(--accent);
  border-radius: 2px;
}

.notif-dot {
  background: var(--danger);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 100px;
  line-height: 16px;
  min-width: 16px;
  text-align: center;
}

.nav-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.nav-avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  object-fit: cover;
  background: var(--surface);
  border: 2px solid var(--border);
  cursor: pointer;
}

.nav-signout {
  background: var(--surface);
  border: 1px solid var(--border);
  color: var(--muted2);
  width: 32px;
  height: 32px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 15px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}
.nav-signout:hover { border-color: rgba(240,106,77,0.5); color: var(--danger); background: rgba(240,106,77,0.07); }

/* ===== USER PANEL (below header, in sidebar) ===== */
.user-panel {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 20px;
  display: flex;
  flex-direction: column;   gap: 0;
}

.user-panel-top {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 14px;
}

.user-panel-avatar {
  width: 46px;
  height: 46px;
  border-radius: 50%;
  object-fit: cover;
  background: var(--surface);
  border: 2px solid rgba(77,240,192,0.25);
  flex-shrink: 0;
}

.user-panel-name {
  font-family: 'Syne', sans-serif;
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
  line-height: 1.2;
}

.user-panel-email {
  font-size: 12px;
  color: var(--muted);
  margin-top: 2px;
}

.user-panel-bio {
  font-size: 13px;
  color: var(--muted2);
  line-height: 1.5;
  margin-bottom: 14px;
  min-height: 18px;
}

.user-panel-actions {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.panel-btn {
  background: var(--surface);
  border: 1px solid var(--border);
  color: var(--muted2);
  padding: 9px 14px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  font-family: 'DM Sans', sans-serif;
}
.panel-btn:hover { border-color: rgba(77,240,192,0.3); color: var(--accent); background: rgba(77,240,192,0.04); }
.panel-btn.signout { color: var(--muted); }
.panel-btn.signout:hover { border-color: rgba(240,106,77,0.4); color: var(--danger); background: rgba(240,106,77,0.06); }

/* ===== LAYOUT ===== */
.app-layout {
  max-width: 680px;
  margin: 0 auto;
  padding: 28px 16px;
}

.main-col { min-width: 0; }

/* ===== TABS ===== */
.tab { display: none; animation: fadeIn 0.25s ease; }
.tab.visible { display: block; }

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* ===== POST COMPOSER ===== */
.composer {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 20px;
  margin-bottom: 20px;
}

.composer-top {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.composer-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  object-fit: cover;
  background: var(--surface);
  flex-shrink: 0;
}

.composer textarea {
  flex: 1;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px 16px;
  color: var(--text);
  font-family: 'DM Sans', sans-serif;
  font-size: 14.5px;
  resize: none;
  outline: none;
  transition: border-color 0.2s;
  min-height: 80px;
}
.composer textarea:focus { border-color: rgba(77,240,192,0.3); }
.composer textarea::placeholder { color: var(--muted); }

.composer-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.composer-actions { display: flex; gap: 8px; align-items: center; }

.attach-label {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--muted2);
  font-size: 13px;
  cursor: pointer;
  padding: 7px 12px;
  border-radius: 8px;
  background: var(--surface);
  border: 1px solid var(--border);
  transition: all 0.2s;
}
.attach-label:hover { border-color: rgba(77,240,192,0.3); color: var(--accent); }
.attach-label input { display: none; }

/* ===== POSTS ===== */
.post-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 20px;
  margin-bottom: 16px;
  transition: border-color 0.2s;
}
.post-card:hover { border-color: rgba(255,255,255,0.1); }

.post-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 14px;
}

.post-author {
  display: flex;
  gap: 10px;
  align-items: center;
}

.post-avatar {
  width: 42px;
  height: 42px;
  border-radius: 50%;
  object-fit: cover;
  background: var(--surface);
}

.post-author-info strong {
  display: block;
  font-size: 14.5px;
  font-weight: 600;
  color: var(--text);
}

.post-ts {
  font-size: 12px;
  color: var(--muted);
  margin-top: 2px;
}

.post-text {
  font-size: 15px;
  line-height: 1.65;
  color: #cad8f0;
  margin-bottom: 12px;
}

.post-media {
  border-radius: 12px;
  overflow: hidden;
  margin-bottom: 12px;
}
.post-media img, .post-media video {
  width: 100%;
  display: block;
  max-height: 460px;
  object-fit: cover;
  background: #000;
}

.post-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.reaction-bar { display: flex; gap: 6px; }

.react-btn {
  background: var(--surface);
  border: 1px solid var(--border);
  color: var(--muted2);
  padding: 6px 12px;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 4px;
}
.react-btn:hover { border-color: rgba(255,255,255,0.2); color: var(--text); }
.react-btn.active { background: rgba(77,240,192,0.1); border-color: rgba(77,240,192,0.3); color: var(--accent); }

.follow-btn {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--muted2);
  padding: 6px 14px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  font-family: 'Syne', sans-serif;
  letter-spacing: 0.3px;
}
.follow-btn:hover { border-color: var(--accent); color: var(--accent); }
.follow-btn.active { background: rgba(77,240,192,0.12); border-color: var(--accent); color: var(--accent); }

.comment-count {
  font-size: 12px;
  color: var(--muted);
  display: flex;
  align-items: center;
  gap: 4px;
}


/* Post owner action buttons */
.post-actions {
  display: flex;
  gap: 6px;
}

.action-btn {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--muted);
  width: 30px;
  height: 30px;
  border-radius: 7px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.18s;
  flex-shrink: 0;
}
.action-btn:hover { color: var(--text); border-color: rgba(255,255,255,0.2); }
.action-btn.delete:hover { color: var(--danger); border-color: var(--danger); background: rgba(240,106,77,0.08); }
.action-btn.edit-btn:hover { color: var(--accent); border-color: var(--accent); background: rgba(77,240,192,0.08); }

/* Edit modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.72);
  backdrop-filter: blur(6px);
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  animation: fadeIn 0.2s ease;
}

.modal-box {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 28px;
  width: 100%;
  max-width: 520px;
  box-shadow: 0 40px 100px rgba(0,0,0,0.8);
  animation: fadeUp 0.25s ease;
}

.modal-title {
  font-family: 'Syne', sans-serif;
  font-size: 18px;
  font-weight: 800;
  margin-bottom: 18px;
  letter-spacing: -0.3px;
}

.modal-footer {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

/* Video wrapper for autoplay UI */
.video-wrap {
  position: relative;
  border-radius: 12px;
  overflow: hidden;
  background: #000;
}
.video-wrap video { width: 100%; display: block; max-height: 460px; object-fit: cover; }
.play-hint {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0,0,0,0.32);
  pointer-events: none;
  transition: opacity 0.3s;
}
.play-hint span { font-size: 44px; filter: drop-shadow(0 2px 10px rgba(0,0,0,0.7)); }
.video-wrap.playing .play-hint { opacity: 0; }

.vbadge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #4DF0C0, #7B6EF6);
  color: #030a0e;
  font-size: 10px;
  font-weight: 900;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  margin-left: 4px;
  vertical-align: middle;
  line-height: 1;
}

/* ===== SECTION HEADER ===== */
.section-header {
  margin-bottom: 20px;
}
.section-header h2 {
  font-family: 'Syne', sans-serif;
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.5px;
}
.section-header p {
  color: var(--muted2);
  font-size: 13.5px;
  margin-top: 4px;
}

/* ===== NOTIFICATIONS ===== */
.notif-item {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 14px 0;
  border-bottom: 1px solid var(--border);
}
.notif-item:last-child { border-bottom: none; }

.notif-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: rgba(77,240,192,0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  flex-shrink: 0;
}
.notif-text { font-size: 14px; color: var(--muted2); line-height: 1.5; }
.notif-time { font-size: 12px; color: var(--muted); margin-top: 3px; }

/* ===== MONETIZATION ===== */
.monet-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
  margin-bottom: 24px;
}

.monet-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 20px;
}

.monet-card-label {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  color: var(--muted2);
  font-weight: 600;
  margin-bottom: 8px;
}

.monet-card-value {
  font-family: 'Syne', sans-serif;
  font-size: 28px;
  font-weight: 800;
  color: var(--text);
  letter-spacing: -1px;
}

.monet-card-value.green { color: var(--accent); }

.monet-section-title {
  font-family: 'Syne', sans-serif;
  font-size: 16px;
  font-weight: 700;
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
}

.ad-form {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 20px;
  margin-bottom: 16px;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr auto;
  gap: 10px;
  align-items: end;
}

.form-field { display: flex; flex-direction: column; gap: 6px; }
.form-label { font-size: 12px; color: var(--muted2); font-weight: 500; text-transform: uppercase; letter-spacing: 0.3px; }
.form-input {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 13px;
  color: var(--text);
  font-family: 'DM Sans', sans-serif;
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
}
.form-input:focus { border-color: rgba(77,240,192,0.4); }
.form-input::placeholder { color: var(--muted); }

.ad-item {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 16px;
  margin-bottom: 8px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.ad-item-name { font-size: 14px; font-weight: 500; }
.ad-item-stats { font-size: 12px; color: var(--muted2); display: flex; gap: 12px; }
.ad-stat { display: flex; align-items: center; gap: 4px; }

/* ===== PROFILE ===== */
.profile-header {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 24px;
  margin-bottom: 20px;
  display: flex;
  gap: 20px;
  align-items: flex-start;
}

.profile-avatar-wrap { position: relative; flex-shrink: 0; }
.profile-avatar {
  width: 72px;
  height: 72px;
  border-radius: 50%;
  object-fit: cover;
  background: var(--surface);
  border: 3px solid var(--border);
}

.profile-info { flex: 1; }
.profile-name {
  font-family: 'Syne', sans-serif;
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.5px;
  margin-bottom: 4px;
}
.profile-email { font-size: 13px; color: var(--muted2); margin-bottom: 14px; }

.bio-area {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 11px 14px;
  color: var(--text);
  font-family: 'DM Sans', sans-serif;
  font-size: 14px;
  width: 100%;
  resize: none;
  outline: none;
  transition: border-color 0.2s;
}
.bio-area:focus { border-color: rgba(77,240,192,0.4); }
.bio-area::placeholder { color: var(--muted); }

.empty-state {
  text-align: center;
  padding: 48px 24px;
  color: var(--muted2);
}
.empty-state .empty-icon { font-size: 36px; margin-bottom: 12px; }
.empty-state p { font-size: 14px; }

/* Scrollbar */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 3px; }

/* File name display */
#fileNameDisplay {
  font-size: 12px;
  color: var(--accent);
  margin-top: 4px;
}

@media (max-width: 600px) {
  .auth-wrap { grid-template-columns: 1fr; }
  .auth-brand { display: none; }
  .topnav { padding: 0 10px; gap: 6px; }
  .nav-brand { font-size: 17px; }
  .nav-tabs { padding: 3px; gap: 1px; }
  .nav-tab { padding: 6px 8px; font-size: 11px; gap: 3px; }
  .tab-label { display: none; }
  .monet-grid { grid-template-columns: 1fr; }
  .form-row { grid-template-columns: 1fr; }
  .app-layout { padding: 16px 10px; }
}
</style>
</head>
<body>

<div id="authScreen">
  <div class="auth-wrap">
    <div class="auth-brand">
      <div class="brand-logo">VibeNet</div>
      <div class="brand-tag">Share moments, grow your audience, and earn from your content.</div>
      <div class="brand-pills">
        <span class="pill">📹 Video</span>
        <span class="pill">💰 Earn</span>
        <span class="pill">📈 Grow</span>
        <span class="pill">🌐 Connect</span>
      </div>
    </div>
    <div class="auth-forms">
      <div class="auth-section">
        <h3>Create account</h3>
        <div class="field">
          <div class="field-label">Full Name</div>
          <input id="signupName" placeholder="Your name" />
        </div>
        <div class="field">
          <div class="field-label">Email</div>
          <input id="signupEmail" type="email" placeholder="you@email.com" />
        </div>
        <div class="field">
          <div class="field-label">Password</div>
          <input id="signupPassword" type="password" placeholder="••••••••" />
        </div>
        <div class="field">
          <div class="field-label">Profile photo (optional)</div>
          <input id="signupPic" type="file" accept="image/*" style="background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:10px 14px;color:var(--muted2);width:100%;font-size:13px;" />
        </div>
        <button class="btn-primary" onclick="signup()" style="width:100%;margin-top:4px;">Create Account →</button>
      </div>
      <div class="divider"></div>
      <div class="auth-section">
        <h3>Sign in</h3>
        <div class="field">
          <div class="field-label">Email</div>
          <input id="loginEmail" type="email" placeholder="you@email.com" />
        </div>
        <div class="field">
          <div class="field-label">Password</div>
          <input id="loginPassword" type="password" placeholder="••••••••" />
        </div>
        <button class="btn-ghost" onclick="login()" style="width:100%;">Sign In</button>
      </div>
    </div>
  </div>
</div>

<div id="mainApp">
  <nav class="topnav">
    <div class="nav-brand">VibeNet</div>
    <div class="nav-tabs">
      <button class="nav-tab active" id="navFeed" onclick="showTab('feed')">
        <span>🏠</span><span class="tab-label"> Feed</span>
      </button>
      <button class="nav-tab" id="navNotifs" onclick="showTab('notifications')">
        <span>🔔</span><span class="tab-label"> Alerts</span>
        <span id="notifCount" class="notif-dot" style="display:none"></span>
      </button>
      <button class="nav-tab" id="navMonet" onclick="showTab('monet')">
        <span>💰</span><span class="tab-label"> Earn</span>
      </button>
      <button class="nav-tab" id="navProfile" onclick="showTab('profile')">
        <span>👤</span><span class="tab-label"> Profile</span>
      </button>
    </div>
    <div class="nav-right">
      <img class="nav-avatar" id="topAvatar" src="" onerror="this.style.display='none'" />
      <button class="nav-signout" onclick="logout()" title="Sign out">&#8594;</button>
    </div>
  </nav>

  <div class="app-layout">
    <div class="main-col">

      <div id="feed" class="tab visible">
        <div class="composer">
          <div class="composer-top">
            <img class="composer-avatar" id="composerAvatar" src="" onerror="this.style.display='none'" />
            <textarea id="postText" rows="3" placeholder="What's on your mind?"></textarea>
          </div>
          <div class="composer-footer">
            <div class="composer-actions">
              <label class="attach-label">
                📎 Attach media
                <input id="fileUpload" type="file" accept="image/*,video/*" onchange="showFileName(this)" />
              </label>
              <span id="fileNameDisplay"></span>
            </div>
            <button class="btn-primary" onclick="addPost()">Post →</button>
          </div>
        </div>
        <div id="feedList"></div>
      </div>

      <div id="notifications" class="tab">
        <div class="section-header">
          <h2>Notifications</h2>
          <p>Stay up to date with your community</p>
        </div>
        <div class="post-card" style="padding:0 20px;">
          <div id="notifList"></div>
        </div>
      </div>

      <div id="monet" class="tab">
        <div class="section-header">
          <h2>Earnings &amp; Payments</h2>
          <p>Grow your revenue, run ads, and get verified</p>
        </div>

        <div class="monet-grid">
          <div class="monet-card">
            <div class="monet-card-label">Followers</div>
            <div class="monet-card-value" id="monFollowers">0</div>
          </div>
          <div class="monet-card">
            <div class="monet-card-label">Watch Hours</div>
            <div class="monet-card-value" id="monWatch">0</div>
          </div>
          <div class="monet-card">
            <div class="monet-card-label">Status</div>
            <div class="monet-card-value" id="monStatus" style="font-size:16px;margin-top:4px;">—</div>
          </div>
          <div class="monet-card">
            <div class="monet-card-label">Total Earnings</div>
            <div class="monet-card-value green">P<span id="monEarnings">0.00</span></div>
          </div>
        </div>

        <div style="background:var(--card);border:1px solid var(--border);border-radius:16px;padding:22px;margin-bottom:20px">
          <div class="monet-section-title" style="margin-bottom:6px">📣 Advertise on VibeNet</div>
          <div style="font-size:13px;color:var(--muted2);margin-bottom:16px;line-height:1.6">
            Send your budget via Orange Money to <strong style="color:var(--accent);font-size:15px;letter-spacing:1px">72927417</strong>, then fill in your campaign details below. Your campaign goes live once payment is confirmed.
          </div>
          <div class="form-row">
            <div class="form-field">
              <div class="form-label">Campaign Title</div>
              <input id="adTitle" class="form-input" placeholder="e.g. My Website" />
            </div>
            <div class="form-field">
              <div class="form-label">Budget (P)</div>
              <input id="adBudget" class="form-input" type="number" placeholder="0.00" />
            </div>
            <button class="btn-primary" onclick="createAd()">Create Ad</button>
          </div>

          <div id="adList" style="margin-top:20px"></div>
        </div>

        <div style="background:var(--card);border:1px solid var(--border);border-radius:16px;padding:22px;margin-bottom:20px">
          <div class="monet-section-title">💸 Request Payout</div>
          <div style="display:grid;grid-template-columns: 1fr 1fr auto; gap:10px; align-items:end;">
            <div class="form-field">
              <div class="form-label">Amount (P)</div>
              <input id="payoutAmount" class="form-input" type="number" placeholder="0.00" />
            </div>
            <div class="form-field">
              <div class="form-label">Your Orange Money Number</div>
              <input id="payoutOM" class="form-input" type="text" placeholder="7xxxxxxx" />
            </div>
            <button class="btn-primary" onclick="requestPayout()">Request</button>
          </div>
          <div id="payoutHistory" style="margin-top:20px; border-top: 1px solid var(--border); padding-top:14px;"></div>
        </div>

        <div style="background:var(--card);border:1px solid var(--border);border-radius:16px;padding:22px;margin-bottom:20px">
          <div class="monet-section-title">✨ Get VibeNet Verified</div>
          <p style="font-size:13.5px;color:var(--muted2);margin-bottom:14px;">
            A verification badge increases trust and unlocks higher visibility.
            Requirements: 1,000 followers and 500 watch hours.
          </p>
          <button class="btn-ghost" onclick="applyVerification()" id="verifyBtn">Apply for Verification</button>
        </div>
      </div>

      <div id="profile" class="tab">
        <div class="profile-header">
          <div class="profile-avatar-wrap">
            <img class="profile-avatar" id="profileAvatar" src="" onerror="this.src='https://via.placeholder.com/80'" />
          </div>
          <div class="profile-info">
            <div class="profile-name" id="profileName">Loading...</div>
            <div class="profile-email" id="profileEmail"></div>
            <textarea id="profileBio" class="bio-area" rows="2" placeholder="Tell us about yourself..."></textarea>
            <div style="display:flex;gap:8px;margin-top:12px;">
              <button class="btn-primary" onclick="updateProfile()">Save Bio</button>
              <button class="btn-ghost" onclick="logout()">Sign Out</button>
            </div>
          </div>
        </div>
        <div id="userPostList"></div>
      </div>

    </div>
  </div>
</div>

<script>
let currentUser = null;
let lastNotifId = 0;

function showTab(tabId) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('visible'));
  document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
  document.getElementById(tabId).classList.add('visible');
  document.getElementById('nav' + tabId.charAt(0).toUpperCase() + tabId.slice(1)).classList.add('active');

  if(tabId === 'feed') loadFeed();
  if(tabId === 'monet') loadMonetization();
  if(tabId === 'notifications') loadNotifications();
  if(tabId === 'profile') loadUserProfile();
}

async function signup() {
  const name = document.getElementById("signupName").value.trim();
  const email = document.getElementById("signupEmail").value.trim();
  const password = document.getElementById("signupPassword").value.trim();
  const fileInput = document.getElementById("signupPic");

  if(!name || !email || !password) return alert("Fill all fields");

  const formData = new FormData();
  formData.append("name", name);
  formData.append("email", email);
  formData.append("password", password);
  if(fileInput.files[0]) formData.append("file", fileInput.files[0]);

  const res = await fetch("/api/signup", { method: "POST", body: formData });
  const data = await res.json();
  if(data.success) {
    currentUser = data.user;
    initApp();
  } else {
    alert(data.error);
  }
}

async function login() {
  const email = document.getElementById("loginEmail").value.trim();
  const password = document.getElementById("loginPassword").value.trim();
  if(!email || !password) return alert("Fill all fields");

  const res = await fetch("/api/login", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ email, password })
  });
  const data = await res.json();
  if(data.success) {
    currentUser = data.user;
    initApp();
  } else {
    alert(data.error);
  }
}

function initApp() {
  document.getElementById("authScreen").style.display = "none";
  document.getElementById("mainApp").style.display = "block";
  document.getElementById("topAvatar").src = currentUser.profile_pic;
  document.getElementById("composerAvatar").src = currentUser.profile_pic;
  showTab('feed');
  startNotifPolling();
}

function logout() {
  currentUser = null;
  location.reload();
}

function showFileName(input) {
  const display = document.getElementById("fileNameDisplay");
  display.innerText = input.files[0] ? input.files[0].name : "";
}

async function addPost() {
  const text = document.getElementById("postText").value.trim();
  const fileInput = document.getElementById("fileUpload");
  if(!text && !fileInput.files[0]) return;

  const formData = new FormData();
  formData.append("email", currentUser.email);
  formData.append("text", text);
  if(fileInput.files[0]) formData.append("file", fileInput.files[0]);

  const res = await fetch("/api/posts", { method: "POST", body: formData });
  const data = await res.json();
  if(data.success) {
    document.getElementById("postText").value = "";
    document.getElementById("fileUpload").value = "";
    document.getElementById("fileNameDisplay").innerText = "";
    loadFeed();
  }
}

async function loadFeed() {
  const res = await fetch(`/api/feed?email=${currentUser.email}`);
  const posts = await res.json();
  renderPosts(posts, "feedList");
}

function renderPosts(posts, listId) {
  const list = document.getElementById(listId);
  list.innerHTML = posts.length ? "" : `<div class="empty-state"><div class="empty-icon">🌱</div><p>No posts yet. Start the conversation!</p></div>`;

  posts.forEach(p => {
    const card = document.createElement("div");
    card.className = "post-card";

    let mediaHtml = "";
    if(p.file_url) {
      if(p.file_url.match(/\.(mp4|mov|webm)$|video/i)) {
        mediaHtml = `
          <div class="post-media video-wrap" onclick="togglePlay(this)">
            <video loop muted playsinline src="${p.file_url}"></video>
            <div class="play-hint"><span>▶</span></div>
          </div>`;
      } else {
        mediaHtml = `<div class="post-media"><img src="${p.file_url}" loading="lazy" /></div>`;
      }
    }

    const isOwner = p.author_email === currentUser.email;
    const reactBtnClass = p.user_reaction ? "react-btn active" : "react-btn";
    const vbadge = p.author_verified ? `<span class="vbadge" title="VibeNet Verified">✓</span>` : "";

    card.innerHTML = `
      <div class="post-header">
        <div class="post-author">
          <img class="post-avatar" src="${p.profile_pic || 'https://via.placeholder.com/40'}" />
          <div class="post-author-info">
            <strong>${p.author_name}${vbadge}</strong>
            <div class="post-ts">${p.timestamp}</div>
          </div>
        </div>
        <div class="post-actions">
          ${isOwner ? `
            <button class="action-btn edit-btn" onclick="openEditModal(${p.id}, \`${p.text.replace(/`/g, '\\`')}\`)">✎</button>
            <button class="action-btn delete" onclick="deletePost(${p.id})">✕</button>
          ` : `
            <button class="follow-btn" onclick="toggleFollow('${p.author_email}', this)">Follow</button>
          `}
        </div>
      </div>
      <div class="post-text">${p.text}</div>
      ${mediaHtml}
      <div class="post-footer">
        <div class="reaction-bar">
          <button class="${reactBtnClass}" onclick="react(${p.id}, '👍', this)">
            <span>👍</span> <small>${p.reactions['👍'] || 0}</small>
          </button>
          <button class="react-btn" onclick="react(${p.id}, '😂', this)">
            <span>😂</span> <small>${p.reactions['😂'] || 0}</small>
          </button>
        </div>
        <div class="comment-count">💬 ${p.comments_count}</div>
      </div>
    `;
    list.appendChild(card);
  });

  // Simple intersection observer for autoplay
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      const vid = entry.target.querySelector('video');
      if(!vid) return;
      if(entry.isIntersecting) {
        vid.play().catch(() => {});
        entry.target.classList.add('playing');
      } else {
        vid.pause();
        entry.target.classList.remove('playing');
      }
    });
  }, { threshold: 0.6 });
  list.querySelectorAll('.video-wrap').forEach(el => observer.observe(el));
}

function togglePlay(container) {
  const vid = container.querySelector('video');
  if(vid.paused) {
    vid.play();
    container.classList.add('playing');
  } else {
    vid.pause();
    container.classList.remove('playing');
  }
}

async function react(postId, emoji, btn) {
  const res = await fetch("/api/react", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ email: currentUser.email, post_id: postId, emoji })
  });
  const data = await res.json();
  if(data.success) {
    // simple UI update
    const countEl = btn.querySelector('small');
    let count = parseInt(countEl.innerText);
    if(btn.classList.contains('active')) {
      btn.classList.remove('active');
      countEl.innerText = count - 1;
    } else {
      btn.classList.add('active');
      countEl.innerText = count + 1;
    }
  }
}

async function deletePost(id) {
  if(!confirm("Delete this post?")) return;
  const res = await fetch(`/api/posts/${id}?email=${currentUser.email}`, { method: "DELETE" });
  if((await res.json()).success) loadFeed();
}

function openEditModal(id, oldText) {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.innerHTML = `
    <div class="modal-box">
      <div class="modal-title">Edit Post</div>
      <textarea id="editArea" class="bio-area" rows="4">${oldText}</textarea>
      <div class="modal-footer">
        <button class="btn-ghost" onclick="this.closest('.modal-overlay').remove()">Cancel</button>
        <button class="btn-primary" onclick="saveEdit(${id})">Save Changes</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
}

async function saveEdit(id) {
  const newText = document.getElementById("editArea").value.trim();
  const res = await fetch(`/api/posts/${id}`, {
    method: "PUT",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ email: currentUser.email, text: newText })
  });
  if((await res.json()).success) {
    document.querySelector(".modal-overlay").remove();
    loadFeed();
  }
}

async function toggleFollow(targetEmail, btn) {
  const res = await fetch("/api/follow", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ follower_email: currentUser.email, user_email: targetEmail })
  });
  const data = await res.json();
  if(data.success) {
    btn.innerText = data.following ? "Following" : "Follow";
    btn.classList.toggle("active", data.following);
  }
}

async function loadNotifications() {
  const res = await fetch(`/api/notifications?email=${currentUser.email}`);
  const notifs = await res.json();
  const list = document.getElementById("notifList");
  list.innerHTML = notifs.length ? "" : `<div class="empty-state"><p>All caught up!</p></div>`;

  notifs.forEach(n => {
    const item = document.createElement("div");
    item.className = "notif-item";
    item.innerHTML = `
      <div class="notif-icon">🔔</div>
      <div style="flex:1">
        <div class="notif-text">${n.text}</div>
        <div class="notif-time">${n.timestamp}</div>
      </div>
    `;
    list.appendChild(item);
  });
  document.getElementById("notifCount").style.display = "none";
}

function startNotifPolling() {
  setInterval(async () => {
    const res = await fetch(`/api/notifications/unread?email=${currentUser.email}`);
    const data = await res.json();
    if(data.count > 0) {
      const dot = document.getElementById("notifCount");
      dot.innerText = data.count;
      dot.style.display = "block";
    }
  }, 10000);
}

async function loadMonetization() {
  const res = await fetch(`/api/user/${currentUser.email}`);
  const user = await res.json();
  document.getElementById("monFollowers").innerText = user.followers || 0;
  document.getElementById("monWatch").innerText = user.watch_hours || 0;
  document.getElementById("monEarnings").innerText = user.earnings.toFixed(2);
  document.getElementById("monStatus").innerText = user.verified ? "✅ Verified Creator" : "Standard Tier";

  loadAds();
  loadPayoutHistory();
}

async function createAd() {
  const title = document.getElementById("adTitle").value.trim();
  const budget = parseFloat(document.getElementById("adBudget").value);
  if(!title || isNaN(budget) || budget <= 0) return alert("Enter valid title and budget");

  const res = await fetch("/api/ads", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ email: currentUser.email, title, budget })
  });
  if((await res.json()).success) {
    alert("Ad campaign submitted! Once you send the Orange Money payment, it will be activated.");
    document.getElementById("adTitle").value = "";
    document.getElementById("adBudget").value = "";
    loadAds();
  }
}

async function loadAds() {
  const res = await fetch(`/api/ads?email=${currentUser.email}`);
  const ads = await res.json();
  const list = document.getElementById("adList");
  list.innerHTML = ads.length ? '<div class="monet-section-title">Your Campaigns</div>' : "";
  ads.forEach(ad => {
    const item = document.createElement("div");
    item.className = "ad-item";
    item.innerHTML = `
      <div class="ad-item-name">${ad.title}</div>
      <div class="ad-item-stats">
        <div class="ad-stat">💰 P${ad.budget.toFixed(2)}</div>
        <div class="ad-stat">👁️ ${ad.impressions}</div>
      </div>
    `;
    list.appendChild(item);
  });
}

async function requestPayout() {
  const amount = parseFloat(document.getElementById("payoutAmount").value);
  const om_number = document.getElementById("payoutOM").value.trim();
  if(!amount || amount <= 0 || !om_number) return alert("Enter a valid amount and Orange Money number");

  const res = await fetch("/api/payout", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ email: currentUser.email, amount, om_number })
  });
  const data = await res.json();
  if(data.success) {
    alert(data.message);
    loadMonetization();
  } else {
    alert(data.error);
  }
}

async function loadPayoutHistory() {
  const res = await fetch(`/api/payout/history/${currentUser.email}`);
  const history = await res.json();
  const list = document.getElementById("payoutHistory");
  list.innerHTML = history.length ? '<div class="monet-section-title" style="font-size:13px;color:var(--muted)">Recent Payouts</div>' : "";
  history.forEach(p => {
    const item = document.createElement("div");
    item.style = "display:flex; justify-content:space-between; font-size:12px; margin-bottom:6px; color:var(--muted2)";
    item.innerHTML = `
      <span>P${p.amount.toFixed(2)} (${p.status})</span>
      <span>${p.created_at.split(' ')[0]}</span>
    `;
    list.appendChild(item);
  });
}

async function applyVerification() {
  alert("Verification request sent! Our team will review your profile metrics.");
}

async function loadUserProfile() {
  document.getElementById("profileName").innerText = currentUser.name;
  document.getElementById("profileEmail").innerText = currentUser.email;
  document.getElementById("profileAvatar").src = currentUser.profile_pic;
  document.getElementById("profileBio").value = currentUser.bio || "";

  const res = await fetch(`/api/feed?email=${currentUser.email}&only_mine=1`);
  const posts = await res.json();
  renderPosts(posts, "userPostList");
}

async function updateProfile() {
  const bio = document.getElementById("profileBio").value.trim();
  const res = await fetch("/api/profile/update", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ email: currentUser.email, bio })
  });
  if((await res.json()).success) {
    currentUser.bio = bio;
    alert("Profile updated!");
  }
}

</script>
</body>
</html>
"""

# ---------- API Routes ----------

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/api/signup", methods=["POST"])
def api_signup():
    name     = request.form.get("name", "").strip()
    email    = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "").strip()
    file     = request.files.get("file")

    if not name or not email or not password:
        return jsonify({"error": "Missing fields"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already exists"}), 400

    pic_url = ""
    if file:
        try:
            upload_result = cloudinary.uploader.upload(file, folder="vibenet/profiles")
            pic_url = upload_result.get("secure_url", "")
        except Exception: pass

    user = User(name=name, email=email, password=password, profile_pic=pic_url)
    db.session.add(user)
    db.session.commit()
    return jsonify({"success": True, "user": user.to_dict()})


@app.route("/api/login", methods=["POST"])
def api_login():
    data     = request.get_json() or {}
    email    = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()
    user = User.query.filter_by(email=email, password=password).first()
    if not user:
        return jsonify({"error": "Invalid credentials"}), 401
    return jsonify({"success": True, "user": user.to_dict()})


@app.route("/api/user/<email>")
def api_get_user(email):
    user = User.query.filter_by(email=email).first()
    if not user: return jsonify({"error": "No user"}), 404
    d = user.to_dict()
    d["followers"] = Follower.query.filter_by(user_email=email).count()
    return jsonify(d)


@app.route("/api/profile/update", methods=["POST"])
def api_profile_update():
    data  = request.get_json() or {}
    email = data.get("email", "")
    bio   = data.get("bio", "")
    user = User.query.filter_by(email=email).first()
    if user:
        user.bio = bio
        db.session.commit()
        return jsonify({"success": True})
    return jsonify({"error": "User not found"}), 404


@app.route("/api/posts", methods=["POST"])
def api_create_post():
    email = request.form.get("email")
    text  = request.form.get("text", "")
    file  = request.files.get("file")

    user = User.query.filter_by(email=email).first()
    if not user: return jsonify({"error": "User not found"}), 404

    file_url = ""
    if file:
        try:
            # Automatic resource type detection for images/videos
            res = cloudinary.uploader.upload(file, folder="vibenet/posts", resource_type="auto")
            file_url = res.get("secure_url", "")
        except Exception: pass

    post = Post(
        author_email=user.email,
        author_name=user.name,
        profile_pic=user.profile_pic,
        text=text,
        file_url=file_url
    )
    db.session.add(post)
    db.session.commit()
    return jsonify({"success": True})


@app.route("/api/feed")
def api_feed():
    user_email = request.args.get("email", "")
    only_mine  = request.args.get("only_mine") == "1"

    if only_mine:
        posts = Post.query.filter_by(author_email=user_email).order_by(Post.id.desc()).all()
    else:
        posts = Post.query.order_by(Post.id.desc()).limit(50).all()

    results = []
    for p in posts:
        # Check if current user reacted
        ur = UserReaction.query.filter_by(user_email=user_email, post_id=p.id).first()
        reaction = ur.emoji if ur else None

        # Check if author is verified
        author = User.query.filter_by(email=p.author_email).first()
        is_verified = bool(author.verified) if author else False

        results.append(p.to_dict(user_reaction=reaction, author_verified=is_verified))

    return jsonify(results)


@app.route("/api/posts/<int:post_id>", methods=["PUT", "DELETE"])
def api_modify_post(post_id):
    email = request.args.get("email") or (request.get_json() or {}).get("email")
    post  = Post.query.get(post_id)
    if not post or post.author_email != email:
        return jsonify({"error": "Unauthorized"}), 403

    if request.method == "DELETE":
        db.session.delete(post)
        db.session.commit()
        return jsonify({"success": True})

    if request.method == "PUT":
        data = request.get_json()
        post.text = data.get("text", post.text)
        db.session.commit()
        return jsonify({"success": True})


@app.route("/api/react", methods=["POST"])
def api_react():
    data    = request.get_json()
    email   = data.get("email")
    post_id = data.get("post_id")
    emoji   = data.get("emoji")

    post = Post.query.get(post_id)
    if not post: return jsonify({"error": "Post not found"}), 404

    existing = UserReaction.query.filter_by(user_email=email, post_id=post_id).first()
    reactions = post.reactions()

    if existing:
        # If same emoji, remove it (toggle off)
        if existing.emoji == emoji:
            reactions[emoji] = max(0, reactions.get(emoji, 1) - 1)
            db.session.delete(existing)
        else:
            # Change emoji: decrement old, increment new
            old_emoji = existing.emoji
            reactions[old_emoji] = max(0, reactions.get(old_emoji, 1) - 1)
            reactions[emoji] = reactions.get(emoji, 0) + 1
            existing.emoji = emoji
    else:
        # New reaction
        new_ur = UserReaction(user_email=email, post_id=post_id, emoji=emoji)
        db.session.add(new_ur)
        reactions[emoji] = reactions.get(emoji, 0) + 1

        # Notify author
        if post.author_email != email:
            notif = Notification(user_email=post.author_email, text=f"Someone reacted {emoji} to your post")
            db.session.add(notif)

    post.reactions_json = _json.dumps(reactions)
    db.session.commit()
    return jsonify({"success": True})


@app.route("/api/follow", methods=["POST"])
def api_follow():
    data           = request.get_json()
    follower_email = data.get("follower_email")
    user_email     = data.get("user_email")

    if follower_email == user_email: return jsonify({"error": "Self-follow"}), 400

    existing = Follower.query.filter_by(user_email=user_email, follower_email=follower_email).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({"success": True, "following": False})
    else:
        f = Follower(user_email=user_email, follower_email=follower_email)
        db.session.add(f)
        # Notify
        notif = Notification(user_email=user_email, text="You have a new follower!")
        db.session.add(notif)
        db.session.commit()
        return jsonify({"success": True, "following": True})


@app.route("/api/notifications")
def api_notifications():
    email = request.args.get("email")
    notifs = Notification.query.filter_by(user_email=email).order_by(Notification.id.desc()).limit(20).all()
    # mark seen
    for n in notifs: n.seen = 1
    db.session.commit()
    return jsonify([n.to_dict() for n in notifs])


@app.route("/api/notifications/unread")
def api_unread_notifs():
    email = request.args.get("email")
    count = Notification.query.filter_by(user_email=email, seen=0).count()
    return jsonify({"count": count})


# ---------- Monetization ----------

@app.route("/api/ads", methods=["GET", "POST"])
def api_ads():
    email = request.args.get("email") or (request.get_json() or {}).get("email")
    if request.method == "POST":
        data = request.get_json()
        ad = Ad(title=data["title"], owner_email=email, budget=float(data["budget"]))
        db.session.add(ad)
        db.session.commit()
        return jsonify({"success": True})

    ads = Ad.query.filter_by(owner_email=email).all()
    return jsonify([a.to_dict() for a in ads])


# ---------- Payout Requests ----------
@app.route("/api/payout", methods=["POST"])
def api_payout_request():
    data       = request.get_json() or {}
    email      = data.get("email", "").strip()
    om_number  = data.get("om_number", "").strip()
    amount     = float(data.get("amount", 0))

    if not email or not om_number or amount <= 0:
        return jsonify({"error": "Missing fields"}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user.earnings < amount:
        return jsonify({"error": f"Insufficient earnings. Your balance is P{user.earnings:.2f}"}), 400

    # Hold the amount (deduct from balance, mark pending)
    user.earnings -= amount
    pr = PayoutRequest(
        user_email=email,
        user_name=user.name or "",
        om_number=om_number,
        amount=amount,
        status="pending",
    )
    db.session.add(pr)
    db.session.commit()
    return jsonify({"success": True, "message": f"Payout of P{amount:.2f} requested. You'll receive it on {om_number} within 24–48hrs."})


@app.route("/api/payout/history/<email>")
def api_payout_history(email):
    requests = PayoutRequest.query.filter_by(user_email=email).order_by(PayoutRequest.id.desc()).all()
    return jsonify([r.to_dict() for r in requests])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=app.config["PORT"], debug=True)
