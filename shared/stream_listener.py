import os
import json
import logging
import asyncio
import hashlib
import time

logger = logging.getLogger("stream_listener")


# Handles os.add_dll_directory : DOIVENT rester vivants (sinon le GC retire le dossier
# DLL → cublas64_12.dll introuvable à la transcription). On les garde au niveau module.
_CUDA_DLL_HANDLES = []


def _ensure_cuda_dll_path():
    """Windows : ajoute les DLL CUDA (cuBLAS/cuDNN installées via pip dans le venv)
    au chemin de recherche, sinon ctranslate2 ne les trouve pas pour le GPU. No-op
    ailleurs (Linux, ou bibliothèques absentes)."""
    if os.name != "nt":
        return
    try:
        import site, glob
        roots = list(site.getsitepackages())
        try:
            roots.append(site.getusersitepackages())
        except Exception:
            pass
        for sp in roots:
            for d in glob.glob(os.path.join(sp, "nvidia", "*", "bin")):
                try:
                    _CUDA_DLL_HANDLES.append(os.add_dll_directory(d))  # garder le handle vivant
                except Exception:
                    pass
                # Ceinture+bretelles : PATH (persistant) pour les DLL chargées en cascade.
                if d not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
    except Exception as e:
        logger.warning(f"⚠️ [STREAM_LISTENER] Ajout DLL CUDA échoué : {e}")


# Phrases d'hallucination typiques de Whisper sur le silence/bruit (à ne jamais diffuser).
_HALLUCINATION_MARKERS = (
    "amara.org",
    "sous-titres réalisés",
    "sous-titrage",
    "merci d'avoir regardé",
    "merci de votre attention",
    "abonnez-vous",
    "sous-titres faits par",
)

# Imports défensifs
DEPS_AVAILABLE = False
try:
    import numpy as np
    import sounddevice as sd
    DEPS_AVAILABLE = True
except ImportError:
    logger.warning("⚠️ [STREAM_LISTENER] sounddevice ou numpy manquant. L'écoute continu sera inactive localement.")

WHISPER_AVAILABLE = False
try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    logger.warning("⚠️ [STREAM_LISTENER] faster-whisper non installé. Mode C non disponible localement.")

# Bascule auto GPU : paliers du plus léger au plus lourd + VRAM approx. (Mo, float16).
_MODEL_TIERS = ["small", "medium", "large-v3-turbo"]
_MODEL_VRAM_MB = {"small": 600, "medium": 1600, "large-v3-turbo": 2100}


