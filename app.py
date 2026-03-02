# app.py - VibeNet (Enhanced UI/UX Edition)
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
app.secret_key = os.environ.get("SECRET_KEY", "vibenet_secret_key_dev_123")

# ---------- Database Logic ----------

def get_db_type():
    if DATABASE_URL and HAS_POSTGRES_LIB: return 'postgres'
    return 'sqlite'

class PostgresCursorWrapper:
    def __init__(self, original_cursor):
        self.cursor = original_cursor
        self.lastrowid = None
    def execute(self, sql, args=None):
        sql = sql.replace('?', '%s')
        is_insert = sql.strip().upper().startswith("INSERT")
        if is_insert: sql += " RETURNING id"
        if args is None: self.cursor.execute(sql)
        else: self.cursor.execute(sql, args)
        if is_insert:
            res = self.cursor.fetchone()
            if res: self.lastrowid = res['id']
    def fetchone(self): return self.cursor.fetchone()
    def fetchall(self): return self.cursor.fetchall()
    def __getattr__(self, name): return getattr(self.cursor, name)

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
    if getattr(g, "_db_type", 'sqlite') == 'postgres': return PostgresCursorWrapper(db.cursor())
    return db.cursor()

def init_db():
    db = get_db()
    cur = get_cursor(db)
    pk_def = "SERIAL PRIMARY KEY" if get_db_type() == 'postgres' else "INTEGER PRIMARY KEY AUTOINCREMENT"
    cur.execute(f"CREATE TABLE IF NOT EXISTS users (id {pk_def}, name TEXT, email TEXT UNIQUE, password TEXT, profile_pic TEXT, bio TEXT DEFAULT '', watch_hours INTEGER DEFAULT 0, earnings REAL DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    cur.execute(f"CREATE TABLE IF NOT EXISTS followers (id {pk_def}, user_email TEXT, follower_email TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    cur.execute(f"CREATE TABLE IF NOT EXISTS posts (id {pk_def}, author_email TEXT, author_name TEXT, profile_pic TEXT, text TEXT, file_url TEXT, timestamp TEXT, reactions_json TEXT DEFAULT '{{}}', comments_count INTEGER DEFAULT 0)")
    cur.execute(f"CREATE TABLE IF NOT EXISTS user_reactions (id {pk_def}, user_email TEXT, post_id INTEGER, emoji TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_email, post_id))")
    cur.execute(f"CREATE TABLE IF NOT EXISTS messages (id {pk_def}, sender TEXT, recipient TEXT, text TEXT, timestamp TEXT)")
    cur.execute(f"CREATE TABLE IF NOT EXISTS notifications (id {pk_def}, user_email TEXT, text TEXT, timestamp TEXT, seen INTEGER DEFAULT 0)")
    cur.execute(f"CREATE TABLE IF NOT EXISTS ads (id {pk_def}, title TEXT, owner_email TEXT, budget REAL DEFAULT 0, impressions INTEGER DEFAULT 0, clicks INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    db.commit()

@app.teardown_appcontext
def close_db(exception):
    db = getattr(g, "_db", None)
    if db is not None: db.close()

def now_ts(): return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

with app.app_context(): init_db()

@app.route("/uploads/<path:filename>")
def uploaded_file(filename): return send_from_directory(UPLOAD_DIR, filename)

# ---------- Modernized Frontend ----------
HTML = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>VibeNet — Explore</title>
<script src="https://unpkg.com/lucide@latest"></script>
<style>
:root {
    --bg: #0b0e14;
    --surface: #161b22;
    --border: #30363d;
    --accent: #58a6ff;
    --text-main: #c9d1d9;
    --text-dim: #8b949e;
    --success: #238636;
}
* { box-sizing: border-box; outline: none; }
body { 
    margin: 0; background-color: var(--bg); color: var(--text-main); 
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    line-height: 1.5;
}

/* Layout */
.layout { display: grid; grid-template-columns: 240px 1fr 300px; max-width: 1200px; margin: 0 auto; gap: 20px; padding: 20px; }
@media (max-width: 900px) { .layout { grid-template-columns: 1fr; } .sidebar-left, .sidebar-right { display: none; } }

/* Sidebar Left (Navigation) */
.nav-link { 
    display: flex; align-items: center; gap: 12px; padding: 12px; 
    text-decoration: none; color: var(--text-main); border-radius: 8px; 
    transition: 0.2s; cursor: pointer; margin-bottom: 4px;
}
.nav-link:hover, .nav-link.active { background: #21262d; color: var(--accent); }
.nav-link i { width: 20px; height: 20px; }

/* Cards */
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 16px; margin-bottom: 16px; }

/* Feed & Posts */
.post { border-bottom: 1px solid var(--border); padding: 16px 0; }
.post:last-child { border: none; }
.post-header { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.avatar { width: 40px; height: 40px; border-radius: 50%; object-fit: cover; background: #30363d; }
.post-content { margin-left: 50px; }
.post-media { width: 100%; border-radius: 8px; margin-top: 10px; border: 1px solid var(--border); }

/* Interaction Bar */
.actions { display: flex; gap: 20px; margin-top: 12px; }
.action-btn { 
    background: transparent; border: none; color: var(--text-dim); 
    cursor: pointer; display: flex; align-items: center; gap: 5px; font-size: 14px;
}
.action-btn:hover { color: var(--accent); }
.action-btn.active { color: var(--accent); font-weight: bold; }

/* Inputs */
.input-area { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 16px; margin-bottom: 20px; }
textarea { 
    width: 100%; background: transparent; border: none; color: white; 
    font-size: 18px; resize: none; margin-bottom: 10px;
}
.btn-primary { 
    background: var(--accent); color: white; border: none; 
    padding: 8px 20px; border-radius: 20px; font-weight: bold; cursor: pointer;
}

/* Auth Overlay */
#authCard { 
    position: fixed; inset: 0; background: var(--bg); z-index: 1000; 
    display: flex; align-items: center; justify-content: center;
}
.auth-box { width: 100%; max-width: 400px; text-align: center; }
.auth-input { 
    width: 100%; padding: 12px; margin: 8px 0; background: #0d1117; 
    border: 1px solid var(--border); border-radius: 6px; color: white;
}

.badge { background: #f85149; color: white; font-size: 10px; padding: 2px 6px; border-radius: 10px; margin-left: auto; }
</style>
</head>
<body>

<div id="authCard">
    <div class="auth-box card">
        <h1 style="color:var(--accent)">VibeNet</h1>
        <div id="loginForm">
            <input id="loginEmail" class="auth-input" placeholder="Email" />
            <input id="loginPassword" class="auth-input" type="password" placeholder="Password" />
            <button class="btn-primary" style="width:100%" onclick="login()">Login</button>
            <p class="text-dim" style="font-size:14px; margin-top:15px">New here? <a href="#" onclick="toggleAuth(true)" style="color:var(--accent)">Sign Up</a></p>
        </div>
        <div id="signupForm" style="display:none">
            <input id="signupName" class="auth-input" placeholder="Full Name" />
            <input id="signupEmail" class="auth-input" placeholder="Email" />
            <input id="signupPassword" class="auth-input" type="password" placeholder="Password" />
            <button class="btn-primary" style="width:100%" onclick="signup()">Create Account</button>
            <p class="text-dim" style="font-size:14px; margin-top:15px">Already have an account? <a href="#" onclick="toggleAuth(false)" style="color:var(--accent)">Login</a></p>
        </div>
    </div>
</div>

<div id="app" style="display:none">
    <div class="layout">
        <div class="sidebar-left">
            <h2 style="color:var(--accent); margin-left:12px">VibeNet</h2>
            <nav>
                <div class="nav-link active" onclick="showTab('feed', this)"><i data-lucide="home"></i> Home</div>
                <div class="nav-link" onclick="showTab('messages', this)"><i data-lucide="mail"></i> Messages</div>
                <div class="nav-link" onclick="showTab('notifications', this)"><i data-lucide="bell"></i> Notifications <span id="notifBadge" class="badge" style="display:none">0</span></div>
                <div class="nav-link" onclick="showTab('monet', this)"><i data-lucide="zap"></i> Monetization</div>
                <div class="nav-link" onclick="showTab('profile', this)"><i data-lucide="user"></i> Profile</div>
                <div class="nav-link" onclick="logout()" style="margin-top:20px; color:#f85149"><i data-lucide="log-out"></i> Logout</div>
            </nav>
        </div>

        <main>
            <div id="feedTab" class="content-tab">
                <div class="input-area">
                    <textarea id="postText" placeholder="What's happening?"></textarea>
                    <div style="display:flex; justify-content: space-between; align-items: center;">
                        <input type="file" id="fileUpload" style="display:none" onchange="updateFileLabel()">
                        <button class="action-btn" onclick="byId('fileUpload').click()"><i data-lucide="image"></i> <span id="fileName">Media</span></button>
                        <button class="btn-primary" onclick="addPost()">Post</button>
                    </div>
                </div>
                <div id="feedList"></div>
            </div>

            <div id="messagesTab" class="content-tab" style="display:none">
                <div class="card">
                    <h3>Messages</h3>
                    <input id="msgTo" class="auth-input" placeholder="Recipient email" />
                    <textarea id="msgText" placeholder="Type a message..." style="font-size:14px"></textarea>
                    <button class="btn-primary" onclick="sendMessage()">Send Message</button>
                </div>
                <div id="msgList"></div>
            </div>

            <div id="notificationsTab" class="content-tab" style="display:none">
                <div class="card"><h3>Notifications</h3><div id="notifList"></div></div>
            </div>

            <div id="monetTab" class="content-tab" style="display:none">
                <div class="card">
                    <h3>Creator Dashboard</h3>
                    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:10px">
                        <div class="card" style="text-align:center"><h4>Watch Hours</h4><h2 id="monWatch">0</h2></div>
                        <div class="card" style="text-align:center"><h4>Earnings</h4><h2 id="monEarnings">0.00</h2></div>
                    </div>
                </div>
            </div>

            <div id="profileTab" class="content-tab" style="display:none">
                <div class="card" id="profileHeader"></div>
                <div id="profilePosts"></div>
            </div>
        </main>

        <div class="sidebar-right">
            <div class="card">
                <h4>Suggested Creators</h4>
                <div id="suggestions">...</div>
            </div>
            <div class="card">
                <h4 style="margin-top:0">Sponsored</h4>
                <div id="adsList" style="font-size:13px; color:var(--text-dim)"></div>
            </div>
        </div>
    </div>
</div>

<script>
const API = '/api';
let currentUser = null;

function byId(id){ return document.getElementById(id); }
function toggleAuth(showSignup){
    byId('loginForm').style.display = showSignup ? 'none' : 'block';
    byId('signupForm').style.display = showSignup ? 'block' : 'none';
}

function updateFileLabel() {
    const file = byId('fileUpload').files[0];
    byId('fileName').textContent = file ? file.name.substring(0,10) + '...' : 'Media';
}

window.addEventListener('load', async () => {
    lucide.createIcons();
    const res = await fetch(API + '/me');
    const j = await res.json();
    if(j.user) { currentUser = j.user; onLogin(); }
});

async function login(){
    const email = byId('loginEmail').value;
    const password = byId('loginPassword').value;
    const res = await fetch(API + '/login', { 
        method:'POST', 
        headers:{'Content-Type':'application/json'}, 
        body: JSON.stringify({ email, password })
    });
    const j = await res.json();
    if(j.user){ currentUser = j.user; onLogin(); } else alert('Fail');
}

async function signup(){
    const fd = new FormData();
    fd.append('name', byId('signupName').value);
    fd.append('email', byId('signupEmail').value);
    fd.append('password', byId('signupPassword').value);
    const res = await fetch(API + '/signup', { method:'POST', body: fd });
    const j = await res.json();
    if(j.user){ currentUser = j.user; onLogin(); }
}

function onLogin(){
    byId('authCard').style.display = 'none';
    byId('app').style.display = 'block';
    refreshAll();
    setInterval(() => { loadNotifications(); }, 5000);
}

function showTab(tabName, el){
    document.querySelectorAll('.content-tab').forEach(t => t.style.display = 'none');
    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
    byId(tabName + 'Tab').style.display = 'block';
    el.classList.add('active');
}

async function addPost(){
    const text = byId('postText').value;
    const file = byId('fileUpload').files[0];
    let url = '';
    if(file){
        const fd = new FormData(); fd.append('file', file);
        const up = await fetch(API + '/upload', { method:'POST', body: fd });
        const upj = await up.json(); url = upj.url;
    }
    await fetch(API + '/posts', { 
        method:'POST', 
        headers:{'Content-Type':'application/json'}, 
        body: JSON.stringify({
            author_email: currentUser.email, author_name: currentUser.name, 
            profile_pic: currentUser.profile_pic, text, file_url: url
        })
    });
    byId('postText').value = ''; byId('fileUpload').value = '';
    loadFeed();
}

async function loadFeed(){
    const res = await fetch(API + '/posts');
    const posts = await res.json();
    const list = byId('feedList'); list.innerHTML = '';
    posts.forEach(p => {
        const div = document.createElement('div');
        div.className = 'post';
        const media = p.file_url ? (p.file_url.endsWith('.mp4') ? 
            `<video src="${p.file_url}" class="post-media" controls></video>` : 
            `<img src="${p.file_url}" class="post-media">`) : '';
        
        div.innerHTML = `
            <div class="post-header">
                <img src="${p.profile_pic || 'https://via.placeholder.com/40'}" class="avatar">
                <div>
                    <strong>${p.author_name}</strong>
                    <div style="font-size:12px; color:var(--text-dim)">${p.timestamp}</div>
                </div>
            </div>
            <div class="post-content">
                <div>${p.text}</div>
                ${media}
                <div class="actions">
                    <button class="action-btn" onclick="react(${p.id}, '👍')"><i data-lucide="thumbs-up"></i> ${p.reactions['👍'] || 0}</button>
                    <button class="action-btn" onclick="react(${p.id}, '❤️')"><i data-lucide="heart"></i> ${p.reactions['❤️'] || 0}</button>
                    <button class="action-btn"><i data-lucide="message-circle"></i> ${p.comments_count}</button>
                </div>
            </div>
        `;
        list.appendChild(div);
    });
    lucide.createIcons();
}

async function react(postId, emoji){
    await fetch(API + '/react', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ post_id: postId, emoji, user_email: currentUser.email })
    });
    loadFeed();
}

async function loadNotifications(){
    const res = await fetch(API + '/notifications/' + encodeURIComponent(currentUser.email));
    const data = await res.json();
    const badge = byId('notifBadge');
    if(data.length > 0){
        badge.style.display = 'inline-block';
        badge.textContent = data.length;
    }
    const list = byId('notifList'); list.innerHTML = '';
    data.forEach(n => {
        const d = document.createElement('div');
        d.style.padding = '10px 0'; d.style.borderBottom = '1px solid var(--border)';
        d.innerHTML = `<div>${n.text}</div><div style="font-size:11px; color:var(--text-dim)">${n.timestamp}</div>`;
        list.appendChild(d);
    });
}

async function logout(){
    await fetch(API + '/logout', { method: 'POST' });
    location.reload();
}

async function refreshAll(){
    loadFeed();
    loadNotifications();
    // Load monetization data
    const mon = await (await fetch(API + '/monetization/' + encodeURIComponent(currentUser.email))).json();
    byId('monWatch').textContent = mon.watch_hours;
    byId('monEarnings').textContent = mon.earnings.toFixed(2);
}
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML)

# [Remaining API routes from original vibenet.py go here - they remain unchanged]
@app.route("/api/signup", methods=["POST"])
def api_signup():
    db = get_db(); cur = get_cursor(db)
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
    try:
        cur.execute("INSERT INTO users (name,email,password,profile_pic) VALUES (?,?,?,?)", (name, email, password, profile_pic))
        db.commit()
    except: return jsonify({"error":"Exists"}), 400
    user = {"name": name, "email": email, "profile_pic": profile_pic}
    session['user_email'] = email
    return jsonify({"user": user})

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json()
    cur = get_cursor(get_db())
    cur.execute("SELECT name,email,profile_pic FROM users WHERE email=? AND password=?", (data['email'], data['password']))
    r = cur.fetchone()
    if not r: return jsonify({"error":"Fail"}), 401
    session['user_email'] = r['email']
    return jsonify({"user": dict(r)})

@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"status": "ok"})

