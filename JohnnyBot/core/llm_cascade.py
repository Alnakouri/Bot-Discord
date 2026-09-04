# ⚠️ FICHIER GENERE — NE PAS EDITER ICI.
# Source : shared/llm_cascade.py — modifier la source puis relancer :
#     python tools/vendor_core.py
# La sonde tools/sonde_core_drift.py echoue si cette copie diverge.

"""
Cascade LLM partagée — essaie les modèles dans l'ordre renvoyé par get_model_cascade()
jusqu'à obtenir une réponse. Extrait de bot_johnny.py (référence) pour dédupliquer les 6 bots.
"""
import time
import asyncio
import base64
import logging

from google.genai import types
from core.safe_client import get_client as get_safe_genai_client
from core.media_handler import process_image_ollama
from core.smart_router import get_model_cascade, RequestType
from core.models import groq_kwargs, nvidia_kwargs, bot_id_depuis_label, details_de_quota
from core.api_tracking import tracer_appel

logger = logging.getLogger("llm_cascade")


def _est_vide(txt):
    """Un modèle peut répondre 200 OK avec un contenu VIDE, sans lever d'exception.

    Vu en prod le 2026-08-26 : Groq (openai/gpt-oss-120b) rend un contenu vide et le bot
    tente alors un envoi Discord vide -> 400 « Cannot send an empty message », donc bot
    muet. Le vide n'est pas une réponse : on descend la cascade au lieu de la casser.
    """
    return not (txt and txt.strip())


def _fuite_de_raisonnement(msg):
    """Certains modèles recopient leur PENSÉE dans `content` au lieu de la garder à part.

    Mesuré le 2026-08-26 sur `nvidia/nemotron-3-super-120b-a12b:free` (OpenRouter) :
    `content` commence par le raisonnement en anglais (« Okay, the user sent... »), le
    budget de tokens y passe entièrement (`finish_reason="length"`) et aucune vraie
    réponse n'arrive jamais. Malena a récité ce raisonnement en plein Discord.
    `reasoning: {exclude: true}` ne corrige PAS le problème : il retire juste le champ,
    la pensée reste dans `content`.

    On détecte la recopie : `content` démarre comme `reasoning`.
    """
    pensee = (getattr(msg, "reasoning", None) or "").strip()
    contenu = (getattr(msg, "content", None) or "").strip()
    if not pensee or not contenu:
        return False
    tete = pensee[:60]
    return len(tete) >= 20 and contenu.startswith(tete)


def _blocs_de_details(details):
    """Rend les dictionnaires où un `retryDelay` peut se trouver, quelle que soit la forme.

    ⚠️ `google.genai.errors.APIError.details` n'est PAS la liste des détails RPC : c'est
    le JSON **complet** de la réponse. Pour un 429, le `google.rpc.RetryInfo` est donc au
    troisième niveau, jamais au premier :

        {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": [
            {"@type": ".../QuotaFailure", ...},
            {"@type": ".../RetryInfo", "retryDelay": "24s"}]}}

    Un extracteur qui ne lit que le premier niveau ne trouve jamais rien et retombe
    silencieusement sur le délai par défaut. La forme aplatie (une liste de blocs RPC)
    est acceptée aussi : c'est celle que rendent d'autres SDK.
    """
    if isinstance(details, dict):
        blocs = [details]
        erreur = details.get("error")
        if isinstance(erreur, dict):
            blocs.append(erreur)
            imbriques = erreur.get("details")
            if isinstance(imbriques, list):
                blocs.extend(b for b in imbriques if isinstance(b, dict))
        return blocs
    if isinstance(details, list):
        return [b for b in details if isinstance(b, dict)]
    return []