class StreamListenerHub:
    """
    Hub Windows unique capturant le micro et distribuant les transcriptions aux bots.
    Gère également l'arbitrage (1 seule réponse max par énoncé).
    """
    def __init__(self, port: int = 8765, mode: str = "C", model_size: str = "large-v3-turbo", device: str = "cpu", voice_min_interval: float = 45.0, input_device=None, initial_prompt=None, rms_threshold: float = 0.02, max_segment_sec: float = 12.0, auto_switch: bool = False):
        self.port = port
        self.mode = mode  # A (NIM), B (NeMo), C (Whisper)
        self.model_size = model_size      # modèle ACTUEL (peut changer si auto_switch)
        self.max_model_size = model_size  # plafond = modèle configuré (jamais au-dessus)
        self.device = device              # device de CALCUL ASR (cpu/cuda)
        self.input_device = input_device  # périphérique micro sounddevice (index/nom) ; None = défaut Windows
        self.initial_prompt = initial_prompt  # biaise Whisper vers le vocabulaire (noms des bots)
        self.rms_threshold = rms_threshold    # seuil anti-silence/bruit (monte-le si bruit de fond)
        self.max_segment_sec = max_segment_sec  # plafond dur de durée d'un énoncé (anti-accumulation)
        self.auto_switch = auto_switch    # GPU : descend le modèle si la VRAM se remplit (jeu)
        self._last_switch_ts = 0.0
        self.voice_min_interval = voice_min_interval
        self.last_grant_ts = 0.0
        self.enabled = False
        self.clients = set()
        self.claim_locks = {}  # text_hash -> bot_id
        self._stopped = False
        self.whisper_model = None

    async def start(self):
        self.enabled = True
        logger.info(f"🎤 [STREAM_LISTENER] Démarrage du hub sur le port {self.port} (Mode: {self.mode})")

        if self.mode == "C" and WHISPER_AVAILABLE:
            try:
                if self.device == "cuda":
                    _ensure_cuda_dll_path()
                compute_type = "float16" if self.device == "cuda" else "int8"
                logger.info(f"🧠 Chargement du modèle Whisper {self.model_size} sur {self.device} ({compute_type})...")
                self.whisper_model = WhisperModel(self.model_size, device=self.device, compute_type=compute_type)
                logger.info("✅ Modèle Whisper chargé avec succès.")
            except Exception as e:
                logger.error(f"❌ Échec chargement Whisper ({self.device}): {e}")
                if self.device == "cuda":
                    logger.warning("↩️ Repli sur CPU (int8)...")
                    try:
                        self.whisper_model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
                        self.device = "cpu"  # repli effectif → pas de bascule VRAM
                        logger.info("✅ Modèle Whisper chargé sur CPU (repli).")
                    except Exception as e2:
                        logger.error(f"❌ Échec repli CPU: {e2}")
                        self.whisper_model = None
                else:
                    self.whisper_model = None

        # Serveur WebSocket
        try:
            import websockets
        except ImportError:
            logger.error("❌ websockets non installé. Hub désactivé.")
            return

        async def handler(websocket):
            self.clients.add(websocket)
            logger.info(f"🔌 Client Bot connecté au Hub. Total: {len(self.clients)}")
            try:
                async for message in websocket:
                    data = json.loads(message)
                    action = data.get("action")
                    if action == "claim":
                        text_hash = data.get("hash")
                        bot_id = data.get("bot_id")
                        now = time.time()
                        if now - self.last_grant_ts < self.voice_min_interval:
                            granted = False                      # intervalle global (tous bots confondus)
                        elif text_hash not in self.claim_locks:
                            self.claim_locks[text_hash] = bot_id # 1er arrivé gagne, jamais d'écrasement
                            self.last_grant_ts = now
                            granted = True
                        else:
                            granted = False                      # déjà pris par un autre bot
                        await websocket.send(json.dumps(
                            {"type": "claim_response", "hash": text_hash, "granted": granted}))
                        logger.info(f"{'🏆 Claim accordé à' if granted else '⛔ Claim refusé à'} {bot_id} ({text_hash})")
            except websockets.exceptions.ConnectionClosed:
                pass
            finally:
                self.clients.remove(websocket)
                logger.info(f"🔌 Client Bot déconnecté. Total: {len(self.clients)}")

        self.server = await websockets.serve(handler, "localhost", self.port)
        if DEPS_AVAILABLE:
            asyncio.create_task(self._capture_and_process())
        else:
            logger.warning("⚠️ Capture audio non démarrée (sounddevice/numpy manquant). Le hub fonctionnera en WS uniquement.")

        if self.auto_switch and self.device == "cuda" and self.whisper_model is not None:
            asyncio.create_task(self._vram_watch_loop())

    async def _set_model(self, new_size: str):
        """Recharge Whisper avec une autre taille (bascule auto VRAM). Atomique :
        on charge le nouveau modèle PUIS on échange la référence."""
        if new_size == self.model_size or not WHISPER_AVAILABLE:
            return
        loop = asyncio.get_running_loop()
        logger.info(f"🔄 [STREAM_LISTENER] Bascule modèle {self.model_size} → {new_size} (VRAM)...")
        try:
            new_model = await loop.run_in_executor(
                None, lambda: WhisperModel(new_size, device="cuda", compute_type="float16")
            )
            old = self.whisper_model
            self.whisper_model = new_model
            self.model_size = new_size
            del old
            import gc
            gc.collect()
            self._last_switch_ts = time.time()
            logger.info(f"✅ [STREAM_LISTENER] Modèle actif : {new_size}")
        except Exception as e:
            logger.error(f"❌ [STREAM_LISTENER] Bascule modèle échouée : {e}")

    async def _vram_watch_loop(self):
        """Surveille la VRAM libre et descend/remonte le modèle (plafond = max_model_size).
        Décision basée sur la VRAM 'externe' (hors notre modèle) → stable, pas de flapping."""
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        except Exception as e:
            logger.warning(f"⚠️ [STREAM_LISTENER] Bascule auto VRAM indisponible (pynvml) : {e}")
            return

        ceiling_idx = _MODEL_TIERS.index(self.max_model_size) if self.max_model_size in _MODEL_TIERS else len(_MODEL_TIERS) - 1
        logger.info(f"🎛️ [STREAM_LISTENER] Bascule auto VRAM active (plafond : {self.max_model_size}).")

        while not self._stopped:
            await asyncio.sleep(8)
            if time.time() - self._last_switch_ts < 30:  # cooldown anti-flapping
                continue
            try:
                free_mb = pynvml.nvmlDeviceGetMemoryInfo(handle).free / (1024 * 1024)
            except Exception:
                continue
            # VRAM dispo SI notre modèle n'était pas chargé (décision indépendante du modèle courant)
            external_free = free_mb + _MODEL_VRAM_MB.get(self.model_size, 2000)
            if external_free >= 3200:
                want_idx = 2  # large-v3-turbo
            elif external_free >= 2200:
                want_idx = 1  # medium
            else:
                want_idx = 0  # small
            want_idx = min(want_idx, ceiling_idx)
            target = _MODEL_TIERS[want_idx]
            if target != self.model_size:
                logger.info(f"🎛️ [STREAM_LISTENER] VRAM libre ~{free_mb:.0f} Mo → cible {target}")
                await self._set_model(target)

    async def _capture_and_process(self):
        logger.info("🎤 [STREAM_LISTENER] Enregistrement audio en cours d'écoute (Input Stream)...")
        
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()
        
        def audio_callback(indata, frames, time_info, status):
            if status:
                logger.warning(f"⚠️ [STREAM_LISTENER] Statut InputStream: {status}")
            loop.call_soon_threadsafe(queue.put_nowait, indata.copy())
            
        sample_rate = 16000
        channels = 1
        
        try:
            if self.input_device is not None:
                try:
                    _name = sd.query_devices(self.input_device)["name"]
                except Exception:
                    _name = "?"
                logger.info(f"🎚️ [STREAM_LISTENER] Micro forcé : index/nom={self.input_device} ({_name})")
            stream = sd.InputStream(
                samplerate=sample_rate,
                channels=channels,
                dtype='float32',
                device=self.input_device,
                callback=audio_callback
            )
        except Exception as e:
            logger.error(f"❌ Échec de l'ouverture du flux audio sounddevice (device={self.input_device}): {e}")
            return
            
        rms_threshold = self.rms_threshold
        max_segment_sec = self.max_segment_sec
        accumulated_audio = []
        segment_duration = 0.0
        silence_duration = 0.0
        has_speech = False

        async def _finalize():
            nonlocal accumulated_audio, segment_duration, silence_duration, has_speech
            blocks = accumulated_audio
            accumulated_audio = []
            segment_duration = 0.0
            silence_duration = 0.0
            has_speech = False
            await self._process_accumulated_audio(blocks)

        with stream:
            while not self._stopped:
                try:
                    block = await asyncio.wait_for(queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    if has_speech:
                        silence_duration += 0.1
                        if silence_duration >= 0.7:
                            await _finalize()
                    continue

                rms = np.sqrt(np.mean(block**2))
                block_duration = len(block) / sample_rate

                if rms > rms_threshold:
                    has_speech = True
                    silence_duration = 0.0
                    accumulated_audio.append(block)
                    segment_duration += block_duration
                else:
                    if has_speech:
                        accumulated_audio.append(block)
                        segment_duration += block_duration
                        silence_duration += block_duration
                        if silence_duration >= 0.7:
                            await _finalize()
                            continue

                # Filet de sécurité : ne jamais accumuler plus de max_segment_sec
                # (sinon un bruit de fond continu au-dessus du seuil crée des segments
                # de plusieurs minutes → latence énorme + audio jeté par le VAD).
                if has_speech and segment_duration >= max_segment_sec:
                    await _finalize()

    async def _process_accumulated_audio(self, blocks):
        if not blocks or not DEPS_AVAILABLE:
            return
        
        audio_data = np.concatenate(blocks, axis=0).flatten()
        duration = len(audio_data) / 16000
        if duration < 0.5:
            return
            
        if self.mode == "C" and self.whisper_model and WHISPER_AVAILABLE:
            try:
                logger.info(f"🎙️ Transcription d'un segment de {duration:.2f}s...")
                loop = asyncio.get_running_loop()

                def _do_transcribe():
                    # transcribe() renvoie (générateur de segments, info) ; le vrai calcul
                    # a lieu en consommant le générateur → tout faire DANS l'executor.
                    # vad_filter : coupe le silence avant ASR (tue les hallucinations).
                    # condition_on_previous_text=False : évite les boucles de répétition.
                    seg_gen, _info = self.whisper_model.transcribe(
                        audio_data, language="fr", beam_size=5,
                        vad_filter=True, condition_on_previous_text=False,
                        initial_prompt=self.initial_prompt
                    )
                    return " ".join(seg.text for seg in seg_gen).strip()

                text = await loop.run_in_executor(None, _do_transcribe)
                if not text:
                    return
                low = text.lower()
                if any(m in low for m in _HALLUCINATION_MARKERS):
                    logger.info(f"🔇 Hallucination Whisper ignorée: \"{text}\"")
                    return
                words = text.split()
                if len(words) >= 3 and not all(w.lower() in ["euh", "ah", "oh", "hein"] for w in words):
                    await self.broadcast(text)
                else:
                    logger.info(f"🔇 Transcrit ignoré (trop court/bruit): \"{text}\"")
            except Exception as e:
                logger.error(f"❌ Erreur lors de la transcription Whisper: {e}")

    async def broadcast(self, text: str):
        if not text or not self.clients:
            return
        text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
        msg = json.dumps({
            "type": "transcript",
            "text": text,
            "hash": text_hash
        })
        logger.info(f"📡 Diffusion du transcrit : \"{text}\"")
        for ws in list(self.clients):
            try:
                await ws.send(msg)
            except Exception:
                pass

    def stop(self):
        self._stopped = True
        if hasattr(self, "server"):
            self.server.close()


class StreamListenerClient:
    """
    Client à instancier dans chaque bot pour se connecter au Hub d'écoute continu.
    """
    def __init__(self, bot_id: str, logger, on_transcript_received_callback, port: int = 8765):
        self.bot_id = bot_id
        self.logger = logger
        self.on_transcript = on_transcript_received_callback
        self.port = port
        self._stopped = False
        self.ws = None
        self.pending_claims = {} # hash -> future

    async def run(self):
        self.logger.info(f"🎙️ [STREAM_CLIENT:{self.bot_id}] Connexion au Hub d'écoute continu...")
        backoff = 1
        while not self._stopped:
            try:
                import websockets
                async with websockets.connect(f"ws://localhost:{self.port}") as ws:
                    self.ws = ws
                    backoff = 1
                    self.logger.info(f"🎙️ [STREAM_CLIENT:{self.bot_id}] Connecté au Hub.")
                    async for message in ws:
                        data = json.loads(message)
                        msg_type = data.get("type")
                        
                        if msg_type == "transcript":
                            text = data.get("text")
                            text_hash = data.get("hash")
                            asyncio.create_task(self.on_transcript(text, text_hash))
                            
                        elif msg_type == "claim_response":
                            text_hash = data.get("hash")
                            granted = data.get("granted", False)
                            future = self.pending_claims.pop(text_hash, None)
                            if future and not future.done():
                                future.set_result(granted)
            except Exception as e:
                self.logger.warning(f"🎙️ [STREAM_CLIENT:{self.bot_id}] Déconnecté du Hub : {e}")
            
            if self._stopped:
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

    async def request_claim(self, text_hash: str, priority: bool = False) -> bool:
        if not self.ws:
            return False
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self.pending_claims[text_hash] = future
        
        try:
            await self.ws.send(json.dumps({
                "action": "claim",
                "hash": text_hash,
                "bot_id": self.bot_id,
                "priority": priority
            }))
            # Attendre au maximum 2 secondes la réponse du Hub
            return await asyncio.wait_for(future, timeout=2.0)
        except Exception as e:
            self.logger.error(f"❌ [STREAM_CLIENT:{self.bot_id}] Échec de la requête de claim: {e}")
            self.pending_claims.pop(text_hash, None)
            return False

    def stop(self):
        self._stopped = True
