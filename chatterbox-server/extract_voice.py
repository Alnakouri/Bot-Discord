"""
Script d'extraction de la voix de Sheogorath (Philippe Bozo) pour Chatterbox.

Usage:
    python extract_voice.py <URL_YOUTUBE>
    
    Ou sans URL pour utiliser le mode interactif.

Ce script :
1. Télécharge l'audio d'une vidéo YouTube de dialogues Sheogorath VF
2. Permet de couper un extrait propre de 10-15 secondes
3. Sauvegarde le fichier de référence pour Chatterbox

Conseils pour le sample :
- Choisir un passage où Sheogorath parle SEUL (pas d'autre personnage)
- Pas de musique de fond, pas d'effets sonores
- Le plus théâtral possible (c'est sa signature)
- Idéalement 10-15 secondes continues
"""

import sys
import os
import subprocess
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "voices"
OUTPUT_DIR.mkdir(exist_ok=True)

RAW_FILE = OUTPUT_DIR / "sheogorath_raw.wav"
REF_FILE = OUTPUT_DIR / "sheogorath_ref.wav"


def download_audio(url: str):
    """Télécharge l'audio d'une vidéo YouTube."""
    print(f"\n🎬 Téléchargement de l'audio depuis : {url}")
    
    cmd = [
        "yt-dlp",
        "-x",                          # Extraire l'audio
        "--audio-format", "wav",        # Format WAV
        "--audio-quality", "0",         # Meilleure qualité
        "-o", str(RAW_FILE),            # Fichier de sortie
        "--no-playlist",                # Pas de playlist
        url
    ]
    
    result = subprocess.run(cmd, capture_output=False)
    
    if result.returncode != 0:
        print("❌ Erreur lors du téléchargement.")
        return False
    
    # yt-dlp peut ajouter une extension différente
    for ext in [".wav", ".wav.wav", ".opus", ".webm"]:
        candidate = OUTPUT_DIR / f"sheogorath_raw{ext}"
        if candidate.exists():
            if candidate != RAW_FILE:
                candidate.rename(RAW_FILE)
            break
    
    if RAW_FILE.exists():
        size_mb = RAW_FILE.stat().st_size / (1024 * 1024)
        print(f"✅ Audio téléchargé : {RAW_FILE} ({size_mb:.1f} Mo)")
        return True
    else:
        print("❌ Fichier audio non trouvé après téléchargement.")
        return False


def get_audio_duration(filepath: Path) -> float:
    """Obtient la durée d'un fichier audio en secondes."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(filepath)],
            capture_output=True, text=True
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def cut_segment(start_seconds: float, duration: float = 12.0):
    """Coupe un segment de l'audio brut."""
    if not RAW_FILE.exists():
        print("❌ Fichier brut non trouvé. Téléchargez d'abord.")
        return False
    
    # Convertir en mm:ss pour l'affichage
    start_mm = int(start_seconds // 60)
    start_ss = int(start_seconds % 60)
    
    print(f"\n✂️ Extraction : {start_mm}:{start_ss:02d} → +{duration}s")
    
    cmd = [
        "ffmpeg", "-y",
        "-i", str(RAW_FILE),
        "-ss", str(start_seconds),
        "-t", str(duration),
        "-ar", "22050",               # 22kHz (optimal pour Chatterbox)
        "-ac", "1",                    # Mono
        "-acodec", "pcm_s16le",        # PCM 16-bit
        str(REF_FILE)
    ]
    
    result = subprocess.run(cmd, capture_output=True)
    
    if result.returncode == 0 and REF_FILE.exists():
        size_kb = REF_FILE.stat().st_size / 1024
        print(f"✅ Fichier de référence créé : {REF_FILE} ({size_kb:.0f} Ko)")
        print(f"   → Prêt pour Chatterbox !")
        return True
    else:
        print(f"❌ Erreur ffmpeg : {result.stderr.decode()[:200]}")
        return False


def interactive_mode():
    """Mode interactif pour choisir le segment."""
    total = get_audio_duration(RAW_FILE)
    if total <= 0:
        print("❌ Impossible de lire la durée du fichier.")
        return
    
    print(f"\n📏 Durée totale de l'audio : {int(total//60)}:{int(total%60):02d}")
    print("=" * 50)
    print("INSTRUCTIONS :")
    print("1. Écoute le fichier avec un lecteur audio")
    print(f"   → {RAW_FILE}")
    print("2. Note le timestamp où Sheogorath parle SEUL")
    print("3. Entre le début et la durée ci-dessous")
    print("=" * 50)
    
    try:
        start = input("\n⏱️ Début du passage (en secondes, ex: 83 pour 1:23) : ")
        start = float(start)
        
        dur = input("⏱️ Durée à extraire (défaut: 12s) : ").strip()
        dur = float(dur) if dur else 12.0
        
        cut_segment(start, dur)
    except ValueError:
        print("❌ Valeur invalide. Utilisez des nombres.")
    except KeyboardInterrupt:
        print("\n👋 Annulé.")


def main():
    print("=" * 60)
    print("🎭 EXTRACTEUR DE VOIX — Sheogorath (Philippe Bozo, VF TESO)")
    print("=" * 60)
    
    if len(sys.argv) > 1:
        url = sys.argv[1]
        
        # Vérifier si c'est un timestamp direct (pas d'URL)
        if url.replace(".", "").replace(":", "").isdigit():
            # Mode : python extract_voice.py <start> [duration]
            start = float(url)
            dur = float(sys.argv[2]) if len(sys.argv) > 2 else 12.0
            cut_segment(start, dur)
            return
        
        # Mode : python extract_voice.py <URL>
        if download_audio(url):
            interactive_mode()
    else:
        # Mode interactif complet
        if RAW_FILE.exists():
            print(f"\n📁 Fichier brut existant trouvé : {RAW_FILE}")
            choice = input("   Utiliser ce fichier ? (o/n) : ").strip().lower()
            if choice in ("o", "oui", "y", "yes", ""):
                interactive_mode()
                return
        
        url = input("\n🔗 Colle l'URL YouTube d'une vidéo de dialogues Sheogorath VF : ").strip()
        if url:
            if download_audio(url):
                interactive_mode()
        else:
            print("❌ Pas d'URL fournie.")


if __name__ == "__main__":
    main()
