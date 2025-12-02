import os
import uuid
import datetime
import json as _json
import threading
import time
import urllib.request
from flask import Flask, request, jsonify, render_template_string, session
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor
from supabase import create_client, Client

# ---------- Config ----------
app = Flask(__name__)
# Render will provide the PORT env var
app.config['PORT'] = int(os.environ.get("PORT", 5000))
app.secret_key = os.environ.get("SECRET_KEY", "vibenet-secret-key-dev")

# SUPABASE CREDENTIALS (These must be set in Render Environment Variables)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")

# Supabase Client for Storage
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL else None

# ---------- Database Helper (PostgreSQL) ----------
def get_db_connection():
    """Connects to the PostgreSQL database using the environment variable."""
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        # In a real app, you'd handle this more gracefully
        raise ConnectionError("Failed to connect to the database. Check DATABASE_URL.")

def now_ts():
    """Returns current timestamp string."""
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

def query_db(query, args=(), one=False):
    """Executes a database query, handles connection, commit, and close."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        # Execute query using %s placeholders (PostgreSQL standard)
        cur.execute(query, args)
        if query.strip().upper().startswith("SELECT"):
            rv = cur.fetchall()
            return (rv[0] if rv else None) if one else rv
        else:
            conn.commit()
            if "INSERT" in query.upper() and "RETURNING" in query.upper():
                return cur.fetchone()
    finally:
        conn.close()

# ---------- Keep Alive (Optional, for staying awake) ----------
def keep_alive_pinger():
    port = app.config['PORT']
    time.sleep(5)
    while True:
        try:
            # Pings the local server every 10 minutes
            urllib.request.urlopen(f"http://127.0.0.1:{port}/ping")
        except: pass
        time.sleep(600)

@app.route("/ping")
def ping(): return "Pong", 200

# ---------- Frontend (HTML/JS template unchanged for brevity) ----------
HTML = r"""
<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>VibeNet (Cloud Edition)</title>
<style>
:root{--bg:#07101a;--card:#0e1620;--accent:#00bfff;--danger:#ff4d4d;--muted:#9fb0c6}
*{box-sizing:border-box}
body{margin:0;background:linear-gradient(180deg,#041022,#07101a);font-family:Inter,Arial,sans-serif;color:#e6f7ff}
.container{max-width:1000px;margin:18px auto;padding:12px}
.header{display:flex;justify-content:space-between;align-items:center}
.brand h1{margin:0;color:var(--accent)}
.controls{display:flex;gap:8px;align-items:center}
.card{background:var(--card);padding:12px;border-radius:10px;box-shadow:0 8px 30px rgba(0,0,0,.6)}
.input,textarea{width:100%;padding:10px;margin-top:8px;border-radius:8px;border:0;background:#081221;color:#fff}
.btn{background:var(--accent);border:0;padding:8px 12px;border-radius:8px;color:#001;cursor:pointer;font-weight:bold}
.btn-danger{background:var(--danger);color:#fff}
.nav{display:flex;gap:8px;margin-top:12px;overflow-x:auto}
.nav button{flex:1;padding:10px;border-radius:8px;border:0;background:#081827;color:#fff;cursor:pointer;white-space:nowrap}
.nav button.active{background:linear-gradient(90deg,#0aa,#06d);color:#001}
.row{display:flex;gap:12px;align-items:flex-start}
.col{flex:1}
.sidebar{width:300px}
@media(max-width:700px){.row{flex-direction:column}.sidebar{width:100%}}
.post{background:#061221;padding:12px;border-radius:10px;margin-bottom:12px;position:relative}
.post-header{display:flex;justify-content:space-between;align-items:center}
.post-meta{display:flex;gap:10px;align-items:center}
.profile-pic{width:48px;height:48px;border-radius:50%;object-fit:cover;background:#0b1220}
.timestamp{font-size:12px;color:var(--muted)}
.reaction-bar{display:flex;gap:8px;margin-top:8px}
.reaction-button{background:#081827;border:0;padding:6px 10px;border-radius:8px;color:#fff;cursor:pointer}
.reaction-button.active{background:var(--accent);color:#001}
.follow-btn{background:#102430;border:0;padding:6px 10px;border-radius:8px;color:#fff;cursor:pointer}
.delete-btn{background:transparent;border:0;color:var(--danger);cursor:pointer;font-size:18px;margin-left:8px}
.small{font-size:13px;color:var(--muted)}
.video{width:100%;border-radius:8px;background:#000;margin-top:8px}
.badge{background:#ff6b6b;color:#fff;padding:2px 8px;border-radius:999px}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div class="brand">
      <h1>VibeNet</h1>
      <div class="small">Cloud Edition</div>
    </div>
    <div class="controls" id="topControls"></div>
  </div>
  <div id="authCard" class="card">
    <h3>Join or Login</h3>
    <div style="display:flex;gap:12px;flex-wrap:wrap">
      <div style="flex:1;min-width:280px">
        <input id="signupName" class="input" placeholder="Full name" />
        <input id="signupEmail" class="input" placeholder="Email" />
        <input id="signupPassword" class="input" type="password" placeholder="Password" />
        <label class="small">Profile picture</label>
        <input id="signupPic" type="file" accept="image/*" class="input" />
        <button class="btn" onclick="signup()">Sign up</button>
      </div>
      <div style="flex:1;min-width:280px">
        <h4>Login</h4>
        <input id="loginEmail" class="input" placeholder="Email" />
        <input id="loginPassword" class="input" type="password" placeholder="Password" />
        <button class="btn" onclick="login()">Login</button>
      </div>
    </div>
  </div>
  <div id="app" style="display:none" class="card">
    <div class="row">
      <div class="col">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <div><h2 style="margin:0">Feed</h2></div>
          <button class="btn" onclick="logout()">Logout</button>
        </div>
        <div class="nav">
          <button id="navFeed" class="active" onclick="showTab('feed')">🏠 Feed</button>
          <button id="navMessages" onclick="showTab('messages')">📁 Messages</button>
          <button id="navNotifs" onclick="showTab('notifications')">🔔 <span id="notifCount" class="badge" style="display:none"></span></button>
          <button id="navMonet" onclick="showTab('monet')">💲 Earn</button>
          <button id="navProfile" onclick="showTab('profile')">👤 Profile</button>
        </div>
        <div id="feed" class="tab">
          <div style="display:flex;gap:12px;align-items:flex-start;margin-top:12px">
            <textarea id="postText" class="input" rows="2" placeholder="What's happening?"></textarea>
            <div style="min-width:100px">
              <input id="fileUpload" type="file" accept="image/*,video/*" class="input" style="width:100px" />
              <button class="btn" onclick="addPost()">Post</button>
            </div>
          </div>
          <div id="feedList" style="margin-top:12px"></div>
        </div>
        <div id="messages" class="tab" style="display:none">
          <input id="msgTo" class="input" placeholder="Send to (email)" />
          <textarea id="msgText" class="input" rows="3" placeholder="Type message..."></textarea>
          <button class="btn" onclick="sendMessage()">Send</button>
          <h4 style="margin-top:12px">Inbox</h4>
          <div id="msgList"></div>
        </div>
        <div id="notifications" class="tab" style="display:none">
          <h4>Notifications</h4>
          <div id="notifList"></div>
        </div>
        <div id="monet" class="tab" style="display:none">
          <h4>Stats & Ads</h4>
          <p>Followers: <strong id="monFollowers">0</strong></p>
          <p>Earnings: <strong id="monEarnings">0.00</strong></p>
          <hr />
          <h4>Create Ad</h4>
          <input id="adTitle" class="input" placeholder="Ad title" />
          <input id="adBudget" class="input" placeholder="Budget" />
          <button class="btn" onclick="createAd()">Create</button>
          <div id="adsList" style="margin-top:8px"></div>
        </div>
        <div id="profile" class="tab" style="display:none">
          <h4>Profile</h4>
          <textarea id="profileBio" class="input" rows="3" placeholder="Update bio"></textarea>
          <button class="btn" onclick="updateBio()">Save bio</button>
          <h4 style="margin-top:12px">My posts</h4>
          <div id="profilePosts"></div>
        </div>
      </div>
      <div class="sidebar">
        <div class="card" style="padding:10px;margin-bottom:12px">
          <h4 style="margin:0">Stats</h4>
          <div class="small">Followers: <span id="sideFollowers">0</span></div>
          <div class="small">Earnings: <span id="sideEarnings">0</span></div>
        </div>
      </div>
    </div>
  </div>
</div>
<script>
const API = '/api'; let currentUser = null;
function byId(id){ return document.getElementById(id); }
function escapeHtml(s){ if(!s) return ''; return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]); }
async function checkSession(){
  try { const j = await (await fetch(API+'/me')).json(); if(j.user){ currentUser = j.user; onLogin(); } } catch(e){}
}
async function signup(){
  const name = byId('signupName').value.trim(), email = byId('signupEmail').value.trim().toLowerCase(), pass = byId('signupPassword').value;
  if(!name||!email||!pass){ alert('Fill all'); return; }
  const fd = new FormData(); fd.append('name', name); fd.append('email', email); fd.append('password', pass);
  if(byId('signupPic').files[0]) fd.append('file', byId('signupPic').files[0]);
  const j = await (await fetch(API+'/signup', { method:'POST', body: fd })).json();
  if(j.user){ currentUser = j.user; onLogin(); } else alert(j.error);
}
async function login(){
  const email = byId('loginEmail').value.trim().toLowerCase(), password = byId('loginPassword').value;
  const j = await (await fetch(API+'/login', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({email, password})})).json();
  if(j.user){ currentUser = j.user; onLogin(); } else alert(j.error);
}
async function logout(){ await fetch(API+'/logout', {method:'POST'}); currentUser=null; byId('app').style.display='none'; byId('authCard').style.display='block'; if(window._vn_poll) clearInterval(window._vn_poll); }
function onLogin(){ byId('authCard').style.display='none'; byId('app').style.display='block'; refreshAll(); window._vn_poll = setInterval(()=>{ if(currentUser){ loadNotifications(); loadMonetization(); } }, 4000); }
function showTab(tab){
  ['feed','messages','notifications','monet','profile'].forEach(t => byId(t).style.display = 'none');
  document.querySelectorAll('.nav button').forEach(b => b.classList.remove('active'));
  byId(tab).style.display = 'block';
  if(tab==='feed') byId('navFeed').classList.add('active'); if(tab==='messages') byId('navMessages').classList.add('active');
  if(tab==='notifications') byId('navNotifs').classList.add('active'); if(tab==='monet') byId('navMonet').classList.add('active');
  if(tab==='profile') byId('navProfile').classList.add('active');
}
async function uploadFile(f){ const fd = new FormData(); fd.append('file',f); return (await (await fetch(API+'/upload',{method:'POST',body:fd})).json()).url||''; }
async function addPost(){
  const text = byId('postText').value.trim(), fileEl = byId('fileUpload'); let url = '';
  if(fileEl.files[0]) url = await uploadFile(fileEl.files[0]);
  if(!text && !url) return;
  await fetch(API+'/posts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({author_email:currentUser.email,author_name:currentUser.name,profile_pic:currentUser.profile_pic||'',text,file_url:url})});
  byId('postText').value=''; fileEl.value=''; await loadFeed(); await loadProfilePosts();
}
async function deletePost(id){ if(confirm('Delete?')) { await fetch(API+'/posts/'+id,{method:'DELETE'}); refreshAll(); } }
function createPostElement(p){
  const div = document.createElement('div'); div.className='post';
  div.innerHTML = `<div class="post-header"><div class="post-meta"><img class="profile-pic" src="${p.profile_pic||'#null'}" onerror="this.src='https://placehold.co/48x48/000000/FFFFFF?text=P'"><div><strong>${escapeHtml(p.author_name)}</strong><div class="timestamp">${escapeHtml(p.timestamp)}</div></div></div></div>`;
  const btnGroup = document.createElement('div');
  if(currentUser && currentUser.email!==p.author_email){
    const fb = document.createElement('button'); fb.className='follow-btn'; fb.textContent='Follow';
    fb.onclick = async ()=>{ await fetch(API+'/follow',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({follower_email:currentUser.email,target_email:p.author_email})}); loadMonetization(); };
    btnGroup.append(fb);
  }
  if(currentUser && currentUser.email===p.author_email){
      const db = document.createElement('button'); db.className='delete-btn'; db.textContent='🗑️'; db.onclick = ()=>deletePost(p.id); btnGroup.append(db);
  }
  div.querySelector('.post-header').append(btnGroup);
  if(p.text) div.innerHTML+=`<div style="margin-top:8px">${escapeHtml(p.text)}</div>`;
  if(p.file_url){
    if(p.file_url.endsWith('.mp4')||p.file_url.endsWith('.webm')) div.innerHTML+=`<video src="${p.file_url}" controls class="video"></video>`;
    else div.innerHTML+=`<img src="${p.file_url}" style="max-width:100%;margin-top:8px">`;
  }
  const bar = document.createElement('div'); bar.className='reaction-bar';
  ['👍','❤️','😂'].forEach(em=>{
    const btn=document.createElement('button'); btn.className='reaction-button'; if(p.user_reaction===em) btn.classList.add('active');
    btn.textContent=`${em} ${p.reactions&&p.reactions[em]?p.reactions[em]:0}`;
    btn.onclick = async ()=>{ if(!currentUser)return; await fetch(API+'/react',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({post_id:p.id,emoji:em})}); loadFeed(); };
    bar.append(btn);
  });
  div.append(bar); return div;
}
async function loadFeed(){ const l = await (await fetch(API+'/posts')).json(); byId('feedList').innerHTML=''; l.forEach(p=>byId('feedList').append(createPostElement(p))); }
async function sendMessage(){ const to=byId('msgTo').value, text=byId('msgText').value; if(to&&text){ await fetch(API+'/messages',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({from:currentUser.email,to,text})}); byId('msgText').value=''; loadMessages(); } }
async function loadMessages(){ const l = await (await fetch(API+'/messages/'+encodeURIComponent(currentUser.email))).json(); byId('msgList').innerHTML=''; l.forEach(m=>byId('msgList').innerHTML+=`<div class="post"><strong>${escapeHtml(m.sender)}</strong>: ${escapeHtml(m.text)}</div>`); }
async function loadNotifications(){ const l = await (await fetch(API+'/notifications/'+encodeURIComponent(currentUser.email))).json(); byId('notifList').innerHTML=''; byId('notifCount').style.display=l.length?'inline-block':'none'; byId('notifCount').textContent=l.length; l.forEach(n=>byId('notifList').innerHTML+=`<div class="post">${escapeHtml(n.text)}</div>`); }
async function loadProfilePosts(){ const j = await (await fetch(API+'/profile/'+encodeURIComponent(currentUser.email))).json(); byId('profileBio').value=j.bio||''; byId('profilePosts').innerHTML=''; (j.posts||[]).forEach(p=>byId('profilePosts').append(createPostElement(p))); }
async function updateBio(){ await fetch(API+'/update_bio',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:currentUser.email,bio:byId('profileBio').value})}); alert('Saved'); }
async function loadMonetization(){ const j = await (await fetch(API+'/monetization/'+encodeURIComponent(currentUser.email))).json(); byId('monFollowers').textContent=j.followers; byId('sideFollowers').textContent=j.followers; byId('monEarnings').textContent=(j.earnings||0).toFixed(2); byId('sideEarnings').textContent=(j.earnings||0).toFixed(2); }
async function createAd(){ await fetch(API+'/ads',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:byId('adTitle').value,budget:parseFloat(byId('adBudget').value),owner:currentUser.email})}); loadAds(); }
async function loadAds(){ const l = await (await fetch(API+'/ads')).json(); byId('adsList').innerHTML=''; l.forEach(a=>byId('adsList').innerHTML+=`<div class="small">${a.title} ($${a.budget})</div>`); }
async function refreshAll(){ await loadFeed(); await loadMessages(); await loadNotifications(); await loadProfilePosts(); await loadMonetization(); await loadAds(); }
checkSession();
</script>
</body>
</html>
"""

@app.route("/")
def index(): return render_template_string(HTML)

# ---------- API Endpoints ----------

@app.route("/api/upload", methods=["POST"])
def api_upload():
    """Uploads a file to Supabase Storage and returns the public URL."""
    if 'file' not in request.files: return jsonify({"error":"No file"}), 400
    f = request.files['file']
    fn = f"{uuid.uuid4().hex}_{f.filename}"
    file_bytes = f.read()
    
    try:
        # Upload to Supabase Storage bucket 'uploads'
        supabase.storage.from_("uploads").upload(fn, file_bytes, {"content-type": f.content_type})
        # Get Public URL for client to view
        url = supabase.storage.from_("uploads").get_public_url(fn)
        return jsonify({"url": url})
    except Exception as e:
        print(f"Supabase upload error: {e}")
        return jsonify({"error": f"Upload failed: {e}"}), 500

@app.route("/api/signup", methods=["POST"])
def api_signup():
    """Handles user sign-up and uploads profile pic to Supabase Storage."""
    name=request.form.get("name")
    email=request.form.get("email","").strip().lower()
    password=request.form.get("password")
    profile_pic=""
    
    if 'file' in request.files:
        f = request.files['file']
        fn = f"{uuid.uuid4().hex}_{f.filename}"
        supabase.storage.from_("uploads").upload(fn, f.read(), {"content-type": f.content_type})
        profile_pic = supabase.storage.from_("uploads").get_public_url(fn)

    hashed = generate_password_hash(password)
    try:
        # Use %s placeholders for Postgres
        query_db("INSERT INTO users (name, email, password, profile_pic) VALUES (%s, %s, %s, %s)", (name, email, hashed, profile_pic))
        session['user_email'] = email
        return jsonify({"user": {"name":name, "email":email, "profile_pic":profile_pic, "bio":"", "watch_hours":0, "earnings":0}})
    except Exception as e:
        return jsonify({"error": "Email taken or database error"}), 400

@app.route("/api/login", methods=["POST"])
def api_login():
    """Authenticates user against the Supabase database."""
    d = request.get_json()
    email = d.get("email","").strip().lower()
    # Use %s placeholders for Postgres
    user = query_db("SELECT * FROM users WHERE email=%s", (email,), one=True)
    if user and check_password_hash(user['password'], d.get("password")):
        u = dict(user)
        del u['password']
        session['user_email'] = email
        return jsonify({"user": u})
    return jsonify({"error": "Invalid credentials"}), 401

@app.route("/api/logout", methods=["POST"])
def api_logout(): session.clear(); return jsonify({"success":True})

@app.route("/api/me")
def api_me():
    email = session.get("user_email")
    if not email: return jsonify({"user":None})
    user = query_db("SELECT name, email, profile_pic, bio, watch_hours, earnings FROM users WHERE email=%s", (email,), one=True)
    if not user: session.clear(); return jsonify({"user":None})
    return jsonify({"user": dict(user)})

@app.route("/api/posts", methods=["GET","POST"])
def api_posts():
    if request.method=="GET":
        posts = query_db("SELECT * FROM posts ORDER BY id DESC")
        out = []
        for p in posts:
            rec = dict(p)
            rec['reactions'] = _json.loads(rec.get('reactions_json') or '{}')
            rec['user_reaction'] = None
            if 'user_email' in session:
                ur = query_db("SELECT emoji FROM user_reactions WHERE user_email=%s AND post_id=%s", (session['user_email'], rec['id']), one=True)
                if ur: rec['user_reaction'] = ur['emoji']
            out.append(rec)
        return jsonify(out)
    else:
        d=request.get_json()
        query_db("INSERT INTO posts (author_email, author_name, profile_pic, text, file_url, timestamp) VALUES (%s, %s, %s, %s, %s, %s)",
                 (d.get('author_email'), d.get('author_name'), d.get('profile_pic'), d.get('text'), d.get('file_url'), now_ts()))
        return jsonify({"success":True})

@app.route("/api/posts/<int:id>", methods=["DELETE"])
def api_delete_post(id):
    post = query_db("SELECT author_email FROM posts WHERE id=%s", (id,), one=True)
    if post and post['author_email'] == session.get('user_email'):
        query_db("DELETE FROM posts WHERE id=%s", (id,))
        return jsonify({"success":True})
    return jsonify({"error":"Forbidden"}), 403

@app.route("/api/react", methods=["POST"])
def api_react():
    d=request.get_json(); pid=d.get("post_id"); em=d.get("emoji"); email=session.get("user_email")
    if not email: return jsonify({"error":"Login"}), 401
    
    post = query_db("SELECT reactions_json FROM posts WHERE id=%s", (pid,), one=True)
    if not post: return jsonify({"error":"404"}), 404
    
    reacts = _json.loads(post['reactions_json'] or '{}')
    prev = query_db("SELECT emoji FROM user_reactions WHERE user_email=%s AND post_id=%s", (email, pid), one=True)
    
    if prev and prev['emoji']:
        reacts[prev['emoji']] = max(0, reacts.get(prev['emoji'], 0) - 1)
        query_db("DELETE FROM user_reactions WHERE user_email=%s AND post_id=%s", (email, pid))
    
    if not prev or prev['emoji'] != em:
        query_db("INSERT INTO user_reactions (user_email, post_id, emoji) VALUES (%s, %s, %s)", (email, pid, em))
        reacts[em] = reacts.get(em, 0) + 1
        
    query_db("UPDATE posts SET reactions_json=%s WHERE id=%s", (_json.dumps(reacts), pid))
    return jsonify({"success":True})

@app.route("/api/follow", methods=["POST"])
def api_follow():
    d=request.get_json()
    exists = query_db("SELECT id FROM followers WHERE user_email=%s AND follower_email=%s", (d.get("target_email"), d.get("follower_email")), one=True)
    if not exists:
        query_db("INSERT INTO followers (user_email, follower_email) VALUES (%s, %s)", (d.get("target_email"), d.get("follower_email")))
    return jsonify({"success":True})

@app.route("/api/messages", methods=["GET","POST"])
def api_msg():
    if request.method=="POST":
        d=request.get_json()
        query_db("INSERT INTO messages (sender, recipient, text, timestamp) VALUES (%s, %s, %s, %s)", (d.get("from"), d.get("to"), d.get("text"), now_ts()))
        return jsonify({"success":True})
    msgs = query_db("SELECT * FROM messages WHERE recipient=%s OR sender=%s ORDER BY id DESC LIMIT 50", (session.get('user_email'), session.get('user_email')))
    return jsonify([dict(m) for m in msgs])

@app.route("/api/notifications/<path:e>")
def api_n(e):
    nots = query_db("SELECT * FROM notifications WHERE user_email=%s ORDER BY id DESC LIMIT 20", (e,))
    return jsonify([dict(n) for n in nots])

@app.route("/api/profile/<path:e>")
def api_p(e):
    u = query_db("SELECT bio FROM users WHERE email=%s", (e,), one=True)
    p = query_db("SELECT * FROM posts WHERE author_email=%s ORDER BY id DESC", (e,))
    return jsonify({"bio": u['bio'] if u else "", "posts": [dict(r) for r in p]})

@app.route("/api/update_bio", methods=["POST"])
def api_ub():
    d=request.get_json()
    query_db("UPDATE users SET bio=%s WHERE email=%s", (d.get("bio"), d.get("email")))
    return jsonify({"success":True})

@app.route("/api/monetization/<path:e>")
def api_mon(e):
    # COUNT(*) returns a long integer, which RealDictCursor handles fine.
    f = query_db("SELECT COUNT(*) as c FROM followers WHERE user_email=%s", (e,), one=True)['c']
    u = query_db("SELECT watch_hours, earnings FROM users WHERE email=%s", (e,), one=True)
    return jsonify({"followers": f, "watch_hours": u['watch_hours'] if u else 0, "earnings": u['earnings'] if u else 0})

@app.route("/api/ads", methods=["GET","POST"])
def api_a():
    if request.method=="POST":
        d=request.get_json()
        query_db("INSERT INTO ads (title, owner_email, budget) VALUES (%s, %s, %s)", (d.get("title"), d.get("owner"), d.get("budget")))
        return jsonify({"success":True})
    ads = query_db("SELECT * FROM ads ORDER BY id DESC")
    return jsonify([dict(a) for a in ads])


if __name__ == "__main__":
    # Start the keep-alive thread
    threading.Thread(target=keep_alive_pinger, daemon=True).start()
    app.run(host="0.0.0.0", port=app.config['PORT'], debug=True)
