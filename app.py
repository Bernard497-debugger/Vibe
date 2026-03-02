# app.py - VibeNet (Render PostgreSQL Compatible + Sessions)
import os
import uuid
import datetime
import json as _json
from flask import Flask, request, jsonify, send_from_directory, g, render_template_string, session

# ---------- Database Imports ----------
import sqlite3
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    HAS_POSTGRES_LIB = True
except ImportError:
    HAS_POSTGRES_LIB = False

# ---------- Config ----------
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_DIR, "data")
UPLOAD_DIR = os.path.join(APP_DIR, "uploads")
DB_PATH = os.path.join(DATA_DIR, "vibenet.db")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__, static_folder=None)
app.config['MAX_CONTENT_LENGTH'] = 300 * 1024 * 1024  
app.config['PORT'] = int(os.environ.get("PORT", 5000))
DATABASE_URL = os.environ.get("DATABASE_URL")
app.secret_key = os.environ.get("SECRET_KEY", "vibenet_secret_key_change_this_in_production")

# ---------- Database Logic (Hybrid SQLite/Postgres) ----------

def get_db_type():
    if DATABASE_URL and HAS_POSTGRES_LIB:
        return 'postgres'
    return 'sqlite'

class PostgresCursorWrapper:
    def __init__(self, original_cursor):
        self.cursor = original_cursor
        self.lastrowid = None

    def execute(self, sql, args=None):
        sql = sql.replace('?', '%s')
        is_insert = sql.strip().upper().startswith("INSERT")
        if is_insert:
            sql += " RETURNING id"
        if args is None:
            self.cursor.execute(sql)
        else:
            self.cursor.execute(sql, args)
        if is_insert:
            res = self.cursor.fetchone()
            if res:
                self.lastrowid = res['id']

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()
    
    def __getattr__(self, name):
        return getattr(self.cursor, name)

