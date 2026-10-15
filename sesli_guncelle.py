from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime

p = Path("app.py")
s = p.read_text(encoding="utf-8")

yedek = Path("app.py.yedek_sesli_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
shutil.copy2(p, yedek)

def degistir(eski, yeni, ad):
    global s
    adet = s.count(eski)
    if adet != 1:
        print(f"HATA: {ad} bölümü 1 kez bulunmalı; bulunan: {adet}")
        print("Dosya değiştirilmedi. Yedek:", yedek)
        sys.exit(1)
    s = s.replace(eski, yeni, 1)

degistir(
    '<button class="tool" id="mic" aria-label="Ses kaydet">',
    '<button class="tool" id="voiceMode" aria-label="Sesli sohbet" title="Sesli sohbet">🗣️</button>\n      <button class="tool" id="mic" aria-label="Ses kaydet">',
    "Sesli sohbet düğmesi"
)

degistir(
    '#mic.recording{background:#d33;color:white}',
    '#mic.recording{background:#d33;color:white}\n'
    '#voiceMode.voice-active{background:#315a43;color:#fff}',
    "Sesli sohbet tasarımı"
)

degistir(
    'let audioChunks = [];',
    'let audioChunks = [];\nlet sesliSohbetAktif = false;',
    "Sesli sohbet durumu"
)

degistir(
    '$("mic").onclick = async () => {',
    '''$("voiceMode").onclick = () => {
  sesliSohbetAktif = !sesliSohbetAktif;
  $("voiceMode").classList.toggle("voice-active", sesliSohbetAktif);
  $("voiceMode").textContent = sesliSohbetAktif ? "🔊" : "🗣️";
  toast(sesliSohbetAktif
    ? "Sesli sohbet açıldı. Mikrofonla konuş."
    : "Sesli sohbet kapatıldı.");
  if (!sesliSohbetAktif && "speechSynthesis" in window) {
    speechSynthesis.cancel();
  }
};

$("mic").onclick = async () => {''',
    "Sesli sohbet kontrolü"
)

degistir(
    '''    $("filename").textContent = "🎙 Ses kaydı hazır";
    $("preview").style.display = "block";
    toast("Ses hazır. Göndermek için oka bas.");''',
    '''    $("filename").textContent = "🎙 Ses kaydı hazır";
    $("preview").style.display = "block";

    if (sesliSohbetAktif) {
     toast("Ses gönderiliyor...");
     sendMessage();
    } else {
     toast("Ses hazır. Göndermek için oka bas.");
    }''',
    "Kaydı otomatik gönderme"
)

degistir(
    '''   bindCopy(bubble);
   addSpeechButton(bubble, data.cevap);

   conversation.push({role: "assistant", content: data.cevap});''',
    '''   bindCopy(bubble);
   addSpeechButton(bubble, data.cevap);

   if (sesliSohbetAktif) {
    if ("speechSynthesis" in window) {
     speechSynthesis.cancel();
     const okunacak = String(data.cevap)
      .replace(/```[\\\\s\\\\S]*?```/g, "Kod bloğu")
      .replace(/[*#`_>]/g, "");
     const ses = new SpeechSynthesisUtterance(okunacak);
     ses.lang = "tr-TR";
     ses.rate = 1;
     speechSynthesis.speak(ses);
    } else {
     toast("Bu Android WebView sesli yanıtı desteklemiyor.");
    }
   }

   conversation.push({role: "assistant", content: data.cevap});''',
    "Yanıtı otomatik seslendirme"
)

p.write_text(s, encoding="utf-8")
print("Sesli sohbet kodu eklendi.")
print("Yedek:", yedek)
