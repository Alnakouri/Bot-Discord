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
import re
from collections import Counter

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


# Seuils de degenerescence, MESURES sur les 153 reponses des rapports du 2026-09-16
# avant d'etre poses (jamais choisis a vue) :
#   - 8 reponses degenerees, toutes de Malena, toutes a >= 90 % d'un seul mot ;
#   - le ratio legitime le plus haut est 20 % (une reponse de 10 mots) ;
#   - le mot le plus long legitime fait 16 caracteres, contre 404 pour le cas casse.
# Les bornes laissent donc une marge enorme des deux cotes : elles visent la panne, pas
# le style. Malena dit « Oh la la » et doit pouvoir continuer.
_DEGEN_MOTS_MIN = 20      # sous ce volume, un ratio ne veut rien dire
_DEGEN_RATIO = 0.5        # un seul mot occupe la moitie de la reponse
_DEGEN_MOT_MAX = 40       # « ohhhh... » sur 404 caracteres n'est pas un mot


def _est_degenere(txt):
    """Un modele peut boucler : rendre 200 OK, ne rien lever, et repeter un mot 200 fois.

    Vu le 2026-09-16 dans les rapports d'eval : Malena a rendu **8 reponses sur 26** de la
    forme « Oh la la la la la... » jusqu'a la coupure de `max_tokens`, notees 0 par le
    juge. En direct, un utilisateur Discord recoit ce pave tel quel.

    C'est exactement la regle de `_est_vide`, un cran plus loin : une boucle n'est pas une
    reponse, donc on descend la cascade au lieu de l'envoyer. Deux formes distinctes sont
    couvertes, parce qu'elles n'ont pas la meme signature :
      - la boucle de MOTS (« la » x201), invisible a un compteur qui filtre les mots
        courts — c'est ainsi que `tests/eval/gimmick.py` l'a laissee passer : il ne
        retient que les mots de 4 lettres ou plus, et « la » en fait deux ;
      - la boucle de CARACTERES (« ohhhh... » sur 404 signes), qui ne fait qu'UN mot et
        echappe donc a tout ratio.
    """
    if not txt:
        return False
    mots = re.sub(r"[^\w\s]", " ", txt.lower()).split()
    if not mots:
        return False

    if max(len(m) for m in mots) >= _DEGEN_MOT_MAX:
        return True

    if len(mots) < _DEGEN_MOTS_MIN:
        return False

    return Counter(mots).most_common(1)[0][1] / len(mots) >= _DEGEN_RATIO


# Marqueurs de méta-discours : le modèle PARLE DE la conversation au lieu d'y participer.
# Repris de `tools/sonde_fuite_raisonnement.py`, qui les a établis et élargis au français
# le 2026-09-04 (un détecteur anglophone avait classé « propres » trois vraies fuites).
#
# ⚠️ Mesuré avant d'être branché, le 2026-09-05 :
#   * sur 460 vraies réponses des 6 bots (mémoires, archives, bios, statuts) →
#     **0 faux positif**. Le seul marqueur qui en produisait, `mon rôle est de`, a été
#     retiré : « Mon rôle est de répondre, pas de me taire » est une réplique EN
#     PERSONNAGE, pas une fuite. Il reste dans la sonde, où un humain lit le verdict.
#   * sur 12 appels NVIDIA sans garde-fou → **12 fuites sur 12, toutes attrapées**
#     (« Here's a thinking process: ... »).
_MARQUEURS_META = [
    r"\bl'utilisateur\b", r"\bthe user\b", r"\bl'usager\b",
    r"\bje dois r[ée]pondre\b", r"\bi need to respond\b", r"\bi should respond\b",
    r"\bthinking process\b", r"\blet me think\b", r"\bfirst,? i\b",
    r"\bsystem prompt\b", r"\ble prompt\b", r"\brappel des consignes\b",
    r"\ben tant que .{0,30}, je dois\b",
    r"\bd'apr[èe]s le transcript\b", r"\bthe assistant\b",
    r"^<think>", r"\bokay,? so\b",
]
_META = re.compile("|".join(_MARQUEURS_META), re.I | re.M)


