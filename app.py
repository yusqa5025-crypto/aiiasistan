import os
import io
import re
import json
import base64
import mimetypes
import socket
import requests

from flask import Flask, request, jsonify, Response
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024


def _env_yukle():
    yol = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(yol):
        with open(yol, encoding="utf-8") as dosya:
            for satir in dosya:
                satir = satir.strip()
                if satir and not satir.startswith("#") and "=" in satir:
                    k, v = satir.split("=", 1)
                    os.environ[k.strip()] = v.strip().strip("\"'")


_env_yukle()

API_KEY = os.environ.get("GROQ_API_KEY", "").strip().strip("\"'")
API_URL = "https://api.groq.com/openai/v1"
SIFRE = os.environ.get("APP_SIFRE", "")
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "5000"))

MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
VISION_MODEL = os.environ.get("GROQ_VISION_MODEL", "qwen/qwen3.8-27b")

# Fotoğraf okumada sırayla denenir; ilki yoksa/limitliyse sıradakine geçer
VISION_MODELLER = []
for _m in (
    VISION_MODEL,
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
):
    if _m and _m not in VISION_MODELLER:
        VISION_MODELLER.append(_m)

YEDEK_MODELLER = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]

SISTEM = """Her zaman kullanıcının yazdığı dilde cevap ver.
Görselde veya metinde olmayan bilgiyi uydurma. Okunamayan veya kesik yerleri açıkça belirt.

ÇEVİRİ: Çeviri istenirse ilk cümleden sona kadar TAMAMINI çevir, özetleme, cümle atlama.

TEST / SORU ÇÖZME:
- Her soruyu ayrı ayrı, kendi numarasıyla çöz. Soru numarası uydurma, yalnızca verilen numaraları kullan.
- Önce verilenleri yaz, sonra doğru formülü seç, birimleri kontrol ederek hesapla, sonra sonucu şıklarla karşılaştır.
- Fizik/matematikte sonucu mutlaka şıklarla eşleştir. Hiçbir şık tutmuyorsa hesabını tekrar kontrol et.
- Kağıt üzerindeki kalem işaretlerini (daire, çarpı, çizgi) öğrencinin cevabı say ve ona güvenme. Soruyu bağımsız çöz.
- Şekil/grafik açıklaması varsa ona göre hesapla. Şekil eksik veya kesikse tahmin yürütme, o soruyu "şekil eksik" diye belirt.
- Son bölümde tablo KULLANMA, yalnızca şu biçimde düz liste ver:
Numara: Şık
- Emin olmadığın soruyu belirt, tahmin ettiğini söyle.
"""


def groq_headers():
    key = API_KEY
    return {"Authorization": f"Bearer {key}"}


def groq_chat(body, timeout=120):
    return requests.post(
        f"{API_URL}/chat/completions",
        headers={**groq_headers(), "Content-Type": "application/json"},
        json=body,
        timeout=timeout,
    )


def model_hatasi(r):
    return r.status_code in (400, 404) and "model" in r.text.lower()


@app.before_request
def kilit():
    if not SIFRE:
        return None

    a = request.authorization
    if not a or a.password != SIFRE:
        return Response(
            "Şifre gerekli",
            401,
            {"WWW-Authenticate": 'Basic realm="Asistan"'},
        )
    return None


