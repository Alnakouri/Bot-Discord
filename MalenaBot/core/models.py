# ⚠️ FICHIER GENERE — NE PAS EDITER ICI.
# Source : shared/models.py — modifier la source puis relancer :
#     python tools/vendor_core.py
# La sonde tools/sonde_core_drift.py echoue si cette copie diverge.

# Source unique de vérité des identifiants de modèles.
# Vérifiés vivants le 2026-08-24 (sonde réelle, clés de prod).
GEMINI_FLASH      = "gemini-3.5-flash"
GEMINI_FLASH_LITE = "gemini-3.5-flash-lite"
GROQ_FAST         = "openai/gpt-oss-120b"
MISTRAL_MAIN      = "mistral-large-latest"
OPENROUTER_FREE   = "nvidia/nemotron-3-super-120b-a12b:free"


# Modeles a RAISONNEMENT : ils depensent des tokens en pensee AVANT de repondre.
# Mesure Groq du 2026-08-26 (openai/gpt-oss-120b, meme prompt) :
#   defaut          -> 144 tokens de completion
#   effort "low"    ->  71 tokens
#   low + "hidden"  ->  47 tokens
# Sans cela, avec max_tokens=300 et un prompt de persona un peu long, la pensee mange
# tout le budget : finish_reason="length" et un `content` VIDE, donc bot muet.
# Meme famille que le gotcha Gemini "thinking mange max_output_tokens".
GROQ_REASONING_MODELS = ("gpt-oss",)


def groq_kwargs(model_name):
    """Arguments a ajouter a un appel Groq selon que le modele raisonne ou non.

    `reasoning_format="hidden"` garantit en plus que la pensee n'atterrit JAMAIS dans
    `content` — c'est ce genre de fuite qui a fait reciter son raisonnement a Malena
    en pleine conversation Discord.
    """
    if any(marqueur in (model_name or "") for marqueur in GROQ_REASONING_MODELS):
        return {"reasoning_effort": "low", "reasoning_format": "hidden"}
    return {}


# ---------------------------------------------------------------------------
# Modeles supplementaires, mesures vivants le 2026-08-26
# (tools/sonde_modeles_persona.py, appels reels avec les vraies personas).
# ---------------------------------------------------------------------------
GROQ_QWEN     = "qwen/qwen3.8-27b"      # Groq — le plus incisif, reponses courtes
GROQ_SMALL    = "openai/gpt-oss-20b"    # Groq — le plus rapide (0.45 s median)
MISTRAL_SMALL = "mistral-small-latest"  # Mistral — argot FR le plus naturel

# ---------------------------------------------------------------------------
# CASCADE PAR PERSONA
#
# Les 6 bots partageaient exactement la meme cascade : meme modele, donc meme
# "voix" de fond sous six personnalites differentes. Le choix ci-dessous vient
# d'une sonde reelle (3 messages x 6 personas x 10 modeles) — pas d'une intuition.
#
# Mesures qui ont ecarte des candidats :
#   - free-tier OpenRouter    : 12 echecs sur 12 (429 en rafale, 60-120 s de latence).
#                               Retire des cascades de persona, garde comme code mort utile
#                               si un jour un modele gratuit redevient fiable.
#   - qwen3.6-27b             : recopie sa pensee (<think>) dans la reponse.
#   - groq/compound-mini      : 8 echecs sur 12.
#   - nemotron*:free          : fuite de raisonnement systematique (cf. gotcha).
#   - gemini-3.5-flash        : 10,3 s de latence mediane — trop lent pour du chat.
#
# Chaque cascade melange des fournisseurs DIFFERENTS : leurs quotas sont independants,
# donc si l'un throttle, l'echelon suivant repond quand meme.
# ---------------------------------------------------------------------------
CASCADES_PERSONA = {
    # Majordome : ironie seche, formulation soignee. Mistral Large tient le registre
    # « Monsieur » sans deraper. (« Monsieur a enfin compris l'evidence. Une demi-journee
    # de retard, mais mieux vaut tard que jamais. »)
    "alfred": [("mistral", MISTRAL_MAIN), ("groq", GROQ_FAST), ("gemini", GEMINI_FLASH_LITE)],

    # Rockerboy de Night City : argot cru, phrases qui cognent. Mistral Small est le seul
    # a sortir le vocabulaire de la rue sans l'edulcorer (« t'es un gonk avec un clavier »).
    "johnny": [("mistral", MISTRAL_SMALL), ("groq", GROQ_FAST), ("gemini", GEMINI_FLASH_LITE)],

    # Prince Daedra de la Folie : chaos, lore ESO, images viscerales. Qwen ressort le
    # Wabbajack et Haskill de lui-meme, la ou les autres restent generiques.
    "sheo": [("groq", GROQ_QWEN), ("mistral", MISTRAL_MAIN), ("groq", GROQ_FAST)],

    # Piques courtes et sechees. Qwen a la mediane de tokens la plus basse (43) : il
    # tranche au lieu de meubler (« plus polymorphe que ton vocabulaire entier, peteur »).
    "sugar": [("groq", GROQ_QWEN), ("mistral", MISTRAL_SMALL), ("gemini", GEMINI_FLASH_LITE)],

    # Menteur cryptique d'Elder Scrolls : absurde bref a la 3e personne. Gemini Flash-Lite
    # invente les meilleures faussetes (« La troisieme lune existe. Elle est juste
    # invisible pour les imbeciles. »)
    "maiq": [("gemini", GEMINI_FLASH_LITE), ("mistral", MISTRAL_MAIN), ("groq", GROQ_SMALL)],

    # Diva gitane marseillaise : l'argot local doit sonner juste. Mistral Small sort
    # « chanklette », « bonne mere », « gatee va » sans qu'on le lui souffle.
    "malena": [("mistral", MISTRAL_SMALL), ("gemini", GEMINI_FLASH_LITE), ("groq", GROQ_FAST)],
}

