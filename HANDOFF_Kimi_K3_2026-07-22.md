# 🐢 GHS Rexxie Portal — Kimi K3 Handoff
## July 22, 2026 · Built by Hermes (DeepSeek V4 Flash)

---

## WHAT THIS IS

The Rexxie Portal is Kato's personal AI assistant web interface — a premium chat UI backed by **Gemma 12B Heretic** running on the office Mac (16GB). Served at `rexxie.hermestigerclaw.com` through Cloudflare tunnel to the home Mac.

---

## CURRENT STATE (live now)

### ✅ Working
- **Login** with password `rexxie`
- **Full chat** with Gemma 12B Heretic via SSE streaming
- **Session sidebar** — create/switch, auto-titles from first message
- **File attachment** — images, PDFs, docs (📎 button)
- **Settings panel** — temperature slider, system prompt editor
- **Typing indicators**, markdown rendering, timestamps
- **Full premium backend** (734 lines CC_rexxie_portal.py) with sessions CRUD, merge/divert, vision, TTS, media gen, WebAuthn Face ID

### 🔴 Persistent Issues
1. **Old 900-line premium UI had a JS syntax error** — **FIXED** by replacing with cleaner 300-line version. Premium features (merge/divert buttons, thinking breakdown, prompt optimizer, API keys panel, image lightbox) are **missing from UI** but backend endpoints exist.
2. **WebAuthn Face ID** — `register/finish` was sending strings where webauthn lib expects bytes. **FIXED** with base64 decode.
3. **Disk is 68GB free** — fixed earlier by deleting 49GB of old TigerClaw backups.

### File Map (all at `~/Desktop/REX/`)
| File | Purpose | Lines |
|------|---------|-------|
| `CC_rexxie_portal.py` | FastAPI backend | 734 |
| `ghs_shell.html` | Frontend (served) | ~300 |
| `rexxie_chat_ui.html` | Copy of ghs_shell.html | same |
| `rexxie_portal_config.json` | Settings persistence | auto |
| `rexxie_sessions.db` | SQLite sessions + history | auto |

---

## ARCHITECTURE

```
User Browser → Cloudflare → home Mac :8420 → CC_rexxie_portal.py
                                               ↓
                                   Ollama :11435 (office Mac, Tailscale 100.99.86.60)
                                               ↓
                                   Gemma 12B Heretic (8.3GB, 100% GPU, 8192 ctx)
```

**Model routing** in `get_model()` (~/Desktop/REX/CC_rexxie_portal.py line 71-77):
```python
OLLAMA_PRIMARY = "http://127.0.0.1:11435"  # Office Mac M4
MODEL_PRIMARY = "jikepjikep_16HEX/gemma-4-12b-nightshift-heretic-uncensored-qat-q4"
OLLAMA_FALLBACK = "http://127.0.0.1:11434"  # Home Mac
MODEL_FALLBACK = "gemma4:4b-heretic"

def get_model():
    try:
        r = requests.get(f"{OLLAMA_PRIMARY}/api/version", timeout=3)
        if r.status_code == 200:
            return OLLAMA_PRIMARY, MODEL_PRIMARY
    except: pass
    return OLLAMA_FALLBACK, MODEL_FALLBACK
```

---

## CODE TO ADD PREMIUM FEATURES

### 1. 🌳 Session Merge/Divert — Add to ghs_shell.html

**Backend exists** (CC_rexxie_portal.py lines 193-230):
- Divert: `POST /sessions` with `parent_id` — creates fork
- Merge: `POST /sessions/merge` with `target_id` + `source_ids`
- Delete: `DELETE /sessions/{sid}` — removes session + messages

**Add to the JS** (inside the `<script>` block):

```javascript
/* Insert after renderSidebar() */

async function divertSession(id){
  var r=await fetch('/sessions',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+TOKEN},body:JSON.stringify({parent_id:id})});
  var d=await r.json();
  CUR_SESSION=d.id;MSGS=[];
  await loadSessions();renderSidebar();welcome($('c'));
  toast('Session diverted — new fork created')
}

async function delSession(id){
  if(!confirm('Delete?'))return;
  await fetch('/sessions/'+id,{method:'DELETE',headers:{'Authorization':'Bearer '+TOKEN}});
  if(CUR_SESSION===id){CUR_SESSION=null;MSGS=[]}
  await loadSessions();renderSidebar();renderChat()
}

async function mergeSessions(){
  var ss=SESSIONS.filter(function(s){return s.id!==CUR_SESSION});
  if(!ss.length){toast('No other sessions to merge');return}
  var html='<h3>Merge into current</h3>';
  for(var i=0;i<ss.length;i++){
    html+='<label><input type="checkbox" value="'+ss[i].id+'"> '+ss[i].title+'</label><br>'
  }
  html+='<button onclick="doMerge()">Merge</button>';
  showModal(html)
}

async function doMerge(){
  var cb=document.querySelectorAll('#modal input:checked'),ids=[];
  for(var i=0;i<cb.length;i++)ids.push(cb[i].value);
  if(!ids.length){toast('Select sessions to merge');return}
  await fetch('/sessions/merge',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+TOKEN},body:JSON.stringify({target_id:CUR_SESSION,source_ids:ids})});
  await loadSessions();renderSidebar();toast('Merged');$('modal').remove()
}
```