HTML = r'''<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,viewport-fit=cover,interactive-widget=resizes-content">
<meta name="theme-color" content="#212121">
<title>AI Asistan</title>

<script>
window.MathJax = {
  tex: {
    inlineMath: [['\\(', '\\)']],
    displayMath: [['\\[', '\\]'], ['$$', '$$']]
  },
  options: {
    skipHtmlTags: ['script','noscript','style','textarea','pre','code']
  },
  startup: { typeset: false }
};
</script>
<script defer src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>

<style>
:root{
 --bg:#212121;--panel:#171717;--hover:#303030;--text:#f4f4f4;
 --muted:#aaa;--line:#414141;--blue:#7da4ff;--user:#303030;
}
*{box-sizing:border-box}
html,body{height:100%;margin:0;overflow:hidden;overscroll-behavior:none}
body{
 background:var(--bg);color:var(--text);
 font-family:system-ui,-apple-system,sans-serif
}
button,textarea{font:inherit;color:inherit}
button{cursor:pointer}
#app{
 position:fixed;left:0;right:0;top:0;height:100dvh;
 display:flex;flex-direction:column;background:var(--bg)
}
#top{
 flex-shrink:0;display:flex;align-items:center;justify-content:space-between;
 padding:0 12px;border-bottom:1px solid #333;
 --st:env(safe-area-inset-top,0px);padding-top:var(--st);
 min-height:calc(64px + var(--st))
}
.topgroup{display:flex;align-items:center;gap:8px}
.iconbtn{
 width:42px;height:42px;border:0;border-radius:50%;
 background:transparent;font-size:22px
}
.iconbtn:hover,.tool:hover{background:var(--hover)}
.brand{font-weight:650;font-size:17px}
.brand small{display:block;font-weight:400;color:var(--muted);font-size:12px}
#newBtn{
 background:transparent;border:1px solid var(--line);
 border-radius:24px;padding:10px 12px;font-size:13px
}
#layout{display:flex;flex:1;min-height:0;position:relative}
#sidebar{
 width:275px;flex-shrink:0;background:var(--panel);
 padding:12px;display:flex;flex-direction:column;gap:8px;z-index:5
}
.sidebtn,.chatitem{
 border:0;background:transparent;text-align:left;
 padding:12px;border-radius:12px
}
.sidebtn:hover,.chatitem:hover{background:var(--hover)}
#historyTitle{color:var(--muted);font-size:12px;padding:12px 8px 4px}
#history{display:flex;flex-direction:column;gap:4px;overflow-y:auto}
.chatitem{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#shade{display:none}
#main{flex:1;min-width:0;min-height:0;display:flex;flex-direction:column;position:relative}
#messages{flex:1;min-height:0;overflow-y:auto;padding:20px 16px}
#welcome{max-width:580px;margin:18vh auto 0;text-align:center;padding:12px}
#welcome h1{font-size:27px;font-weight:600;line-height:1.35}
#welcome p{color:var(--muted);line-height:1.7}
.msgrow{display:flex;gap:10px;max-width:800px;margin:0 auto 22px}
.msgrow.user{justify-content:flex-end}
.bubble{min-width:0;max-width:100%;overflow-wrap:anywhere;line-height:1.75}
.user .bubble{
 background:var(--user);padding:11px 16px;border-radius:22px;
 max-width:88%;white-space:pre-wrap
}
.assistant .bubble{flex:1;padding:2px 0}
.avatar{
 width:30px;height:30px;flex-shrink:0;border-radius:50%;
 display:grid;place-items:center;background:#303030;
 color:#c6d8ff;font-size:12px;font-weight:700
}
.assistant .bubble h1,.assistant .bubble h2,.assistant .bubble h3{color:var(--blue)}
.assistant .bubble strong{color:#a9c2ff}
.assistant .bubble a{color:#9bbaff}
.assistant .bubble pre{overflow:auto}
.assistant .bubble p{margin:8px 0}
.assistant .bubble mjx-container{max-width:100%;overflow-x:auto;overflow-y:hidden}
.codebox{margin:12px 0;border:1px solid #444;border-radius:12px;overflow:hidden;background:#101010}
.codehead{
 display:flex;align-items:center;justify-content:space-between;
 padding:8px 12px;background:#292929;font-size:12px;color:#ccc
}
.copy,.speak{background:#393939;border:0;border-radius:8px;padding:6px 10px;font-size:12px;margin:3px}
.codebox pre{margin:0;padding:14px;overflow-x:auto;font-size:13px}
.codebox code{font-family:ui-monospace,monospace}
#composerWrap{
 flex-shrink:0;width:100%;max-width:850px;margin:0 auto;
 padding:8px 12px max(12px,env(safe-area-inset-bottom))
}
#preview{
 display:none;border:1px solid var(--line);padding:9px 12px;
 border-radius:12px;margin-bottom:8px;font-size:13px
}
#removeFile{float:right;background:none;border:0;font-size:20px}
#composer{border:1px solid #454545;border-radius:27px;background:#303030;padding:8px 9px}
#entry{
 display:block;width:100%;min-height:36px;max-height:150px;
 resize:none;outline:none;border:0;background:transparent;color:white;
 padding:8px;font-size:16px;line-height:1.5
}
#entry::placeholder{color:#aaa}
#tools{display:flex;align-items:center;gap:8px}
#tools .sp{flex:1}
.tool{
 width:42px;height:42px;border:0;border-radius:50%;
 display:grid;place-items:center;background:transparent;
 font-size:24px;flex-shrink:0
}
#mic{background:#3d3d3d;color:#f4f4f4}
#mic:hover{background:#4a4a4a}
#mic.recording{background:#d33;color:white}
#voiceMode.voice-active{background:#315a43;color:#fff}
#send{background:#f4f4f4;color:#222}
#send:hover{background:#ddd}
#send:disabled{opacity:.5}
#fileInput,#cameraInput,#photoInput,#audioInput,#micInput{display:none}
#hint{text-align:center;font-size:11px;color:#888;padding-top:8px}
#attachMenu{
 display:none;position:absolute;bottom:108px;left:14px;
 background:#303030;border:1px solid #454545;border-radius:18px;
 padding:8px;width:225px;z-index:8;box-shadow:0 8px 30px #0008
}
.menuitem{
 display:flex;align-items:center;gap:14px;
 padding:13px 14px;border-radius:12px;cursor:pointer;font-size:16px
}
.menuitem svg{flex-shrink:0;width:22px;height:22px;color:#cfcfcf}
.menuitem span{flex:1}
.menuitem:hover{background:#444}
#toast{
 display:none;position:fixed;bottom:100px;left:50%;
 transform:translateX(-50%);background:#444;color:white;
 padding:10px 16px;border-radius:20px;z-index:20;font-size:13px;
 max-width:90%;text-align:center
}
@media(max-width:650px){
 #sidebar{
  position:absolute;inset:0 auto 0 0;width:min(82vw,300px);
  transform:translateX(-105%);transition:transform .2s
 }
 #sidebar.open{transform:translateX(0);box-shadow:12px 0 40px #0008}
 #shade.show{display:block;position:absolute;inset:0;background:#0008;z-index:4}
 #messages{padding:18px 14px}
 #welcome{margin-top:12vh}
 #welcome h1{font-size:24px}
 #newBtn{font-size:12px;padding:9px}
}
</style>
</head>

<body>
<div id="app">
<header id="top">
 <div class="topgroup">
  <button class="iconbtn" id="menuBtn" aria-label="Menü">☰</button>
  <div class="brand">AI Asistan<small>Metin · Fotoğraf · Ses · Dosya</small></div>
 </div>
 <div class="topgroup"><button id="newBtn">＋ Yeni sohbet</button></div>
</header>

<div id="layout">
 <aside id="sidebar">
  <button class="sidebtn" id="sideNew">＋　Yeni sohbet</button>
  <div id="historyTitle">Sohbet geçmişi</div>
  <div id="history"></div>
 </aside>
 <div id="shade"></div>

 <main id="main">
  <section id="messages"></section>

  <div id="attachMenu">
   <div class="menuitem" data-action="camera">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8h3l2-3h6l2 3h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z"/><circle cx="12" cy="13" r="3.5"/></svg>
    <span>Kamera</span>
   </div>
   <div class="menuitem" data-action="photos">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="1.8"/><path d="M21 16l-5-5-8 9"/></svg>
    <span>Fotoğraflar</span>
   </div>
   <div class="menuitem" data-action="files">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11l-8.5 8.5a5 5 0 0 1-7-7L14 4a3.3 3.3 0 0 1 4.7 4.7l-8.5 8.5a1.7 1.7 0 0 1-2.4-2.4L15 7"/></svg>
    <span>Dosyalar</span>
   </div>
   <div class="menuitem" data-action="audio">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>
    <span>Ses dosyası</span>
   </div>
  </div>

  <div id="composerWrap">
   <div id="preview"><span id="filename"></span><button id="removeFile">×</button></div>
   <div id="composer">
    <textarea id="entry" rows="1" placeholder="Herhangi bir şey sor"></textarea>
    <div id="tools">
     <button class="tool" id="plus" aria-label="Dosya ekle">＋</button>
     <span class="sp"></span>
     <button class="tool" id="voiceMode" aria-label="Sesli sohbet" title="Sesli sohbet">🗣️</button>
      <button class="tool" id="mic" aria-label="Ses kaydet">
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>
     </button>
     <button class="tool" id="send" aria-label="Gönder">
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>
     </button>
    </div>
   </div>
   <div id="hint">AI Asistan hata yapabilir. Önemli bilgileri kontrol et.</div>
   <input id="fileInput" type="file" accept="image/*,audio/*,.pdf,.txt,.md,.csv,.json,.py,.js,.html,.css,.xml,.log,.docx">
   <input id="cameraInput" type="file" accept="image/*" capture="environment">
   <input id="photoInput" type="file" accept="image/*" multiple>
   <input id="audioInput" type="file" accept="audio/*">
   <input id="micInput" type="file" accept="audio/*" capture>
  </div>
 </main>
</div>
</div>
<div id="toast"></div>

<script>
const $ = id => document.getElementById(id);
const KULLANICI = __ISIM__;
const HISTKEY = "ai_history_list" + (KULLANICI ? "_" + KULLANICI.toLowerCase() : "");

const MIC_SVG = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>';
const STOP_SVG = '<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>';

const messagesEl = $("messages");
const entry = $("entry");

let conversation = [];
let historyList = [];

try {
 historyList = JSON.parse(localStorage.getItem(HISTKEY) || "[]");
 if (!Array.isArray(historyList)) historyList = [];
} catch(e) {
 historyList = [];
}

let activeId = null;
let selectedFiles = [];
let recorder = null;
let audioChunks = [];
let sesliSohbetAktif = false;

function toast(t) {
 $("toast").textContent = t;
 $("toast").style.display = "block";
 setTimeout(() => $("toast").style.display = "none", 2500);
}

function scrollBottom() {
 messagesEl.scrollTop = messagesEl.scrollHeight;
}

function closeMenus() {
 $("sidebar").classList.remove("open");
 $("shade").classList.remove("show");
 $("attachMenu").style.display = "none";
}

function welcomeEl() {
 const w = document.createElement("div");
 w.id = "welcome";

 const h = document.createElement("h1");
 h.textContent = KULLANICI
  ? KULLANICI + ", sana nasıl yardımcı olabilirim?"
  : "Sana nasıl yardımcı olabilirim?";

 const p = document.createElement("p");
 p.textContent = "Soru sor, fotoğraf gönder, ses kaydet veya dosya yükle.";

 w.append(h, p);
 return w;
}

function newChat() {
 activeId = null;
 conversation = [];
 selectedFiles = [];
 $("preview").style.display = "none";
 messagesEl.replaceChildren(welcomeEl());
 closeMenus();
}

function saveHistory() {
 if (!activeId) activeId = String(Date.now());

 let item = historyList.find(x => x.id === activeId);

 if (!item) {
  item = {
   id: activeId,
   title: conversation.find(x => x.role === "user")?.content?.slice(0, 38) || "Yeni sohbet",
   messages: []
  };
  historyList.unshift(item);
 }

 item.messages = conversation;

 try {
  localStorage.setItem(HISTKEY, JSON.stringify(historyList));
 } catch(e) {
  toast("Sohbet geçmişi kaydedilemedi.");
 }

 renderHistory();
}

function renderHistory() {
 $("history").replaceChildren();

 historyList.forEach(item => {
  const b = document.createElement("button");
  b.className = "chatitem";
  b.textContent = "▢　" + item.title;

  b.onclick = () => {
   activeId = item.id;
   conversation = JSON.parse(JSON.stringify(item.messages || []));
   messagesEl.replaceChildren();
   conversation.forEach(m => renderMessage(m.role, m.content, false));
   closeMenus();
   scrollBottom();
  };

  $("history").appendChild(b);
 });
}

$("menuBtn").onclick = () => {
 $("sidebar").classList.toggle("open");
 if (innerWidth <= 650) $("shade").classList.toggle("show");
};

$("shade").onclick = closeMenus;
$("newBtn").onclick = newChat;
$("sideNew").onclick = newChat;

$("plus").onclick = () => {
 const m = $("attachMenu");
 m.style.display = m.style.display === "block" ? "none" : "block";
};

$("attachMenu").onclick = e => {
 const action = e.target.closest(".menuitem")?.dataset.action;
 if (!action) return;

 $("attachMenu").style.display = "none";

 if (action === "camera") $("cameraInput").click();
 if (action === "photos") $("photoInput").click();
 if (action === "files") $("fileInput").click();
 if (action === "audio") $("audioInput").click();
};

["fileInput", "cameraInput", "photoInput", "audioInput", "micInput"].forEach(id => {
 $(id).onchange = () => {
  const input = $(id);
  const files = Array.from(input.files || []);

  if (files.length) {
   selectedFiles = id === "photoInput" ? files : [files[0]];
   const ses = id === "micInput";

   $("filename").textContent =
    (ses ? "🎙 " : "📎 ") +
    selectedFiles.map(f => f.name).join(", ");
   $("preview").style.display = "block";

   if (ses) toast("Ses hazır. Göndermek için oka bas.");
   else if (selectedFiles.length > 1) {
    toast(selectedFiles.length + " fotoğraf seçildi.");
   }
  }

  input.value = "";
 };
});

$("removeFile").onclick = () => {
 selectedFiles = [];
 $("preview").style.display = "none";
};

entry.addEventListener("input", () => {
 entry.style.height = "auto";
 entry.style.height = Math.min(entry.scrollHeight, 150) + "px";
});

entry.addEventListener("focus", () => {
 setTimeout(() => { fitViewport(); scrollBottom(); }, 300);
});

entry.addEventListener("keydown", e => {
 if (e.key === "Enter" && !e.shiftKey) {
  e.preventDefault();
  sendMessage();
 }
});

$("send").onclick = sendMessage;

function escapeHtml(s) {
 return String(s).replace(/[&<>"]/g, c => ({
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;"
 }[c]));
}

function renderMarkdown(text) {
 text = String(text)
  .replace(/\\?&(?:amp;)?#91;/g, "\\[")
  .replace(/\\?&(?:amp;)?#93;/g, "\\]")
  .replace(/\\([.,:;!?])/g, "$1");

 const blocks = [];

 let s = text.replace(/```([\w+-]*)\n?([\s\S]*?)```/g, (all, lang, code) => {
  blocks.push({lang, code});
  return "\u0000CODE" + (blocks.length - 1) + "\u0000";
 });

 s = escapeHtml(s);

 s = s.replace(/`([^`\n]+)`/g, "<code>$1</code>");
 s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
 s = s.replace(/\*(.+?)\*/g, "<em>$1</em>");
 s = s.replace(/^### (.+)$/gm, "<h3>$1</h3>");
 s = s.replace(/^## (.+)$/gm, "<h2>$1</h2>");
 s = s.replace(/^# (.+)$/gm, "<h1>$1</h1>");
 s = s.replace(/^\s*[-*] (.+)$/gm, "<li>$1</li>");
 s = s.replace(/(?:<li>.*?<\/li>\n?)+/gs, x => "<ul>" + x + "</ul>");

 s = s.split(/\n{2,}/).map(p => {
  p = p.trim();
  if (!p) return "";
  if (/^<(h\d|ul|ol|div|pre)/i.test(p)) return p;
  return "<p>" + p.replace(/\n/g, "<br>") + "</p>";
 }).join("");

 s = s.replace(/\u0000CODE(\d+)\u0000/g, (_, i) => {
  const b = blocks[Number(i)];
  return '<div class="codebox"><div class="codehead"><span>' +
   escapeHtml(b.lang || "Kod") +
   '</span><button class="copy">Kopyala</button></div><pre><code>' +
   escapeHtml(b.code) +
   '</code></pre></div>';
 });

 return s;
}

function typesetMath(el, deneme = 0) {
 if (window.MathJax && window.MathJax.typesetPromise) {
  window.MathJax.typesetPromise([el]).catch(() => {});
 } else if (deneme < 40) {
  setTimeout(() => typesetMath(el, deneme + 1), 150);
 }
}

function addSpeechButton(bubble, text) {
 const btn = document.createElement("button");
 btn.className = "speak";
 btn.textContent = "🔊 Sesli dinle";

 btn.onclick = () => {
  if (!("speechSynthesis" in window)) {
   toast("Tarayıcı seslendirmeyi desteklemiyor.");
   return;
  }

  speechSynthesis.cancel();

  const temiz = text
   .replace(/```[\s\S]*?```/g, " kod bloğu ")
   .replace(/[*#`_>]/g, "");

  const utterance = new SpeechSynthesisUtterance(temiz);
  utterance.lang = "tr-TR";
  utterance.rate = 1;

  speechSynthesis.speak(utterance);
 };

 bubble.appendChild(btn);
}

function bindCopy(bubble) {
 bubble.querySelectorAll(".copy").forEach(btn => {
  btn.onclick = async () => {
   const code = btn.closest(".codebox").querySelector("code").textContent;

   try {
    await navigator.clipboard.writeText(code);
   } catch(e) {
    const t = document.createElement("textarea");
    t.value = code;
    document.body.appendChild(t);
    t.select();
    document.execCommand("copy");
    t.remove();
   }

   btn.textContent = "Kopyalandı";
   setTimeout(() => btn.textContent = "Kopyala", 1500);
  };
 });
}

function renderMessage(role, content, scroll = true) {
 $("welcome")?.remove();

 const row = document.createElement("div");
 row.className = "msgrow " + (role === "user" ? "user" : "assistant");

 if (role !== "user") {
  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = "AI";
  row.appendChild(avatar);
 }

 const bubble = document.createElement("div");
 bubble.className = "bubble";

 if (role === "user") {
  bubble.textContent = content;
 } else {
  bubble.innerHTML = renderMarkdown(content);
  typesetMath(bubble);
  bindCopy(bubble);
  addSpeechButton(bubble, content);
 }

 row.appendChild(bubble);
 messagesEl.appendChild(row);

 if (scroll) scrollBottom();

 return row;
}

async function sendMessage() {
 const text = entry.value.trim();

 if (!text && !selectedFiles.length) return;

 const files = [...selectedFiles];
 selectedFiles = [];
 $("preview").style.display = "none";

 entry.value = "";
 entry.style.height = "auto";
 $("send").disabled = true;

 const voiceOnly = sesliSohbetAktif &&
   files.length === 1 && files[0].name === "ses-kaydi.webm";
  let display = voiceOnly ? "Sesli mesaj" : text;
  if (files.length && !voiceOnly) {
   display += (display ? "\n\n" : "") +
    files.map(f => "Dosya: " + f.name).join("\n");
  }

 conversation.push({role: "user", content: display});
 renderMessage("user", display);
 saveHistory();

 const wait = renderMessage("assistant", "Yanıt hazırlanıyor…");
 const bubble = wait.querySelector(".bubble");

 try {
  const form = new FormData();
  form.append("mesajlar", JSON.stringify(conversation.slice(-20)));
  form.append(
   "mesaj",
   voiceOnly
    ? "Bu ses kaydındaki konuşmayı yazıya çevir ve kullanıcının söylediklerine doğrudan cevap ver. Doğal, kısa ve konuşma dilinde yanıtla."
    : text
  );

  files.forEach(file => form.append("dosyalar", file, file.name));

  const response = await fetch("/sohbet", {
   method: "POST",

   body: form
  });

  const data = await response.json();

  if (!response.ok || !data.ok) {
   throw new Error(data.cevap || "İstek başarısız.");
  }

  bubble.innerHTML = renderMarkdown(data.cevap);
  typesetMath(bubble);
  bindCopy(bubble);
  addSpeechButton(bubble, data.cevap);

  if (sesliSohbetAktif) {
   if ("speechSynthesis" in window) {
    speechSynthesis.cancel();

    const okunacak = String(data.cevap)
     .replace(/```[\s\S]*?```/g, "kod bloğu")
     .replace(/[*#`_>]/g, "");

    const ses = new SpeechSynthesisUtterance(okunacak);
    ses.lang = "tr-TR";
    ses.rate = 1;

    const turkceSes = speechSynthesis.getVoices()
     .find(v => /^tr(-|_)/i.test(v.lang));
    if (turkceSes) ses.voice = turkceSes;

    ses.onstart = () => {
     if (sesliSohbetAktif) voiceStatus("Yanıt veriyorum…");
    };

    ses.onend = () => {
     if (sesliSohbetAktif && !voiceClosing) {
      voiceStatus("Dinliyorum…");
      setTimeout(() => startVoiceRecording(), 400);
     }
    };

    ses.onerror = () => {
     if (sesliSohbetAktif && !voiceClosing) {
      voiceStatus("Dinlemeye yeniden başlıyorum…");
      setTimeout(() => startVoiceRecording(), 800);
     }
    };

    voiceStatus("Yanıt hazırlanıyor…");
    speechSynthesis.speak(ses);
   } else {
    voiceStatus("Seslendirme desteklenmiyor; yeniden dinliyorum…");
    setTimeout(() => startVoiceRecording(), 800);
   }
  }

  conversation.push({role: "assistant", content: data.cevap});
  saveHistory();

 } catch(e) {
  bubble.textContent = "Hata: " + e.message;
  toast("Yanıt alınamadı");
 } finally {
  $("send").disabled = false;
  scrollBottom();
 }
}


let voiceOverlay = null;
let voiceStream = null;
let voiceAudioContext = null;
let voiceAnalyser = null;
let voiceFrame = 0;
let voiceClosing = false;
let voiceStarting = false;

function voiceStatus(text) {
  const el = document.getElementById("voiceStatus");
  if (el) el.textContent = text;
}

function createVoiceOverlay() {
  if (voiceOverlay) return;

  const style = document.createElement("style");
  style.id = "voiceChatStyle";
  style.textContent = `
    #voiceChatOverlay {
      position:fixed; inset:0; z-index:99999;
      background:#101010; color:#f5f5f5;
      display:flex; flex-direction:column; align-items:center;
      justify-content:center; padding:24px; box-sizing:border-box;
      font-family:system-ui,sans-serif;
    }
    #voiceChatOverlay .voice-orb {
      width:128px;height:128px;border-radius:50%;
      display:flex;align-items:center;justify-content:center;
      background:radial-gradient(circle at 35% 30%,#7b9cff,#5542a8 65%,#25204b);
      box-shadow:0 0 55px #6655bb55;font-size:44px;
      animation:voicePulse 2s ease-in-out infinite;
    }
    #voiceChatOverlay .voice-title {font-size:24px;font-weight:650;margin-top:30px}
    #voiceChatOverlay .voice-status {color:#b8b8c5;margin-top:12px;text-align:center}
    #voiceChatOverlay .voice-close {
      position:absolute;top:24px;right:22px;border:0;border-radius:50%;
      width:46px;height:46px;background:#292929;color:white;font-size:24px;
    }
    #voiceChatOverlay .voice-hint {color:#85858f;font-size:13px;margin-top:20px;text-align:center}
    @keyframes voicePulse {50%{transform:scale(1.06);box-shadow:0 0 75px #6655bb88}}
  `;
  document.head.appendChild(style);

  voiceOverlay = document.createElement("div");
  voiceOverlay.id = "voiceChatOverlay";
  voiceOverlay.innerHTML = `
    <button class="voice-close" id="voiceClose" aria-label="Sesli sohbeti kapat">×</button>
    <div class="voice-orb">✦</div>
    <div class="voice-title">Sesli sohbet</div>
    <div class="voice-status" id="voiceStatus">Mikrofon hazırlanıyor…</div>
    <div class="voice-hint">Konuşmanı bitirdiğinde otomatik olarak yanıt vereceğim.</div>
  `;
  document.body.appendChild(voiceOverlay);
  document.getElementById("voiceClose").onclick = closeVoiceChat;
}

async function startVoiceRecording() {
  if (!sesliSohbetAktif || voiceClosing || voiceStarting) return;
  if (recorder && recorder.state === "recording") return;

  if (!window.isSecureContext ||
      !navigator.mediaDevices?.getUserMedia ||
      !window.MediaRecorder) {
    voiceStatus("Mikrofon için HTTPS veya localhost bağlantısı gerekiyor.");
    toast("Bu bağlantıda mikrofon kullanılamıyor.");
    return;
  }

  voiceStarting = true;
  try {
    voiceStream = await navigator.mediaDevices.getUserMedia({audio:true});
    if (!sesliSohbetAktif || voiceClosing) {
      voiceStream.getTracks().forEach(t => t.stop());
      voiceStream = null;
      return;
    }

    audioChunks = [];
    recorder = new MediaRecorder(voiceStream);
    voiceAudioContext = new (window.AudioContext || window.webkitAudioContext)();
    const source = voiceAudioContext.createMediaStreamSource(voiceStream);
    voiceAnalyser = voiceAudioContext.createAnalyser();
    voiceAnalyser.fftSize = 2048;
    source.connect(voiceAnalyser);

    let speechDetected = false;
    let lastLoudAt = performance.now();
    const startedAt = performance.now();
    const samples = new Uint8Array(voiceAnalyser.fftSize);

    recorder.ondataavailable = e => {
      if (e.data && e.data.size) audioChunks.push(e.data);
    };

    recorder.onstop = async () => {
      cancelAnimationFrame(voiceFrame);
      if (voiceStream) {
        voiceStream.getTracks().forEach(t => t.stop());
        voiceStream = null;
      }
      if (voiceAudioContext) {
        try { await voiceAudioContext.close(); } catch (_) {}
        voiceAudioContext = null;
      }

      const blob = new Blob(audioChunks, {
        type: recorder?.mimeType || "audio/webm"
      });

      if (!sesliSohbetAktif || voiceClosing) return;

      if (speechDetected && blob.size > 1000) {
        voiceStatus("Söylediklerin gönderiliyor…");
        selectedFiles = [
          new File([blob], "ses-kaydi.webm", {type: blob.type || "audio/webm"})
        ];
        $("filename").textContent = "🎙 Sesli sohbet";
        $("preview").style.display = "block";
        await sendMessage();
      } else {
        voiceStatus("Seni duymaya çalışıyorum…");
        setTimeout(() => {
          if (sesliSohbetAktif && !voiceClosing) startVoiceRecording();
        }, 500);
      }
    };

    recorder.start(250);
    voiceStatus("Dinliyorum… konuşabilirsin.");

    const detectSilence = () => {
      if (!recorder || recorder.state !== "recording" || voiceClosing) return;

      voiceAnalyser.getByteTimeDomainData(samples);
      let sum = 0;
      for (let i = 0; i < samples.length; i++) {
        const v = (samples[i] - 128) / 128;
        sum += v * v;
      }
      const rms = Math.sqrt(sum / samples.length);
      const now = performance.now();

      if (rms > 0.012) {
        speechDetected = true;
        lastLoudAt = now;
      }

      // Konuşma bittikten sonra 2,2 saniye bekle.
      if (speechDetected && now - lastLoudAt > 2200) {
        voiceStatus("Konuşman alındı, yanıt hazırlanıyor…");
        recorder.stop();
        return;
      }

      // Tek seferlik kayıt süresini 30 saniyeye çıkar.
      if (now - startedAt > 30000) {
        recorder.stop();
        return;
      }

      // Konuşma başlamazsa mikrofonu 10 saniye sonra yeniden dene.
      if (!speechDetected && now - startedAt > 10000) {
        recorder.stop();
        return;
      }

      voiceFrame = requestAnimationFrame(detectSilence);
    };

    voiceFrame = requestAnimationFrame(detectSilence);
  } catch (e) {
    voiceStatus("Mikrofon açılamadı. Tarayıcı izinlerini kontrol et.");
    toast("Mikrofon izni gerekli.");
    if (voiceStream) {
      voiceStream.getTracks().forEach(t => t.stop());
      voiceStream = null;
    }
  } finally {
    voiceStarting = false;
  }
}

function closeVoiceChat() {
  voiceClosing = true;
  sesliSohbetAktif = false;
  cancelAnimationFrame(voiceFrame);

  if ("speechSynthesis" in window) speechSynthesis.cancel();

  if (recorder && recorder.state === "recording") {
    recorder.onstop = null;
    try { recorder.stop(); } catch (_) {}
  }
  if (voiceStream) {
    voiceStream.getTracks().forEach(t => t.stop());
    voiceStream = null;
  }
  if (voiceAudioContext) {
    try { voiceAudioContext.close(); } catch (_) {}
    voiceAudioContext = null;
  }

  voiceOverlay?.remove();
  voiceOverlay = null;
  $("voiceMode").classList.remove("voice-active");
  $("voiceMode").textContent = "🗣️";
  voiceClosing = false;
  toast("Sesli sohbet kapatıldı.");
}

$("voiceMode").onclick = async () => {
  if (sesliSohbetAktif) {
    closeVoiceChat();
    return;
  }

  sesliSohbetAktif = true;
  voiceClosing = false;
  $("voiceMode").classList.add("voice-active");
  $("voiceMode").textContent = "🔊";
  createVoiceOverlay();
  voiceStatus("Mikrofon hazırlanıyor…");
  await startVoiceRecording();
};


$("mic").onclick = async () => {
 if (recorder && recorder.state === "recording") {
  recorder.stop();
  $("mic").classList.remove("recording");
  $("mic").innerHTML = MIC_SVG;
  return;
 }

 if (!window.isSecureContext ||
     !navigator.mediaDevices?.getUserMedia ||
     !window.MediaRecorder) {
  $("micInput").click();
  return;
 }

 try {
  const stream = await navigator.mediaDevices.getUserMedia({audio: true});
  audioChunks = [];

  recorder = new MediaRecorder(stream);

  recorder.ondataavailable = e => {
   if (e.data.size) audioChunks.push(e.data);
  };

  recorder.onstop = () => {
   stream.getTracks().forEach(t => t.stop());

   const blob = new Blob(audioChunks, {
    type: recorder.mimeType || "audio/webm"
   });

   selectedFiles = [new File([blob], "ses-kaydi.webm", {type: blob.type})];

   $("filename").textContent = "🎙 Ses kaydı hazır";
   $("preview").style.display = "block";

   if (typeof sesliSohbetAktif !== "undefined" && sesliSohbetAktif) {
    toast("Ses gönderiliyor...");
    sendMessage();
   } else {
    toast("Ses hazır. Göndermek için oka bas.");
   }
  };

  recorder.start();
  $("mic").classList.add("recording");
  $("mic").innerHTML = STOP_SVG;
  toast("Konuş. Bitirmek için tekrar mikrofona bas.");

 } catch(e) {
  toast("Mikrofon izni yok. Telefonun ses kaydedicisini kullan.");
  $("micInput").click();
 }
};



messagesEl.appendChild(welcomeEl());
renderHistory();

/* Klavye açılınca uygulamayı görünür alana sığdır */
/* Android klavyesi için görünür alanı takip et */
function fitViewport() {
  const app = document.getElementById("app");
  const main = document.getElementById("main");
  const composer = document.getElementById("composerWrap");
  const viewport = window.visualViewport;

  const height = viewport
    ? viewport.height
    : window.innerHeight;

  const offsetTop = viewport
    ? viewport.offsetTop
    : 0;

  app.style.top = offsetTop + "px";
  app.style.height = height + "px";
  app.style.bottom = "auto";

  if (main) {
    main.style.minHeight = "0";
    main.style.overflow = "hidden";
  }

  if (composer) {
    composer.style.flexShrink = "0";
    composer.style.position = "relative";
    composer.style.visibility = "visible";
  }
}

if (window.visualViewport) {
  window.visualViewport.addEventListener("resize", fitViewport);
  window.visualViewport.addEventListener("scroll", fitViewport);
}

window.addEventListener("resize", fitViewport);
window.addEventListener("orientationchange", fitViewport);

fitViewport();

</script>
</body>
</html>'''


