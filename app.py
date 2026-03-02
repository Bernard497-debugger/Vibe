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
  cursor
