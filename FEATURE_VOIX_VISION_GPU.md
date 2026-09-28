# Feature parkée — Voix clonée (TTS) + Vision locale (GPU)

> ⚠️ **MAJ 2026-09-28 : la VOIX est ABANDONNÉE** (décision d'Ahmed). `chatterbox-server/`,
> `Sheogorath/sheo_voice.py` et les commandes vocales sont supprimés (SUITES 16 et 17). Les
> enregistrements de référence sont archivés hors dépôt dans `D:\Archives\BotDiscordoix-sheogorath`.
> Tout ce qui suit sur la voix est historique ; seule la **vision** reste valable.
>
> **Statut : retirée du déploiement le 2026-06-17.** À refaire autrement plus tard.
> Le **code reste dans le repo** (inerte, dégradation propre). Seuls les services
> Docker GPU ont été retirés du `docker-compose.yml`.

## Pourquoi c'est parti

Cible de déploiement = **Oracle Cloud free tier** (Ampere A1 : 4 OCPU ARM / 24 Go RAM,
**aucun GPU**). Les deux services concernés exigent un GPU NVIDIA (`runtime: nvidia`)
et ne peuvent pas y tourner :

| Service retiré | Rôle | Coût |
|---|---|---|
| `chatterbox-tts` | Voix clonée de Sheogorath (Philippe Bozo, VF TESO) via Chatterbox Turbo | image PyTorch+CUDA (~6-8 Go), modèle 350M, **~3-4 Go VRAM** |
| `bots-ollama-vision` (+ `ollama-model-init`) | Vision locale d'images via Moondream sur Ollama | GPU + VRAM, image Ollama |

Les **6 bots Discord** eux-mêmes restent légers (`python:3.11-slim`, inférence déléguée
aux API cloud) et tournent sans souci sur Oracle free tier.

## Ce qui a changé (et ce qui n'a PAS changé)

**Retiré** (`docker-compose.yml` uniquement) :
- services `bots-ollama-vision`, `ollama-model-init`, `chatterbox-tts`
- volume `chatterbox-models`
- env vars `OLLAMA_VISION_URL` / `PIPER_TTS_URL` et le `depends_on: chatterbox-tts` de Sheogorath

**Conservé tel quel** (à NE PAS supprimer — c'est la base du futur re-build) :
- `chatterbox-server/` (Dockerfile + `server.py` FastAPI + voix de réf.)
- `Sheogorath/sheo_voice.py` (pipeline TTS complet : préparation texte, humeurs, vocal Discord)
- `shared/media_handler.py::process_image_ollama` (vision locale Moondream)

## Pourquoi rien ne casse sans ces services

Les deux intégrations **dégradent proprement** (vérifié) :

- **TTS** — `check_piper_available()` fait un fast-fail (cache 60s), `send_voice_response()`
  renvoie `False`. Sheogorath répond simplement **en texte, sans voix**. Aucun crash.
- **Vision** — `process_image_ollama()` fast-fail en 3s → `None` → la **cascade LLM continue
  automatiquement vers Gemini cloud** (`process_image`). **La vision marche toujours**,
  juste via Gemini au lieu de Moondream local.

## Pistes pour la refonte (« m'y prendre autrement »)

- TTS : envisager un service **CPU-only** (Piper natif, déjà partiellement supporté par
  `sheo_voice.py` qui tente `/health` Chatterbox puis fallback `GET /?text=`), ou un TTS
  **API cloud** (ElevenLabs est déjà dans `requirements.txt`).
- Vision : s'appuyer sur la **vision Gemini cloud** (déjà le fallback actif), ou un service
  vision distant hébergé sur la machine GPU maison + tunnel.
- Si on garde du GPU local : réintroduire via un **profil Docker** (`profiles: [gpu]`) plutôt
  qu'en dur, pour qu'Oracle ne les lance pas et que la machine maison les active à la demande.

## Pour réactiver à l'identique (machine GPU)

Récupérer l'ancien bloc des 3 services dans l'historique git de `docker-compose.yml`
(commit précédant le retrait) et restaurer aussi les env vars `OLLAMA_VISION_URL` /
`PIPER_TTS_URL` + `depends_on` de Sheogorath.
