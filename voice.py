"""
Voix de l'ingénieur (étape 2).

- Voix principale : Piper (gratuit, local), voix française "Jessica" (fr_FR-upmc-medium).
  Le fichier de voix (~77 Mo) est téléchargé une seule fois au premier lancement.
- Effet radio : filtre passe-bande + légère saturation + petit "clic" de micro.
- Secours : si Piper n'est pas disponible, la voix intégrée de Windows prend le relais.

Les messages urgents (box, neutralisation) passent devant les autres.
"""

from __future__ import annotations

import io
import math
import queue
import re
import subprocess
import sys
import threading
import urllib.request
import wave
from pathlib import Path

HERE = Path(__file__).parent
from paths import DATA, LOCAL  # noqa: E402
MODELS = LOCAL / "models"
import i18n

VOICES = {   # langue -> (nom du modèle, dossier sur Hugging Face, n° de voix, nom affiché)
    "fr": ("fr_FR-upmc-medium", "fr/fr_FR/upmc/medium/", 0, "Jessica"),        # CC BY-SA 4.0 (MaryTTS upmc)
    "en": ("en_US-ljspeech-high", "en/en_US/ljspeech/high/", 0, "LJ"),          # domaine public (LJ Speech)
}
BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
SPEAKER = 0
SPEED = 0.92         # < 1 = plus rapide
RADIO_EFFECT = True


def spoken(text: str) -> str:
    """Adapte le texte pour qu'il soit bien prononcé."""
    if i18n.en():
        text = text.replace("%", " percent").replace("°", " degrees")
    else:
        text = re.sub(r"(\d)\.(\d)", r"\1,\2", text)      # 3.6 -> 3,6
        text = text.replace("%", " pour cent").replace("°", " degrés")
    text = re.sub(r"\bP(\d+)\b", r"P \1", text)
    text = text.replace("!", ".")
    return text


def _download(url: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"  Téléchargement de la voix : {dest.name} …")
    with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while chunk := r.read(1 << 16):
            f.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {done * 100 // total:3d} %", end="", flush=True)
    print()
    tmp.replace(dest)


def _radio(pcm16: bytes, rate: int, volume: float = 1.3) -> bytes:
    """Effet radio : bande 300–3400 Hz, saturation douce, petit clic de micro."""
    import numpy as np

    x = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / rate)
    gain = np.clip((f - 200) / 150, 0, 1) * np.clip((3800 - f) / 600, 0, 1)
    x = np.fft.irfft(spec * gain, n=len(x))
    # volume : plus de "compression" radio + niveau plus haut (1.0 = ancien niveau, 1.6 = max)
    x = np.tanh(2.2 * volume * x / (np.max(np.abs(x)) or 1.0)) * min(0.99, 0.6 + 0.25 * volume)
    i = np.arange(int(rate * 0.012))
    click = 0.5 * np.sin(i * 0.9) * np.exp(-i / 40)
    gap = np.zeros(int(rate * 0.04))
    y = np.concatenate([click, gap, x, gap, click])
    return (np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes()


class Voice:
    def __init__(self) -> None:
        self.enabled = True
        self.quiet = False      # mode silence : seulement l'urgent (box, neutralisation, spotter, réponses)
        self.volume = 1.3
        self.engine = "aucune"
        self._q: queue.PriorityQueue = queue.PriorityQueue()
        self._n = 0
        self._piper = None
        threading.Thread(target=self._worker, daemon=True).start()

    # ------------------------------------------------------------ chargement
    def _load(self) -> None:
        try:
            from piper import PiperVoice  # noqa
            MODELS.mkdir(parents=True, exist_ok=True)
            name, folder, self.speaker, shown = VOICES[i18n.LANG]
            url = BASE_URL + folder + name
            onnx = MODELS / f"{name}.onnx"
            cfg = MODELS / f"{name}.onnx.json"
            if not cfg.exists():
                _download(url + ".onnx.json", cfg)
            if not onnx.exists():
                _download(url + ".onnx", onnx)
            self._piper = PiperVoice.load(onnx, config_path=cfg)
            self.engine = f"Piper · {shown}"
        except Exception as e:
            import traceback; traceback.print_exc()
            print(f"  Voix Piper indisponible ({e!r}). Utilisation de la voix Windows.")
            self.engine = "Windows" if sys.platform == "win32" else "aucune"
        print(f"  Voix : {self.engine}")

    # ------------------------------------------------------------ API
    def flush(self) -> None:
        """Vide la file d'attente (changement de langue)."""
        try:
            while True:
                self._q.get_nowait()
        except queue.Empty:
            pass

    def say(self, text: str, urgent: bool = False, spot: bool = False) -> None:
        """spot=True : message du spotter (« à gauche »), passe devant tout et est jeté s'il arrive trop tard."""
        if not self.enabled or (self.quiet and not urgent and not spot):
            return
        self._n += 1
        import time as _t
        self._q.put((-1 if spot else 0 if urgent else 1, self._n, text, _t.monotonic(), spot))

    # ------------------------------------------------------------ rendu
    def _render_piper(self, text: str) -> bytes:
        from piper import SynthesisConfig
        cfg = SynthesisConfig(speaker_id=getattr(self, "speaker", SPEAKER), length_scale=SPEED)
        pcm = bytearray()
        rate = 22050
        for chunk in self._piper.synthesize(text, syn_config=cfg):
            pcm += chunk.audio_int16_bytes
            rate = chunk.sample_rate
        data = _radio(bytes(pcm), rate, self.volume) if RADIO_EFFECT else bytes(pcm)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
            w.writeframes(data)
        return buf.getvalue()

    def _play(self, wav: bytes) -> None:
        if sys.platform == "win32":
            import winsound
            winsound.PlaySound(wav, winsound.SND_MEMORY)
        else:  # tests hors Windows : on enregistre le fichier
            (LOCAL / "derniere_annonce.wav").write_bytes(wav)

    def _speak_windows(self, text: str) -> None:
        safe = text.replace("'", "''")
        ps = ("Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              f"$v=$s.GetInstalledVoices()|?{{$_.VoiceInfo.Culture.Name -like '{i18n.LANG}*'}}|select -First 1; "
              "if($v){$s.SelectVoice($v.VoiceInfo.Name)}; $s.Rate=1; "
              f"$s.Speak('{safe}')")
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode:
            print(f"  Erreur voix Windows : {r.stderr.strip()[:300]}")

    def _worker(self) -> None:
        self._load()
        loaded = i18n.LANG
        while True:
            _, _, text, t0, spot = self._q.get()
            import time as _t
            if i18n.LANG != loaded:           # langue changée : on charge l'autre voix
                loaded = i18n.LANG
                self._piper = None
                self._load()
            if spot and _t.monotonic() - t0 > 1.2:
                continue   # info du spotter périmée : on ne la dit pas
            print(f"  [radio] {text}")
            if not self.enabled:
                continue
            try:
                t = spoken(text)
                if self._piper is not None:
                    self._play(self._render_piper(t))
                elif self.engine == "Windows":
                    self._speak_windows(t)
            except Exception as e:
                import traceback; traceback.print_exc()
                print(f"  Erreur voix : {e!r}")