def delai_de_reprise(exc):
    """Délai (en secondes) que le fournisseur lui-même annonce, ou None s'il n'en donne pas.

    Sur un 429, deviner la durée du cooldown est un pari : « trop de requêtes cette
    MINUTE » et « quota du JOUR épuisé » rendent le même code. Google, lui, dit combien
    de temps attendre — autant l'écouter plutôt que d'inventer une heure.

    ⚠️ Cet extracteur tourne DÉJÀ à l'intérieur d'un `except` : il ne doit jamais lever,
    quelle que soit la forme de l'exception reçue. En cas de doute il rend None, et
    l'appelant retombe sur sa valeur par défaut.
    """
    try:
        for bloc in _blocs_de_details(getattr(exc, "details", None)):
            if "retryDelay" not in bloc:
                continue
            valeur = bloc["retryDelay"]
            if isinstance(valeur, str):
                valeur = valeur.strip()
                if valeur.endswith("s"):
                    valeur = valeur[:-1]
                return float(valeur)
            if isinstance(valeur, bool):
                return None
            if isinstance(valeur, (int, float)):
                return float(valeur)
            return None
    except Exception:
        return None
    return None


# Borne par défaut d'un appel, quand l'appelant n'en fournit pas.
#
# Sans borne, un 429 Groq coûte 36 SECONDES : le SDK réessaie tout seul avec backoff
# avant de rendre la main, et pendant ce temps la cascade ne bascule pas — le bot reste
# muet alors que l'échelon suivant répondrait en une seconde. Mesuré deux fois sur sheo
# dans data/api_usage.db (latency_ms 36205, 37390, 36284, toutes en code 429).
# Seul JohnnyBot passait `call_timeout=15` ; son commentaire dit « comme Sheo », mais
# Sheo ne le passait pas. D'où une valeur par défaut plutôt qu'un kwarg à recopier
# dans les 12 appels des 6 bots.
#
# Un média est légitimement plus lent qu'un tour de chat : lui donner la même borne
# ferait échouer des analyses d'image qui aboutissaient.
_BORNE_TEXTE = 15.0
_BORNE_MEDIA = 45.0