def resim_hazirla(raw, heic_mi):
    """EXIF dönüklüğünü düzeltir, büyük fotoğrafı küçültür, JPEG yapar."""
    try:
        from PIL import Image, ImageOps

        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
        except Exception:
            pass

        with Image.open(io.BytesIO(raw)) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((2400, 2400))
            cikti = io.BytesIO()
            im.save(cikti, format="JPEG", quality=92)
            return cikti.getvalue(), "image/jpeg", None
    except Exception as e:
        if heic_mi:
            return None, None, str(e)[:250]
        return raw, None, None


def extract_file(file):
    name = secure_filename(file.filename or "") or "dosya"
    raw = file.read()
    mime = file.mimetype or mimetypes.guess_type(name)[0] or ""
    uzanti = os.path.splitext(name)[1].lower()

    heic_mi = uzanti in (".heic", ".heif") or mime.lower() in (
        "image/heic", "image/heif", "image/heic-sequence",
        "image/heif-sequence",
    )

    if mime.startswith("image/") or heic_mi:
        yeni, yeni_mime, hata = resim_hazirla(raw, heic_mi)

        if hata:
            return {
                "type": "error",
                "text": f"HEIC fotoğrafı JPEG'e dönüştürülemedi. Detay: {hata}",
            }

        raw = yeni
        if yeni_mime:
            mime = yeni_mime
            name = os.path.splitext(name)[0] + ".jpg"

        return {
            "type": "image",
            "mime": mime or "image/jpeg",
            "data": base64.b64encode(raw).decode("ascii"),
            "name": name,
        }

    ses_uzantilari = (
        ".wav", ".mp3", ".m4a", ".ogg", ".webm",
        ".flac", ".mpga", ".aac", ".amr", ".3gp",
    )

    if mime.startswith("audio/") or name.lower().endswith(ses_uzantilari):
        try:
            files = {"file": (name, io.BytesIO(raw), mime or "audio/webm")}
            data = {"model": "whisper-large-v3-turbo", "response_format": "json"}

            r = requests.post(
                f"{API_URL}/audio/transcriptions",
                headers=groq_headers(),
                files=files,
                data=data,
                timeout=120,
            )

            if r.status_code != 200:
                raise RuntimeError(r.text[:300])

            transcript = (r.json().get("text") or "").strip()
            if not transcript:
                return {"type": "error", "text": "Ses anlaşılmadı. Lütfen tekrar konuş."}
            return {
                "type": "audio",
                "text": transcript,
                "name": name,
            }

        except Exception as e:
            return {"type": "text", "text": f"Ses çözümlenemedi: {e}"}

    if name.lower().endswith(".pdf"):
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(raw))
            text = "\n".join(p.extract_text() or "" for p in reader.pages)
            return {"type": "text", "text": f"PDF ({name}):\n{text[:25000]}"}

        except Exception as e:
            return {"type": "text", "text": f"PDF okunamadı: {e}"}

    if name.lower().endswith(".docx"):
        try:
            from zipfile import ZipFile
            from xml.etree import ElementTree

            with ZipFile(io.BytesIO(raw)) as z:
                xml = z.read("word/document.xml")

            root = ElementTree.fromstring(xml)
            text = " ".join(
                el.text or "" for el in root.iter() if el.tag.endswith("}t")
            )
            return {"type": "text", "text": f"DOCX ({name}):\n{text[:25000]}"}

        except Exception as e:
            return {"type": "text", "text": f"DOCX okunamadı: {e}"}

    metin_uzantilari = (
        ".txt", ".md", ".csv", ".json", ".py",
        ".js", ".html", ".css", ".xml", ".log",
    )

    if mime.startswith("text/") or name.lower().endswith(metin_uzantilari):
        return {
            "type": "text",
            "text": (
                f"Dosya içeriği ({name}):\n"
                + raw.decode("utf-8", errors="replace")[:25000]
            ),
        }

    return {
        "type": "text",
        "text": (
            f"{name} dosyası desteklenmiyor. "
            "TXT, PDF, DOCX, kod, fotoğraf veya ses dene."
        ),
    }


