"""
Cascade LLM partagée — essaie les modèles dans l'ordre renvoyé par get_model_cascade()
jusqu'à obtenir une réponse. Extrait de bot_johnny.py (référence) pour dédupliquer les 6 bots.
"""
import asyncio
import base64
import logging

from google.genai import types
from shared.safe_client import get_client as get_safe_genai_client
from shared.media_handler import process_image_ollama
from shared.smart_router import get_model_cascade, RequestType

logger = logging.getLogger("llm_cascade")


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
) -> str | None:
    """Retourne le texte de réponse, ou None si toute la cascade a échoué.
    Le fallback spécifique au bot (message d'échec multimodal, phrase par défaut)
    reste géré par l'appelant."""
    cascade = get_model_cascade(routing["type"])
    has_image = routing.get("has_image") and media_data is not None
    has_audio = routing.get("has_audio") and media_data is not None
    response_text = None

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
                resp = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model_name, contents=gemini_messages,
                    config=types.GenerateContentConfig(temperature=temperature, max_output_tokens=gemini_max_tokens or max_tokens),
                )
                response_text = resp.text
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
                chat = await asyncio.to_thread(
                    mistral_client.chat.complete,
                    model=model_name,
                    messages=[{"role": "system", "content": system_prompt},
                              {"role": "user", "content": f"TRANSCRIPT:\n{transcript}\nMESSAGE: {user_message}"}],
                )
                response_text = chat.choices[0].message.content
                logger.info(f"🌪️ [MISTRAL {model_name}] {bot_label}")
                break

            # 3. GROQ
            elif client_type == "groq" and groq_client:
                msgs = [{"role": "system", "content": system_prompt}]
                for msg in conversation_history:
                    r = "user" if msg["role"] == "user" else "assistant"
                    msgs.append({"role": r, "content": msg["parts"][0]})
                msgs.append({"role": "user", "content": user_message})
                chat = await asyncio.to_thread(
                    groq_client.chat.completions.create,
                    messages=msgs, model=model_name, temperature=temperature,
                )
                response_text = chat.choices[0].message.content
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
                chat = await asyncio.to_thread(
                    openrouter_client.chat.completions.create,
                    model=model_name,
                    messages=[{"role": "system", "content": system_prompt},
                              {"role": "user", "content": user_content}],
                    temperature=temperature, max_tokens=max_tokens,
                    extra_headers={"HTTP-Referer": "https://discord-bot.local", "X-Title": bot_label},
                )
                response_text = chat.choices[0].message.content
                # Un modèle :free peut renvoyer un contenu VIDE sans lever d'exception →
                # on ne casse pas la cascade sur du vide, on tente l'échelon suivant.
                if not (response_text and response_text.strip()):
                    logger.warning(f"⚠️ [OPENROUTER {model_name}] réponse vide → échelon suivant")
                    response_text = None
                    continue
                logger.info(f"🌌 [OPENROUTER {model_name}] {bot_label}")
                break

        except Exception as e:
            logger.warning(f"⚠️ [{client_type.upper()} FAIL] {e}")
            if client_type == "gemini" and api_key:
                error_code = getattr(e, 'code', getattr(e, 'status_code', 0))
                key_manager.report_error("gemini", api_key, error_code)
            continue

    return response_text
