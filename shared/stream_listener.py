import os
import json
import logging
import asyncio
import hashlib
import time

logger = logging.getLogger("stream_listener")

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


class StreamListenerHub:
    """
    Hub Windows unique capturant le micro et distribuant les transcriptions aux bots.
    Gère également l'arbitrage (1 seule réponse max par énoncé).
    """
    def __init__(self, port: int = 8765, mode: str = "C", model_size: str = "large-v3-turbo", device: str = "cpu"):
        self.port = port
        self.mode = mode  # A (NIM), B (NeMo), C (Whisper)
        self.model_size = model_size
        self.device = device
        self.enabled = False
        self.clients = set()
        self.claim_locks = {}  # text_hash -> bot_id
        self._stopped = False
        self.whisper_model = None

    async def start(self):
        if not DEPS_AVAILABLE:
            logger.error("❌ Impossible de démarrer le hub d'écoute: dépendances sounddevice/numpy manquantes.")
            return

        self.enabled = True
        logger.info(f"🎤 [STREAM_LISTENER] Démarrage du hub sur le port {self.port} (Mode: {self.mode})")

        if self.mode == "C" and WHISPER_AVAILABLE:
            try:
                logger.info(f"🧠 Chargement du modèle Whisper {self.model_size} sur {self.device}...")
                self.whisper_model = WhisperModel(self.model_size, device=self.device, compute_type="int8")
                logger.info("✅ Modèle Whisper chargé avec succès.")
            except Exception as e:
                logger.error(f"❌ Échec chargement Whisper: {e}")
                self.whisper_model = None

        # Serveur WebSocket
        try:
            import websockets
        except ImportError:
            logger.error("❌ websockets non installé. Hub désactivé.")
            return

        async def handler(websocket, path):
            self.clients.add(websocket)
            logger.info(f"🔌 Client Bot connecté au Hub. Total: {len(self.clients)}")
            try:
                async for message in websocket:
                    data = json.loads(message)
                    action = data.get("action")
                    if action == "claim":
                        text_hash = data.get("hash")
                        bot_id = data.get("bot_id")
                        priority = data.get("priority", False)

                        current_claim = self.claim_locks.get(text_hash)
                        if not current_claim:
                            self.claim_locks[text_hash] = bot_id
                            await websocket.send(json.dumps({"type": "claim_response", "hash": text_hash, "granted": True}))
                            logger.info(f"🏆 Claim accordé à {bot_id} pour l'énoncé {text_hash}")
                        elif priority and current_claim != bot_id:
                            self.claim_locks[text_hash] = bot_id
                            await websocket.send(json.dumps({"type": "claim_response", "hash": text_hash, "granted": True}))
                            logger.info(f"🏆 Claim prioritaire accordé à {bot_id} (écrase {current_claim})")
                        else:
                            await websocket.send(json.dumps({"type": "claim_response", "hash": text_hash, "granted": False}))
            except websockets.exceptions.ConnectionClosed:
                pass
            finally:
                self.clients.remove(websocket)
                logger.info(f"🔌 Client Bot déconnecté. Total: {len(self.clients)}")

        self.server = await websockets.serve(handler, "localhost", self.port)
        asyncio.create_task(self._capture_and_process())

    async def _capture_and_process(self):
        # Capture audio simplifiée pour l'écoute du streamer
        # En mode continu réel, nous utiliserions sounddevice pour lire les frames PCM
        logger.info("🎤 Enregistrement audio en cours d'écoute...")
        while not self._stopped:
            await asyncio.sleep(1)
            # Implémentation factice ou allégée du loop pour ne pas bloquer
            # En production, les frames PCM sont envoyées à l'ASR et quand un énoncé
            # est finalisé, on le diffuse aux bots via self.broadcast(...)

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
