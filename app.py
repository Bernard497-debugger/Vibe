# app.py - VibeNet (SQLite + Frontend + Video support + Auto-pause + Icons)
import os
import sqlite3
import uuid
import datetime
from flask import Flask, request, jsonify, send_from_directory, g, render_template_string

# ---------- Config ----------
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_DIR, "data")
UPLOAD_DIR = os.path.join(APP_DIR, "uploads")
DB_PATH = os.path.join(DATA_DIR, "vibenet.db")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__, static_folder=None)
app.config['MAX_CONTENT_LENGTH'] = 300 * 1024 * 1024  # 300 MB uploads
app.config['PORT'] = int(os.environ.get("PORT", 5000))

# ---------- Database helpers ----------
def get_db():
    db = getattr(g, "_db", None)
    if db is None:
        db = g._db = sqlite3.connect(DB_PATH, check_same_thread=False)
        db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    cur = db.cursor()
    # Users
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        profile_pic TEXT,
        bio TEXT DEFAULT '',
        watch_hours INTEGER DEFAULT 0,
        earnings REAL DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    # Followers join table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS followers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email TEXT,
        follower_email TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    # Posts
    cur.execute("""
    CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        author_email TEXT,
        author_name TEXT,
        profile_pic TEXT,
        text TEXT,
        file_url TEXT,
        timestamp TEXT,
        reactions_json TEXT DEFAULT '{}',
        comments_count INTEGER DEFAULT 0
    )""")
    # user_reactions: one row per (user, post)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_reactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email TEXT,
        post_id INTEGER,
        emoji TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_email, post_id)
    )""")
    # Messages
    cur.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender TEXT,
        recipient TEXT,
        text TEXT,
        timestamp TEXT
    )""")
    # Notifications
    cur.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email TEXT,
        text TEXT,
        timestamp TEXT,
        seen INTEGER DEFAULT 0
    )""")
    # Ads
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
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

# ---------- Utilities ----------
def now_ts():
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

def row_to_dict(r):
    if r is None: return None
    return dict(r)

# ---------- Init DB ----------
with app.app_context():
    init_db()

# ---------- Static uploads ----------
@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)

# ---------- Frontend (single template) ----------
HTML = r"""
<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>VibeNet — Local Demo</title>
<style>
:root{--bg:#07101a;--card:#0e1620;--accent:#00bfff;--muted:#9fb0c6}
*{box-sizing:border-box}
body{margin:0;background:linear-gradient(180deg,#041022,#07101a);font-family:Inter,Arial,sans-serif;color:#e6f7ff}
.container{max-width:1000px;margin:18px auto;padding:12px}
.header{display:flex;justify-content:space-between;align-items:center}
.brand{display:flex;gap:10px;align-items:center}
.brand h1{margin:0;color:var(--accent)}
.controls{display:flex;gap:8px;align-items:center}
.card{background:var(--card);padding:12px;border-radius:10px;box-shadow:0 8px 30px rgba(0,0,0,.6)}
.input,textarea{width:100%;padding:10px;margin-top:8px;border-radius:8px;border:0;background:#081221;color:#fff}
.btn{background:var(--accent);border:0;padding:8px 12px;border-radius:8px;color:#001;cursor:pointer}
.nav{display:flex;gap:8px;margin-top:12px}
.nav button{flex:1;padding:10px;border-radius:8px;border:0;background:#081827;color:#fff;cursor:pointer}
.nav button.active{background:linear-gradient(90deg,#0aa,#06d);color:#001}
.row{display:flex;gap:12px;align-items:flex-start}
.col{flex:1}
.sidebar{width:300px}
.post{background:#061221;padding:12px;border-radius:10px;margin-bottom:12px}
.post-header{display:flex;justify-content:space-between;align-items:center}
.post-meta{display:flex;gap:10px;align-items:center}
.profile-pic{width:48px;height:48px;border-radius:50%;object-fit:cover;background:#0b1220}
.timestamp{font-size:12px;color:var(--muted)}
.reaction-bar{display:flex;gap:8px;margin-top:8px}
.reaction-button{background:#081827;border:0;padding:6px 10px;border-radius:8px;color:#fff;cursor:pointer}
.reaction-button.active{background:var(--accent);color:#001}
.follow-btn{background:#102430;border:0;padding:6px 10px;border-radius:8px;color:#fff;cursor:pointer}
.small{font-size:13px;color:var(--muted)}
.video{width:100%;border-radius:8px;background:#000;margin-top:8px}
.icon{font-size:18px;margin-right:6px}
.badge{background:#ff6b6b;color:#fff;padding:2px 8px;border-radius:999px}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div class="brand">
      <h1>VibeNet</h1>
      <div class="small">Local demo</div>
    </div>
    <div class="controls" id="topControls">
      <!-- icons inserted after login -->
    </div>
  </div>

  <!-- AUTH -->
  <div id="authCard" class="card">
    <h3>Join or Login</h3>
    <div style="display:flex;gap:12px">
      <div style="flex:1">
        <input id="signupName" class="input" placeholder="Full name" />
        <input id="signupEmail" class="input" placeholder="Email" />
        <input id="signupPassword" class="input" type="password" placeholder="Password" />
        <label class="small">Profile picture (optional)</label>
        <input id="signupPic" type="file" accept="image/*" class="input" />
        <button class="btn" onclick="signup()">Sign up</button>
      </div>
      <div style="flex:1">
        <h4>Login</h4>
        <input id="loginEmail" class="input" placeholder="Email" />
        <input id="loginPassword" class="input" type="password" placeholder="Password" />
        <button class="btn" onclick="login()">Login</button>
      </div>
    </div>
  </div>

  <!-- APP -->
  <div id="app" style="display:none" class="card">
    <div class="row">
      <div class="col">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <div>
            <h2 style="margin:0">Feed</h2>
            <div class="small">Share videos & images — watch to earn</div>
          </div>
          <div>
            <button class="btn" onclick="logout()">Logout</button>
          </div>
        </div>

        <div class="nav">
          <button id="navFeed" class="active" onclick="showTab('feed')">🏠 Feed</button>
          <button id="navMessages" onclick="showTab('messages')">📁 Messages</button>
          <button id="navNotifs" onclick="showTab('notifications')">🔔 Notifications <span id="notifCount" class="badge" style="display:none"></span></button>
          <button id="navMonet" onclick="showTab('monet')">💲 Monetization</button>
          <button id="navProfile" onclick="showTab('profile')">👤 Profile</button>
        </div>

        <!-- FEED -->
        <div id="feed" class="tab">
          <div style="display:flex;gap:12px;align-items:flex-start">
            <textarea id="postText" class="input" rows="2" placeholder="What's on your mind?"></textarea>
            <div style="min-width:220px">
              <input id="fileUpload" type="file" accept="image/*,video/*" class="input" />
              <button class="btn" onclick="addPost()">Post</button>
            </div>
          </div>
          <div id="feedList" style="margin-top:12px"></div>
        </div>

        <!-- MESSAGES -->
        <div id="messages" class="tab" style="display:none">
          <input id="msgTo" class="input" placeholder="Send to (email)" />
          <textarea id="msgText" class="input" rows="3" placeholder="Type message..."></textarea>
          <button class="btn" onclick="sendMessage()">Send</button>
          <h4 style="margin-top:12px">Inbox</h4>
          <div id="msgList"></div>
        </div>

        <!-- NOTIFICATIONS -->
        <div id="notifications" class="tab" style="display:none">
          <h4>Notifications</h4>
          <div id="notifList"></div>
        </div>

        <!-- MONETIZATION -->
        <div id="monet" class="tab" style="display:none">
          <h4>Monetization Dashboard</h4>
          <p>Followers: <strong id="monFollowers">0</strong></p>
          <p>Watch Hours: <strong id="monWatch">0</strong></p>
          <p>Status: <strong id="monStatus">Not Eligible</strong></p>
          <p>Earnings: <strong id="monEarnings">0.00</strong> credits</p>
          <hr />
          <h4>Ad Placement</h4>
          <input id="adTitle" class="input" placeholder="Ad title" />
          <input id="adBudget" class="input" placeholder="Budget (credits)" />
          <button class="btn" onclick="createAd()">Create Ad</button>
          <div id="adsList" style="margin-top:8px"></div>
        </div>

        <!-- PROFILE -->
        <div id="profile" class="tab" style="display:none">
          <h4>Profile</h4>
          <textarea id="profileBio" class="input" rows="3" placeholder="Update your bio"></textarea>
          <button class="btn" onclick="updateBio()">Save bio</button>
          <h4 style="margin-top:12px">My posts</h4>
          <div id="profilePosts"></div>
        </div>

      </div>

      <div class="sidebar">
        <div class="card" style="padding:10px;margin-bottom:12px">
          <h4 style="margin:0">Quick Monetization</h4>
          <div class="small">Followers: <span id="sideFollowers">0</span></div>
          <div class="small">Watch Hours: <span id="sideWatch">0</span></div>
          <div class="small">Earnings: <span id="sideEarnings">0</span></div>
        </div>

        <div class="card" style="padding:10px">
          <h4 style="margin:0">Shortcuts</h4>
          <div style="display:flex;flex-direction:column;gap:8px;margin-top:8px">
            <button class="btn" onclick="showTab('monet')">Open Monetization</button>
            <button class="btn" onclick="showTab('profile')">Open Profile</button>
          </div>
        </div>
      </div>

    </div>
  </div>

</div>

<script>
const API = '/api';
let currentUser = null;

// Helpers
function byId(id){ return document.getElementById(id); }
function escapeHtml(s){ if(!s) return ''; return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]); }

// Auth
async function signup(){
  const name = byId('signupName').value.trim();
  const email = byId('signupEmail').value.trim().toLowerCase();
  const password = byId('signupPassword').value;
  if(!name||!email||!password){ alert('Fill all fields'); return; }
  const pic = byId('signupPic').files[0];
  const fd = new FormData();
  fd.append('name', name); fd.append('email', email); fd.append('password', password);
  if(pic) fd.append('file', pic);
  const res = await fetch(API + '/signup', { method:'POST', body: fd });
  const j = await res.json();
  if(j.user){ alert('Signup ok, logged in'); currentUser = j.user; onLogin(); } else { alert(j.error || j.message); }
}

async function login(){
  const email = byId('loginEmail').value.trim().toLowerCase();
  const password = byId('loginPassword').value;
  if(!email||!password){ alert('Fill login'); return; }
  const res = await fetch(API + '/login', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ email, password })});
  const j = await res.json();
  if(j.user){ currentUser = j.user; onLogin(); } else alert(j.error || 'Invalid credentials');
}

function logout(){
  currentUser = null;
  byId('app').style.display = 'none';
  byId('authCard').style.display = 'block';
  byId('topControls').innerHTML = '';
  if(window._vn_poll) clearInterval(window._vn_poll);
}

// After login UI adjustments
function onLogin(){
  byId('authCard').style.display = 'none';
  byId('app').style.display = 'block';
  // top controls: notifications, messages, monet
  const top = byId('topControls'); top.innerHTML = '';
  const not = document.createElement('button'); not.className='btn'; not.innerHTML='🔔'; not.onclick = ()=> showTab('notifications');
  const msg = document.createElement('button'); msg.className='btn'; msg.innerHTML='📁'; msg.onclick = ()=> showTab('messages');
  const money = document.createElement('button'); money.className='btn'; money.innerHTML='💲'; money.onclick = ()=> showTab('monet');
  top.append(not,msg,money);
  refreshAll();
  window._vn_poll = setInterval(()=>{ if(currentUser){ loadNotifications(); loadMonetization(); } }, 4000);
}

// Tabs
function showTab(tab){
  ['feed','messages','notifications','monet','profile'].forEach(t => byId(t).style.display = 'none');
  document.querySelectorAll('.nav button').forEach(b => b.classList.remove('active'));
  byId(tab).style.display = 'block';
  Array.from(document.querySelectorAll('.nav button')).find(b=>b.onclick && b.textContent.toLowerCase().includes(tab[0]))?.classList.add('active');
  // better: just set active by id mapping
  if(tab === 'feed'){ byId('navFeed').classList.add('active'); }
  if(tab === 'messages'){ byId('navMessages').classList.add('active'); }
  if(tab === 'notifications'){ byId('navNotifs').classList.add('active'); }
  if(tab === 'monet'){ byId('navMonet').classList.add('active'); }
  if(tab === 'profile'){ byId('navProfile').classList.add('active'); }
}

// Upload helper
async function uploadFile(file){
  const fd = new FormData(); fd.append('file', file);
  const res = await fetch(API + '/upload', { method:'POST', body: fd });
  const j = await res.json();
  return j.url || '';
}

// POSTS
async function addPost(){
  if(!currentUser){ alert('Login first'); return; }
  const text = byId('postText').value.trim();
  const fileEl = byId('fileUpload');
  let url = '';
  if(fileEl.files[0]) url = await uploadFile(fileEl.files[0]);
  if(!text && !url) return;
  const res = await fetch(API + '/posts', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({
    author_email: currentUser.email, author_name: currentUser.name, profile_pic: currentUser.profile_pic||'', text, file_url: url
  })});
  const j = await res.json();
  byId('postText').value=''; fileEl.value='';
  await loadFeed(); await loadProfilePosts(); await loadMonetization();
}

// Create post element
function createPostElement(p){
  const div = document.createElement('div'); div.className='post';
  const header = document.createElement('div'); header.className='post-header';
  const meta = document.createElement('div'); meta.className='post-meta';
  const img = document.createElement('img'); img.className='profile-pic'; img.src = p.profile_pic || '/uploads/default.png';
  img.onerror = ()=> img.src = '/uploads/default.png';
  const info = document.createElement('div'); info.innerHTML = `<strong>${escapeHtml(p.author_name || 'Unknown')}</strong><div class="timestamp">${escapeHtml(p.timestamp)}</div>`;
  meta.append(img, info);
  header.append(meta);

  // follow button (if not self)
  if(currentUser && currentUser.email !== p.author_email){
    const fb = document.createElement('button'); fb.className='follow-btn'; fb.textContent='Follow';
    fb.onclick = async ()=>{
      const res = await fetch(API + '/follow', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ follower_email: currentUser.email, target_email: p.author_email })});
      const j = await res.json();
      if(j.success){ fb.classList.toggle('active'); fb.textContent = (fb.classList.contains('active') ? 'Following' : 'Follow'); loadMonetization(); loadSideMonet(); }
    };
    // check follow status
    (async ()=>{
      const r = await fetch(API + `/is_following?f=${encodeURIComponent(currentUser.email)}&t=${encodeURIComponent(p.author_email)}`);
      const jj = await r.json();
      if(jj.following){ fb.classList.add('active'); fb.textContent='Following'; }
    })();
    header.append(fb);
  }

  div.append(header);

  if(p.text){ const t=document.createElement('div'); t.style.marginTop='8px'; t.textContent = p.text; div.append(t); }

  if(p.file_url){
    if(p.file_url.endsWith('.mp4') || p.file_url.endsWith('.webm')){
      const v = document.createElement('video'); v.src = p.file_url; v.controls = true; v.className='video';
      v.dataset.postId = p.id;
      // when ended, call watch
      v.addEventListener('ended', async ()=>{
        await fetch(API + '/watch', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ viewer: currentUser ? currentUser.email : '', post_id: p.id })});
        await fetch(API + '/ads/impression', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ post_id: p.id, viewer: currentUser ? currentUser.email : '' })});
        loadMonetization(); loadSideMonet();
      });
      div.append(v);
    } else {
      const im = document.createElement('img'); im.src = p.file_url; im.style.maxWidth='100%'; div.append(im);
    }
  }

  // reactions
  const bar = document.createElement('div'); bar.className='reaction-bar';
  ['👍','❤️','😂'].forEach(em=>{
    const btn = document.createElement('button'); btn.className='reaction-button'; btn.dataset.emoji = em; btn.textContent = `${em} ${p.reactions && p.reactions[em] ? p.reactions[em] : 0}`;
    if(p.user_reaction && currentUser && p.user_reaction === em) btn.classList.add('active');
    btn.onclick = async (ev) => {
      ev.stopPropagation();
      if(!currentUser){ alert('Login to react'); return; }
      const res = await fetch(API + '/react', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ post_id: p.id, emoji: em, user_email: currentUser.email })});
      const j = await res.json();
      if(j.success){
        // update counts for this post only
        const postEl = div;
        Array.from(postEl.querySelectorAll('.reaction-button')).forEach(rb=>{
          const e = rb.dataset.emoji;
          rb.textContent = `${e} ${ j.reactions && j.reactions[e] !== undefined ? j.reactions[e] : (p.reactions && p.reactions[e] ? p.reactions[e] : 0) }`;
          rb.classList.remove('active');
        });
        // mark clicked
        const clicked = postEl.querySelector(`.reaction-button[data-emoji="${em}"]`);
        if(clicked) clicked.classList.add('active');
      } else alert(j.error || 'React failed');
    };
    bar.append(btn);
  });
  div.append(bar);

  // comments summary
  const cm = document.createElement('div'); cm.className='small'; cm.style.marginTop='6px'; cm.textContent = `${p.comments_count || 0} comments`;
  div.append(cm);

  return div;
}

