# app.py - VibeNet (Monetized & Modernized)
import os
import uuid
import datetime
import json as _json
from flask import Flask, request, jsonify, send_from_directory, g, render_template_string, session

# ---------- Database Setup ----------
import sqlite3
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    HAS_POSTGRES_LIB = True
except ImportError:
    HAS_POSTGRES_LIB = False

APP_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(APP_DIR, "uploads")
DB_PATH = os.path.join(APP_DIR, "data", "vibenet.db")
os.makedirs(os.path.join(APP_DIR, "data"), exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "vibe_dev_key_99")

# ---------- DB Logic (Postgres/SQLite Hybrid) ----------
def get_db():
    if not hasattr(g, "_db"):
        if os.environ.get("DATABASE_URL") and HAS_POSTGRES_LIB:
            g._db = psycopg2.connect(os.environ.get("DATABASE_URL"), cursor_factory=RealDictCursor)
        else:
            g._db = sqlite3.connect(DB_PATH)
            g._db.row_factory = sqlite3.Row
    return g._db

def init_db():
    db = get_db()
    cur = db.cursor()
    # Simplified table creation for demo
    cur.execute("CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, name TEXT, email TEXT UNIQUE, password TEXT, profile_pic TEXT, watch_hours INTEGER DEFAULT 0, earnings REAL DEFAULT 0)")
    cur.execute("CREATE TABLE IF NOT EXISTS posts (id SERIAL PRIMARY KEY, author_email TEXT, text TEXT, file_url TEXT, reactions_json TEXT DEFAULT '{}', timestamp TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS messages (id SERIAL PRIMARY KEY, sender TEXT, recipient TEXT, text TEXT, timestamp TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS notifications (id SERIAL PRIMARY KEY, user_email TEXT, text TEXT, seen INTEGER DEFAULT 0, timestamp TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS user_reactions (user_email TEXT, post_id INTEGER, emoji TEXT, PRIMARY KEY(user_email, post_id))")
    db.commit()