OCR_ISTEM = (
    "Bu fotoğraftaki bütün yazıyı AYNEN ve sırayla yaz. Çözme, yorum yapma.\n"
    "- Sayfa iki sütunluysa önce SOL sütunu yukarıdan aşağı, sonra SAĞ sütunu yaz.\n"
    "- Her sorunun numarasını, soru metnini ve A-E şıklarını olduğu gibi yaz. "
    "Soru numarası uydurma, yalnızca görünenleri yaz.\n"
    "- Şekil, grafik veya tablo varsa [ŞEKİL: ...] içinde ne gördüğünü yaz "
    "(ölçüler, oklar, kütleler, eksen ve sayı değerleri, hangi noktalar).\n"
    "- Kalemle çizilmiş daire, çarpı, çizik ve el yazısı işaretlerini YOK SAY.\n"
    "- Sayfa kenarında kesik kalan soru veya şık varsa [kesik] diye belirt.\n"
    "- Okunamayanı [okunamadı] diye belirt."
)


def resimden_metin(att):
    url = f"data:{att['mime']};base64,{att['data']}"

    for vm in VISION_MODELLER:
        try:
            r = groq_chat(
                {
                    "model": vm,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": OCR_ISTEM},
                            {"type": "image_url", "image_url": {"url": url}},
                        ],
                    }],
                    "temperature": 0,
                    "max_tokens": 6000,
                },
                timeout=120,
            )
        except requests.RequestException:
            continue

        if r.status_code == 200:
            try:
                t = r.json()["choices"][0]["message"].get("content") or ""
            except Exception:
                continue
            t = re.sub(r"<think>.*?</think>", "", t, flags=re.S).strip()
            if t:
                return t
            continue

        if r.status_code == 429 or model_hatasi(r):
            continue
        break

    return ""