def _fuite_de_raisonnement(msg):
    """Le modèle recopie sa PENSÉE dans `content` au lieu de la garder à part.

    Deux formes, et il faut les deux — c'est tout l'objet du correctif du 2026-09-05.

    **Forme 1, le champ `reasoning`.** Mesurée le 2026-08-26 sur
    `nvidia/nemotron-3-super-120b-a12b:free` (OpenRouter) : `content` commence par le
    raisonnement en anglais (« Okay, the user sent... »), le budget de tokens y passe
    entièrement (`finish_reason="length"`) et aucune vraie réponse n'arrive jamais.
    Malena a récité ce raisonnement en plein Discord. `reasoning: {exclude: true}` ne
    corrige PAS le problème : il retire juste le champ, la pensée reste dans `content`.
    On détecte la recopie : `content` démarre comme `reasoning`.

    **Forme 2, le contenu seul.** ⚠️ La forme 1 était un FILET MORT sur NVIDIA, le seul
    fournisseur qui appelle encore cette fonction depuis le retrait d'OpenRouter :
    l'endpoint NVIDIA **ne remplit jamais `reasoning`** (mesuré le 2026-09-05, 16 appels,
    vide à chaque fois), donc le test sortait toujours par `if not pensee: return False`.
    Et nemotron fuit quand même, ~1 fois sur 20 malgré `reasoning_effort="none"` :

        'p? The user wants exactly: pong'

    Le commentaire « Filet malgré tout » des branches nvidia promettait donc une
    protection qui n'existait pas. Un filet écrit pour un fournisseur ne mord pas chez le
    suivant : il faut le vérifier, pas le reconduire.

    ⚠️ La forme 2 juge le TEXTE, donc elle s'applique à tout appelant, pas seulement à
    NVIDIA. C'est voulu : le coût mesuré est nul (0 faux positif sur 460 réponses
    réelles) et un échelon non terminal ne perd qu'un saut de cascade.
    """
    contenu = (getattr(msg, "content", None) or "").strip()
    if not contenu:
        return False

    pensee = (getattr(msg, "reasoning", None) or "").strip()
    tete = pensee[:60]
    if len(tete) >= 20 and contenu.startswith(tete):
        return True

    return bool(_META.search(contenu))


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
    de temps attendre — autant l'écouter plutôt que d'inventer une heure. Deux endroits
    à lire, et il faut les deux : Gemini l'annonce dans le CORPS de l'erreur, les SDK de
    style OpenAI (Groq, NVIDIA, Mistral) dans une EN-TÊTE HTTP.

    ⚠️ Cet extracteur tourne DÉJÀ à l'intérieur d'un `except` : il ne doit jamais lever,
    quelle que soit la forme de l'exception reçue. En cas de doute il rend None, et
    l'appelant retombe sur sa valeur par défaut.
    """
    valeur = _delai_dans_le_corps(exc)
    return valeur if valeur is not None else _delai_dans_les_entetes(exc)


def _delai_dans_le_corps(exc):
    """Le délai annoncé dans le CORPS de l'erreur (forme Google/`APIError.details`)."""
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


# Unités que les fournisseurs mélangent dans une même en-tête : « 7.66s », « 2m59.56s »,
# « 500ms », ou un nombre nu (`retry-after` en secondes).
_UNITES_DE_DUREE = {"h": 3600.0, "m": 60.0, "s": 1.0, "ms": 0.001, "": 1.0}
_MORCEAU_DE_DUREE = re.compile(r"(\d+(?:\.\d+)?)(ms|h|m|s)?")


def _duree_en_secondes(brut):
    """« 24 », « 7.66s », « 2m59.56s », « 500ms » -> secondes. None si illisible.

    ⚠️ Une date HTTP (« Wed, 21 Oct 2015 07:28:00 GMT ») est un `retry-after` valide que
    ce lecteur refuse VOLONTAIREMENT : l'interpréter comme une durée poserait une
    quarantaine absurde. Refuser rend None, et l'appelant retombe sur ses 60 s.
    """
    texte = str(brut).strip().lower()
    if not texte:
        return None
    total = 0.0
    position = 0
    for morceau in _MORCEAU_DE_DUREE.finditer(texte):
        if morceau.start() != position:
            return None                      # du texte non numérique s'est glissé au milieu
        total += float(morceau.group(1)) * _UNITES_DE_DUREE[morceau.group(2) or ""]
        position = morceau.end()
    if position == 0 or position != len(texte):
        return None
    return total


def _delai_dans_les_entetes(exc):
    """Le délai annoncé dans les EN-TÊTES HTTP (Groq, NVIDIA, Mistral — SDK style OpenAI).

    ⚠️ Gemini est le seul fournisseur à annoncer son délai dans le CORPS de l'erreur. Les
    autres le mettent dans une en-tête — que `details_de_quota()` lisait DÉJÀ pour le
    journal, sans que personne ne s'en serve pour la quarantaine. Un extracteur écrit
    pour un fournisseur ne mord pas chez le suivant, il faut le vérifier.
    """
    try:
        entetes = getattr(getattr(exc, "response", None), "headers", None) or {}
        for nom in ("retry-after", "x-ratelimit-reset-tokens", "x-ratelimit-reset-requests"):
            brut = entetes.get(nom)
            if brut is None:
                continue
            valeur = _duree_en_secondes(brut)
            if valeur is not None:
                return valeur
    except Exception:
        return None
    return None