# ---------- UI Template ----------
HTML = r"""
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>VibeNet — Explore</title>
    <script src="https://unpkg.com/lucide@latest"></script>
    <style>
        :root { --bg: #0b0e14; --card: #161b22; --border: #30363d; --accent: #58a6ff; --text: #c9d1d9; }
        body { background: var(--bg); color: var(--text); font-family: sans-serif; margin: 0; }
        .layout { display: grid; grid-template-columns: 260px 1fr 300px; max-width: 1200px; margin: 0 auto; gap: 20px; padding: 20px; }
        .nav-item { display: flex; align-items: center; gap: 12px; padding: 12px; cursor: pointer; border-radius: 8px; transition: 0.2s; }
        .nav-item:hover { background: #21262d; }
        .card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 16px; margin-bottom: 15px; }
        .post-media { width: 100%; border-radius: 8px; margin: 10px 0; border: 1px solid var(--border); }
        .badge { background: #f85149; color: white; font-size: 10px; padding: 2px 6px; border-radius: 10px; margin-left: auto; }
        .btn-post { background: var(--accent); color: white; border: none; padding: 8px 20px; border-radius: 20px; cursor: pointer; }
        textarea { width: 100%; background: transparent; border: none; color: white; resize: none; font-size: 16px; }
        #authOverlay { position: fixed; inset: 0; background: var(--bg); z-index: 100; display: flex; align-items: center; justify-content: center; }
    </style>
</head>
<body>
    <div id="authOverlay">
        <div class="card" style="width: 350px; text-align: center;">
            <h2 style="color: var(--accent)">VibeNet</h2>
            <input id="authEmail" placeholder="Email" style="width:100%; margin-bottom:10px; padding:8px;">
            <input id="authPass" type="password" placeholder="Password" style="width:100%; margin-bottom:10px; padding:8px;">
            <button class="btn-post" onclick="login()" style="width:100%">Enter VibeNet</button>
        </div>
    </div>

    <div class="layout" id="mainApp" style="display:none">
        <aside>
            <h2 style="color: var(--accent); margin-left:12px">VibeNet</h2>
            <div class="nav-item" onclick="showTab('feed')"><i data-lucide="home"></i> Home</div>
            <div class="nav-item" onclick="showTab('messages')"><i data-lucide="mail"></i> Messages</div>
            <div class="nav-item" onclick="showTab('notifications')"><i data-lucide="bell"></i> Notifications <span id="nBadge" class="badge" style="display:none"></span></div>
            <div class="nav-item" onclick="showTab('monetization')"><i data-lucide="zap"></i> Monetization</div>
        </aside>

        <main>
            <div id="feedTab" class="tab-content">
                <div class="card">
                    <textarea id="postText" placeholder="What's the vibe?"></textarea>
                    <hr style="border: 0.5px solid var(--border)">
                    <div style="display: flex; justify-content: space-between">
                        <input type="file" id="fileIn" style="display:none">
                        <button class="btn-post" style="background:#21262d" onclick="document.getElementById('fileIn').click()">Media</button>
                        <button class="btn-post" onclick="createPost()">Post</button>
                    </div>
                </div>
                <div id="postList"></div>
            </div>

            <div id="messagesTab" class="tab-content" style="display:none">
                <div class="card">
                    <h3>Direct Messages</h3>
                    <input id="msgTo" placeholder="Recipient email" style="width:100%; margin-bottom:10px; padding:8px; background:#0d1117; color:white; border:1px solid var(--border)">
                    <textarea id="msgBody" placeholder="Message content..."></textarea>
                    <button class="btn-post" onclick="sendMsg()">Send</button>
                </div>
                <div id="msgList"></div>
            </div>

            <div id="notificationsTab" class="tab-content" style="display:none">
                <div class="card"><h3>Notifications</h3><div id="notifList"></div></div>
            </div>

            <div id="monetizationTab" class="tab-content" style="display:none">
                <div class="card" style="text-align: center;">
                    <h3>Creator Stats</h3>
                    <div style="display: flex; justify-content: space-around;">
                        <div><h4>Watch Hours</h4><h2 id="mHours">0</h2></div>
                        <div><h4>Credits</h4><h2 id="mEarnings">0.00</h2></div>
                    </div>
                </div>
            </div>
        </main>

        <aside>
            <div class="card">
                <h4>Trending Vibes</h4>
                <p style="font-size: 14px; color: #8b949e">#VibeNetCloud<br>#DevLife<br>#MonetizeMe</p>
            </div>
        </aside>
    </div>

    <script>
        let user = null;
        async function login() {
            const email = document.getElementById('authEmail').value;
            const res = await fetch('/api/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email, password: '123'})
            });
            const data = await res.json();
            if(data.user) {
                user = data.user;
                document.getElementById('authOverlay').style.display = 'none';
                document.getElementById('mainApp').style.display = 'grid';
                refresh();
                setInterval(refresh, 5000);
            }
        }

        function showTab(name) {
            document.querySelectorAll('.tab-content').forEach(t => t.style.display = 'none');
            document.getElementById(name + 'Tab').style.display = 'block';
        }

        async function refresh() {
            lucide.createIcons();
            loadFeed();
            loadNotifs();
            loadMonet();
        }

        async function loadFeed() {
            const res = await fetch('/api/posts');
            const posts = await res.json();
            const list = document.getElementById('postList');
            list.innerHTML = posts.map(p => `
                <div class="card">
                    <strong>${p.author_email}</strong>
                    <p>${p.text}</p>
                    ${p.file_url ? `<img src="${p.file_url}" class="post-media">` : ''}
                    <div style="display:flex; gap:15px">
                        <button onclick="react(${p.id}, '👍')" style="background:none; border:none; color:white; cursor:pointer">👍 ${p.reactions['👍'] || 0}</button>
                        <button onclick="react(${p.id}, '❤️')" style="background:none; border:none; color:white; cursor:pointer">❤️ ${p.reactions['❤️'] || 0}</button>
                    </div>
                </div>
            `).join('');
        }

        async function react(postId, emoji) {
            await fetch('/api/react', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({post_id: postId, emoji, user_email: user.email})
            });
            loadFeed();
        }

        async function loadNotifs() {
            const res = await fetch('/api/notifications/' + user.email);
            const data = await res.json();
            if(data.length) {
                document.getElementById('nBadge').style.display = 'inline-block';
                document.getElementById('nBadge').innerText = data.length;
            }
            document.getElementById('notifList').innerHTML = data.map(n => `<div style="padding:10px; border-bottom:1px solid var(--border)">${n.text}</div>`).join('');
        }

        async function loadMonet() {
            const res = await fetch('/api/monetization/' + user.email);
            const data = await res.json();
            document.getElementById('mHours').innerText = data.watch_hours;
            document.getElementById('mEarnings').innerText = data.earnings.toFixed(2);
        }
        
        async function sendMsg() {
            const recipient = document.getElementById('msgTo').value;
            const text = document.getElementById('msgBody').value;
            await fetch('/api/messages', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({from: user.email, to: recipient, text})
            });
            document.getElementById('msgBody').value = '';
        }
    </script>
</body>
</html>
"""

