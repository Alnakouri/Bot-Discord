# -*- coding: utf-8 -*-
"""
Commandes slash centralisées pour l'écosystème des bots Discord.
Fournit : /reputation, /leaderboard, /birthday, /quests, /stats, /ping, /help
"""
import discord
from discord import app_commands
from shared.shared_database import (
    get_reputation, get_reputation_level, get_next_rank_info,
    get_reputation_leaderboard,
    set_birthday, get_todays_birthdays,
    get_daily_quests, create_daily_quests, complete_quest,
    get_bot_interaction_stats,
    is_maintenance_mode
)


# Ce que /help affiche, dans l'ordre. Une seule liste : une commande retiree par `sans`
# disparait des DEUX endroits, et /help ne promet jamais une commande absente.
_AIDE = [
    ("reputation", "/reputation [user]", "Affiche vos points et votre rang."),
    ("leaderboard", "/leaderboard [top]", "Classement de réputation du serveur."),
    ("birthday", "/birthday <jour> <mois>", "Enregistre votre date d'anniversaire."),
    ("quests", "/quests", "Affiche vos quêtes quotidiennes."),
    ("stats", "/stats", "Statistiques des duels inter-bots."),
    ("ping", "/ping", "Vérifie la latence du bot."),
]
_RETIRABLES = frozenset(nom for nom, _, _ in _AIDE)