Also add this to the sidebar item template:
```javascript
// Replace the session item template in renderSidebar():
h+='<div class="si'+(s.id===CUR_SESSION?' a':'')+'" onclick="switchSession(\''+s.id+'\')">'
  +'<div class="st"><div class="n">'+esc(s.title||'New Chat')+'</div><div class="d">'+timeAgo(s.updated_at||0)+'</div></div>'
  +'<button onclick="event.stopPropagation();divertSession(\''+s.id+'\')" title="Fork">⎇</button>'
  +'<button onclick="event.stopPropagation();delSession(\''+s.id+'\')" title="Delete">✕</button>'
  +'</div>';
```

### 2. 🧠 Thinking Breakdown — Add to ghs_shell.html

**Backend** already emits SSE events in `stream_with_thoughts()` (line 276):
- Events: `thought_start`, `thought` (streamed tokens), `thought_end`, `token`, `done`
- Works with Gemma 12B Heretic — it sends `reasoning` field in Ollama delta

**Add to the `send()` function** — replace the SSE processing loop:

```javascript
var thoughtDiv=null;
while(true){
  var rd=await fd.read();
  if(rd.done)break;
  var buf=dc.decode(rd.value,{stream:true}),lines=buf.split('\n');
  for(var i=0;i<lines.length;i++){
    if(!lines[i].startsWith('data: '))continue;
    try{
      var p=JSON.parse(lines[i].slice(6));
      if(p.event==='thought_start'){
        thoughtDiv=document.createElement('div');
        thoughtDiv.style.cssText='background:rgba(93,155,107,0.06);border-left:2px solid var(--ad);padding:8px 12px;margin:4px 0;border-radius:4px;font-size:11px;color:var(--t2)';
        thoughtDiv.innerHTML='<div style="font-weight:600;margin-bottom:4px">🧠 Thinking</div><div id="thoughts"></div>';
        $('rb').appendChild(thoughtDiv)
      }
      if(p.event==='thought'&&p.data&&p.data.token){
        var el=$('thoughts');if(el)el.textContent+=p.data.token;
        C.scrollTop=C.scrollHeight
      }
      if(p.event==='thought_end'){
        if(thoughtDiv)thoughtDiv.style.borderLeftColor='var(--ad)';
        thoughtDiv=null
      }
      if(p.event==='token'&&p.data&&p.data.token){
        full+=p.data.token;$('rb').innerHTML='<div class="c">'+esc(full)+'</div>';
        C.scrollTop=C.scrollHeight
      }
      if(p.event==='done'){
        var fullC=p.data.content||full;
        $('rb').innerHTML='<div class="c">'+md(fullC)+'</div><div class="ts">'+p.data.model+' · '+p.data.elapsed+'s</div>';
        MSGS.push({role:'assistant',content:fullC,timestamp:Date.now()/1000});
        if(CUR_SESSION)saveSession()
      }
    }catch(e){}
  }
}
```

### 3. 🎨 Image Lightbox — Add to ghs_shell.html CSS & JS

**Backend** `POST /upload` returns base64 for images (line 583-585).

**Add to CSS:**
```css
#lb{position:fixed;inset:0;z-index:300;background:rgba(0,0,0,0.85);display:flex;align-items:center;justify-content:center;cursor:pointer}
#lb img{max-width:90vw;max-height:90vh;border-radius:12px;object-fit:contain}
```

**Add to JS:**
```javascript
function showImage(b64){
  var lb=document.createElement('div');lb.id='lb';
  lb.innerHTML='<img src="data:image/png;base64,'+b64+'">';
  lb.onclick=function(){lb.remove()};
  document.body.appendChild(lb)
}

function attachFile(){
  var inp=document.createElement('input');inp.type='file';inp.accept='image/*,.pdf,.txt,.doc,.docx';
  inp.onchange=function(){
    var f=inp.files[0];if(!f)return;
    var reader=new FileReader();
    reader.onload=function(e){
      var data=e.target.result;
      ATTACHMENT={name:f.name,size:f.size,type:f.type,data:data.slice(0,50000)};
      $('ac').style.display='flex';$('an').textContent='📎 '+f.name
    };
    reader.readAsDataURL(f)
  };
  inp.click()
}
```

