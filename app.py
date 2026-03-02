import os, uuid, datetime, sqlite3
import json as _json
from flask import Flask, request, jsonify, g, render_template_string, session

app = Flask(__name__)
app.secret_key = "vibe_secret_key"
DB_PATH = "vibenet.db"

# ---------- Database Logic ----------
def get_db():
    if not hasattr(g, "_db"):
        g._db = sqlite3.connect(DB_PATH)
        g._db.row_factory = sqlite3.Row
    return g._db

def init_db():
    db = get_db()
    cur = db.cursor()
    # Users & Monetization
    cur.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, name TEXT, watch_hours INTEGER DEFAULT 0, earnings REAL DEFAULT 0.0)")
    # Posts & 1-Reaction Logic
    cur.execute("CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY AUTOINCREMENT, author_email TEXT, text TEXT, reactions_json TEXT DEFAULT '{}', timestamp TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS user_reactions (user_email TEXT, post_id INTEGER, emoji TEXT, PRIMARY KEY(user_email, post_id))")
    # Messages & Notifications
    cur.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, sender TEXT, recipient TEXT, text TEXT, timestamp TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, user_email TEXT, text TEXT, seen INTEGER DEFAULT 0, timestamp TEXT)")
    db.commit()

@app.teardown_appcontext
def close_db(e):
    if hasattr(g, "_db"): g._db.close()