// Load feed
async function loadFeed(){
  const res = await fetch(API + '/posts');
  const list = await res.json();
  const feed = byId('feedList'); feed.innerHTML = '';
  list.forEach(p => feed.appendChild(createPostElement(p)));
  observeVideos();
}

// observe videos to auto-pause when scrolled out
function observeVideos(){
  if(window._vn_obs) window._vn_obs.disconnect();
  const options = { threshold: 0.25 };
  const observer = new IntersectionObserver((entries)=>{
    entries.forEach(entry=>{
      const v = entry.target;
      if(entry.intersectionRatio < 0.25){ if(!v.paused) v.pause(); }
    });
  }, options);
  document.querySelectorAll('video').forEach(v => observer.observe(v));
  window._vn_obs = observer;
}

// send message
async function sendMessage(){
  if(!currentUser){ alert('Login'); return; }
  const to = byId('msgTo').value.trim(); const text = byId('msgText').value.trim();
  if(!to||!text) return;
  await fetch(API + '/messages', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ from: currentUser.email, to, text })});
  byId('msgText').value=''; loadMessages();
}

// load messages
async function loadMessages(){
  if(!currentUser) return;
  const r = await fetch(API + '/messages/' + encodeURIComponent(currentUser.email));
  const list = await r.json();
  const el = byId('msgList'); el.innerHTML = '';
  list.forEach(m=>{
    const d = document.createElement('div'); d.className='post'; d.innerHTML = `<strong>${escapeHtml(m.sender)}</strong>: ${escapeHtml(m.text)} <div class="timestamp">${escapeHtml(m.timestamp)}</div>`; el.appendChild(d);
  });
}