# ---------- API Routes ----------
@app.route("/")
def index(): return render_template_string(HTML)

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.json
    db = get_db(); cur = db.cursor()
    cur.execute("SELECT * FROM users WHERE email=?", (data['email'],))
    u = cur.fetchone()
    if not u:
        cur.execute("INSERT INTO users (email, name) VALUES (?,?)", (data['email'], data['email'].split('@')[0]))
        db.commit()
        cur.execute("SELECT * FROM users WHERE email=?", (data['email'],))
        u = cur.fetchone()
    return jsonify({"user": dict(u)})

@app.route("/api/posts")
def get_posts():
    db = get_db(); cur = db.cursor()
    cur.execute("SELECT * FROM posts ORDER BY id DESC")
    rows = [dict(r) for r in cur.fetchall()]
    for r in rows: r['reactions'] = _json.loads(r['reactions_json'])
    return jsonify(rows)

@app.route("/api/react", methods=["POST"])
def react():
    data = request.json
    db = get_db(); cur = db.cursor()
    # Logic: 1 reaction per user per post (Upsert)
    cur.execute("INSERT OR REPLACE INTO user_reactions (user_email, post_id, emoji) VALUES (?,?,?)", 
                (data['user_email'], data['post_id'], data['emoji']))
    # Recalculate reaction counts for post
    cur.execute("SELECT emoji, count(*) as cnt FROM user_reactions WHERE post_id=? GROUP BY emoji", (data['post_id'],))
    counts = {r['emoji']: r['cnt'] for r in cur.fetchall()}
    cur.execute("UPDATE posts SET reactions_json=? WHERE id=?", (_json.dumps(counts), data['post_id']))
    db.commit()
    return jsonify({"success": True})

@app.route("/api/monetization/<email>")
def get_monet(email):
    cur = get_db().cursor()
    cur.execute("SELECT watch_hours, earnings FROM users WHERE email=?", (email,))
    return jsonify(dict(cur.fetchone()))

@app.route("/api/notifications/<email>")
def get_notifs(email):
    cur = get_db().cursor()
    cur.execute("SELECT * FROM notifications WHERE user_email=? ORDER BY id DESC", (email,))
    return jsonify([dict(r) for r in cur.fetchall()])

@app.route("/api/messages", methods=["POST"])
def post_msg():
    data = request.json
    db = get_db(); cur = db.cursor()
    cur.execute("INSERT INTO messages (sender, recipient, text, timestamp) VALUES (?,?,?,?)", 
                (data['from'], data['to'], data['text'], datetime.datetime.now().isoformat()))
    db.commit()
    return jsonify({"success": True})

if __name__ == "__main__":
    with app.app_context(): init_db()
    app.run(debug=True, port=5001)