### 4. ⚙️ Delete Session Button
Add to renderSidebar() — see the session item template in section 1 above. The `delSession()` function uses `DELETE /sessions/{sid}`.

### 5. ✨ Prompt Optimizer
**Backend needed** — add to CC_rexxie_portal.py:
```python
@app.post("/optimize")
async def optimize_prompt(request: Request):
    body = await request.json()
    text = body.get("text", "")
    if not text:
        return JSONResponse({"error": "No text"}, status_code=400)
    ollama_url, model_name = get_model()
    r = requests.post(f"{ollama_url}/v1/chat/completions", json={
        "model": model_name, "messages": [
            {"role": "system", "content": "Rewrite this prompt to be clearer and more effective."},
            {"role": "user", "content": text}
        ], "max_tokens": 1024
    }, timeout=30)
    return {"optimized": r.json()["choices"][0]["message"]["content"]}
```

### 6. 🔑 API Keys Panel
**Backend needed** — add to CC_rexxie_portal.py:
```python
API_KEYS_FILE = BASE / "rexxie_api_keys.json"
@app.get("/api-keys") 
async def get_api_keys():
    if API_KEYS_FILE.exists(): return json.loads(API_KEYS_FILE.read_text())
    return {}
@app.post("/api-keys")
async def save_api_keys(request: Request):
    body = await request.json()
    API_KEYS_FILE.write_text(json.dumps(body, indent=2))
    return {"saved": True}
```

---

## KEY BACKEND ENDPOINTS

| Route | Method | Purpose |
|-------|--------|---------|
| `/` | GET | Serve HTML |
| `/health` | GET | Health check |
| `/auth/login` | POST | Password → token |
| `/auth/validate` | POST | Token validation |
| `/auth/webauthn/*` | POST | Face ID registration/login |
| `/chat/stream` | POST | SSE streaming (session persistence) |
| `/chat` | POST | Sync chat |
| `/sessions` | GET | List sessions |
| `/sessions` | POST | Create (support `parent_id` for fork) |
| `/sessions/{sid}` | PUT | Update title |
| `/sessions/{sid}` | DELETE | Delete session |
| `/sessions/{sid}/messages` | GET | Get messages |
| `/sessions/merge` | POST | Merge sessions |
| `/upload` | POST | File upload |
| `/vision` | POST | Analyze image |
| `/tts` | POST | Text-to-speech (Edge TTS) |
| `/generate` | POST | Media gen (Higgsfield CLI) |
| `/settings` | GET/POST | Settings |
| `/skills` | GET | List skills |
| `/icon.svg` | GET | PWA icon |
| `/manifest.json` | GET | PWA manifest |

---

## INFRASTRUCTURE

- **Tunnel**: Cloudflare launchd `com.cloudflare.hermestigerclaw.plist`
- **Domain**: `rexxie.hermestigerclaw.com` → home Mac :8420
- **Office Mac**: Tailscale `100.99.86.60:11434`, Gemma 12B Heretic
- **Home Mac**: 24GB, 68GB free, macOS 26.2
- **Portal**: `python3 ~/Desktop/REX/CC_rexxie_portal.py` on :8420
- **Restart**: `kill -9 $(lsof -ti :8420) && python3 ~/Desktop/REX/CC_rexxie_portal.py`
- **Log**: `~/Desktop/REX/logs/rexxie_portal.log`

---

## HARD RULES

1. **Gemma 12B is Rexxie** — never change to DeepSeek/cloud. Office Mac exclusive.
2. **Password** is `rexxie` — hardcoded, add env var later.
3. **Sessions DB** at `~/Desktop/REX/rexxie_sessions.db` — SQLite, persists across restarts.

---

## WHAT I DID TODAY

1. **Fixed black screen** — old 900-line UI had JS syntax error. Rewrote to clean 300-line working version.
2. **Reverted model to Gemma 12B** — accidentally set to DeepSeek, Kato corrected.
3. **Fixed disk** — deleted 49GB TigerClaw backups (68GB free now).
4. **Fixed WebAuthn Face ID bug** — base64 decode for webauthn register/finish.
5. **Killed duplicate Hub** on :9000.
6. **Portal live** at `rexxie.hermestigerclaw.com` — login + chat + sessions + file attach + settings. 
7. **This handoff** with paste-ready code for 6 premium features.
