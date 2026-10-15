from pathlib import Path
import shutil
import sys
from datetime import datetime

p = Path("app.py")
s = p.read_text(encoding="utf-8")

yedek = Path(
    "app.py.yedek_sesli_tam_" +
    datetime.now().strftime("%Y%m%d_%H%M%S")
)

degisiklikler = [
    (
        '<button class="tool" id="mic" aria-label="Ses kaydet">',
        '<button class="tool" id="voiceMode" aria-label="Sesli sohbet" title="Sesli sohbet">🗣️</button>\n      <button class="tool" id="mic" aria-label="Ses kaydet">',
        "Sesli sohbet düğmesi"
    ),
    (
        '#mic.recording{background:#d33;color:white}',
        '#mic.recording{background:#d33;color:white}\n#voiceMode.voice-active{background:#315a43;color:#fff}',
        "Sesli sohbet CSS"
    ),
    (
        'let audioChunks = [];',
        'let audioChunks = [];\nlet sesliSohbetAktif = false;',
        "Sesli sohbet değişkeni"
    ),
    (
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
]

for eski, yeni, ad in degisiklikler:
    adet = s.count(eski)
    if adet != 1:
        print(f"HATA: {ad}: beklenen 1, bulunan {adet}")
        print("Dosya değiştirilmedi.")
        sys.exit(1)

if 'if (typeof sesliSohbetAktif !== "undefined" && sesliSohbetAktif)' not in s:
    print("HATA: Otomatik gönderme bölümü bulunamadı. Dosya değiştirilmedi.")
    sys.exit(1)

if 'addSpeechButton(bubble, data.cevap);' not in s:
    print("HATA: Yanıt seslendirme bölümü bulunamadı. Dosya değiştirilmedi.")
    sys.exit(1)

shutil.copy2(p, yedek)

for eski, yeni, ad in degisiklikler:
    s = s.replace(eski, yeni, 1)
    print("Eklendi:", ad)

p.write_text(s, encoding="utf-8")
print("Tamamlandı. Yedek:", yedek)