@app.route("/api/me", methods=["GET"])
def api_me():
    email = session.get('user_email')
    if not email: return jsonify({"user": None})
    cur = get_cursor(get_db())
    cur.execute("SELECT name,email,profile_pic FROM users WHERE email=?", (email,))
    r = cur.fetchone()
    return jsonify({"user": dict(r) if r else None})

@app.route("/api/upload", methods=["POST"])
def api_upload():
    f = request.files['file']
    fn = f"{uuid.uuid4().hex}_{f.filename}"
    f.save(os.path.join(UPLOAD_DIR, fn))
    return jsonify({"url": f"/uploads/{fn}"})

@app.route("/api/posts", methods=["GET","POST"])
def api_posts():
    db = get_db(); cur = get_cursor(db)
    if request.method == "GET":
        cur.execute("SELECT * FROM posts ORDER BY id DESC")
        rows = cur.fetchall()
        out = []
        for r in rows:
            rec = dict(r)
            rec['reactions'] = _json.loads(rec.get('reactions_json','{}'))
            out.append(rec)
        return jsonify(out)
    else:
        data = request.get_json()
        cur.execute("INSERT INTO posts (author_email,author_name,profile_pic,text,file_url,timestamp) VALUES (?,?,?,?,?,?)", 
                    (data['author_email'], data['author_name'], data.get('profile_pic'), data.get('text'), data.get('file_url'), now_ts()))
        db.commit()
        return jsonify({"status":"ok"})

