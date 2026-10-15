from pathlib import Path
import re
import shutil
import sys
from datetime import datetime

p = Path("app.py")
s = p.read_text(encoding="utf-8")

# Önce yeni yedek oluştur.
backup = Path("app.py.yedek_tek_dugme_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
shutil.copy2(p, backup)
print("Yedek:", backup)

# Beklenen eski sesli sohbet düğmesini bul.
pattern = r'\$\("voiceMode"\)\.onclick\s*=\s*\(\)\s*=>\s*\{.*?\n\};(?=\s*\n\$\("mic"\)\.onclick)'
m = re.search(pattern, s, re.S)
if not m:
    print("HATA: Eski sesli sohbet düğmesi bulunamadı. Dosya değiştirilmedi.")
    sys.exit(1)

new_handler = r'''
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

      if (rms > 0.018) {
        speechDetected = true;
        lastLoudAt = now;
      }

      if (speechDetected && now - lastLoudAt > 1300) {
        voiceStatus("Konuşman alındı, yanıt hazırlanıyor…");
        recorder.stop();
        return;
      }

      if (now - startedAt > 15000) {
        recorder.stop();
        return;
      }

      if (!speechDetected && now - startedAt > 8000) {
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
'''

s = s[:m.start()] + new_handler + s[m.end():]

# Yanıt okunurken durum göster; ses bitince yeniden dinlemeye başla.
old = '''   ses.lang = "tr-TR";
   ses.rate = 1;
   speechSynthesis.speak(ses);'''
new = '''   ses.lang = "tr-TR";
   ses.rate = 1;
   ses.onstart = () => {
    if (sesliSohbetAktif) voiceStatus("Yanıt veriyorum…");
   };
   ses.onend = () => {
    if (sesliSohbetAktif && !voiceClosing) {
     voiceStatus("Yeniden dinliyorum…");
     setTimeout(() => startVoiceRecording(), 350);
    }
   };
   ses.onerror = () => {
    if (sesliSohbetAktif && !voiceClosing) {
     setTimeout(() => startVoiceRecording(), 500);
    }
   };
   if (sesliSohbetAktif) voiceStatus("Yanıt hazırlanıyor…");
   speechSynthesis.speak(ses);'''

if old not in s:
    print("HATA: Seslendirme bölümü bulunamadı. Yedek oluşturuldu; dosya değiştirilmedi.")
    sys.exit(1)

s = s.replace(old, new, 1)

p.write_text(s, encoding="utf-8")
print("Güncelleme tamamlandı.")
print("Yedek dosya:", backup)