_MARQUEURS_BOT = {
    "alfred": ("alfred",),
    "johnny": ("johnny", "silverhand"),
    "maiq":   ("maiq",),
    "malena": ("malena",),
    "sheo":   ("sheogorath", "sheo"),
    "sugar":  ("sugar",),
}


def bot_id_depuis_label(label):
    """Retrouve l'identifiant du bot depuis son etiquette d'affichage.

    Les etiquettes ne sont pas normalisees dans le code des bots : on croise
    « Johnny » et « Johnny Silverhand », « M'aiq », « M'aiq le Menteur » et « Maiq ».
    """
    normalise = (label or "").lower().replace("'", "").replace("\u2019", "")
    for bot_id, marqueurs in _MARQUEURS_BOT.items():
        if any(marqueur in normalise for marqueur in marqueurs):
            return bot_id
    return None


def cascade_persona(bot_id_ou_label):
    """Cascade propre a la persona, ou None si le bot n'en a pas."""
    if not bot_id_ou_label:
        return None
    bot_id = bot_id_ou_label if bot_id_ou_label in CASCADES_PERSONA else bot_id_depuis_label(bot_id_ou_label)
    cascade = CASCADES_PERSONA.get(bot_id)
    return list(cascade) if cascade else None


# ---------------------------------------------------------------------------
# CASCADE DES ANNONCES DE LIVE
#
# Une annonce n'est pas une reponse de chat : elle est PUBLIQUE, lue par tout le
# monde, et un francais bancal s'y voit tout de suite. C'est donc la qualite de
# langue qui commande, pas le ton — comme pour la vision, ou c'est la capacite du
# modele qui commande.
#
# Mesure du 2026-08-26 sur le vrai prompt d'annonce (Sugar, 4 tirages/modele) :
#   qwen3.8-27b        francais le PLUS faible : « KCD2, ca s'quille ! Ma_Streameuse
#                      est derriere les foudres du fer » ne veut rien dire.
#                      C'est ce modele qui a produit « son goat de Boheme ».
#   gemini-flash-lite  le plus sur : correct, varie, en personnage, sans invention
#   mistral-large      francais impeccable mais tres repetitif (3 tirages sur 4
#                      commencent par la meme tournure) et coupe a 120 tokens
#   gpt-oss-120b       correct mais invente des superlatifs, ce que le prompt interdit
#
# La persona reste audible : elle vient du prompt systeme, pas du modele.
CASCADE_ANNONCE = [
    ("gemini", GEMINI_FLASH_LITE),
    ("mistral", MISTRAL_MAIN),
    ("groq", GROQ_FAST),
]
