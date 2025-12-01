from flask import Flask, request, jsonify, render_template_string, send_from_directory
from werkzeug.utils import secure_filename
import os, json, datetime

app = Flask(__name__)

# ---------------------- CONFIG ----------------------
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

DATA_FILES = {
    'users': 'users.json',
    'posts': 'posts.json',
    'messages': 'messages.json',
    'notifications': 'notifications.json'
}

def load_json(path, default):
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

users = load_json(DATA_FILES['users'], [])
posts = load_json(DATA_FILES['posts'], [])
messages = load_json(DATA_FILES['messages'], [])
notifications = load_json(DATA_FILES['notifications'], [])

def add_notification(user_email, text):
    notifications.append({'user': user_email, 'text': text})
    save_json(DATA_FILES['notifications'], notifications)

# ---------------------- FRONTEND ----------------------
HTML = '''
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>VibeNet Pro</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body{background:#121212;color:#fff;font-family:Arial;margin:0}
.container{max-width:550px;margin:30px auto;background:#1e1e1e;border-radius:12px;padding:15px}
input,textarea,select{width:100%;padding:10px;margin:6px 0;border-radius:8px;border:none;background:#252525;color:#fff}
button{background:#00bfff;border:none;color:white;padding:10px;border-radius:8px;cursor:pointer}
.nav{display:flex;justify-content:space-around;background:#222;margin-bottom:10px}
.nav button{background:#333;color:#fff;flex:1;border:none}
.nav button.active{background:#00bfff}
.tab{display:none}
.post{background:#222;padding:10px;margin:10px 0;border-radius:10px}
.profile-pic{width:40px;height:40px;border-radius:50%;margin-right:8px}
.post-header{display:flex;align-items:center}
.reaction-bar button{background:#333;margin:4px 6px 0 0}
</style>
</head>

<body>

<div class="container" id="auth">
<h2>Join VibeNet Pro</h2>
<input id="signupName" placeholder="Full Name">
<input id="signupEmail" placeholder="Email">
<input id="signupPassword" type="password" placeholder="Password">
<button onclick="signup()">Sign Up</button>

<h3>Login</h3>
<input id="loginEmail" placeholder="Email">
<input id="loginPassword" type="password" placeholder="Password">
<button onclick="login()">Login</button>
</div>

<div class="container" id="main" style="display:none">

<div class="nav">
<button onclick="showTab('feed')" class="active">🏠 Feed</button>
<button onclick="showTab('messages')">💬 Messages</button>
<button onclick="showTab('notifications')">🔔</button>
<button onclick="showTab('monetization')">💰</button>
<button onclick="showTab('profile')">👤</button>
</div>

<div id="feed" class="tab" style="display:block">
<textarea id="postText" placeholder="What's on your mind?"></textarea>
<input type="file" id="fileUpload">
<button onclick="addPost()">Post</button>
<div id="feedList"></div>
</div>

<div id="messages" class="tab">
<input id="msgTo" placeholder="Send to (email)">
<textarea id="msgText"></textarea>
<button onclick="sendMessage()">Send</button>
<div id="msgList"></div>
</div>

<div id="notifications" class="tab">
<div id="notifList"></div>
</div>

<div id="monetization" class="tab">
<h3>📊 Monetization Dashboard</h3>
<p>Followers: <span id="monFollowers">0</span></p>
<p>Watch hours: <span id="monWatch">0</span></p>
<p>Status: <b id="monStatus">Not Eligible</b></p>
</div>

<div id="profile" class="tab">
<h3>Your Profile</h3>
<textarea id="profileBio"></textarea>
<button onclick="updateBio()">Save Bio</button>
<div id="profilePosts"></div>
</div>

</div>

<script>
const API="/api";
let currentUser=null;

// ---------- AUTH ----------
async function signup(){
  const res=await fetch(API+'/signup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    name:signupName.value,
    email:signupEmail.value,
    password:signupPassword.value
  })});
  alert((await res.json()).message || "Done");
}

async function login(){
  const res=await fetch(API+'/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    email:loginEmail.value,
    password:loginPassword.value
  })});
  const data=await res.json();
  if(data.user){
    currentUser=data.user;
    auth.style.display="none";
    main.style.display="block";
    loadFeed(); loadMessages(); loadNotifications(); loadMon();
  }
}

// ---------- TABS ----------
function showTab(tab){
  document.querySelectorAll('.tab').forEach(t=>t.style.display="none");
  document.getElementById(tab).style.display="block";
}

// ---------- POSTS ----------
async function addPost(){
  const res=await fetch(API+'/posts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    authorEmail:currentUser.email,
    authorName:currentUser.name,
    text:postText.value
  })});
  postText.value="";
  const newPost=await res.json();
  feedList.prepend(renderPost(newPost));
}

async function loadFeed(){
  const res=await fetch(API+'/posts');
  const data=await res.json();
  feedList.innerHTML="";
  data.forEach(p=>feedList.appendChild(renderPost(p)));
}

function renderPost(p){
  const div=document.createElement('div');
  div.className="post";
  div.innerHTML=`
   <div class="post-header"><b>${p.authorName}</b></div>
   <p>${p.text}</p>

   <button onclick="followUser('${p.authorEmail}')">➕ Follow</button>

   <div class="reaction-bar">
     <button onclick="react(${p.id},'👍',this)">👍 ${p.reactions['👍']}</button>
     <button onclick="react(${p.id},'❤️',this)">❤️ ${p.reactions['❤️']}</button>
     <button onclick="react(${p.id},'😂',this)">😂 ${p.reactions['😂']}</button>
   </div>
  `;
  return div;
}

async function react(id,emoji,btn){
 const res=await fetch(API+'/react',{method:'POST',headers:{'Content-Type':'application/json'},
 body:JSON.stringify({postId:id,emoji:emoji,userEmail:currentUser.email})});
 const data=await res.json();
 if(data.updated){
   btn.innerText = emoji+" "+data.count;
 }
}

// ---------- FOLLOW ----------
async function followUser(target){
 await fetch(API+'/follow',{method:'POST',headers:{'Content-Type':'application/json'},
 body:JSON.stringify({followerEmail:currentUser.email,targetEmail:target})});
 alert("Followed");
 loadMon();
}

// ---------- MESSAGES ----------
async function sendMessage(){
  await fetch(API+'/messages',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    from:currentUser.email,
    to:msgTo.value,
    text:msgText.value
  })});
  loadMessages();
}

async function loadMessages(){
  const res=await fetch(API+'/messages/'+currentUser.email);
  const msgs=await res.json();
  msgList.innerHTML="";
  msgs.forEach(m=>msgList.innerHTML+=`<div class="post">${m.from}: ${m.text}</div>`);
}

// ---------- NOTIFS ----------
async function loadNotifications(){
  const res=await fetch(API+'/notifications/'+currentUser.email);
  const data=await res.json();
  notifList.innerHTML="";
  data.forEach(n=>notifList.innerHTML+=`<div class="post">${n.text}</div>`);
}
setInterval(()=>{if(currentUser)loadNotifications()},5000);

// ---------- MONETIZATION ----------
async function loadMon(){
 const u=currentUser;
 const f=u.followers?.length||0;
 const w=u.watch_hours||0;
 monFollowers.innerText=f;
 monWatch.innerText=w;
 monStatus.innerText=(f>=1000 && w>=5000)?"✅ Eligible":"❌ Not Eligible";
}

// ---------- PROFILE ----------
async function updateBio(){
 await fetch(API+'/updatebio',{method:'POST',headers:{'Content-Type':'application/json'},
 body:JSON.stringify({email:currentUser.email,bio:profileBio.value})});
}
</script>
</body>
</html>
'''

