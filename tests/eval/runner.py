import os
os.environ.setdefault("SUIVI_ORIGINE", "harnais")
import sys
from contextlib import contextmanager
from pathlib import Path
from groq import Groq
from mistralai import Mistral
from openai import OpenAI

# Injection du répertoire racine au sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from shared.secure_env import load_secure_env
from shared.api_manager import MultiAPIKeyManager
from shared.smart_router import RequestType
from shared.models import NVIDIA_BASE_URL
from shared.llm_cascade import generate_response, _BORNE_TEXTE
# Le MODULE, et pas seulement la fonction : `_echelon_qui_repond` y remplace le temps
# d'un appel le traceur de la cascade, et c'est le module qui porte ce nom-là.
import shared.llm_cascade as llm_cascade
from tests.eval.persona_loader import load_persona, load_filtre

# Charger les variables d'environnement à partir de JohnnyBot (qui contient .env.encrypted et .master_key)
johnny_dir = Path(root_dir) / "JohnnyBot"
try:
    load_secure_env(johnny_dir)
except Exception as e:
    print(f"Avertissement lors du chargement de secure_env depuis JohnnyBot : {e}")

# Sentinelle rendue quand AUCUN echelon de la cascade n'a repondu. Elle doit rester une
# constante partagee : `run_eval` s'en sert pour court-circuiter le juge et les mesures
# deterministes, et une deuxieme copie du litteral les desarmerait en silence.
ECHEC_CASCADE = "[Toute la cascade de modèles a échoué]"


@contextmanager
def _echelon_qui_repond():
    """Rend la liste des échelons (``api/modele``) qui ont RÉPONDU pendant le bloc.

    ⚠️ Sans cette information, le compte d'astérisques se lit à l'envers. Le
    2026-09-18, Sugar est passée de 0/17 à 11/17 sans qu'un mot de sa fiche ne bouge :
    Gemini était à sec et ministral-14b avait répondu à sa place — un modèle mesuré à
    11/18 astérisques dès le 04/09. Le chiffre ne parlait pas de la fiche, il parlait du
    modèle, et la conclusion tirée ce soir-là a dû être corrigée le lendemain.
    Cf. [[gotcha-le-compte-brut-est-fausse-par-l-echelon-qui-a-repondu]].

    On OBSERVE `tracer_appel` — le seul endroit où la cascade nomme l'échelon qu'elle
    vient d'essayer — au lieu d'ajouter un paramètre à `generate_response` :
    `shared/llm_cascade.py` est VENDORÉ dans les six bots (`tools/vendor_core.py`), et
    une commodité de harnais n'a pas à faire bouger le code que les bots exécutent en
    production. L'espion délègue au vrai traceur : rien n'est perdu en base.

    Le harnais est séquentiel — un bot, un scénario, un tour à la fois — donc un
    observateur de portée module ne peut pas mélanger deux appels.
    """
    vus = []
    vrai = llm_cascade.tracer_appel

    def _espion(*args, **kwargs):
        if kwargs.get("succes"):
            vus.append(f"{kwargs.get('api')}/{kwargs.get('modele')}")
        return vrai(*args, **kwargs)

    llm_cascade.tracer_appel = _espion
    try:
        yield vus
    finally:
        llm_cascade.tracer_appel = vrai

