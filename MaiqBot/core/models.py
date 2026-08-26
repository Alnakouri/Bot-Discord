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