# ---------------- ROUTES -----------------

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/api/signup', methods=['POST'])
def signup():
    d=request.json
    if any(u['email']==d['email'] for u in users):
        return jsonify({'error':'User exists'})
    user={'name':d['name'],'email':d['email'],'password':d['password'],'followers':[],'watch_hours':0}
    users.append(user)
    save_json(DATA_FILES['users'],users)
    return jsonify({'message':'Account created'})

@app.route('/api/login', methods=['POST'])
def login():
    d=request.json
    user=next((u for u in users if u['email']==d['email'] and u['password']==d['password']),None)
    return jsonify({'user':user} if user else {'error':'Invalid'})

@app.route('/api/posts',methods=['GET','POST'])
def post_sys():
    if request.method=='GET': return jsonify(posts)
    d=request.json
    post={'id':len(posts)+1,'authorEmail':d['authorEmail'],'authorName':d['authorName'],'text':d['text'],
    'reactions':{'👍':0,'❤️':0,'😂':0}}
    posts.insert(0,post)
    save_json(DATA_FILES['posts'],posts)
    return jsonify(post)

@app.route('/api/react',methods=['POST'])
def react():
    d=request.json
    p=next(p for p in posts if p['id']==d['postId'])
    p['reactions'][d['emoji']] += 1
    save_json(DATA_FILES['posts'],posts)
    return jsonify({'updated':True,'count':p['reactions'][d['emoji']]})

@app.route('/api/follow',methods=['POST'])
def follow():
    d=request.json
    t=next(u for u in users if u['email']==d['targetEmail'])
    if d['followerEmail'] not in t['followers']:
        t['followers'].append(d['followerEmail'])
    save_json(DATA_FILES['users'],users)
    return jsonify({'success':True})

@app.route('/api/messages',methods=['POST'])
def send_msg():
    m=request.json
    messages.append(m)
    save_json(DATA_FILES['messages'],messages)
    return jsonify(m)

@app.route('/api/messages/<email>')
def get_msg(email):
    return jsonify([m for m in messages if m['to']==email or m['from']==email])

@app.route('/api/notifications/<email>')
def get_notif(email):
    return jsonify([n for n in notifications if n['user']==email])

@app.route('/api/updatebio',methods=['POST'])
def update_bio():
    d=request.json
    u=next(u for u in users if u['email']==d['email'])
    u['bio']=d['bio']
    save_json(DATA_FILES['users'],users)
    return jsonify({'success':True})

# ----------- RUN FOR RENDER -----------
if __name__ == '__main__':
    port=int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0",port=port,debug=True)