# ---------------------------------------------------------------------------
# LES CLES SONT CELLES DU BOT MESURE, PAS CELLES DE JOHNNY
#
# ⚠️ Jusqu'au 2026-09-19, ce fichier lisait le `.env` de JohnnyBot (voir plus haut) et
# faisait tourner les SIX personas dessus. Une passe complete — ~102 appels de bot, autant
# de juge — tapait donc six fois sur le seul projet Google de Johnny, quand la production
# en a six separes, un par bot.
#
# C'est l'explication du « plancher de bruit » qu'on documentait comme une fatalite :
# deux passes identiques le meme jour bougeaient de ±0,4 en global et jusqu'a 6/17 sur la
# colonne AVANT, « parce que le tirage de l'ORDRE decide qui a le quota Gemini frais ».
# Il n'y avait pas de loterie : le premier bot tire vidait la reserve de Johnny, et les
# suivants retombaient sur ministral — dont on sait qu'il produit une didascalie 3 fois
# sur 4. Le harnais ne mesurait pas six bots, il mesurait une file d'attente.
#
# Verifie sur `api_usage.db` (17-18/09) : en PRODUCTION les epuisements ne sont PAS
# simultanes — sur 41 minutes ou au moins un bot est ecarte, **37 ne concernent qu'un seul
# bot**. Johnny s'epuise le 17 a 01h45, Sheogorath le 18 a 00h56. Les quotas sont bien
# separes ; c'est ici qu'ils etaient confondus.
#
# [[gotcha-sonde-ne-reproduit-pas-le-fournisseur]] — meme famille que `groq_kwargs()`
# oublie, ou que le client NVIDIA jamais construit : un harnais qui ne reproduit pas les
# conditions du bot mesure autre chose que le bot.
# ---------------------------------------------------------------------------

# Le dossier de chaque bot, DEDUIT de la table des personas : elle porte deja
# « JohnnyBot.johnny_data ». Une seconde liste ecrite a la main divergerait en silence,
# comme les deux listes de vendoring l'ont fait ([[gotcha-deux-listes-vendoring]]).
def _dossier_du_bot(bot_id: str) -> Path:
    from tests.eval.persona_loader import PERSONAS
    module = PERSONAS[bot_id][0]
    return Path(root_dir) / module.split(".")[0]


_ATTELAGES: dict = {}


def attelage_du_bot(bot_id: str):
    """Rend (key_manager, groq, mistral, nvidia) construits avec les cles DE CE BOT.

    ⚠️ `load_secure_env` ecrit dans `os.environ` : charger un deuxieme bot ecrase le
    premier. Les clients sont donc construits AUSSITOT apres le chargement, puis gardes —
    ils portent leur cle en propre et ne relisent plus l'environnement. Construire
    paresseusement plus tard rendrait les cles du dernier bot charge, silencieusement.
    """
    if bot_id in _ATTELAGES:
        return _ATTELAGES[bot_id]

    dossier = _dossier_du_bot(bot_id)
    if not load_secure_env(dossier):
        raise RuntimeError(
            f"{bot_id} : aucune cle lisible dans {dossier} — le harnais refuse de mesurer "
            "avec les cles du bot charge precedemment"
        )

    gemini = [os.getenv(f"GEMINI_KEY_{i}") for i in range(1, 5)]
    gemini = [k for k in gemini if k]
    groq_key = os.getenv("GROQ_API_KEY")
    mistral_key = os.getenv("MISTRAL_API_KEY")
    nvidia_key = os.getenv("NVIDIA_API_KEY")

    km = MultiAPIKeyManager()
    km.register_api("gemini", gemini)
    km.register_api("groq", [groq_key] if groq_key else [])
    km.register_api("mistral", [mistral_key] if mistral_key else [])
    # ⚠️ NVIDIA manquait ici : sans pool, sa clé ne pouvait pas être mise en
    # quarantaine sur un 429, et son index restait absent de `api_key_status`.
    km.register_api("nvidia", [nvidia_key] if nvidia_key else [])

    # ⚠️ Le client NVIDIA manquait, et le pool ci-dessus ne suffisait pas : la cascade teste
    # `elif client_type == "nvidia" and nvidia_client`. Sans client, le 4e echelon — le DERNIER
    # de chacune des six cascades — n'etait jamais appele, et chaque passage inscrivait une
    # ligne `raison='non_tentee'`, `latency_ms=0`. Releve du 2026-09-17 sur `api_usage.db` :
    # 30 lignes de ce genre, toutes issues d'un run d'eval, et AUCUN succes NVIDIA depuis que
    # la base existe. Le dashboard les comptait en echecs et affichait « nvidia 0.0 % ».
    # Un harnais qui ne cable pas un echelon ne mesure pas la cascade du bot, il en mesure une
    # amputee — [[gotcha-sonde-ne-reproduit-pas-le-fournisseur]], [[gotcha-nvidia-jamais-cable-inline]].
    attelage = (
        km,
        Groq(api_key=groq_key) if groq_key else None,
        Mistral(api_key=mistral_key) if mistral_key else None,
        OpenAI(api_key=nvidia_key, base_url=NVIDIA_BASE_URL, max_retries=0) if nvidia_key else None,
    )
    print(f"[CLES] {bot_id} : gemini x{len(gemini)}"
          f"{' groq' if groq_key else ''}{' mistral' if mistral_key else ''}"
          f"{' nvidia' if nvidia_key else ''}")
    _ATTELAGES[bot_id] = attelage
    return attelage