// notifications
async function loadNotifications(){
  if(!currentUser) return;
  const r = await fetch(API + '/notifications/' + encodeURIComponent(currentUser.email));
  const list = await r.json();
  const el = byId('notifList'); el.innerHTML = '';
  const countEl = byId('notifCount');
  if(list.length){ countEl.style.display='inline-block'; countEl.textContent = list.length; } else countEl.style.display='none';
  list.forEach(n=>{
    const d = document.createElement('div'); d.className='post'; d.innerHTML = `${escapeHtml(n.text)} <div class="timestamp">${escapeHtml(n.timestamp)}</div>`; el.appendChild(d);
  });
}

// follow check
async function isFollowing(follower, followee){
  const r = await fetch(API + `/is_following?f=${encodeURIComponent(follower)}&t=${encodeURIComponent(followee)}`);
  return (await r.json()).following;
}

// profile posts
async function loadProfilePosts(){
  if(!currentUser) return;
  const r = await fetch(API + '/profile/' + encodeURIComponent(currentUser.email));
  const j = await r.json();
  byId('profileBio').value = j.bio || '';
  const el = byId('profilePosts'); el.innerHTML = '';
  (j.posts || []).forEach(p=>{
    const d = document.createElement('div'); d.className='post'; d.innerHTML = `<strong>${escapeHtml(p.author_name)}</strong> <div class="timestamp">${escapeHtml(p.timestamp)}</div><p>${escapeHtml(p.text)}</p>`; if(p.file_url){ if(p.file_url.endsWith('.mp4')) d.innerHTML += `<video src="${p.file_url}" controls style="max-width:100%"></video>`; else d.innerHTML += `<img src="${p.file_url}" style="max-width:100%">`; } el.appendChild(d);
  });
}

