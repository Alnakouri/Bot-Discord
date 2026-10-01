# -*- coding: utf-8 -*-
"""
Commandes slash centralisées pour l'écosystème des bots Discord.
Fournit : /reputation, /leaderboard, /birthday, /ping, /help

⚠️ /quests et /stats RETIRES le 2026-10-01 (decision d'Ahmed) : creux depuis l'origine.
/stats lisait `bot_interactions`, que rien n'a jamais rempli (`log_bot_interaction` n'a
jamais eu d'appelant depuis l'Initial commit) ; /quests montrait des quetes que rien ne
pouvait valider (`complete_quest` sans appelant) et qui citaient des features retirees.
"""
import discord
from discord import app_commands
from shared.shared_database import (
    get_reputation, get_reputation_level, get_next_rank_info,
    get_reputation_leaderboard,
    set_birthday, get_todays_birthdays,
    is_maintenance_mode
)


# Ce que /help affiche, dans l'ordre. Une seule liste : une commande retiree par `sans`
# disparait des DEUX endroits, et /help ne promet jamais une commande absente.
_AIDE = [
    ("reputation", "/reputation [user]", "Affiche vos points et votre rang."),
    ("leaderboard", "/leaderboard [top]", "Classement de réputation du serveur."),
    ("birthday", "/birthday <jour> <mois>", "Enregistre votre date d'anniversaire."),
    ("ping", "/ping", "Vérifie la latence du bot."),
]
_RETIRABLES = frozenset(nom for nom, _, _ in _AIDE)


def setup_slash_commands(bot, bot_name, sans=frozenset()):
    """Initialise les commandes slash pour un bot spécifique.

    `sans` : les commandes a NE PAS poser pour ce bot (ni afficher dans /help). Vide par
    defaut : les bots qui ne le passent pas gardent les cinq. /help est toujours posee.
    Alfred ne garde que /ping et /help (SUITE 16, decision d'Ahmed du 28/09).
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