def setup_slash_commands(bot, bot_name, sans=frozenset()):
    """Initialise les commandes slash pour un bot spécifique.

    `sans` : les commandes a NE PAS poser pour ce bot (ni afficher dans /help). Vide par
    defaut : les bots qui ne le passent pas gardent les sept. /help est toujours posee.
    Alfred ne garde que /ping, /stats et /help (SUITE 16, decision d'Ahmed du 28/09).
    """
    sans = frozenset(sans)
    inconnues = sans - _RETIRABLES
    if inconnues:
        # Une faute de frappe laisserait la commande en place sans rien dire.
        raise ValueError(f"commandes slash inconnues dans `sans` : {sorted(inconnues)}")

    def _poser(nom, **kw):
        """`bot.tree.command`, ou un decorateur qui ne pose rien si `nom` est retiree."""
        if nom in sans:
            return lambda f: f
        return bot.tree.command(name=nom, **kw)

    # ──────────────── /reputation ────────────────
    @_poser("reputation", description="Affiche votre réputation et votre rang.")
    @app_commands.describe(user="L'utilisateur dont vous voulez voir la réputation (optionnel)")
    async def reputation(interaction: discord.Interaction, user: discord.Member = None):
        target = user or interaction.user
        rep_data = get_reputation(target.id)
        points = rep_data.get("points", 0)
        level = get_reputation_level(points)
        next_pts, next_rank = get_next_rank_info(points)

        embed = discord.Embed(
            title=f"✨ Réputation de {target.display_name}",
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Points", value=str(points), inline=True)
        embed.add_field(name="Rang", value=level, inline=True)

        if next_pts < 999999:
            progress = points / next_pts if next_pts > 0 else 0
            bar = "▰" * int(progress * 10) + "▱" * (10 - int(progress * 10))
            embed.add_field(name=f"Prochain Rang : {next_rank}", value=f"{bar} ({points}/{next_pts})", inline=False)

        embed.set_footer(text=f"Bot : {bot_name}")
        await interaction.response.send_message(embed=embed)

    # ──────────────── /leaderboard ────────────────
    @_poser("leaderboard", description="Affiche le classement de réputation du serveur.")
    @app_commands.describe(top="Nombre de joueurs à afficher (défaut : 10)")
    async def leaderboard(interaction: discord.Interaction, top: int = 10):
        top = min(max(top, 1), 25)  # Limiter entre 1 et 25
        leaders = get_reputation_leaderboard(limit=top)

        if not leaders:
            await interaction.response.send_message("📭 Aucune donnée de réputation pour l'instant.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🏆 Classement de Réputation",
            color=discord.Color.dark_gold()
        )

        medals = ["🥇", "🥈", "🥉"]
        description_lines = []
        for i, entry in enumerate(leaders):
            medal = medals[i] if i < 3 else f"**{i+1}.**"
            name = entry.get("display_name") or entry.get("username", "Inconnu")
            pts = entry.get("points", 0)
            level = get_reputation_level(pts)
            description_lines.append(f"{medal} **{name}** — {pts} pts ({level})")

        embed.description = "\n".join(description_lines)
        embed.set_footer(text=f"Top {len(leaders)} • Bot : {bot_name}")
        await interaction.response.send_message(embed=embed)

    # ──────────────── /birthday ────────────────
    @_poser("birthday", description="Enregistre votre date d'anniversaire.")
    @app_commands.describe(jour="Jour de naissance (1-31)", mois="Mois de naissance (1-12)")
    async def birthday(interaction: discord.Interaction, jour: int, mois: int):
        # Validation
        if not (1 <= jour <= 31) or not (1 <= mois <= 12):
            await interaction.response.send_message("❌ Date invalide. Jour : 1-31, Mois : 1-12.", ephemeral=True)
            return

        mois_noms = [
            "", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
            "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"
        ]

        success = set_birthday(interaction.user.id, jour, mois)
        if success:
            embed = discord.Embed(
                title="🎂 Anniversaire enregistré !",
                description=f"**{interaction.user.display_name}** — {jour} {mois_noms[mois]}",
                color=discord.Color.magenta()
            )
            embed.set_footer(text=f"Les bots vous souhaiteront un joyeux anniversaire ! • {bot_name}")
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("❌ Erreur lors de l'enregistrement.", ephemeral=True)

    # ──────────────── /quests ────────────────
    @_poser("quests", description="Affiche vos quêtes quotidiennes.")
    async def quests(interaction: discord.Interaction):
        user_quests = get_daily_quests(interaction.user.id)
        if not user_quests:
            user_quests = create_daily_quests(interaction.user.id)

        quest_labels = {
            "chat_sheogorath": "💬 Discuter avec Sheogorath",
            "chat_maiq": "🐱 Écouter une rumeur de M'aiq",
            "chat_alfred": "🎩 Demander un service à Alfred",
            "participate_game": "🎮 Participer à un mini-jeu",
            "make_bot_laugh": "😂 Faire rire un bot",
            "help_someone": "🤝 Aider un autre membre",
        }

        embed = discord.Embed(
            title="📋 Quêtes Quotidiennes",
            color=discord.Color.teal()
        )

        for q in user_quests:
            label = quest_labels.get(q["quest_type"], q["quest_type"])
            status = "✅" if q["completed"] else "⬜"
            reward = q.get("reward", 0)
            embed.add_field(
                name=f"{status} {label}",
                value=f"Récompense : **{reward}** pts",
                inline=False
            )

        embed.set_footer(text=f"Les quêtes se réinitialisent chaque jour • {bot_name}")
        await interaction.response.send_message(embed=embed)

    # ──────────────── /stats ────────────────
    @_poser("stats", description="Affiche les statistiques des duels inter-bots.")
    async def stats(interaction: discord.Interaction):
        global_stats = get_bot_interaction_stats(days=30)

        embed = discord.Embed(
            title="📊 Statistiques des Duels Inter-Bots",
            description="Derniers 30 jours",
            color=discord.Color.dark_purple()
        )

        # Stats par bot
        by_bot = global_stats.get("by_bot", [])
        if by_bot:
            bot_lines = []
            for entry in by_bot[:6]:
                bot_lines.append(f"⚔️ **{entry['bot1']}** — {entry['count']} duels")
            embed.add_field(name="Activité par Bot", value="\n".join(bot_lines) or "Aucun", inline=False)

        # Top paires
        top_pairs = global_stats.get("top_pairs", [])
        if top_pairs:
            pair_lines = []
            for entry in top_pairs[:5]:
                pair_lines.append(f"🤝 {entry['bot1']} vs {entry['bot2']} — {entry['count']}x")
            embed.add_field(name="Top Rivalités", value="\n".join(pair_lines) or "Aucune", inline=False)

        if not by_bot and not top_pairs:
            embed.description = "Aucun duel enregistré sur les 30 derniers jours."

        embed.set_footer(text=f"Bot : {bot_name}")
        await interaction.response.send_message(embed=embed)

    # ──────────────── /ping ────────────────
    @_poser("ping", description="Vérifie la latence du bot.")
    async def ping(interaction: discord.Interaction):
        latency_ms = round(bot.latency * 1000)
        # Indicateur visuel de la qualité de la connexion
        if latency_ms < 100:
            indicator = "🟢"
        elif latency_ms < 250:
            indicator = "🟡"
        else:
            indicator = "🔴"
        await interaction.response.send_message(f"{indicator} **Pong !** Latence : `{latency_ms}ms`")

    # ──────────────── /help ────────────────
    @bot.tree.command(name="help", description="Affiche l'aide des commandes disponibles.")
    async def help_cmd(interaction: discord.Interaction):
        embed = discord.Embed(
            title="📚 Aide — Commandes Slash",
            description="Voici les commandes disponibles sur tous les bots :",
            color=discord.Color.blue()
        )
        for nom, usage, description in _AIDE:
            if nom not in sans:
                embed.add_field(name=usage, value=description, inline=False)
        embed.set_footer(text=f"Écosystème Discord Bots v2.5 • {bot_name}")
        await interaction.response.send_message(embed=embed)


async def sync_slash_commands(bot):
    """Synchronise les commandes slash avec Discord."""
    try:
        synced = await bot.tree.sync()
        print(f"[SLASH] {len(synced)} commandes synchronisees")
        return synced
    except Exception as e:
        print(f"[SLASH] Erreur de synchronisation : {e}")
        return []
