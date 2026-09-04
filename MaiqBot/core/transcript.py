# ⚠️ FICHIER GENERE — NE PAS EDITER ICI.
# Source : shared/transcript.py — modifier la source puis relancer :
#     python tools/vendor_core.py
# La sonde tools/sonde_core_drift.py echoue si cette copie diverge.

def ligne_de_contexte(hist_msg, moi, *, avec_mention=False):
    """Rend la ligne à mettre au transcript pour ce message, ou None s'il n'y a rien à dire."""
    if hist_msg.author.bot and hist_msg.author != moi:
        # Trace neutre pour les autres bots
        return f"{hist_msg.author.name} : [a repondu]\n"
        
    # Verbatim pour l'utilisateur et le bot lui-même
    if avec_mention:
        return f"{hist_msg.author.name} ({hist_msg.author.mention}): {hist_msg.content}\n"
    else:
        return f"{hist_msg.author.name}: {hist_msg.content}\n"