@app.route("/api/notifications/<email>")
def api_notifications_get(email):
    cur = get_cursor(get_db())
    cur.execute("SELECT * FROM notifications WHERE user_email=? ORDER BY id DESC", (email,))
    return jsonify([dict(r) for r in cur.fetchall()])

@app.route("/api/monetization/<email>")
def api_monetization_get(email):
    cur = get_cursor(get_db())
    cur.execute("SELECT watch_hours, earnings FROM users WHERE email=?", (email,))
    u = cur.fetchone()
    return jsonify(dict(u) if u else {"watch_hours":0, "earnings":0})

@app.route("/api/react", methods=["POST"])
def api_react():
    data = request.get_json()
    db = get_db(); cur = get_cursor(db)
    cur.execute("SELECT reactions_json, author_email FROM posts WHERE id=?", (data['post_id'],))
    row = cur.fetchone()
    reactions = _json.loads(row['reactions_json'] or '{}')
    emoji = data['emoji']
    reactions[emoji] = reactions.get(emoji, 0) + 1
    cur.execute("UPDATE posts SET reactions_json=? WHERE id=?", (_json.dumps(reactions), data['post_id']))
    if row['author_email'] != data['user_email']:
        cur.execute("INSERT INTO notifications (user_email, text, timestamp) VALUES (?,?,?)", (row['author_email'], f"Someone reacted {emoji} to your post", now_ts()))
    db.commit()
    return jsonify({"success":True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=app.config['PORT'], debug=True)