# ---------- UI Design (Modern Dark Theme) ----------
HTML = r"""
<!DOCTYPE html>
<html>
<head>
    <script src="https://unpkg.com/lucide@latest"></script>
    <style>
        :root { --bg: #0b0e14; --card: #161b22; --border: #30363d; --accent: #58a6ff; --text: #c9d1d9; }
        body { background: var(--bg); color: var(--text); font-family: -apple-system, sans-serif; margin: 0; }
        
        /* Layout Grid */
        .app-container { display: grid; grid-template-columns: 250px 1fr 300px; max-width: 1200px; margin: 0 auto; gap: 20px; padding: 20px; }
        
        /* Sidebar Menu */
        .menu-item { display: flex; align-items: center; gap: 12px; padding: 12px; cursor: pointer; border-radius: 8px; transition: 0.2s; font-weight: 500; }
        .menu-item:hover { background: #21262d; color: var(--accent); }
        .active { color: var(--accent); background: #1c2128; }
        
        /* Cards & Feed */
        .card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 16px; margin-bottom: 16px; }
        .btn { background: var(--accent); color: white; border: none; padding: 8px 16px; border-radius: 20px; cursor: pointer; font-weight: bold; }
        textarea { width: 100%; background: transparent; border: none; color: white; font-size: 16px; resize: none; margin-bottom: 10px; }
        
        .badge { background: #f85149; color: white; font-size: 10px; padding: 2px 6px; border-radius: 10px; margin-left: auto; }
        .stat-box { text-align: center; border-right: 1px solid var(--border); }
        .stat-box:last-child { border: none; }
    </style>
</head>
<body>
    <div id="auth" style="display: flex; height: 100vh; align-items: center; justify-content: center;">
        <div class="card" style="width: 300px; text-align: center;">
            <h2 style="color:var(--accent)">VibeNet</h2>
            <input id="email" placeholder="Enter Email" style="width:90%; padding:10px; margin-bottom:10px; border-radius:5px; border:1px solid var(--border); background:#0d1117; color:white;">
            <button class="btn" style="width:100%" onclick="login()">Enter</button>
        </div>
    </div>

    <div id="main" class="app-container" style="display:none">
        <nav>
            <h2 style="color:var(--accent); margin-left:12px;">VibeNet</h2>
            <div class="menu-item active" onclick="showTab('feed')"><i data-lucide="home"></i> Home</div>
            <div class="menu-item" onclick="showTab('messages')"><i data-lucide="mail"></i> Messages</div>
            <div class="menu-item" onclick="showTab('notifs')"><i data-lucide="bell"></i> Notifications <span id="nBadge" class="badge" style="display:none">0</span></div>
            <div class="menu-item" onclick="showTab('monet')"><i data-lucide="zap"></i> Monetization</div>
        </nav>

        <main>
            <div id="feedTab">
                <div class="card">
                    <textarea id="postContent" placeholder="Share your vibe..."></textarea>
                    <div style="text-align: right;"><button class="btn" onclick="postVibe()">Post</button></div>
                </div>
                <div id="vibeList"></div>
            </div>

            <div id="messagesTab" style="display:none">
                <div class="card">
                    <h3>Messages</h3>
                    <input id="msgTo" placeholder="To (email)" style="width:95%; padding:8px; margin-bottom:10px; background:#0d1117; color:white; border:1px solid var(--border);">
                    <textarea id="msgBody" placeholder="Type a message..."></textarea>
                    <button class="btn" onclick="sendMsg()">Send</button>
                </div>
                <div id="inbox"></div>
            </div>

            <div id="notifsTab" style="display:none">
                <div class="card"><h3>Notifications</h3><div id="notifList"></div></div>
            </div>

            <div id="monetTab" style="display:none">
                <div class="card">
                    <h3>Creator Revenue</h3>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; margin-top:20px;">
                        <div class="stat-box"><small>WATCH HOURS</small><h2 id="mHours">0</h2></div>
                        <div class="stat-box"><small>EST. EARNINGS</small><h2 id="mCash">$0.00</h2></div>
                    </div>
                </div>
            </div>
        </main>

        <aside>
            <div class="card">
                <h4>Your Stats</h4>
                <p id="userMail" style="font-size:12px; color:var(--accent)"></p>
                <hr style="border:0.1px solid var(--border)">
                <small>Every view on your posts adds to your earnings!</small>
            </div>
        </aside>
    </div>

    <script>
        let currentUser = null;
        async function login() {
            const email = document.getElementById('email').value;
            if(!email) return;
            const res = await fetch('/api/login', {
                method: 'POST', 
                headers: {'Content-Type': 'application/json'}, 
                body: JSON.stringify({email})
            });
            const data = await res.json();
            currentUser = data.user;
            document.getElementById('auth').style.display = 'none';
            document.getElementById('main').style.display = 'grid';
            document.getElementById('userMail').innerText = currentUser.email;
            refresh();
            setInterval(refresh, 5000);
        }

        function showTab(name) {
            ['feedTab', 'messagesTab', 'notifsTab', 'monetTab'].forEach(t => document.getElementById(t).style.display = 'none');
            document.getElementById(name + 'Tab').style.display = 'block';
            document.querySelectorAll('.menu-item').forEach(m => m.classList.remove('active'));
            event.currentTarget.classList.add('active');
        }

        async function postVibe() {
            const text = document.getElementById('postContent').value;
            await fetch('/api/posts', {
                method: 'POST', 
                headers: {'Content-Type': 'application/json'}, 
                body: JSON.stringify({email: currentUser.email, text})
            });
            document.getElementById('postContent').value = '';
            refresh();
        }

        async function react(postId, emoji) {
            await fetch('/api/react', {
                method: 'POST', 
                headers: {'Content-Type': 'application/json'}, 
                body: JSON.stringify({post_id: postId, emoji, email: currentUser.email})
            });
            refresh();
        }

        async function refresh() {
            lucide.createIcons();
            // Load Feed
            const pRes = await fetch('/api/posts');
            const posts = await pRes.json();
            document.getElementById('vibeList').innerHTML = posts.map(p => `
                <div class="card">
                    <div style="font-weight:bold; margin-bottom:8px;">${p.author_email}</div>
                    <div>${p.text}</div>
                    <div style="margin-top:15px; display:flex; gap:10px;">
                        <button class="btn" style="background:#21262d" onclick="react(${p.id}, '🔥')">🔥 ${p.reactions['🔥'] || 0}</button>
                        <button class="btn" style="background:#21262d" onclick="react(${p.id}, '💎')">💎 ${p.reactions['💎'] || 0}</button>
                    </div>
                </div>
            `).join('');

            // Load Monetization
            const mRes = await fetch('/api/monetization/' + currentUser.email);
            const mData = await mRes.json();
            document.getElementById('mHours').innerText = mData.watch_hours;
            document.getElementById('mCash').innerText = '$' + mData.earnings.toFixed(2);
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
    email = request.json['email']
    db = get_db(); cur = db.cursor()
    cur.execute("INSERT OR IGNORE INTO users (email, name) VALUES (?,?)", (email, email.split('@')[0]))
    db.commit()
    cur.execute("SELECT * FROM users WHERE email=?", (email,))
    return jsonify({"user": dict(cur.fetchone())})

@app.route("/api/posts", methods=["GET", "POST"])
def handle_posts():
    db = get_db(); cur = db.cursor()
    if request.method == "POST":
        cur.execute("INSERT INTO posts (author_email, text, timestamp) VALUES (?,?,?)", 
                    (request.json['email'], request.json['text'], datetime.datetime.now().isoformat()))
        db.commit()
        return jsonify({"ok": True})
    cur.execute("SELECT * FROM posts ORDER BY id DESC")
    rows = [dict(r) for r in cur.fetchall()]
    for r in rows: r['reactions'] = _json.loads(r['reactions_json'])
    return jsonify(rows)

@app.route("/api/react", methods=["POST"])
def api_react():
    data = request.json
    db = get_db(); cur = db.cursor()
    # 1. Update/Insert the specific user's choice (restricts to 1 reaction total per post)
    cur.execute("INSERT OR REPLACE INTO user_reactions (user_email, post_id, emoji) VALUES (?,?,?)", 
                (data['email'], data['post_id'], data['emoji']))
    # 2. Rebuild the reaction JSON for the post
    cur.execute("SELECT emoji, count(*) as count FROM user_reactions WHERE post_id=? GROUP BY emoji", (data['post_id'],))
    counts = {r['emoji']: r['count'] for r in cur.fetchall()}
    cur.execute("UPDATE posts SET reactions_json=? WHERE id=?", (_json.dumps(counts), data['post_id']))
    db.commit()
    return jsonify({"success": True})

@app.route("/api/monetization/<email>")
def get_monet(email):
    cur = get_db().cursor()
    cur.execute("SELECT watch_hours, earnings FROM users WHERE email=?", (email,))
    return jsonify(dict(cur.fetchone()))

if __name__ == "__main__":
    with app.app_context(): init_db()
    app.run(host="0.0.0.0", port=5000)