def get_db():
    if getattr(g, "_db", None) is None:
        if get_db_type() == 'postgres':
            conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
            g._db = conn
            g._db_type = 'postgres'
        else:
            conn = sqlite3.connect(DB_PATH, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            g._db = conn
            g._db_type = 'sqlite'
    return g._db

def get_cursor(db):
    if getattr(g, "_db_type", 'sqlite') == 'postgres':
        return PostgresCursorWrapper(db.cursor())
    return db.cursor()

def init_db():
    db = get_db()
    cur = get_cursor(db)
    
    if get_db_type() == 'postgres':
        pk_def = "SERIAL PRIMARY KEY"
    else:
        pk_def = "INTEGER PRIMARY KEY AUTOINCREMENT"

    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS users (
        id {pk_def},
        name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        profile_pic TEXT,
        bio TEXT DEFAULT '',
        watch_hours INTEGER DEFAULT 0,
        earnings REAL DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS followers (
        id {pk_def},
        user_email TEXT,
        follower_email TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS posts (
        id {pk_def},
        author_email TEXT,
        author_name TEXT,
        profile_pic TEXT,
        text TEXT,
        file_url TEXT,
        timestamp TEXT,
        reactions_json TEXT DEFAULT '{{}}',
        comments_count INTEGER DEFAULT 0
    )""")
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS user_reactions (
        id {pk_def},
        user_email TEXT,
        post_id INTEGER,
        emoji TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_email, post_id)
    )""")
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS notifications (
        id {pk_def},
        user_email TEXT,
        text TEXT,
        timestamp TEXT,
        seen INTEGER DEFAULT 0
    )""")
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS ads (
        id {pk_def},
        title TEXT,
        owner_email TEXT,
        budget REAL DEFAULT 0,
        impressions INTEGER DEFAULT 0,
        clicks INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    db.commit()

@app.teardown_appcontext
def close_db(exception):
    db = getattr(g, "_db", None)
    if db is not None:
        db.close()

def now_ts():
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

with app.app_context():
    init_db()

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
  background: rgba(6,9,16,0.85);
  backdrop-filter: blur(20px);
  border-bottom: 1px solid var(--border);
  padding: 0 32px;
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.nav-brand {
  font-family: 'Syne', sans-serif;
  font-size: 22px;
  font-weight: 800;
  color: var(--accent);
  letter-spacing: -0.5px;
}

.nav-tabs {
  display: flex;
  gap: 4px;
  background: var(--surface);
  padding: 4px;
  border-radius: 12px;
  border: 1px solid var(--border);
}

.nav-tab {
  background: transparent;
  border: none;
  color: var(--muted2);
  padding: 7px 18px;
  border-radius: 9px;
  font-family: 'DM Sans', sans-serif;
  font-weight: 500;
  font-size: 13.5px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 6px;
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
  width: 20px;
  height: 2px;
  background: var(--accent);
  border-radius: 2px;
}

.notif-dot {
  background: var(--danger);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 100px;
  line-height: 16px;
  min-width: 18px;
  text-align: center;
}

.nav-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.user-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--card2);
  border: 1px solid var(--border);
  border-radius: 100px;
  padding: 4px 14px 4px 4px;
  cursor: pointer;
}

.user-chip-avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  object-fit: cover;
  background: var(--surface);
}

.user-chip-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
}

/* ===== LAYOUT ===== */
.app-layout {
  max-width: 1120px;
  margin: 0 auto;
  padding: 28px 20px;
  display: grid;
  grid-template-columns: 1fr 300px;
  gap: 24px;
  align-items: start;
}

.main-col { min-width: 0; }

/* Sidebar */
.sidebar {
  display: flex;
  flex-direction: column;
  gap: 16px;
  position: sticky;
  top: 84px;
}

.sidebar-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 20px;
}

.sidebar-card h4 {
  font-family: 'Syne', sans-serif;
  font-size: 13px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  color: var(--muted2);
  margin-bottom: 14px;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
}
.stat-row:last-child { border-bottom: none; }

.stat-label { font-size: 13px; color: var(--muted2); }
.stat-value { font-family: 'Syne', sans-serif; font-size: 16px; font-weight: 700; color: var(--text); }

.quick-btns { display: flex; flex-direction: column; gap: 8px; margin-top: 4px; }
.quick-btn {
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
}
.quick-btn:hover { border-color: rgba(77,240,192,0.3); color: var(--accent); background: rgba(77,240,192,0.04); }

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

@media (max-width: 768px) {
  .auth-wrap { grid-template-columns: 1fr; }
  .auth-brand { display: none; }
  .app-layout { grid-template-columns: 1fr; }
  .sidebar { display: none; }
  .topnav { padding: 0 16px; }
  .nav-tabs { gap: 2px; }
  .nav-tab { padding: 7px 10px; font-size: 12px; }
  .monet-grid { grid-template-columns: 1fr; }
  .form-row { grid-template-columns: 1fr; }
}
</style>
</head>
<body>

<!-- ===== AUTH SCREEN ===== -->
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

<!-- ===== MAIN APP ===== -->
<div id="mainApp">
  <!-- Top Nav -->
  <nav class="topnav">
    <div class="nav-brand">VibeNet</div>

    <div class="nav-tabs">
      <button class="nav-tab active" id="navFeed" onclick="showTab('feed')">
        <span>🏠</span> Feed
      </button>
      <button class="nav-tab" id="navNotifs" onclick="showTab('notifications')">
        <span>🔔</span> Alerts
        <span id="notifCount" class="notif-dot" style="display:none"></span>
      </button>
      <button class="nav-tab" id="navMonet" onclick="showTab('monet')">
        <span>💰</span> Earn
      </button>
      <button class="nav-tab" id="navProfile" onclick="showTab('profile')">
        <span>👤</span> Profile
      </button>
    </div>

    <div class="nav-right">
      <div class="user-chip" onclick="showTab('profile')">
        <img class="user-chip-avatar" id="topAvatar" src="" onerror="this.style.display='none'" />
        <span class="user-chip-name" id="topName">—</span>
      </div>
      <button class="btn-ghost" onclick="logout()" style="padding:7px 14px;font-size:13px;">Sign out</button>
    </div>
  </nav>

  <!-- Layout -->
  <div class="app-layout">
    <!-- Main column -->
    <div class="main-col">

      <!-- Feed Tab -->
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

      <!-- Notifications Tab -->
      <div id="notifications" class="tab">
        <div class="section-header">
          <h2>Notifications</h2>
          <p>Stay up to date with your community</p>
        </div>
        <div class="post-card" style="padding:0 20px;">
          <div id="notifList"></div>
        </div>
      </div>

      <!-- Monetization Tab -->
      <div id="monet" class="tab">
        <div class="section-header">
          <h2>Earnings & Ads</h2>
          <p>Track your revenue and manage ad campaigns</p>
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
            <div class="monet-card-value green">$<span id="monEarnings">0.00</span></div>
          </div>
        </div>

        <div class="ad-form">
          <div class="monet-section-title">Create Ad Campaign</div>
          <div class="form-row">
            <div class="form-field">
              <div class="form-label">Campaign Title</div>
              <input id="adTitle" class="form-input" placeholder="My awesome campaign" />
            </div>
            <div class="form-field">
              <div class="form-label">Budget (credits)</div>
              <input id="adBudget" class="form-input" type="number" placeholder="500" />
            </div>
            <button class="btn-primary" onclick="createAd()" style="height:42px;">Launch →</button>
          </div>
        </div>

        <div class="monet-section-title">Active Campaigns</div>
        <div id="adsList"></div>
      </div>

      <!-- Profile Tab -->
      <div id="profile" class="tab">
        <div class="section-header">
          <h2>My Profile</h2>
          <p>Manage your identity and content</p>
        </div>

        <div class="profile-header">
          <div class="profile-avatar-wrap">
            <img class="profile-avatar" id="profileAvatar" src="" onerror="this.style.background='var(--surface)'" />
          </div>
          <div class="profile-info">
            <div class="profile-name" id="profileName">—</div>
            <div class="profile-email" id="profileEmail">—</div>
            <textarea id="profileBio" class="bio-area" rows="2" placeholder="Write something about yourself..."></textarea>
            <button class="btn-primary" onclick="updateBio()" style="margin-top:10px;">Save Bio</button>
          </div>
        </div>

        <div class="monet-section-title">My Posts</div>
        <div id="profilePosts"></div>
      </div>

    </div><!-- /main-col -->

    <!-- Sidebar -->
    <div class="sidebar">
      <div class="sidebar-card">
        <h4>Your Stats</h4>
        <div class="stat-row">
          <span class="stat-label">Followers</span>
          <span class="stat-value" id="sideFollowers">0</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">Watch Hours</span>
          <span class="stat-value" id="sideWatch">0</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">Earnings</span>
          <span class="stat-value" style="color:var(--accent)">$<span id="sideEarnings">0.00</span></span>
        </div>
      </div>

      <div class="sidebar-card">
        <h4>Quick Access</h4>
        <div class="quick-btns">
          <button class="quick-btn" onclick="showTab('monet')">💰 Monetization Dashboard</button>
          <button class="quick-btn" onclick="showTab('profile')">✏️ Edit Profile</button>
          <button class="quick-btn" onclick="showTab('notifications')">🔔 View Notifications</button>
        </div>
      </div>
    </div>

  </div><!-- /app-layout -->
</div><!-- /mainApp -->

<script>
const API = '/api';
let currentUser = null;

function byId(id){ return document.getElementById(id); }
function escapeHtml(s){ if(!s) return ''; return String(s).replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]); }

function showFileName(input){
  const d = byId('fileNameDisplay');
  d.textContent = input.files[0] ? input.files[0].name : '';
}

window.addEventListener('load', async () => {
  try {
    const res = await fetch(API + '/me');
    const j = await res.json();
    if(j.user){ currentUser = j.user; onLogin(); }
  } catch(e) {}
});

async function signup(){
  const name = byId('signupName').value.trim();
  const email = byId('signupEmail').value.trim().toLowerCase();
  const password = byId('signupPassword').value;
  if(!name||!email||!password){ alert('Please fill all required fields.'); return; }
  const pic = byId('signupPic').files[0];
  const fd = new FormData();
  fd.append('name', name); fd.append('email', email); fd.append('password', password);
  if(pic) fd.append('file', pic);
  const res = await fetch(API + '/signup', { method:'POST', body: fd });
  const j = await res.json();
  if(j.user){ currentUser = j.user; onLogin(); } else alert(j.error || j.message);
}

async function login(){
  const email = byId('loginEmail').value.trim().toLowerCase();
  const password = byId('loginPassword').value;
  if(!email||!password){ alert('Please fill in your login details.'); return; }
  const res = await fetch(API + '/login', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({email, password})});
  const j = await res.json();
  if(j.user){ currentUser = j.user; onLogin(); } else alert(j.error || 'Invalid credentials');
}

async function logout(){
  await fetch(API + '/logout', {method:'POST'});
  currentUser = null;
  byId('mainApp').style.display = 'none';
  byId('authScreen').style.display = 'flex';
  if(window._vn_poll) clearInterval(window._vn_poll);
}

function onLogin(){
  byId('authScreen').style.display = 'none';
  byId('mainApp').style.display = 'block';

  // Populate top nav
  const av = byId('topAvatar');
  if(currentUser.profile_pic){ av.src = currentUser.profile_pic; av.style.display = ''; }
  byId('topName').textContent = currentUser.name || currentUser.email;

  // Composer avatar
  const ca = byId('composerAvatar');
  if(currentUser.profile_pic){ ca.src = currentUser.profile_pic; ca.style.display = ''; }

  // Profile section
  byId('profileName').textContent = currentUser.name || '—';
  byId('profileEmail').textContent = currentUser.email;
  const pa = byId('profileAvatar');
  if(currentUser.profile_pic){ pa.src = currentUser.profile_pic; }

  refreshAll();
  window._vn_poll = setInterval(()=>{ if(currentUser){ loadNotifications(); loadMonetization(); } }, 5000);
}

// Tabs
function showTab(tab){
  const tabs = ['feed','notifications','monet','profile'];
  const navMap = { feed:'navFeed', notifications:'navNotifs', monet:'navMonet', profile:'navProfile' };
  tabs.forEach(t => {
    byId(t).classList.remove('visible');
    byId(t).style.display = 'none';
  });
  document.querySelectorAll('.nav-tab').forEach(b => b.classList.remove('active'));
  byId(tab).style.display = 'block';
  byId(tab).classList.add('visible');
  if(navMap[tab]) byId(navMap[tab]).classList.add('active');

  if(tab === 'profile') loadProfilePosts();
  if(tab === 'notifications') loadNotifications();
  if(tab === 'monet'){ loadMonetization(); loadAds(); }
}

async function uploadFile(file){
  const fd = new FormData(); fd.append('file', file);
  const res = await fetch(API + '/upload', {method:'POST', body: fd});
  const j = await res.json();
  return j.url || '';
}

async function addPost(){
  if(!currentUser){ alert('Please login first.'); return; }
  const text = byId('postText').value.trim();
  const fileEl = byId('fileUpload');
  let url = '';
  if(fileEl.files[0]) url = await uploadFile(fileEl.files[0]);
  if(!text && !url) return;
  await fetch(API + '/posts', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({
    author_email: currentUser.email, author_name: currentUser.name, profile_pic: currentUser.profile_pic||'', text, file_url: url
  })});
  byId('postText').value=''; fileEl.value=''; byId('fileNameDisplay').textContent='';
  await loadFeed(); await loadProfilePosts(); await loadMonetization();
}

function createPostElement(p){
  const div = document.createElement('div'); div.className='post-card';

  const header = document.createElement('div'); header.className='post-header';
  const authorWrap = document.createElement('div'); authorWrap.className='post-author';
  const img = document.createElement('img'); img.className='post-avatar'; img.src = p.profile_pic || '';
  img.onerror = ()=> { img.style.background='var(--surface)'; img.src=''; };
  const info = document.createElement('div'); info.className='post-author-info';
  info.innerHTML = `<strong>${escapeHtml(p.author_name || 'Unknown')}</strong><div class="post-ts">${escapeHtml(p.timestamp)}</div>`;
  authorWrap.append(img, info);
  header.append(authorWrap);

  if(currentUser && currentUser.email !== p.author_email){
    const fb = document.createElement('button'); fb.className='follow-btn'; fb.textContent='+ Follow';
    fb.onclick = async ()=>{
      const res = await fetch(API+'/follow',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({follower_email:currentUser.email,target_email:p.author_email})});
      const j = await res.json();
      if(j.success){ fb.classList.toggle('active'); fb.textContent=fb.classList.contains('active')?'✓ Following':'+ Follow'; loadMonetization(); }
    };
    (async()=>{
      const r = await fetch(API+`/is_following?f=${encodeURIComponent(currentUser.email)}&t=${encodeURIComponent(p.author_email)}`);
      const jj = await r.json();
      if(jj.following){ fb.classList.add('active'); fb.textContent='✓ Following'; }
    })();
    header.append(fb);
  }

  div.append(header);

  if(p.text){ const t=document.createElement('div'); t.className='post-text'; t.textContent=p.text; div.append(t); }

  if(p.file_url){
    const media = document.createElement('div'); media.className='post-media';
    if(p.file_url.endsWith('.mp4')||p.file_url.endsWith('.webm')){
      const v=document.createElement('video'); v.src=p.file_url; v.controls=true;
      v.addEventListener('ended', async()=>{
        await fetch(API+'/watch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({viewer:currentUser?currentUser.email:'',post_id:p.id})});
        await fetch(API+'/ads/impression',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({post_id:p.id,viewer:currentUser?currentUser.email:''})});
        loadMonetization();
      });
      media.append(v);
    } else {
      const im=document.createElement('img'); im.src=p.file_url; media.append(im);
    }
    div.append(media);
  }

  const footer = document.createElement('div'); footer.className='post-footer';
  const bar = document.createElement('div'); bar.className='reaction-bar';
  ['👍','❤️','😂'].forEach(em=>{
    const btn=document.createElement('button'); btn.className='react-btn'; btn.dataset.emoji=em;
    btn.innerHTML=`${em} <span>${p.reactions&&p.reactions[em]?p.reactions[em]:0}</span>`;
    if(p.user_reaction&&currentUser&&p.user_reaction===em) btn.classList.add('active');
    btn.onclick=async(ev)=>{
      ev.stopPropagation();
      if(!currentUser){ alert('Login to react'); return; }
      const res=await fetch(API+'/react',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({post_id:p.id,emoji:em,user_email:currentUser.email})});
      const j=await res.json();
      if(j.success){
        div.querySelectorAll('.react-btn').forEach(rb=>{
          const e=rb.dataset.emoji;
          rb.innerHTML=`${e} <span>${j.reactions&&j.reactions[e]!==undefined?j.reactions[e]:(p.reactions&&p.reactions[e]?p.reactions[e]:0)}</span>`;
          rb.classList.remove('active');
        });
        const clicked=div.querySelector(`.react-btn[data-emoji="${em}"]`);
        if(clicked) clicked.classList.add('active');
      }
    };
    bar.append(btn);
  });

  const cc=document.createElement('div'); cc.className='comment-count'; cc.innerHTML=`💬 ${p.comments_count||0}`;
  footer.append(bar, cc);
  div.append(footer);
  return div;
}

async function loadFeed(){
  const res = await fetch(API+'/posts');
  const list = await res.json();
  const feed = byId('feedList'); feed.innerHTML='';
  if(!list.length){
    feed.innerHTML='<div class="empty-state"><div class="empty-icon">📭</div><p>No posts yet. Be the first to share something!</p></div>';
    return;
  }
  list.forEach(p=>feed.appendChild(createPostElement(p)));
  observeVideos();
}

function observeVideos(){
  if(window._vn_obs) window._vn_obs.disconnect();
  const obs=new IntersectionObserver(entries=>entries.forEach(e=>{if(e.intersectionRatio<0.25&&!e.target.paused)e.target.pause();}),{threshold:0.25});
  document.querySelectorAll('video').forEach(v=>obs.observe(v));
  window._vn_obs=obs;
}

async function loadNotifications(){
  if(!currentUser) return;
  const r=await fetch(API+'/notifications/'+encodeURIComponent(currentUser.email));
  const list=await r.json();
  const el=byId('notifList'); el.innerHTML='';
  const countEl=byId('notifCount');
  if(list.length){ countEl.style.display='inline-block'; countEl.textContent=list.length; } else countEl.style.display='none';
  if(!list.length){
    el.innerHTML='<div class="empty-state" style="padding:32px"><div class="empty-icon">🎉</div><p>All caught up!</p></div>';
    return;
  }
  list.forEach(n=>{
    const d=document.createElement('div'); d.className='notif-item';
    const icon=n.text.includes('reaction')?'⚡':n.text.includes('follow')?'👋':'🔔';
    d.innerHTML=`<div class="notif-icon">${icon}</div><div><div class="notif-text">${escapeHtml(n.text)}</div><div class="notif-time">${escapeHtml(n.timestamp)}</div></div>`;
    el.appendChild(d);
  });
}

async function loadProfilePosts(){
  if(!currentUser) return;
  const r=await fetch(API+'/profile/'+encodeURIComponent(currentUser.email));
  const j=await r.json();
  byId('profileBio').value=j.bio||'';
  const el=byId('profilePosts'); el.innerHTML='';
  if(!j.posts||!j.posts.length){
    el.innerHTML='<div class="empty-state"><div class="empty-icon">✏️</div><p>No posts yet.</p></div>';
    return;
  }
  j.posts.forEach(p=>{
    const d=document.createElement('div'); d.className='post-card';
    d.innerHTML=`<div class="post-text">${escapeHtml(p.text||'')}</div><div class="post-ts">${escapeHtml(p.timestamp)}</div>`;
    if(p.file_url){
      if(p.file_url.endsWith('.mp4')||p.file_url.endsWith('.webm')){
        d.innerHTML+=`<div class="post-media"><video src="${p.file_url}" controls></video></div>`;
      } else {
        d.innerHTML+=`<div class="post-media"><img src="${p.file_url}"></div>`;
      }
    }
    el.appendChild(d);
  });
}

async function updateBio(){
  if(!currentUser) return;
  await fetch(API+'/update_bio',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:currentUser.email,bio:byId('profileBio').value.trim()})});
  const saved=document.createElement('span');
  saved.style.cssText='color:var(--accent);font-size:13px;margin-left:10px;';
  saved.textContent='Saved ✓';
  const btn=document.querySelector('[onclick="updateBio()"]');
  btn.parentNode.insertBefore(saved, btn.nextSibling);
  setTimeout(()=>saved.remove(), 2000);
}

async function loadMonetization(){
  if(!currentUser) return;
  const r=await fetch(API+'/monetization/'+encodeURIComponent(currentUser.email));
  const j=await r.json();
  byId('monFollowers').textContent=j.followers;
  byId('monWatch').textContent=j.watch_hours;
  byId('monEarnings').textContent=(j.earnings||0).toFixed(2);
  byId('monStatus').textContent=j.followers>=1000&&j.watch_hours>=4000?'✅ Eligible':'⏳ Growing';
  byId('sideFollowers').textContent=j.followers;
  byId('sideWatch').textContent=j.watch_hours;
  byId('sideEarnings').textContent=(j.earnings||0).toFixed(2);
}

async function createAd(){
  const title=byId('adTitle').value.trim(); const budget=parseFloat(byId('adBudget').value||0);
  if(!title||!budget){ alert('Please enter a title and budget.'); return; }
  await fetch(API+'/ads',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,budget,owner:currentUser.email})});
  byId('adTitle').value=''; byId('adBudget').value='';
  loadAds();
}

async function loadAds(){
  const r=await fetch(API+'/ads');
  const list=await r.json();
  const el=byId('adsList'); el.innerHTML='';
  if(!list.length){
    el.innerHTML='<div class="empty-state"><div class="empty-icon">📢</div><p>No campaigns yet. Launch your first one above!</p></div>';
    return;
  }
  list.forEach(a=>{
    const d=document.createElement('div'); d.className='ad-item';
    d.innerHTML=`<div class="ad-item-name">${escapeHtml(a.title)}</div><div class="ad-item-stats"><span class="ad-stat">💰 ${a.budget}</span><span class="ad-stat">👁 ${a.impressions}</span><span class="ad-stat">🖱 ${a.clicks}</span></div>`;
    el.appendChild(d);
  });
}

async function refreshAll(){ await loadFeed(); await loadNotifications(); await loadProfilePosts(); await loadMonetization(); await loadAds(); }
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML)

# ---------- API: Auth ----------
@app.route("/api/signup", methods=["POST"])
def api_signup():
    db = get_db()
    cur = get_cursor(db)
    name = request.form.get("name")
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password")
    profile_pic = ""
    if 'file' in request.files:
        f = request.files['file']
        if f and f.filename:
            fn = f"{uuid.uuid4().hex}_{f.filename}"
            f.save(os.path.join(UPLOAD_DIR, fn))
            profile_pic = f"/uploads/{fn}"
    if not email or not password:
        return jsonify({"error":"email+password required"}), 400
    try:
        cur.execute("INSERT INTO users (name,email,password,profile_pic) VALUES (?,?,?,?)", (name, email, password, profile_pic))
        db.commit()
    except Exception as e:
        if "unique" in str(e).lower():
            return jsonify({"error":"User already exists"}), 400
        return jsonify({"error": str(e)}), 500
    user = {"name": name, "email": email, "profile_pic": profile_pic, "bio": "", "watch_hours": 0, "earnings": 0}
    session['user_email'] = email
    return jsonify({"user": user})

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password")
    db = get_db()
    cur = get_cursor(db)
    cur.execute("SELECT name,email,profile_pic,bio,watch_hours,earnings FROM users WHERE email=? AND password=?", (email, password))
    r = cur.fetchone()
    if not r:
        return jsonify({"error":"Invalid credentials"}), 401
    session['user_email'] = email
    return jsonify({"user": dict(r)})

@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"status": "logged out"})

@app.route("/api/me")
def api_me():
    email = session.get('user_email')
    if not email:
        return jsonify({"user": None})
    db = get_db()
    cur = get_cursor(db)
    cur.execute("SELECT name,email,profile_pic,bio,watch_hours,earnings FROM users WHERE email=?", (email,))
    r = cur.fetchone()
    return jsonify({"user": dict(r) if r else None})

# ---------- Upload ----------
@app.route("/api/upload", methods=["POST"])
def api_upload():
    if 'file' not in request.files:
        return jsonify({"error":"No file"}), 400
    f = request.files['file']
    if f.filename == "":
        return jsonify({"error":"No filename"}), 400
    fn = f"{uuid.uuid4().hex}_{f.filename}"
    f.save(os.path.join(UPLOAD_DIR, fn))
    return jsonify({"url": f"/uploads/{fn}"})

# ---------- Posts ----------
@app.route("/api/posts", methods=["GET","POST"])
def api_posts():
    db = get_db()
    cur = get_cursor(db)
    if request.method == "GET":
        cur.execute("SELECT * FROM posts ORDER BY id DESC")
        rows = cur.fetchall()
        out = []
        for r in rows:
            rec = dict(r)
            try: rec['reactions'] = _json.loads(rec.get('reactions_json','{}'))
            except: rec['reactions'] = {'👍':0,'❤️':0,'😂':0}
            rec['user_reaction'] = None
            out.append(rec)
        return jsonify(out)
    else:
        data = request.get_json() or {}
        ts = now_ts()
        rj = _json.dumps({'👍':0,'❤️':0,'😂':0})
        cur.execute("INSERT INTO posts (author_email,author_name,profile_pic,text,file_url,timestamp,reactions_json,comments_count) VALUES (?,?,?,?,?,?,?,?)",
            (data.get('author_email'), data.get('author_name'), data.get('profile_pic',''), data.get('text',''), data.get('file_url',''), ts, rj, 0))
        db.commit()
        post_id = cur.lastrowid
        cur.execute("SELECT * FROM posts WHERE id=?", (post_id,))
        rec = dict(cur.fetchone())
        rec['reactions'] = _json.loads(rec['reactions_json'])
        rec['user_reaction'] = None
        return jsonify(rec)

# ---------- React ----------
@app.route("/api/react", methods=["POST"])
def api_react_post():
    data = request.get_json() or {}
    post_id = data.get("post_id")
    emoji = data.get("emoji")
    user_email = data.get("user_email")
    db = get_db()
    cur = get_cursor(db)
    cur.execute("SELECT id,reactions_json,author_email FROM posts WHERE id=?", (post_id,))
    row = cur.fetchone()
    if not row:
        return jsonify({"error":"Post not found"}), 404
    reactions = _json.loads(row['reactions_json'] or '{}')
    cur.execute("SELECT emoji FROM user_reactions WHERE user_email=? AND post_id=?", (user_email, post_id))
    prev = cur.fetchone()
    prev_emoji = prev['emoji'] if prev else None
    if prev_emoji == emoji:
        return jsonify({"success":True, "reactions": reactions})
    if prev_emoji:
        reactions[prev_emoji] = max(0, reactions.get(prev_emoji,0)-1)
        cur.execute("DELETE FROM user_reactions WHERE user_email=? AND post_id=?", (user_email, post_id))
    try:
        cur.execute("INSERT INTO user_reactions (user_email,post_id,emoji) VALUES (?,?,?)", (user_email, post_id, emoji))
    except: pass
    reactions[emoji] = reactions.get(emoji,0) + 1
    cur.execute("UPDATE posts SET reactions_json=? WHERE id=?", (_json.dumps(reactions), post_id))
    db.commit()
    if row['author_email'] != user_email:
        cur.execute("INSERT INTO notifications (user_email,text,timestamp) VALUES (?,?,?)", (row['author_email'], f"{emoji} reaction on your post", now_ts()))
        db.commit()
    return jsonify({"success":True, "reactions": reactions})

# ---------- Notifications ----------
@app.route("/api/notifications/<email>")
def api_notifications_get(email):
    db = get_db()
    cur = get_cursor(db)
    cur.execute("SELECT * FROM notifications WHERE user_email=? ORDER BY id DESC", (email,))
    return jsonify([dict(r) for r in cur.fetchall()])

# ---------- Monetization / Profile ----------
@app.route("/api/monetization/<email>")
def api_monetization_get(email):
    db = get_db()
    cur = get_cursor(db)
    cur.execute("SELECT COUNT(*) as cnt FROM followers WHERE user_email=?", (email,))
    res = cur.fetchone()
    followers = res['cnt'] if res else 0
    cur.execute("SELECT watch_hours, earnings FROM users WHERE email=?", (email,))
    u = cur.fetchone()
    if u:
        return jsonify({"followers": followers, "watch_hours": u['watch_hours'], "earnings": u['earnings']})
    return jsonify({"followers": 0, "watch_hours": 0, "earnings": 0})

@app.route("/api/profile/<email>")
def api_profile_get(email):
    db = get_db()
    cur = get_cursor(db)
    cur.execute("SELECT bio FROM users WHERE email=?", (email,))
    u = cur.fetchone()
    cur.execute("SELECT * FROM posts WHERE author_email=? ORDER BY id DESC", (email,))
    posts = [dict(r) for r in cur.fetchall()]
    return jsonify({"bio": u['bio'] if u else "", "posts": posts})

@app.route("/api/update_bio", methods=["POST"])
def api_update_bio():
    data = request.get_json() or {}
    db = get_db()
    cur = get_cursor(db)
    cur.execute("UPDATE users SET bio=? WHERE email=?", (data.get("bio"), data.get("email")))
    db.commit()
    return jsonify({"success": True})

# ---------- Following ----------
@app.route("/api/follow", methods=["POST"])
def api_follow():
    data = request.get_json() or {}
    follower = data.get("follower_email")
    target = data.get("target_email")
    db = get_db()
    cur = get_cursor(db)
    cur.execute("SELECT id FROM followers WHERE user_email=? AND follower_email=?", (target, follower))
    if cur.fetchone():
        cur.execute("DELETE FROM followers WHERE user_email=? AND follower_email=?", (target, follower))
        db.commit()
        return jsonify({"success": True, "status": "unfollowed"})
    cur.execute("INSERT INTO followers (user_email, follower_email) VALUES (?,?)", (target, follower))
    cur.execute("INSERT INTO notifications (user_email, text, timestamp) VALUES (?,?,?)", (target, f"{follower} followed you", now_ts()))
    db.commit()
    return jsonify({"success": True, "status": "followed"})

@app.route("/api/is_following")
def api_is_following():
    f = request.args.get("f")
    t = request.args.get("t")
    db = get_db()
    cur = get_cursor(db)
    cur.execute("SELECT id FROM followers WHERE user_email=? AND follower_email=?", (t, f))
    return jsonify({"following": bool(cur.fetchone())})

# ---------- Watch / Ads ----------
@app.route("/api/watch", methods=["POST"])
def api_watch():
    data = request.get_json() or {}
    viewer = data.get("viewer")
    post_id = data.get("post_id")
    db = get_db()
    cur = get_cursor(db)
    cur.execute("SELECT author_email FROM posts WHERE id=?", (post_id,))
    row = cur.fetchone()
    if row and row['author_email'] != viewer:
        cur.execute("UPDATE users SET watch_hours=watch_hours+1, earnings=earnings+0.1 WHERE email=?", (row['author_email'],))
        db.commit()
    return jsonify({"success": True})

@app.route("/api/ads", methods=["GET","POST"])
def api_ads():
    db = get_db()
    cur = get_cursor(db)
    if request.method == "POST":
        data = request.get_json() or {}
        cur.execute("INSERT INTO ads (title, owner_email, budget) VALUES (?,?,?)", (data.get('title'), data.get('owner'), data.get('budget')))
        db.commit()
        return jsonify({"message": "Ad created"})
    cur.execute("SELECT * FROM ads ORDER BY id DESC")
    return jsonify([dict(r) for r in cur.fetchall()])

@app.route("/api/ads/impression", methods=["POST"])
def api_ads_impression():
    return jsonify({"success": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=app.config['PORT'], debug=True)