@app.route("/")
def ana():
    isim = ""
    a = request.authorization

    if a and a.username:
        isim = a.username.strip()[:30]

    if isim:
        ilk = "İ" if isim[0] == "i" else isim[0].upper()
        isim = ilk + isim[1:]

    js_isim = json.dumps(isim).replace("<", "\\u003c")
    sayfa = HTML.replace("__ISIM__", js_isim)

    return Response(sayfa, mimetype="text/html; charset=utf-8")


@app.route("/sohbet", methods=["POST"])
def sohbet():
    if not API_KEY:
        return jsonify(
            ok=False,
            cevap="Sunucuda GROQ_API_KEY ayarlanmamış.",
        ), 500

    try:
        mesajlar = json.loads(request.form.get("mesajlar", "[]"))
        mesaj = request.form.get("mesaj", "").strip()
        uploaded_files = request.files.getlist("dosyalar")
        if not uploaded_files:
            uploaded_files = request.files.getlist("dosya")

        attachments = [
            extract_file(f)
            for f in uploaded_files
            if f and f.filename
        ]

        attachment_error = next(
            (a for a in attachments if a.get("type") == "error"),
            None,
        )
        if attachment_error:
            return jsonify(ok=False, cevap=attachment_error["text"]), 400

        if not mesaj and not attachments:
            return jsonify(ok=False, cevap="Mesaj veya dosya gönder."), 400

        api_messages = [{"role": "system", "content": SISTEM}]

        for item in mesajlar[-20:-1]:
            role = item.get("role")
            content = item.get("content", "")

            if role in ("user", "assistant") and isinstance(content, str):
                api_messages.append({"role": role, "content": content[:12000]})

        ses_metinleri = [
            (a.get("text") or "").strip()
            for a in attachments
            if a.get("type") == "audio" and (a.get("text") or "").strip()
        ]
        if ses_metinleri:
            user_content = (
                "Kullanıcının sesli mesajında söylediği sözler: "
                + " ".join(ses_metinleri)
                + "\nBuna doğrudan ve doğal bir sohbet yanıtı ver. "
                + "Dosyadan bahsetme ve kullanıcının dilinde cevap ver."
            )
        else:
            user_content = mesaj or "Eklediğim dosyaları incele ve yardımcı ol."
        low = user_content.lower()
        if "çevir" in low or "tercüme" in low:
            user_content += (
                "\n\n(Metnin TAMAMINI eksiksiz çevir. "
                "Hiçbir paragrafı veya cümleyi atlama, yarıda bırakma.)"
            )

        model = MODEL
        adaylar = None
        efor = "medium"
        metin_parcalari = []
        okunamayan_resimler = []
        test_notu = (
            "\n\n(Bu bir test sayfasıysa: her soruyu kendi numarasıyla, "
            "adım adım çöz, sonucu şıklarla eşleştir. Sonda tablo değil, "
            "düz 'Numara: Şık' listesi ver.)"
        )

        for attachment in attachments:
            if attachment["type"] == "image":
                efor = "high"
                ocr_text = resimden_metin(attachment)
                if ocr_text:
                    metin_parcalari.append(
                        test_notu
                        + "\n\n--- FOTOĞRAFTAN OKUNAN METİN: "
                        + attachment.get("name", "Fotoğraf")
                        + " ---\n"
                        + ocr_text
                    )
                else:
                    okunamayan_resimler.append(attachment)
            elif attachment["type"] == "audio":
                continue
            else:
                metin_parcalari.append(
                    "\n\n" + attachment.get("text", "")
                )

        if metin_parcalari:
            user_content += "".join(metin_parcalari)

        if okunamayan_resimler:
            icerik = [{"type": "text", "text": user_content + test_notu}]
            for attachment in okunamayan_resimler:
                icerik.append({
                    "type": "image_url",
                    "image_url": {
                        "url": (
                            f"data:{attachment['mime']};base64,"
                            f"{attachment['data']}"
                        )
                    },
                })
            user_content = icerik
            adaylar = list(VISION_MODELLER)

        api_messages.append({"role": "user", "content": user_content})

        if adaylar is None:
            adaylar = [model] + [m for m in YEDEK_MODELLER if m != model]

        r = None

        for aday in adaylar:
            govde = {
                "model": aday,
                "messages": api_messages,
                "temperature": 0.2,
                "max_tokens": 8000,
            }

            if aday.startswith("openai/gpt-oss"):
                govde["reasoning_effort"] = efor

            r = groq_chat(govde, timeout=150)

            if r.status_code == 429 or model_hatasi(r):
                continue

            break

        if r is None:
            return jsonify(ok=False, cevap="Kullanılabilir model bulunamadı."), 502

        if r.status_code != 200:
            try:
                detail = r.json().get("error", {}).get("message", r.text)
            except Exception:
                detail = r.text

            return jsonify(
                ok=False,
                cevap=f"Groq API hatası ({r.status_code}): {str(detail)[:500]}",
            ), 502

        answer = r.json()["choices"][0]["message"].get("content")

        if isinstance(answer, list):
            answer = "\n".join(
                p.get("text", "") for p in answer if isinstance(p, dict)
            )

        if not isinstance(answer, str):
            answer = str(answer or "Yanıt oluşturulamadı.")

        answer = re.sub(r"<think>.*?</think>", "", answer, flags=re.S).strip()

        return jsonify(ok=True, cevap=answer or "Yanıt oluşturulamadı.")

    except requests.Timeout:
        return jsonify(ok=False, cevap="İstek zaman aşımına uğradı. Tekrar dene."), 504

    except Exception as e:
        return jsonify(ok=False, cevap=f"Sunucu hatası: {str(e)[:300]}"), 500


@app.errorhandler(413)
def too_large(_):
    return jsonify(
        ok=False,
        cevap="Dosya çok büyük. En fazla 20 MB yükleyebilirsin.",
    ), 413


def yerel_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]

    except Exception:
        return "IP-bulunamadi"

    finally:
        s.close()


if __name__ == "__main__":
    if HOST != "127.0.0.1" and not SIFRE:
        print(
            "HATA: Ağa açıkken APP_SIFRE şart. "
            ".env dosyasına APP_SIFRE=... ekle."
        )
        raise SystemExit(1)

    print(f"\nBu telefon: http://127.0.0.1:{PORT}")

    if HOST != "127.0.0.1":
        print(f"Arkadaşın: http://{yerel_ip()}:{PORT} (aynı Wi-Fi)\n")

    app.run(host=HOST, port=PORT, debug=False)
