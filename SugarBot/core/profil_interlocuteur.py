# ⚠️ FICHIER GENERE — NE PAS EDITER ICI.
# Source : shared/profil_interlocuteur.py — modifier la source puis relancer :
#     python tools/vendor_core.py
# La sonde tools/sonde_core_drift.py echoue si cette copie diverge.

# -*- coding: utf-8 -*-
"""Profil structurel Discord — calculé à partir des données de membre livrées par Discord.

Ces faits sont purement structurels : calculés, jamais extraits par un LLM.
Ils ne passent JAMAIS par la balise <fact> et sont donc immunisés contre
l'auto-attribution.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, List
import discord


def _duree_lisible(dt: datetime, now: datetime) -> str:
    """Calcule une durée lisible en français entre dt et now."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    delta = now - dt
    jours = delta.days
    if jours < 1:
        return "aujourd'hui"
    if jours < 30:
        return f"{jours} jour{'s' if jours > 1 else ''}"
    mois = jours // 30
    if mois < 12:
        return f"{mois} mois"
    annees = jours // 365
    reste_mois = (jours % 365) // 30
    if annees == 1 and reste_mois >= 6:
        return "1 an et demi"
    if annees > 1 and reste_mois >= 6:
        return f"{annees} ans et demi"
    if annees <= 1:
        return "1 an"
    return f"{annees} ans"


def construire_profil_discord(
    author,
    now: Optional[datetime] = None,
    reputation_data: Optional[Dict] = None,
    quests_data: Optional[List[Dict]] = None,
) -> str:
    """Construit un bloc de contexte structurel à partir d'un membre Discord (salon serveur).

    ⚠️ En message privé, message.author est un User et non un Member :
    roles et joined_at n'existent pas. On retourne une chaîne vide dans ce cas,
    sans lever d'exception.
    """
    if author is None:
        return ""

    # En message privé, message.author est un User (sans rôles ni joined_at)
    if isinstance(author, discord.User) and not isinstance(author, discord.Member):
        return ""

    # Doit posséder une date d'arrivée sur le serveur valide (datetime)
    joined_at = getattr(author, "joined_at", None)
    if not isinstance(joined_at, datetime):
        return ""

    if now is None:
        now = datetime.now(timezone.utc)

    lignes = []

    # 1. Ancienneté sur le serveur (joined_at)
    duree_serveur = _duree_lisible(joined_at, now)
    date_serveur = joined_at.strftime("%d/%m/%Y")
    lignes.append(f"Sur ce serveur depuis : {duree_serveur} (rejoint le {date_serveur})")

    # 2. Rôles sur le serveur (hors @everyone)
    roles = getattr(author, "roles", None)
    if isinstance(roles, (list, tuple, set)) and roles:
        noms_roles = [
            getattr(r, "name", str(r))
            for r in roles
            if getattr(r, "name", str(r)) != "@everyone"
        ]
        if noms_roles:
            roles_str = ", ".join(noms_roles[:8])
            if len(noms_roles) > 8:
                roles_str += f" (+{len(noms_roles) - 8} autres)"
            lignes.append(f"Rôles sur le serveur : {roles_str}")

    # 3. Surnom vs nom
    nick = getattr(author, "nick", None)
    name = getattr(author, "name", "")
    if isinstance(nick, str) and isinstance(name, str) and nick and nick != name:
        lignes.append(f"Surnom sur le serveur : {nick} (nom de compte : {name})")

    # 4. Booster du serveur (premium_since)
    premium_since = getattr(author, "premium_since", None)
    if isinstance(premium_since, datetime):
        duree_boost = _duree_lisible(premium_since, now)
        lignes.append(f"Booster du serveur : oui (depuis {duree_boost})")

    # 5. Ancienneté du compte Discord (created_at)
    created_at = getattr(author, "created_at", None)
    if isinstance(created_at, datetime):
        duree_compte = _duree_lisible(created_at, now)
        date_compte = created_at.strftime("%d/%m/%Y")
        lignes.append(f"Ancienneté du compte Discord : {duree_compte} (créé le {date_compte})")

    # 6. Ce qui dort en base : Réputation & Quêtes (Lot 3)
    if isinstance(reputation_data, dict):
        pts = reputation_data.get("points", 0)
        streak = reputation_data.get("riddle_streak", 0) or 0
        if pts > 0 or streak > 0:
            # `add_reputation` insere une 1re ligne SANS `level` : la cle existe a NULL.
            lvl = reputation_data.get("level") or "Inconnu"
            rep_desc = f"Réputation sur le serveur : {lvl} ({pts} point{'s' if pts > 1 else ''})"
            if streak > 0:
                rep_desc += f" — série d'énigmes : {streak} victoire{'s' if streak > 1 else ''} d'affilée"
            lignes.append(rep_desc)

    if isinstance(quests_data, list) and quests_data:
        nb_faites = sum(1 for q in quests_data if q.get("completed", 0) == 1)
        total_quetes = len(quests_data)
        lignes.append(f"Quêtes du jour : {nb_faites}/{total_quetes} accomplie{'s' if nb_faites > 1 else ''}")

    if not lignes:
        return ""

    return "[PROFIL DISCORD DE L'INTERLOCUTEUR]:\n- " + "\n- ".join(lignes)