async def generate_response(
    *,
    routing: dict,
    system_prompt: str,
    transcript: str,
    user_message: str,
    conversation_history: list,        # liste de {"role": "user"|"assistant", "parts": [str]}
    media_data: bytes | None,
    mime_type: str,
    key_manager,                       # MultiAPIKeyManager (clés gemini)
    mistral_client=None,
    groq_client=None,
    openrouter_client=None,
    nvidia_client=None,
    bot_label: str = "Bot",
    temperature: float = 0.8,
    max_tokens: int = 300,
    gemini_max_tokens: int | None = None,
    call_timeout: float | None = None,   # borne par appel (s) : si un provider traîne, on bascule
                                         # None => borne par défaut, cf. _BORNE_* ci-dessus
    cascade: list | None = None,         # force une cascade au lieu de celle de la persona
) -> str | None:
    """Retourne le texte de réponse, ou None si toute la cascade a échoué.
    Le fallback spécifique au bot (message d'échec multimodal, phrase par défaut)
    reste géré par l'appelant.

    Si `call_timeout` est fourni, chaque appel provider est borné dans le temps :
    au-delà, on lève TimeoutError → la boucle bascule vers l'échelon suivant (plus rapide)."""
    # Certaines sorties ne doivent PAS suivre la voix du bot : une annonce de live est
    # publique et c'est la qualité de langue qui prime (cf. CASCADE_ANNONCE).
    cascade = list(cascade) if cascade else get_model_cascade(routing["type"], bot_label)
    has_image = routing.get("has_image") and media_data is not None
    has_audio = routing.get("has_audio") and media_data is not None
    if call_timeout is None:
        call_timeout = _BORNE_MEDIA if (has_image or has_audio) else _BORNE_TEXTE
    response_text = None

    async def _call(func, **kwargs):
        """Exécute l'appel SDK bloquant hors boucle (to_thread), avec timeout optionnel."""
        coro = asyncio.to_thread(func, **kwargs)
        return await (asyncio.wait_for(coro, timeout=call_timeout) if call_timeout else coro)

    for client_type, model_name in cascade:
        _depart = time.perf_counter()
        _code_erreur = None
        _raison = None
        api_key = None
        try:
            try:
                # 1. GEMINI
                if client_type == "gemini":
                    api_key = key_manager.get_key("gemini")
                    if not api_key:
                        _raison = "pas_de_cle"
                        continue
                    client = get_safe_genai_client(api_key=api_key, http_options={'api_version': 'v1beta'})
                    gemini_messages = []
                    for h_msg in conversation_history:
                        gemini_messages.append(types.Content(
                            role=h_msg["role"],
                            parts=[types.Part(text=p) for p in h_msg["parts"]],
                        ))
                    last_turn_parts = [types.Part(text=f"{system_prompt}\n\nDernier message : {user_message}")]
                    if media_data:
                        last_turn_parts.append(types.Part(inline_data=types.Blob(mime_type=mime_type, data=media_data)))
                    gemini_messages.append(types.Content(role="user", parts=last_turn_parts))
                    if routing["type"] == RequestType.REASONING:
                        cfg = types.GenerateContentConfig(temperature=temperature, max_output_tokens=None)
                    else:
                        cfg = types.GenerateContentConfig(
                            temperature=temperature,
                            max_output_tokens=gemini_max_tokens or max_tokens,
                            thinking_config=types.ThinkingConfig(thinking_level="minimal")
                        )
                    resp = await _call(
                        client.models.generate_content,
                        model=model_name, contents=gemini_messages,
                        config=cfg,
                    )
                    response_text = resp.text
                    if _est_vide(response_text):
                        logger.warning(f"⚠️ [GEMINI {model_name}] réponse vide → échelon suivant")
                        response_text = None
                        _raison = "vide"
                        continue
                    logger.info(f"✅ [GEMINI {model_name}] {bot_label} via {routing.get('reason', '')}")
                    break
    
                # 1.bis OLLAMA (Moondream) — vision locale uniquement
                elif client_type == "ollama":
                    if routing["type"] == RequestType.IMAGE and routing.get("image_attachment"):
                        response_text = await process_image_ollama(
                            attachment=routing["image_attachment"],
                            personality_prompt=system_prompt,
                            user_message=user_message,
                        )
                        if response_text:
                            logger.info(f"✅ [OLLAMA {model_name}] {bot_label}")
                            break
                        continue
                    else:
                        continue
    
                # 2. MISTRAL
                elif client_type == "mistral" and mistral_client:
                    chat = await _call(
                        mistral_client.chat.complete,
                        model=model_name,
                        messages=[{"role": "system", "content": system_prompt},
                                  {"role": "user", "content": f"TRANSCRIPT:\n{transcript}\nMESSAGE: {user_message}"}],
                    )
                    response_text = chat.choices[0].message.content
                    if _est_vide(response_text):
                        logger.warning(f"⚠️ [MISTRAL {model_name}] réponse vide → échelon suivant")
                        response_text = None
                        _raison = "vide"
                        continue
                    logger.info(f"🌪️ [MISTRAL {model_name}] {bot_label}")
                    break
    
                # 3. GROQ
                elif client_type == "groq" and groq_client:
                    msgs = [{"role": "system", "content": system_prompt}]
                    for msg in conversation_history:
                        r = "user" if msg["role"] == "user" else "assistant"
                        msgs.append({"role": r, "content": msg["parts"][0]})
                    msgs.append({"role": "user", "content": user_message})
                    chat = await _call(
                        groq_client.chat.completions.create,
                        messages=msgs, model=model_name, temperature=temperature,
                        **groq_kwargs(model_name),
                    )
                    response_text = chat.choices[0].message.content
                    if _est_vide(response_text):
                        logger.warning(f"⚠️ [GROQ {model_name}] réponse vide → échelon suivant")
                        response_text = None
                        _raison = "vide"
                        continue
                    logger.info(f"⚡ [GROQ {model_name}] {bot_label}")
                    break
    
                # 4. NVIDIA (nemotron) — 4e fournisseur, quota independant des 3 autres.
                elif client_type == "nvidia" and nvidia_client:
                    if media_data is not None:
                        logger.warning(f"⚠️ [NVIDIA] Média reçu mais ignoré par {model_name}. Perte silencieuse évitée.")
                    chat = await _call(
                        nvidia_client.chat.completions.create,
                        model=model_name,
                        messages=[{"role": "system", "content": system_prompt},
                                  {"role": "user", "content": f"TRANSCRIPT:\n{transcript}\nLAST MSG: {user_message}"}],
                        temperature=temperature, max_tokens=max_tokens,
                        # ⚠️ SANS ceci, nemotron RECOPIE sa pensée dans `content` (mesuré :
                        # 6 779 ms de méta-discours au lieu d'une réplique). Le paramètre
                        # divise aussi la latence par six.
                        **nvidia_kwargs(model_name),
                    )
                    # Filet malgré tout : le paramètre pourrait cesser d'être honoré.
                    if _fuite_de_raisonnement(chat.choices[0].message):
                        logger.warning(f"⚠️ [NVIDIA {model_name}] le modèle a recopié son raisonnement dans la réponse → échelon suivant")
                        response_text = None
                        _raison = "fuite_raisonnement"
                        continue
                    response_text = chat.choices[0].message.content
                    if _est_vide(response_text):
                        logger.warning(f"⚠️ [NVIDIA {model_name}] réponse vide → échelon suivant")
                        response_text = None
                        _raison = "vide"
                        continue
                    logger.info(f"🟩 [NVIDIA {model_name}] {bot_label}")
                    break
    
                # 4. OPENROUTER (texte + secours multimodal)
                elif client_type == "openrouter" and openrouter_client:
                    user_content = f"{transcript}\n{user_message}"
                    if has_image and media_data:
                        b64_image = base64.b64encode(media_data).decode('utf-8')
                        user_content = [
                            {"type": "text", "text": f"{transcript}\n{user_message}"},
                            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_image}"}},
                        ]
                    chat = await _call(
                        openrouter_client.chat.completions.create,
                        model=model_name,
                        messages=[{"role": "system", "content": system_prompt},
                                  {"role": "user", "content": user_content}],
                        temperature=temperature, max_tokens=max_tokens,
                        extra_headers={"HTTP-Referer": "https://discord-bot.local", "X-Title": bot_label},
                    )
                    if _fuite_de_raisonnement(chat.choices[0].message):
                        logger.warning(f"⚠️ [OPENROUTER {model_name}] le modèle a recopié son raisonnement dans la réponse → échelon suivant")
                        response_text = None
                        _raison = "fuite_raisonnement"
                        continue
                    response_text = chat.choices[0].message.content
                    if _est_vide(response_text):
                        logger.warning(f"⚠️ [OPENROUTER {model_name}] réponse vide → échelon suivant")
                        response_text = None
                        _raison = "vide"
                        continue
                    logger.info(f"🌌 [OPENROUTER {model_name}] {bot_label}")
                    break
    
            except Exception as e:
                error_msg = str(e)
                if not error_msg:
                    error_msg = type(e).__name__
                _raison = type(e).__name__
                _code_erreur = getattr(e, 'code', getattr(e, 'status_code', 0))
                # ⚠️ Un 429 dit POURQUOI dans ses en-tetes : sans ca on ne voit qu'un
                # echec de plus, alors que la cause est un quota par minute depasse.
                _quota = details_de_quota(e)
                logger.warning(
                    f"⚠️ [{client_type.upper()} FAIL] {model_name} - {type(e).__name__}: {error_msg}"
                    + (f"  [QUOTA] {_quota}" if _quota else "")
                )
                if client_type == "gemini" and api_key:
                    key_manager.report_error(
                        "gemini", api_key, _code_erreur,
                        retry_delay_s=delai_de_reprise(e),
                    )
                continue
        finally:
            _latence = int((time.perf_counter() - _depart) * 1000)
            _succes = bool(response_text)
            if not _succes and _raison is None:
                # Aucune branche n'a tourné (client absent, échelon inconnu) : pas un
                # échec d'API. Sans ça, la base se remplit d'échecs sans cause — le
                # bruit « unknown » que ce chantier existe pour supprimer.
                _raison = "non_tentee"
            _index_cle = None
            if client_type == "gemini" and api_key and hasattr(key_manager, "apis"):
                try:
                    _index_cle = key_manager.apis["gemini"]["keys"].index(api_key)
                except (ValueError, KeyError, AttributeError):
                    pass
            _bot_nom = bot_id_depuis_label(bot_label) or (bot_label or "").lower()
            tracer_appel(
                bot=_bot_nom,
                api=client_type,
                modele=model_name,
                index_cle=_index_cle,
                succes=_succes,
                code_erreur=_code_erreur,
                latence_ms=_latence,
                raison=_raison
            )

    return response_text