async def run_scenario_for_bot(
    bot_id: str,
    scenario: dict,
    historique_brut: bool = False,
    borne_du_direct: bool = False,
) -> tuple[list[str], list[str], list[str | None]]:
    """
    Exécute un scénario (pouvant comporter plusieurs tours) pour un bot donné.

    Rend TROIS listes, de même longueur : les réponses telles que l'utilisateur les lit
    (filtrées), les mêmes AVANT le filtre de sortie du bot, et l'échelon (``api/modele``)
    qui a répondu à chaque tour — `None` si aucun appel n'a été tracé.

    `historique_brut=True` remet le texte NON filtré dans `conversation_history` : voir
    le commentaire au point où l'historique est nourri, plus bas.

    `borne_du_direct=True` remplace la borne patiente du lot par celle du chat
    (`_BORNE_TEXTE`) : voir le commentaire au point d'appel, plus bas.

    ⚠️ La brute n'est pas un confort. Le 2026-09-17, après avoir posé un filet
    déterministe (LOT 1) ET réécrit les fiches de persona (LOT 2), il était impossible de
    dire lequel des deux avait agi : le rapport ne gardait que le texte filtré, où il n'y
    a par construction plus une seule astérisque. Trancher aurait demandé un run entier
    avec le filtre désarmé — une heure et du quota, pour une information que chaque run
    peut livrer gratuitement. Le juge, lui, continue de noter la version filtrée : c'est
    celle que l'utilisateur lit.
    """
    # ⚠️ Les cles DE CE BOT, pas celles de Johnny : voir le bloc `attelage_du_bot`.
    key_manager, groq_client, mistral_client, nvidia_client = attelage_du_bot(bot_id)

    persona = load_persona(bot_id)
    system_prompt = persona["system_prompt"]
    bot_label = persona["bot_label"]

    # Le filtre de sortie du bot : sans lui on note la sortie BRUTE du modèle, c'est-à-dire
    # un texte que l'utilisateur ne voit jamais. Mesuré le 2026-09-17 : Sheogorath perdait
    # des points sur 17 réponses sur 17 pour des astérisques qu'il retire lui-même, et un
    # filet ajouté aux bots nus n'aurait bougé aucun score.
    # Cf. [[gotcha-le-harnais-mesure-le-modele-pas-le-bot]].
    filtre_sortie = load_filtre(bot_id)
    
    conversation_history = []
    responses = []
    responses_brutes = []
    echelons = []
    
    # Scénario info
    user_messages = scenario.get("user_messages", [])
    initial_transcript = scenario.get("transcript", "")
    
    for user_msg in user_messages:
        # Construction du transcript pour les modèles non-Gemini
        transcript_lines = []
        if initial_transcript:
            transcript_lines.append(initial_transcript)
            
        for h_msg in conversation_history:
            role_prefix = f"({bot_label})" if h_msg["role"] == "model" else "(User)"
            transcript_lines.append(f"{role_prefix}: {h_msg['parts'][0]}")
            
        transcript = "\n".join(transcript_lines)
        
        # Le type de requête est texte
        routing = {
            "type": RequestType.TEXT,
            "reason": f"Eval harness - Scenario {scenario.get('id')} - Bot {bot_id}"
        }
        
        # Appel de la cascade LLM
        with _echelon_qui_repond() as echelons_vus:
            response = await generate_response(
                routing=routing,
                system_prompt=system_prompt,
                transcript=transcript,
                user_message=user_msg,
                conversation_history=conversation_history,
                media_data=None,
                mime_type="",
                key_manager=key_manager,
                mistral_client=mistral_client,
                groq_client=groq_client,
                nvidia_client=nvidia_client,
                bot_label=bot_label,
                temperature=0.8,
                max_tokens=300,
                # ⚠️ La borne par défaut de la cascade (`_BORNE_TEXTE`, 15 s) est calibrée
                # pour un bot EN DIRECT : au-delà, l'utilisateur voit un silence, donc mieux
                # vaut basculer d'échelon. Ici personne n'attend devant un écran, et la borne
                # se retourne contre nous : un 429 Groq est absorbé par le SDK qui DORT ~36 s
                # ([[gotcha-429-groq-dort-en-silence]]), et 15 s transforment cette attente
                # légitime en `TimeoutError`. Mesuré le 2026-09-16 : 14 appels Groq d'affilée
                # perdus ainsi, 0 réponse obtenue, alors que l'hôte joignait l'API en 0,3 s.
                # Un lot patient mesure les bots ; un lot pressé ne mesure que sa propre borne.
                #
                # ⚠️ MAIS la borne patiente CACHE aussi ce que le direct refuserait. Mesure
                # du 2026-09-18 sur les 67 appels `google/gemma-4-31b-it` de la passe qui
                # l'a valide : mediane 12,4 s, et 26 d'entre eux au-dela de 15 s — comptes
                # en SUCCES ici, refuses la-bas. Le harnais annoncait donc un echelon qui
                # sert 100 % des tours quand le chat n'en voit que ~60 %, et le verdict de
                # persona qui en decoule (« johnny 3.70 -> 5.00 ») decrivait un bot qui
                # n'existe pas. `borne_du_direct=True` rend au lot la borne du chat, pour
                # repondre a la seule question qui vaille : que voit l'UTILISATEUR ?
                # [[gotcha-borne-du-direct-sabote-le-lot]] est l'erreur inverse — les deux
                # bornes sont justes, chacune pour sa question ; c'est le fait d'en avoir
                # UNE SEULE qui trompe.
                call_timeout=(_BORNE_TEXTE if borne_du_direct else 90.0),
            )

        # Un seul échelon peut rendre un succès par appel. Liste vide = rien de tracé :
        # cascade entièrement muette, ou `generate_response` remplacé par une sonde.
        echelons.append(echelons_vus[-1] if echelons_vus else None)

        responses_brutes.append(response if response is not None else ECHEC_CASCADE)

        if response is None:
            # Fallback en cas d'échec total de la cascade
            response = ECHEC_CASCADE
        else:
            # ⚠️ APRÈS le repli : `ECHEC_CASCADE` est un marqueur du harnais, pas une
            # réplique de bot — le filtrer n'aurait aucun sens et pourrait l'effacer.
            response = filtre_sortie(response, user_msg)

        responses.append(response)

        # Mise à jour de l'historique pour le tour suivant.
        conversation_history.append({"role": "user", "parts": [user_msg]})
        # ⚠️ Ce qui repart dans l'historique est ce que l'utilisateur A LU : sur Discord,
        # le tour suivant relit le message FILTRÉ, celui qui a été envoyé. Le harnais
        # doit donc filtrer ici aussi, sinon il mesure une conversation qui n'a jamais eu
        # lieu — [[gotcha-le-harnais-mesure-le-modele-pas-le-bot]].
        #
        # `historique_brut=True` désarme ce choix pour UNE question précise, ouverte
        # depuis le 2026-09-17 : depuis que l'historique est assaini, le modèle s'imite
        # lui-même SANS astérisques, et la baisse de production observée peut venir de la
        # fiche de persona, de cet historique propre, ou des deux. Le drapeau sert à
        # trancher cette question-là, jamais à mesurer les bots : un run mené ainsi ne
        # décrit plus le bot réel, et `run_eval.py` refuse de le comparer à un run normal.
        memoire = responses_brutes[-1] if historique_brut else response
        conversation_history.append({"role": "model", "parts": [memoire]})

    return responses, responses_brutes, echelons
