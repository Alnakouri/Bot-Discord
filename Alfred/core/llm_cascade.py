# ⚠️ FICHIER GENERE — NE PAS EDITER ICI.
# Source : shared/llm_cascade.py — modifier la source puis relancer :
#     python tools/vendor_core.py
# La sonde tools/sonde_core_drift.py echoue si cette copie diverge.

"""
Cascade LLM partagée — essaie les modèles dans l'ordre renvoyé par get_model_cascade()
jusqu'à obtenir une réponse. Extrait de bot_johnny.py (référence) pour dédupliquer les 6 bots.
"""
import asyncio
import base64
import logging

from google.genai import types
from core.safe_client import get_client as get_safe_genai_client
from core.media_handler import process_image_ollama
from core.smart_router import get_model_cascade, RequestType
from core.models import groq_kwargs

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
    bot_label: str = "Bot",
    temperature: float = 0.8,
    max_tokens: int = 300,
    gemini_max_tokens: int | None = None,
    call_timeout: float | None = None,   # borne par appel (s) : si un provider traîne, on bascule
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
    response_text = None

    async def _call(func, **kwargs):
        """Exécute l'appel SDK bloquant hors boucle (to_thread), avec timeout optionnel."""
        coro = asyncio.to_thread(func, **kwargs)
        return await (asyncio.wait_for(coro, timeout=call_timeout) if call_timeout else coro)

    for client_type, model_name in cascade:
        try:
            # 1. GEMINI
            if client_type == "gemini":
                api_key = key_manager.get_key("gemini")
                if not api_key:
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
                    continue
                logger.info(f"⚡ [GROQ {model_name}] {bot_label}")
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
                    continue
                response_text = chat.choices[0].message.content
                if _est_vide(response_text):
                    logger.warning(f"⚠️ [OPENROUTER {model_name}] réponse vide → échelon suivant")
                    response_text = None
                    continue
                logger.info(f"🌌 [OPENROUTER {model_name}] {bot_label}")
                break

        except Exception as e:
            logger.warning(f"⚠️ [{client_type.upper()} FAIL] {type(e).__name__}: {e}")
            if client_type == "gemini" and api_key:
                error_code = getattr(e, 'code', getattr(e, 'status_code', 0))
                key_manager.report_error("gemini", api_key, error_code)
            continue

    return response_text