def _cle_du_pool(key_manager, api_name, exigee=False):
    """Rend `(cle, raison_du_saut)` pour un échelon. `raison` non nulle => sauter.

    `exigee=True` (Gemini) : l'échelon ne peut pas tourner sans la clé, il la passe au
    constructeur du client. Ailleurs le client est déjà bâti et porte sa propre clé ; la
    clé du pool ne sert qu'à nommer le coupable dans `report_error`.

    ⚠️ D'où la garde : un pool NON ENREGISTRÉ ne doit JAMAIS faire sauter un échelon
    facultatif. Sans elle, il suffirait d'oublier un `register_api` pour rendre un
    fournisseur définitivement muet, sans une ligne de journal — le piège exact qui a
    laissé NVIDIA annoncé sur les 6 bots et sans un seul appel pendant huit jours.

    ⚠️ On DEMANDE la clé d'abord, et on n'interprète le refus qu'ensuite. L'ordre inverse
    a rendu la CI rouge le 2026-09-06 : trois tests ne remplacent que `get_key`, sans
    peupler `apis`. En local ils passaient — les vraies clés Gemini y sont — et en CI,
    sans clé, la branche Gemini n'était plus jamais atteinte. Interroger le pool avant le
    gestionnaire, c'est court-circuiter la seule autorité sur la question.
    """
    obtenir = getattr(key_manager, "get_key", None)
    cle = obtenir(api_name) if callable(obtenir) else None
    # ⚠️ `isinstance(cle, str)` n'est pas de la ceinture-bretelles : plusieurs tests
    # passent un `MagicMock` en guise de gestionnaire. Son `get_key` rend un MagicMock,
    # qui n'est pas None — et cette fausse clé finissait bindée dans SQLite
    # (« type 'MagicMock' is not supported »). Une clé est une chaîne, ou n'est pas.
    if isinstance(cle, str) and cle:
        return cle, None

    apis = getattr(key_manager, "apis", None)
    if isinstance(apis, dict) and api_name in apis:
        # Le pool existe et ne rend rien : ses clés sont en cooldown ou revoquées.
        # ⚠️ Un saut muet est un échelon invisible : on le dit, et `tracer_appel` le
        # range en base sous `raison="quarantaine"` — un saut délibéré, pas un échec.
        logger.info(f"⏭️ [{api_name.upper()}] clé en quarantaine → échelon suivant, sans appel")
        return None, "quarantaine"
    return None, ("pas_de_cle" if exigee else None)


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
                    api_key, _saut = _cle_du_pool(key_manager, "gemini", exigee=True)
                    if _saut:
                        _raison = _saut
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
                    if _est_degenere(response_text):
                        logger.warning(f"⚠️ [GEMINI {model_name}] réponse dégénérée (boucle) → échelon suivant")
                        response_text = None
                        _raison = "degeneree"
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
                    api_key, _saut = _cle_du_pool(key_manager, "mistral")
                    if _saut:
                        _raison = _saut
                        continue
                    # ⚠️ Cet échelon ne passait NI `temperature` NI `max_tokens` : il
                    # servait aux défauts du fournisseur pendant que les autres échelons
                    # obéissaient aux nôtres. Mesuré le 2026-09-16 — Malena est le seul
                    # bot dont la cascade est Mistral-FIRST, et le seul dont les réponses
                    # partaient à 432 mots puis dégénéraient en boucle. Ce n'était pas sa
                    # persona : c'était cet échelon-ci.
                    chat = await _call(
                        mistral_client.chat.complete,
                        model=model_name,
                        messages=[{"role": "system", "content": system_prompt},
                                  {"role": "user", "content": f"TRANSCRIPT:\n{transcript}\nMESSAGE: {user_message}"}],
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    response_text = chat.choices[0].message.content
                    if _est_vide(response_text):
                        logger.warning(f"⚠️ [MISTRAL {model_name}] réponse vide → échelon suivant")
                        response_text = None
                        _raison = "vide"
                        continue
                    if _est_degenere(response_text):
                        logger.warning(f"⚠️ [MISTRAL {model_name}] réponse dégénérée (boucle) → échelon suivant")
                        response_text = None
                        _raison = "degeneree"
                        continue
                    logger.info(f"🌪️ [MISTRAL {model_name}] {bot_label}")
                    break
    
                # 3. GROQ
                elif client_type == "groq" and groq_client:
                    api_key, _saut = _cle_du_pool(key_manager, "groq")
                    if _saut:
                        _raison = _saut
                        continue
                    msgs = [{"role": "system", "content": system_prompt}]
                    for msg in conversation_history:
                        r = "user" if msg["role"] == "user" else "assistant"
                        msgs.append({"role": r, "content": msg["parts"][0]})
                    msgs.append({"role": "user", "content": user_message})
                    chat = await _call(
                        groq_client.chat.completions.create,
                        messages=msgs, model=model_name, temperature=temperature,
                        max_tokens=max_tokens,
                        **groq_kwargs(model_name),
                    )
                    response_text = chat.choices[0].message.content
                    if _est_vide(response_text):
                        logger.warning(f"⚠️ [GROQ {model_name}] réponse vide → échelon suivant")
                        response_text = None
                        _raison = "vide"
                        continue
                    if _est_degenere(response_text):
                        logger.warning(f"⚠️ [GROQ {model_name}] réponse dégénérée (boucle) → échelon suivant")
                        response_text = None
                        _raison = "degeneree"
                        continue
                    logger.info(f"⚡ [GROQ {model_name}] {bot_label}")
                    break
    
                # 4. NVIDIA (nemotron) — 4e fournisseur, quota independant des 3 autres.
                elif client_type == "nvidia" and nvidia_client:
                    api_key, _saut = _cle_du_pool(key_manager, "nvidia")
                    if _saut:
                        _raison = _saut
                        continue
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
                    # Filet : `reasoning_effort="none"` n'est pas etanche. Mesure du 2026-09-05,
                    # 12 appels sans lui -> 12 fuites ; avec lui, ~1 sur 20 passe encore.
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
                    if _est_degenere(response_text):
                        logger.warning(f"⚠️ [NVIDIA {model_name}] réponse dégénérée (boucle) → échelon suivant")
                        response_text = None
                        _raison = "degeneree"
                        continue
                    logger.info(f"🟩 [NVIDIA {model_name}] {bot_label}")
                    break
    
                # L'echelon OpenRouter etait ici. Retire le 2026-09-05 :
                # free tier a 12 echecs sur 12, et sa branche etait le SEUL
                # appelant de _fuite_de_raisonnement(). Cf.
                # tests/test_openrouter_est_retire.py
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
                # ⚠️ Longtemps réservé à Gemini : Groq, Mistral et NVIDIA prenaient donc
                # un 429 sans jamais écarter la clé, et retapaient dans le mur au message
                # suivant. Mesuré en base le 2026-09-04 : trois appels Mistral de Johnny
                # sur la MÊME clé morte dans la même seconde (05:30:45), deux de Sheo à
                # 05:30:59. `report_error` ne fait rien si le pool lui est inconnu.
                if api_key:
                    key_manager.report_error(
                        client_type, api_key, _code_erreur,
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
            _index_cle = _index_de_cle(key_manager, client_type, api_key)
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


def _index_de_cle(key_manager, api_name, api_key):
    """Index de la clé dans son pool, ou None. Sert au traçage, jamais à décider."""
    if not api_key or not hasattr(key_manager, "apis"):
        return None
    try:
        index = key_manager.apis[api_name]["keys"].index(api_key)
    except (ValueError, KeyError, AttributeError, TypeError):
        return None
    # ⚠️ Un faux gestionnaire (MagicMock) rend un objet que SQLite refuserait de binder.
    return index if isinstance(index, int) else None


def _texte_de(fournisseur, reponse):
    """Le texte d'une réponse brute. Gemini le porte à plat, les autres l'emboîtent."""
    if fournisseur == "gemini":
        return reponse.text
    return reponse.choices[0].message.content


async def appel_hors_cascade(
    fournisseur,
    fonction=None,
    *,
    key_manager,
    bot_label,
    modele,
    fabrique=None,
    methode=None,
    timeout=None,
    **kwargs,
):
    """UN appel fournisseur isolé — hors cascade — avec l'hygiène d'un échelon de cascade.

    ⚠️ Pourquoi ceci existe. Le chantier du 2026-09-06 a branché `report_error` et
    `tracer_appel` sur les **11 cascades**. Or tous les fournisseurs ne sont pas appelés
    depuis une cascade : `!rumeur`, les décrets, les rattrapages de mention, l'imposteur
    et le conseil hebdomadaire tapent le SDK en direct, avec leur propre repli à deux
    échelons écrit à la main. Constaté en test live le 2026-09-07 à 22:41 chez M'aiq :

        [GROQ RUMEUR] Error code: 429 ... Please try again in 1.785s

    Zéro ligne de quarantaine sur les six bots, zéro ligne en base. La clé restait saine
    pour le gestionnaire, et le message suivant retapait dans le même mur.

    Ce que la fonction garantit, exactement comme un échelon de `generate_response` :
      1. la clé vient du POOL — une clé en quarantaine saute l'appel, sans le tenter ;
      2. un échec appelle `report_error` avec le délai lu chez le fournisseur ;
      3. l'appel est tracé en base, succès comme échec, avec sa raison ;
      4. l'appel est borné dans le temps et ne bloque pas la boucle (`to_thread`).

    Rend le TEXTE, ou None. Les appelants n'extrayaient rien d'autre, et le None couvre
    d'un coup les quatre façons d'échouer : quarantaine, client absent, exception, vide.

    `fabrique` sert au seul Gemini, dont le client se BÂTIT avec la clé : elle reçoit la
    clé et rend le CLIENT ; `methode` nomme le chemin à appeler dessus
    (`"models.generate_content"`). Sa présence rend la clé obligatoire — sans elle il n'y
    a rien à bâtir, alors qu'ailleurs le client est déjà bâti et porte sa propre clé
    (celle du pool ne sert qu'à nommer le coupable dans `report_error`).

    ⚠️ **Pourquoi la fabrique rend le CLIENT et non directement la méthode.** Première
    version, le 2026-09-07 : `fabrique=lambda cle: get_safe_genai_client(cle).models.generate_content`.
    Le `Client` n'était alors référencé par personne — `client.models` ne garde AUCUN lien
    vers lui — donc il était ramassé par le GC, et son transport HTTP fermé avec lui. Tous
    les appels Gemini hors cascade échouaient sur

        RuntimeError: Cannot send a request, as the client has been closed.

    Invisible, parce que l'échelon suivant répondait : le décret du soir est sorti normal,
    signé Mistral. C'est le piège de [[gotcha-echelon-de-secours-invisible]] exactement.
    En rendant le client, il vit dans une variable locale jusqu'à la fin de l'appel.
    """
    if timeout is None:
        timeout = _BORNE_TEXTE
    api_key, _saut = _cle_du_pool(key_manager, fournisseur, exigee=fabrique is not None)

    _depart = time.perf_counter()
    texte = None
    _raison = None
    _code_erreur = 0
    try:
        if _saut:
            _raison = _saut
            return None
        # ⚠️ `client` DOIT rester une variable locale : c'est elle, et rien d'autre, qui
        # empêche le GC de fermer le transport HTTP pendant l'appel. Ne pas l'inliner.
        client = fabrique(api_key) if fabrique is not None else None
        if client is not None:
            appel = client
            for morceau in (methode or "").split("."):
                appel = getattr(appel, morceau)
        else:
            appel = fonction
        if appel is None:
            # Client non construit (clé absente au démarrage) : ce n'est pas un échec
            # d'API, et ça ne doit pas remplir la base d'erreurs sans cause.
            _raison = "non_tentee"
            return None
        reponse = await asyncio.wait_for(asyncio.to_thread(appel, **kwargs), timeout=timeout)
        texte = _texte_de(fournisseur, reponse)
        if _est_vide(texte):
            logger.warning(f"⚠️ [{fournisseur.upper()} {modele}] réponse vide — {bot_label}")
            texte = None
            _raison = "vide"
            return None
        logger.info(f"✅ [{fournisseur.upper()} {modele}] {bot_label} (hors cascade)")
        return texte
    except Exception as e:
        _raison = type(e).__name__
        _code_erreur = getattr(e, "code", getattr(e, "status_code", 0))
        _quota = details_de_quota(e)
        logger.warning(
            f"⚠️ [{fournisseur.upper()} FAIL] {modele} - {type(e).__name__}: {e or type(e).__name__}"
            + (f"  [QUOTA] {_quota}" if _quota else "")
        )
        if api_key:
            key_manager.report_error(
                fournisseur, api_key, _code_erreur,
                retry_delay_s=delai_de_reprise(e),
            )
        return None
    finally:
        tracer_appel(
            bot=bot_id_depuis_label(bot_label) or (bot_label or "").lower(),
            api=fournisseur,
            modele=modele,
            index_cle=_index_de_cle(key_manager, fournisseur, api_key),
            succes=bool(texte),
            code_erreur=_code_erreur,
            latence_ms=int((time.perf_counter() - _depart) * 1000),
            raison=_raison,
        )
