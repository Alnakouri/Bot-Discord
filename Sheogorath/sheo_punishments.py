import os
DATA_DIR = os.getenv("DATA_DIR", ".")
# -*- coding: utf-8 -*-

# INJECTION SHARED FOLDER
import sys
import os
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

"""
Système de punitions de Sheogorath.
Gère les changements de pseudo temporaires (Wabbajack automatique).
"""
import discord
import asyncio
import json
import os
import random
import logging
from datetime import datetime

logger = logging.getLogger("sheogorath")

PUNISHMENT_FILE = os.path.join(DATA_DIR, "sheo_punishments.json")


def load_punishments():
    if not os.path.exists(PUNISHMENT_FILE):
        return {}
    try:
        with open(PUNISHMENT_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Erreur chargement punitions: {e}")
        return {}


def save_punishments(data):
    try:
        with open(PUNISHMENT_FILE, "w") as f:
            json.dump(data, f)
    except OSError as e:
        logger.warning(f"⚠️ Sauvegarde {PUNISHMENT_FILE} impossible ({e}) — état non persisté.")


# LISTE DES SURNOMS DE PUNITION
PUNISHMENT_NICKS = [
    # Classiques
    "L'Idiot du Village", "Fromage Rance", "Saucisse Triste", "Coussin Péteur", "Haskill Jr.", "Tartelette", "Ver de Terre",
    "Chaussette Mouillée", "Grummite Rasé", "Crêpe Molle", "Navet Cosmique", "Pizza l'Ananas", "Rot de Troll",
    "Vase Vide", "Cuillère Tordue", "Escargot Baveux", "Clown Triste", "Chaise Bancale", "Poussière d'Étoile",
    "Salade Flétrie", "Moustique Ivre", "Caillou Inutile", "Perruque de Chauve", "Sandwich au Sable",
    # Titres de noblesse inversés
    "Bouffon Raté", "Roi des Nuls", "Prince du Vide", "Duc de la Poisse", "Baron du Rien", "Comte Zéro",
    "Marquis de l'Échec", "Vicomte Inutile", "Seigneur du Néant", "Empereur de la Lose",
    # Gaming/Internet
    "Jester de Lidl", "Clown Eco+", "NPC Inutile", "Mob de Tutoriel", "Boss Raté", "Lag Humain",
    "Erreur 404", "Ping de 9000", "Connection Lost", "Game Over Vivant", "Respawn Infini",
    "Noob Cosmique", "AFK Mental", "Rage Quit Vivant", "Troll de Level 1", "Smurf Raté",
    "Bug Ambulant", "Glitch Incarné", "Patch Requis", "Nerf Nécessaire", "Delete Account",
    "Low Elo Legend", "Feeder Professionnel", "XP Waste", "Loot Poubelle", "Drop Commun",
    # Nourriture
    "Fromage sans Goût", "Lait Caillé", "Yaourt Périmé", "Croûte de Pain", "Miette de Biscuit",
    "Soupe Tiède", "Pain Rassis", "Salade Fade", "Sauce Tournée", "Dessert Raté",
    "Oeuf Pourri", "Sushi Douteux", "Pizza Froide", "Kebab du Lendemain", "Frite Molle",
    "Burger Écrasé", "Hot-Dog Froid", "Taco Fuyant", "Crêpe Brûlée", "Gaufre Caoutchouc",
    # Lore-based Elder Scrolls
    "Tête de Citrouille", "Face de Sculpin", "Haleine de Ogrim", "Pied de Géant", "Orteil de Galopin",
    "Esclave de Molag Bal", "Jouet de Dagon", "Tapis de Mephala", "Déchet de Peryite", "Erreur de Jyggalag",
    "Ami d'Haskill", "Fan de Jyggalag", "Serviteur de l'Ordre", "Grummite Démaquillé",
    "Mudcrab Écrasé", "Skeever Rachitique", "Horker Pelé", "Kwama Stérile", "Netch Dégonflé",
    "Cliff Racer Plumé", "Dremora Stagiaire", "Scrib Éviscéré", "Kagouti Édenté", "Nix-Hound Chétif",
    "Alit Végétarien", "Dreugh Sans Pinces", "Slaughterfish Végane", "Clannfear Peureux",
    # Objets/Créatures du quotidien
    "Poubelle Ambulante", "Paillasson", "Marchepied", "Cale-Porte", "Ancre de Bateau",
    "Parapluie Troué", "Chaussette Orpheline", "Gant Dépareillé", "Caleçon Troué",
    "Balai Sans Poils", "Serpillière Sèche", "Éponge Dure", "Savon Glissant", "Torchon Miteux",
    "Rideau Terne", "Oreiller Plat", "Couverture Trouée", "Matelas Moisi", "Réveil Cassé",
    # Créatures ratées/mythologiques
    "Dragon Édenté", "Géant de 1m12", "Mammouth Tondu", "Squelette Obèse", "Licorne sans Corne",
    "Vampire Anémique", "Loup-Garou Caniche", "Zombie Vegan", "Fantôme Visible",
    "Sirène Aphone", "Méduse Chauve", "Centaure Cul-de-Jatte", "Minotaure Végétarien", "Hydre Monocéphale",
    "Phoenix Mouillé", "Kraken de Piscine", "Basilic Myope", "Golem d'Argile Molle", "Sphinx Sans Énigme",
    # Ultra-humiliants psychologiques
    "Déception Parentale", "Regret Vivant", "Accident de Parcours", "Erreur de la Nature", "Blague Pas Drôle",
    "Dernier de la Classe", "Ami Imaginaire", "Malchance Incarnée", "Erreur de Casting",
    "CV Rejeté", "Candidat Refusé", "Stage Non Rémunéré", "Stagiaire Éternel", "Echec Scolaire",
    "Option Par Défaut", "Plan B Raté", "Roue de Secours Crevée", "Bouche-Trou Inutile",
    # Métaphores créatives
    "Ombre d'une Ombre", "Écho d'un Pet", "Reflet d'un Vide", "Parfum de Défaite", "Goût d'Échec",
    "Bruit d'un Silence", "Couleur du Néant", "Température Tiède", "Saveur Fade", "Texture Molle",
    # Absurdes poussés
    "Pique-Nique Pluvieux", "Dimanche Pluvieux", "Lundi Matin", "Embouteillage Vivant", "File d'Attente Humaine",
    "Salle d'Attente Incarnée", "Pub YouTube", "Spam Email", "Appel Démarchage", "Colis Perdu",
]


# CATÉGORISATION DES INSULTES PAR GRAVITÉ
LIGHT_INSULTS = ["fou", "naze", "bête", "chiant", "fatigant", "mauvais", "inutile", "ennuyeux", "boring"]
MEDIUM_INSULTS = ["idiot", "débile", "crétin", "imbécile", "abruti", "stupide", "cul", "moche", "tocard", "bouffon", "blaireau", "boloss"]
HEAVY_INSULTS = ["merde", "salope", "batard", "connard", "poubelle", "ferme ta", "taré", "clochard", "pourri", "merdique", "ferme-la", "tg", "fdp", "ntm", "chier", "crève", "gueule", "mongol"]
META_KEYWORDS = ["nul", "radote", "radoter", "répète", "repete", "dico", "vocabulaire", "varié", "original", "parles trop", "cassé", "bug", "broken"]

# Durées selon gravité (en secondes)
DURATION_MAP = {
    1: 300,   # 5 minutes (léger)
    2: 600,   # 10 minutes (moyen)
    3: 900,   # 15 minutes (lourd)
}


def get_insult_severity(msg_lower):
    """Analyse le message et retourne la gravité (0-3)."""
    if any(w in msg_lower for w in HEAVY_INSULTS):
        return 3
    elif any(w in msg_lower for w in MEDIUM_INSULTS):
        return 2
    elif any(w in msg_lower for w in LIGHT_INSULTS):
        return 1
    elif any(w in msg_lower for w in META_KEYWORDS):
        return 2  # Critiquer le bot = medium
    return 0


def get_punishment_messages(member, new_nick):
    """Retourne les listes de messages de punition, libération et échec."""
    punishment_messages = [
        # Classiques méchants
        f"🪄 **WABBAJACK !** {member.mention} → **{new_nick}** ! Porte ce nom avec la honte que tu mérites ! 💀",
        f"✨ *POUF* ✨ {member.mention} n'existe plus. Seul **{new_nick}** reste. Amélioration notable. 🧀",
        f"🌩️ Par les Seize ! {member.mention} ose m'insulter ? Tu es maintenant **{new_nick}** ! Définitif ? On verra. 😈",
        f"📜 Qu'il soit écrit dans les annales : {member.mention} = **{new_nick}**. Pour l'éternité ! (10 min) 🪶",
        f"🎭 Oh ? Tu voulais de l'attention ? EN VOICI ! Bienvenue, **{new_nick}** ! 🎪",
        # Ultra-courts et cinglants
        f"**{new_nick}**. C'est toi maintenant. 💅",
        f"🪄 → **{new_nick}**. Prochaine fois, réfléchis. 🧠❌",
        f"Félicitations ! Tu as gagné le titre de **{new_nick}** ! 🏆🗑️",
        f"**{new_nick}**. Parfait pour toi. 🎯",
        f"Nouveau nom : **{new_nick}**. C'est un ordre. 👑",
        f"Tu es **{new_nick}** maintenant. Deal with it. 😎",
        f"**{new_nick}**. Ça te va bien. Trop bien. 💯",
        f"Voilà : **{new_nick}**. Porte-le fièrement. (Non) 🎪",
        f"**{new_nick}** ! Simple. Efficace. Humiliant. ✨",
        f"Bienvenue **{new_nick}** ! Adieu dignité. 👋",
        f"Tu t'appelles **{new_nick}** maintenant. Merci, au revoir. 🚪",
        f"**{new_nick}**. Un nom PARFAIT pour quelqu'un comme toi. 🎯💩",
        f"Nouveau surnom : **{new_nick}**. J'adore. 😍 (Toi non) 😭",
        f"**{new_nick}** ! C'est décidé. C'est signé. C'est fait. ✍️✅",
        f"Satisfait ? Non ? Tant pis. Tu es **{new_nick}**. 🤷",
        # Menaces absurdes
        f"🔮 Le Wabbajack a parlé ! {member.mention} sera **{new_nick}** jusqu'à ce que les étoiles s'éteignent ! (ou 10 min) ⭐",
        f"🧀 J'aurais pu te transformer en fromage. Mais **{new_nick}** est pire. Profite. 🧀",
        f"💫 *TRANSFORMATION !* {member.mention} disparaît... **{new_nick}** apparaît ! Magie ! 🎩",
        f"⚡ Le sort est lancé ! {member.mention} → **{new_nick}** ! Résiste si tu l'oses ! (Tu ne peux pas) 🔮",
        # Faux compliments
        f"Quel honneur pour toi, {member.mention} ! Tu portes maintenant le noble titre de **{new_nick}** ! 👑🗑️",
        f"Bravo ! Tu as été promu au rang de **{new_nick}** ! Félicitations ? Non. 🎊💀",
        f"MAGNIFIQUE promotion ! {member.mention} → **{new_nick}** ! Ta carrière décolle ! (Vers le bas) 📉✨",
        # Références fromage
        f"🧀 Le fromage a décidé : {member.mention} = **{new_nick}** ! Ne discute PAS avec le fromage ! 🧀",
        f"Le Grand Fromage Cosmique m'a parlé. Il veut que tu sois **{new_nick}**. Qui suis-je pour refuser ? 🌌🧀",
        # Lore-based Elder Scrolls
        f"🌀 Au nom de Mania et Démence, je te baptise **{new_nick}** ! Amen. Ou pas. 🌀",
        f"⚖️ Jyggalag aurait été plus gentil. Moi ? Tu es **{new_nick}**. Souffre. ⚖️",
        f"👔 Même Haskill rirait. **{new_nick}**. C'est magnifique. 👔",
        # Dramatiques/Théâtraux
        f"🎆 PROCLAMATION DIVINE ! {member.mention} cesse d'exister ! Longue vie à **{new_nick}** ! 🎇",
        f"📢 ÉCOUTEZ TOUS ! {member.mention} s'appelle désormais **{new_nick}** ! Applaudissez ! (Ou moquez) 👏😏",
        f"🎺 SONNEZ TROMPETTES ! **{new_nick}** entre en scène ! {member.mention} sort côté cour ! 🎭",
        # Verdict juridique
        f"⚖️ VERDICT : COUPABLE ! Sentence : Devenir **{new_nick}** ! Durée : 10 minutes ! Appel : REFUSÉ ! 🔨",
        f"👨‍⚖️ La Cour de la Folie déclare : {member.mention} → **{new_nick}** ! Que justice soit faite ! ⚖️",
    ]

    release_messages = [
        # Classiques sarcastiques
        f"🔓 Bon. {member.mention}, ta pénitence est terminée. Essaie d'être moins pathétique. 😒",
        f"⏰ Le temps est écoulé. {member.mention} retrouve son identité. Dommage, **{new_nick}** t'allait mieux. 💅",
        f"🎭 Fin du spectacle ! {member.mention} redevient... lui-même. Quelle régression. 🎪",
        f"✨ *La malédiction se dissipe...* Tu peux respirer, {member.mention}. Cette fois. 🌙",
        f"📜 Ta sentence est levée. Ne me fais pas regretter ma clémence, {member.mention}. 👀",
        f"🧀 Le fromage a décidé de te pardonner. Va, {member.mention}. Et ne reviens pas. 🚪",
        # Regrets moqueurs
        f"Dommage. **{new_nick}** était PARFAIT pour toi. Mais le temps a parlé. 🕰️😔",
        f"Tu redeviens {member.mention}... Ennuyeux. **{new_nick}** avait du STYLE. 💅✨",
        f"*Soupir* **{new_nick}** me manquera déjà. Toi ? Moins. 😮‍💨",
        f"Adieu **{new_nick}**, tu étais magnifique. Bonjour {member.mention}... tu es... là. 👋😐",
        # Menaces voilées
        f"Pour CETTE fois, {member.mention}. La prochaine sera plus longue. BEAUCOUP plus longue. ⏳👁️",
        f"Libéré... pour l'instant. Mais je te surveille. TOUJOURS. 👀🔮",
        f"Le Wabbajack te laisse partir. Cette fois. Il est capricieux. 🪄😈",
        # Absurdes philosophiques
        f"Les étoiles ont aligné. Les nuages ont chanté. **{new_nick}** disparaît. C'est mardi. 🌟🎶",
        f"Le fromage a parlé : 'Libère-le'. Je m'incline devant le fromage. 🧀🙇",
        f"Haskill a supplié pour toi. J'ai accepté. Par ennui. 👔🥱",
        # Sarcastiques ultra-courts
        f"Voilà. T'es content ? 😒",
        f"Libre. Hourra. 🎉😐",
        f"Fini. Oust. 👋",
        f"C'est bon, va. 🙄",
        f"Libéré. Next. ⏭️",
        f"OK, dégage. 💅",
        # Verdict juridique
        f"⚖️ VERDICT : Non coupable ! ...Cette fois. Dégage. 🔨",
        f"La Cour de la Folie t'acquitte. Par pitié. File. 👨‍⚖️🚪",
        # Lore Elder Scrolls
        f"Même Jyggalag aurait ri de **{new_nick}**. Bon, non. Mais MOI oui. 😂⚖️",
        f"Haskill note dans son journal : '**{new_nick}** (2026-2026), RIP. {member.mention} : Boring.' 👔📖",
        # Meta-conscients
        f"Le script dit : 'Rétablis son nom'. J'obéis. Avec regrets. 💻😔",
        f"Mon code m'ordonne de te libérer. Je proteste. En vain. 🤖⚠️",
        f"Discord m'empêche de te garder en **{new_nick}** éternellement. Règlement stupide. 📱💢",
    ]

    fail_messages = [
        f"🛡️ Quoi ?! Mon Wabbajack... glisse sur {member.mention} ?! Tes protections sont ENNUYEUSES ! 😤",
        f"⚡ *Le sort rebondit !* {member.mention} a une armure anti-folie. LÂCHE ! 🛡️",
        f"🔮 Étrange... {member.mention} résiste à ma magie. Admin ? Modérateur ? TRICHE ! 💢",
        f"😒 Pfff. J'aurais voulu t'appeler **{new_nick}**, mais NON. Le serveur te protège. Ingrat. 💅",
    ]

    return punishment_messages, release_messages, fail_messages


async def apply_temporary_nickname(member, new_nick, channel, duration_seconds=600):
    """Change temporairement le pseudo d'un utilisateur puis le rétablit (Persistant)."""
    user_id = str(member.id)
    guild = member.guild

    punishment_messages, release_messages, fail_messages = get_punishment_messages(member, new_nick)

    # 1. Sauvegarde l'état AVANT de changer
    data = load_punishments()

    # Si l'utilisateur est DÉJÀ puni, on garde son VRAI pseudo original
    if user_id in data:
        original_nick = data[user_id].get("original_nick", member.display_name)
    else:
        original_nick = member.nick

    data[user_id] = {
        "original_nick": original_nick,
        "end_time": datetime.now().timestamp() + duration_seconds,
        "guild_id": guild.id
    }
    save_punishments(data)
    logger.info(f"💾 [PUNITION] Sauvegardé: {member.name} -> original_nick={original_nick}")

    try:
        await member.edit(nick=new_nick)
        # Message aléatoire parmi les variantes
        await channel.send(random.choice(punishment_messages))
        # Ajouter une réaction au message original si possible
        try:
            async for msg in channel.history(limit=5):
                if msg.author.id == member.id:
                    await msg.add_reaction("🪄")
                    await msg.add_reaction("💀")
                    break
        except discord.HTTPException as e:
            logger.debug(f"[WABBAJACK] reaction sur le message d'origine impossible : {e}")
        logger.info(f"🪄 [WABBAJACK AUTO] Pseudo de {member.name} changé en {new_nick} pour {duration_seconds}s.")
    except discord.Forbidden:
        await channel.send(random.choice(fail_messages))
        logger.warning(f"[WABBAJACK AUTO] Impossible de changer le pseudo de {member.name} (Permissions).")
        data = load_punishments()
        if user_id in data:
            del data[user_id]
            save_punishments(data)
        return
    except Exception as e:
        logger.error(f"[WABBAJACK AUTO] Erreur: {e}")
        return

    # 2. Attendre la durée
    logger.info(f"⏳ [PUNITION] Attente de {duration_seconds}s pour {member.name}...")
    await asyncio.sleep(duration_seconds)

    # 3. Rétablissement
    logger.info(f"🔄 [PUNITION] Fin de punition pour {member.name}, tentative de restauration...")
    try:
        current_member = await guild.fetch_member(member.id)
        await current_member.edit(nick=original_nick)
        # Message de libération sarcastique
        await channel.send(random.choice(release_messages))
        logger.info(f"✅ [WABBAJACK AUTO] Pseudo de {current_member.name} rétabli : {original_nick or '(nom original)'}")

    except discord.Forbidden:
        logger.warning(f"[WABBAJACK AUTO] Impossible de restaurer le pseudo de {member.name} (Permissions).")
    except discord.NotFound:
        logger.warning(f"[WABBAJACK AUTO] Membre {member.name} non trouvé (a quitté le serveur?).")
    except Exception as e:
        logger.error(f"[WABBAJACK AUTO] Erreur lors du rétablissement : {e}")
    finally:
        # TOUJOURS nettoyer l'entrée JSON, même si la restauration a échoué
        data = load_punishments()
        if user_id in data:
            del data[user_id]
            save_punishments(data)
            logger.info(f"🧹 [PUNITION] Entrée nettoyée pour {member.name}")


async def restore_pending_punishments(bot):
    """
    Restaure les punitions après un redémarrage du bot.
    - Si la punition a expiré → restaure le pseudo original immédiatement.
    - Si la punition est encore active → re-programme la restauration avec le temps restant.
    """
    data = load_punishments()
    if not data:
        logger.info("✅ [PUNITION] Aucune punition en attente à restaurer.")
        return

    now = datetime.now().timestamp()
    to_remove = []
    restored = 0
    rescheduled = 0

    for user_id, info in data.items():
        guild_id = info.get("guild_id")
        original_nick = info.get("original_nick")
        end_time = info.get("end_time", 0)

        guild = bot.get_guild(guild_id)
        if not guild:
            logger.warning(f"⚠️ [RESTORE] Guild {guild_id} non trouvée pour user {user_id}")
            to_remove.append(user_id)
            continue

        try:
            member = await guild.fetch_member(int(user_id))
        except (discord.NotFound, discord.HTTPException):
            logger.warning(f"⚠️ [RESTORE] Membre {user_id} non trouvé dans {guild.name}")
            to_remove.append(user_id)
            continue

        remaining = end_time - now

        if remaining <= 0:
            # Punition expirée → restaurer immédiatement
            try:
                await member.edit(nick=original_nick)
                logger.info(f"✅ [RESTORE] Pseudo restauré pour {member.name} → {original_nick or '(nom original)'}")
                restored += 1
            except discord.Forbidden:
                logger.warning(f"⚠️ [RESTORE] Permissions insuffisantes pour restaurer {member.name}")
            except Exception as e:
                logger.error(f"❌ [RESTORE] Erreur restauration {member.name}: {e}")
            to_remove.append(user_id)
        else:
            # Punition encore active → re-programmer la restauration
            logger.info(f"⏳ [RESTORE] Re-programmation pour {member.name}: {int(remaining)}s restantes")
            rescheduled += 1

            async def delayed_restore(m=member, o_nick=original_nick, uid=user_id, rem=remaining):
                await asyncio.sleep(rem)
                try:
                    current_member = await m.guild.fetch_member(m.id)
                    await current_member.edit(nick=o_nick)
                    logger.info(f"✅ [RESTORE-DELAYED] Pseudo restauré pour {current_member.name}")
                except discord.Forbidden:
                    logger.warning(f"⚠️ [RESTORE-DELAYED] Permissions insuffisantes pour {m.name}")
                except discord.NotFound:
                    logger.warning(f"⚠️ [RESTORE-DELAYED] Membre {m.name} non trouvé")
                except Exception as e:
                    logger.error(f"❌ [RESTORE-DELAYED] Erreur: {e}")
                finally:
                    d = load_punishments()
                    if uid in d:
                        del d[uid]
                        save_punishments(d)

            asyncio.create_task(delayed_restore())

    # Nettoyer les punitions expirées
    if to_remove:
        data = load_punishments()
        for uid in to_remove:
            if uid in data:
                del data[uid]
        save_punishments(data)

    logger.info(f"🔄 [RESTORE] Bilan: {restored} restaurés, {rescheduled} reprogrammés, {len(to_remove)} nettoyés")