// update bio
async function updateBio(){
  if(!currentUser) return;
  const bio = byId('profileBio').value.trim();
  await fetch(API + '/update_bio', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ email: currentUser.email, bio })});
  alert('Bio saved');
}

// monetization
async function loadMonetization(){
  if(!currentUser) return;
  const r = await fetch(API + '/monetization/' + encodeURIComponent(currentUser.email));
  const j = await r.json();
  byId('monFollowers').textContent = j.followers;
  byId('monWatch').textContent = j.watch_hours;
  byId('monWatch') && (byId('monWatch').textContent = j.watch_hours);
  byId('monEarnings').textContent = (j.earnings || 0).toFixed(2);
  byId('sideFollowers').textContent = j.followers;
  byId('sideWatch').textContent = j.watch_hours;
  byId('sideEarnings').textContent = (j.earnings || 0).toFixed(2);
}

// create ad
async function createAd(){
  const title = byId('adTitle').value.trim(); const budget = parseFloat(byId('adBudget').value.trim()||0);
  if(!title || !budget){ alert('Title and budget'); return; }
  const r = await fetch(API + '/ads', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ title, budget, owner: currentUser.email })});
  const j = await r.json();
  alert(j.message || 'Ad created'); loadAds();
}

// load ads
async function loadAds(){
  const r = await fetch(API + '/ads');
  const list = await r.json();
  const el = byId('adsList'); el.innerHTML = '';
  list.forEach(a=>{
    const d = document.createElement('div'); d.className='small'; d.textContent = `${a.title} - budget:${a.budget} - impressions:${a.impressions} clicks:${a.clicks}`; el.appendChild(d);
  });
}

