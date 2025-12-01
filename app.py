from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import json, os

app = Flask(__name__)
CORS(app)

USERS_FILE = "users.json"
POSTS_FILE = "posts.json"

def load_data(file):
    if os.path.exists(file):
        with open(file, "r") as f:
            return json.load(f)
    return []

def save_data(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=4)

users = load_data(USERS_FILE)
posts = load_data(POSTS_FILE)

HTML = """
<!DOCTYPE html>
<html>
<head>
<title>VibeNet</title>
<style>
body{background:#0f0f0f;color:white;font-family:Arial}
header{display:flex;justify-content:space-between;align-items:center;padding:10px;background:black}
button{padding:7px;border:none;border-radius:5px;background:#1976d2;color:white}
.card{background:#1c1c1c;margin:10px;padding:10px;border-radius:8px}
img,video{max-width:100%;border-radius:8px}
.icon{font-size:20px;margin:5px;cursor:pointer}
.flex{display:flex;align-items:center;gap:10px}
</style>
</head>
<body>

<header>
  <h2>VibeNet</h2>
  <div>
    <span class="icon" onclick="openPage('feed')">🏠</span>
    <span class="icon" onclick="openPage('profile')">👤</span>
    <span class="icon" onclick="openPage('money')">💲</span>
    <span class="icon" onclick="openPage('notify')">🔔</span>
  </div>
</header>

<div id="app"></div>

<script>
let user = localStorage.getItem("user")

function openPage(page){
 fetch('/page/'+page)
 .then(r=>r.text())
 .then(d=>document.getElementById('app').innerHTML=d)
}

if(!user){openPage('login')}
else{openPage('feed')}

function react(id){
 fetch('/api/react',{method:'POST',headers:{'Content-Type':'application/json'},
 body:JSON.stringify({id:id,user:user})})
 .then(r=>r.json())
 .then(()=>openPage('feed'))
}

function follow(email){
 fetch('/api/follow',{method:'POST',headers:{'Content-Type':'application/json'},
 body:JSON.stringify({from:user,to:email})})
 .then(()=>openPage('feed'))
}

document.addEventListener("scroll",()=>{
 document.querySelectorAll("video").forEach(v=>{
  let r=v.getBoundingClientRect()
  if(r.bottom<0||r.top>window.innerHeight){v.pause()}
 })
})
</script>
</body>
</html>
"""

@app.route("/")
def home(): return HTML

# ---------- PAGES ----------
@app.route("/page/login")
def login():
 return '''
 <div class="card">
 <h3>Login</h3>
 <input id="email" placeholder="Email"><br><br>
 <input id="name" placeholder="Name"><br><br>
 <button onclick="login()">Enter</button>
 </div>
 <script>
 function login(){
  let e=email.value,n=name.value
  localStorage.setItem("user",e)
  fetch('/api/signup',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({email:e,name:n})})
  .then(()=>location.reload())
 }
 </script>
 '''

@app.route("/page/feed")
def feed():
 html=""
 for p in reversed(posts):
  html+=f"""
   <div class="card">
   <div class="flex">
    <img src="{p['avatar']}" width="35">
    <b>{p['name']}</b> 
    <small>{p['time']}</small>
    <button onclick="follow('{p['email']}')">Follow</button>
   </div>
   <p>{p['text']}</p>
   {"<video src='"+p["video"]+"' controls></video>" if p['video'] else ""}
   <br>
   ❤️ {len(p['reactions'])}
   <button onclick="react({p['id']})">React</button>
   </div>
  """
 return html

@app.route("/page/profile")
def profile():
 myposts=[p for p in posts if p['email']==local_user()]
 return "<h3>My Posts</h3>"+ "".join([f"<div class='card'>{p['text']}</div>" for p in myposts])

@app.route("/page/money")
def money():
 u=next((u for u in users if u['email']==local_user()),None)
 if not u:return ""
 status="Eligible" if u['followers']>=5000 and u['hours']>=1000000 else "Not Eligible"
 return f"""
 <div class="card">
 <h3>Monetization</h3>
 Followers: {u['followers']}<br>
 Watch Hours: {u['hours']}<br>
 Status: {status}
 </div>
 """

@app.route("/page/notify")
def notify():
 return "<h3>No new notifications</h3>"

# ---------- API ----------
def local_user():
 return request.headers.get("User","") or request.args.get("user","") or (users[0]['email'] if users else "")

@app.route("/api/signup",methods=["POST"])
def signup():
 data=request.json
 if not any(u['email']==data['email'] for u in users):
  users.append({"email":data['email'],"name":data['name'],"followers":0,"hours":0})
  save_data(USERS_FILE,users)
 return jsonify(ok=True)

@app.route("/api/react",methods=["POST"])
def react_api():
 data=request.json
 for p in posts:
  if p['id']==data['id'] and data['user'] not in p['reactions']:
   p['reactions'].append(data['user'])
   save_data(POSTS_FILE,posts)
 return jsonify(ok=True)

@app.route("/api/follow",methods=["POST"])
def follow_api():
 data=request.json
 target=next((u for u in users if u['email']==data['to']),None)
 if target:
  target['followers']+=1
  save_data(USERS_FILE,users)
 return jsonify(ok=True)

if __name__=="__main__":
 app.run(debug=True)