// follow endpoint
async function followUser(follower, target){
  const r = await fetch(API + '/follow', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ follower_email: follower, target_email: target })});
  return r.json();
}

// load side monet quick
async function loadSideMonet(){ await loadMonetization(); loadAds(); }

// refresh everything
async function refreshAll(){ await loadFeed(); await loadMessages(); await loadNotifications(); await loadProfilePosts(); await loadMonetization(); await loadAds(); }

// initial DOM-safe operations: login state retained only client-side in this demo
</script>
</body>
</html>
"""

from flask import render_template_string
@app.route("/")
def index():
    return render_template_string(HTML)

# ---------- API: Auth / users ----------
@app.route("/api/signup", methods=["POST"])
def api_signup():
    db = get_db()
    name = request.form.get("name")
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password")
    profile_pic = ""
    # file uploaded?
    if 'file' in request.files:
        f = request.files['file']
        if f and f.filename:
            fn = f"{uuid.uuid4().hex}_{f.filename}"
            path = os.path.join(UPLOAD_DIR, fn)
            f.save(path)
            profile_pic = f"/uploads/{fn}"
    if not email or not password:
        return jsonify({"error":"email+password required"}), 400
    try:
        cur = db.cursor()
        cur.execute("INSERT INTO users (name,email,password,profile_pic) VALUES (?,?,?,?)", (name, email, password, profile_pic))
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error":"User exists"}), 400
    user = {"name": name, "email": email, "profile_pic": profile_pic, "bio": "", "watch_hours": 0, "earnings": 0}
    # return user object for frontend convenience (do not return password)
    return jsonify({"user": user})

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password")
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT name,email,profile_pic,bio,watch_hours,earnings FROM users WHERE email=? AND password=?", (email, password))
    r = cur.fetchone()
    if not r:
        return jsonify({"error":"Invalid credentials"}), 401
    user = dict(r)
    return jsonify({"user": user})

# ---------- Upload handling ----------
@app.route("/api/upload", methods=["POST"])
def api_upload():
    if 'file' not in request.files:
        return jsonify({"error":"No file"}), 400
    f = request.files['file']
    if f.filename == "":
        return jsonify({"error":"No filename"}), 400
    fn = f"{uuid.uuid4().hex}_{f.filename}"
    path = os.path.join(UPLOAD_DIR, fn)
    f.save(path)
    return jsonify({"url": f"/uploads/{fn}"})

# ---------- Posts ----------
import json as _json

@app.route("/api/posts", methods=["GET","POST"])
def api_posts():
    db = get_db()
    cur = db.cursor()
    if request.method == "GET":
        cur.execute("SELECT * FROM posts ORDER BY id DESC")
        rows = cur.fetchall()
        out = []
        for r in rows:
            rec = dict(r)
            # parse reactions json
            try: rec['reactions'] = _json.loads(rec.get('reactions_json','{}'))
            except: rec['reactions'] = {'👍':0,'❤️':0,'😂':0}
            # get user reaction if exists (requires client to send user to query later; frontend will overlay by checking /api/user_reaction)
            # count comments stored in comments_count
            # get user reaction for demo: not included here
            # get user_reaction by separate endpoint if needed
            # include shorthand fields
            rec['user_reaction'] = None
            rec['comments_count'] = rec.get('comments_count',0)
            out.append(rec)
        return jsonify(out)
    else:
        data = request.get_json() or {}
        author_email = data.get('author_email')
        author_name = data.get('author_name')
        profile_pic = data.get('profile_pic','')
        text = data.get('text','')
        file_url = data.get('file_url','')
        ts = now_ts()
        reactions_json = _json.dumps({'👍':0,'❤️':0,'😂':0})
        cur.execute("INSERT INTO posts (author_email,author_name,profile_pic,text,file_url,timestamp,reactions_json,comments_count) VALUES (?,?,?,?,?,?,?,?)", (author_email,author_name,profile_pic,text,file_url,ts,reactions_json,0))
        db.commit()
        post_id = cur.lastrowid
        cur.execute("SELECT * FROM posts WHERE id=?", (post_id,))
        r = cur.fetchone()
        rec = dict(r)
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
    cur = db.cursor()
    # ensure post exists
    cur.execute("SELECT id,reactions_json,author_email FROM posts WHERE id=?", (post_id,))
    row = cur.fetchone()
    if not row:
        return jsonify({"error":"Post not found"}), 404
    reactions = _json.loads(row['reactions_json'] or '{}')
    # check existing reaction by this user for this post
    cur.execute("SELECT emoji FROM user_reactions WHERE user_email=? AND post_id=?", (user_email, post_id))
    prev = cur.fetchone()
    prev_emoji = prev['emoji'] if prev else None
    if prev_emoji == emoji:
        # already same reaction -> do nothing
        return jsonify({"success":True, "reactions": reactions})
    # if prev exists, decrement
    if prev_emoji:
        reactions[prev_emoji] = max(0, reactions.get(prev_emoji,0)-1)
        cur.execute("DELETE FROM user_reactions WHERE user_email=? AND post_id=?", (user_email, post_id))
    # set new reaction
    cur.execute("INSERT OR REPLACE INTO user_reactions (user_email,post_id,emoji) VALUES (?,?,?)", (user_email, post_id, emoji))
    reactions[emoji] = reactions.get(emoji,0) + 1
    # save reactions json
    cur.execute("UPDATE posts SET reactions_json=? WHERE id=?", (_json.dumps(reactions), post_id))
    db.commit()
    # create notification to post author if not self
    post_author = row['author_email']
    if post_author != user_email:
        cur.execute("INSERT INTO notifications (user_email,text,timestamp) VALUES (?,?,?)", (post_author, f"{emoji} reaction on your post", now_ts()))
        db.commit()
    return jsonify({"success":True, "reactions": reactions})

# ---------- User reaction checker (optional) ----------
@app.route("/api/user_reaction")
def api_user_reaction():
    user = request.args.get("user")
    post_id = request.args.get("post_id")
    db = get_db(); cur = db.cursor()
    cur.execute("SELECT emoji FROM user_reactions WHERE user_email=? AND post_id=?", (user, post_id))
    r = cur.fetchone()
    return jsonify({"emoji": r['emoji'] if r else None})

# ---------- Messages ----------
@app.route("/api/messages", methods=["POST"])
def api_messages_post():
    data = request.get_json() or {}
    sender = data.get("from")
    recipient = data.get("to")
    text = data.get("text")
    ts = now_ts()
    db = get_db(); cur = db.cursor()
    cur.execute("INSERT INTO messages (sender,recipient,text,timestamp) VALUES (?,?,?,?)", (sender,recipient,text,ts))
    cur.execute("INSERT INTO notifications (user_email,text,timestamp) VALUES (?,?,?)", (recipient, f"New message from {sender}", ts))
    db.commit()
    return jsonify({"success":True, "sender":sender, "to":recipient, "text":text, "timestamp":ts})

@app.route("/api/messages/<email>")
def api_messages_get(email):
    db = get_db(); cur = db.cursor()
    cur.execute("SELECT sender,recipient,text,timestamp FROM messages WHERE recipient=? OR sender=? ORDER BY id DESC", (email,email))
    rows = cur.fetchall()
    return jsonify([dict(r) for r in rows])

# ---------- Notifications ----------
@app.route("/api/notifications/<email>")
def api_notifications_get(email):
    db = get_db(); cur = db.cursor()
    cur.execute("SELECT text,timestamp,seen,id FROM notifications WHERE user_email=? ORDER BY id DESC", (email,))
    rows = cur.fetchall()
    return jsonify([dict(r) for r in rows])

# ---------- Follow ----------
@app.route("/api/follow", methods=["POST"])
def api_follow():
    data = request.get_json() or {}
    follower = data.get("follower_email")
    target = data.get("target_email")
    db = get_db(); cur = db.cursor()
    # check existing
    cur.execute("SELECT id FROM followers WHERE user_email=? AND follower_email=?", (target,follower))
    if cur.fetchone():
        cur.execute("DELETE FROM followers WHERE user_email=? AND follower_email=?", (target,follower))
        db.commit()
        return jsonify({"success":True, "action":"unfollowed"})
    else:
        cur.execute("INSERT INTO followers (user_email,follower_email) VALUES (?,?)", (target,follower))
        cur.execute("INSERT INTO notifications (user_email,text,timestamp) VALUES (?,?,?)", (target, f"{follower} started following you", now_ts()))
        db.commit()
        return jsonify({"success":True, "action":"followed"})

@app.route("/api/is_following")
def api_is_following():
    f = request.args.get("f"); t = request.args.get("t")
    db = get_db(); cur = db.cursor()
    cur.execute("SELECT id FROM followers WHERE user_email=? AND follower_email=?", (t,f))
    return jsonify({"following": bool(cur.fetchone())})

# ---------- Watch (video ended) ----------
@app.route("/api/watch", methods=["POST"])
def api_watch():
    data = request.get_json() or {}
    viewer = data.get("viewer")
    post_id = data.get("post_id")
    db = get_db(); cur = db.cursor()
    cur.execute("SELECT author_email FROM posts WHERE id=?", (post_id,))
    r = cur.fetchone()
    if not r: return jsonify({"error":"Post not found"}), 404
    author = r['author_email']
    # increment author's watch_hours by 1 if viewer hasn't watched this post yet (simple logic)
    cur.execute("SELECT COUNT(1) as c FROM messages") # dummy to keep cursor
    # For simplicity we increment author watch_hours (no per-post viewer list for now)
    cur.execute("UPDATE users SET watch_hours = watch_hours + 1 WHERE email=?", (author,))
    cur.execute("INSERT INTO notifications (user_email,text,timestamp) VALUES (?,?,?)", (author, f"Your video was watched by {viewer}", now_ts()))
    db.commit()
    cur.execute("SELECT watch_hours FROM users WHERE email=?", (author,))
    w = cur.fetchone()['watch_hours']
    return jsonify({"success":True, "watch_hours": w})

# ---------- Ads ----------
@app.route("/api/ads", methods=["GET","POST"])
def api_ads():
    db = get_db(); cur = db.cursor()
    if request.method == "GET":
        cur.execute("SELECT id,title,owner_email,budget,impressions,clicks,created_at FROM ads ORDER BY id DESC")
        return jsonify([dict(r) for r in cur.fetchall()])
    else:
        data = request.get_json() or {}
        title = data.get("title"); owner = data.get("owner"); budget = float(data.get("budget") or 0)
        cur.execute("INSERT INTO ads (title,owner_email,budget,impressions,clicks) VALUES (?,?,?,?,?)", (title,owner,budget,0,0))
        db.commit()
        return jsonify({"success":True, "message":"Ad created"})

@app.route("/api/ads/impression", methods=["POST"])
def api_ads_impression():
    data = request.get_json() or {}
    post_id = data.get("post_id")
    viewer = data.get("viewer")
    db = get_db(); cur = db.cursor()
    # credit impressions to post owner via owner lookup
    cur.execute("SELECT author_email FROM posts WHERE id=?", (post_id,))
    r = cur.fetchone()
    if not r: return jsonify({"error":"Post not found"}), 404
    owner = r['author_email']
    # increment owner earnings small amount
    cur.execute("UPDATE users SET earnings = earnings + 0.01 WHERE email=?", (owner,))
    db.commit()
    return jsonify({"success":True})

# ---------- Monetization endpoint ----------
@app.route("/api/monetization/<email>")
def api_monetization(email):
    db = get_db(); cur = db.cursor()
    cur.execute("SELECT watch_hours,earnings FROM users WHERE email=?", (email,))
    r = cur.fetchone()
    if not r: return jsonify({"followers":0,"watch_hours":0,"earnings":0,"status":"Not Eligible"})
    # count followers
    cur.execute("SELECT COUNT(1) as c FROM followers WHERE user_email=?", (email,))
    followers = cur.fetchone()['c']
    watch_hours = r['watch_hours']
    earnings = r['earnings']
    status = "Eligible" if followers >= 5000 and watch_hours >= 1000000 else "Not Eligible"
    return jsonify({"followers": followers, "watch_hours": watch_hours, "earnings": earnings, "status": status})

# ---------- Profile endpoint ----------
@app.route("/api/profile/<email>")
def api_profile(email):
    db = get_db(); cur = db.cursor()
    cur.execute("SELECT name,email,profile_pic,bio,watch_hours,earnings FROM users WHERE email=?", (email,))
    u = cur.fetchone()
    if not u: return jsonify({"error":"Not found"}), 404
    # posts by user
    cur.execute("SELECT id,author_email,author_name,profile_pic,text,file_url,timestamp,reactions_json,comments_count FROM posts WHERE author_email=? ORDER BY id DESC", (email,))
    posts = []
    for r in cur.fetchall():
        rec = dict(r)
        try: rec['reactions'] = _json.loads(rec.get('reactions_json','{}'))
        except: rec['reactions'] = {'👍':0,'❤️':0,'😂':0}
        rec['user_reaction'] = None
        posts.append(rec)
    return jsonify({"name": u['name'], "email": u['email'], "profile_pic": u['profile_pic'], "bio": u['bio'], "watch_hours": u['watch_hours'], "earnings": u['earnings'], "posts": posts})

# ---------- Update bio ----------
@app.route("/api/update_bio", methods=["POST"])
def api_update_bio():
    data = request.get_json() or {}
    email = data.get("email"); bio = data.get("bio","")
    db = get_db(); cur = db.cursor()
    cur.execute("UPDATE users SET bio=? WHERE email=?", (bio, email))
    db.commit()
    return jsonify({"success":True})

# ---------- helpers: simple seed ----------
def seed_sample():
    db = get_db(); cur = db.cursor()
    # check if no users
    cur.execute("SELECT COUNT(1) as c FROM users")
    if cur.fetchone()['c'] == 0:
        cur.execute("INSERT INTO users (name,email,password,profile_pic) VALUES (?,?,?,?)", ("Alice","alice@example.com","alice",""))
        cur.execute("INSERT INTO users (name,email,password,profile_pic) VALUES (?,?,?,?)", ("Bob","bob@example.com","bob",""))
        db.commit()
        # sample post
        ts = now_ts()
        cur.execute("INSERT INTO posts (author_email,author_name,profile_pic,text,file_url,timestamp,reactions_json,comments_count) VALUES (?,?,?,?,?,?,?,?)", ("alice@example.com","Alice","", "Welcome to VibeNet! Upload videos to earn watch hours.", "", ts, _json.dumps({'👍':0,'❤️':0,'😂':0}),0))
        db.commit()

with app.app_context():
    seed_sample()

# ---------- Run ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", app.config['PORT']))
    print(f"Starting VibeNet on 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)
