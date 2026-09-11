# -*- coding: utf-8 -*-
"""Tests pour le LOT 2 — Profil Discord structurel (sans intent supplémentaire)."""

from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock
import discord

from shared.profil_interlocuteur import construire_profil_discord, _duree_lisible


def test_1_bloc_absent_quand_user_message_prive():
    """Verrou : le bloc de profil est ABSENT quand author est un User (message privé).
    
    En MP, roles et joined_at n'existent pas.
    """
    mock_user = MagicMock(spec=discord.User)
    mock_user.name = "Voyageur"
    mock_user.created_at = datetime(2022, 1, 1, tzinfo=timezone.utc)
    
    # Un discord.User n'est pas un discord.Member
    bloc = construire_profil_discord(mock_user)
    assert bloc == "", f"Le bloc doit être vide pour un User en MP, obtenu : {bloc!r}"


def test_2_bloc_present_et_complet_pour_member():
    """Un discord.Member en salon serveur génère le profil complet sans balise XML."""
    now = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)
    
    mock_member = MagicMock(spec=discord.Member)
    mock_member.name = "Bruce"
    mock_member.nick = "Batman"
    mock_member.created_at = now - timedelta(days=365 * 3)  # 3 ans
    mock_member.joined_at = now - timedelta(days=200)       # ~6 mois
    mock_member.premium_since = now - timedelta(days=60)    # 2 mois

    role_everyone = MagicMock()
    role_everyone.name = "@everyone"
    role_vip = MagicMock()
    role_vip.name = "VIP"
    role_ancien = MagicMock()
    role_ancien.name = "Ancien"
    mock_member.roles = [role_everyone, role_vip, role_ancien]

    bloc = construire_profil_discord(mock_member, now=now)

    assert "[PROFIL DISCORD DE L'INTERLOCUTEUR]:" in bloc
    assert "Sur ce serveur depuis : 6 mois" in bloc
    assert "Rôles sur le serveur : VIP, Ancien" in bloc
    assert "@everyone" not in bloc
    assert "Surnom sur le serveur : Batman (nom de compte : Bruce)" in bloc
    assert "Booster du serveur : oui (depuis 2 mois)" in bloc
    assert "Ancienneté du compte Discord : 3 ans" in bloc


def test_3_verrou_aucun_fait_dans_balise_fact():
    """Verrou : le profil structurel ne doit JAMAIS contenir de balise <fact> ni </fact>.
    
    Les faits structurels sont calculés, jamais extraits par un LLM.
    """
    now = datetime(2026, 9, 11, tzinfo=timezone.utc)
    mock_member = MagicMock(spec=discord.Member)
    mock_member.name = "Test"
    mock_member.nick = None
    mock_member.created_at = now - timedelta(days=100)
    mock_member.joined_at = now - timedelta(days=50)
    mock_member.premium_since = None
    mock_member.roles = []

    bloc = construire_profil_discord(mock_member, now=now)
    assert "<fact>" not in bloc
    assert "</fact>" not in bloc


def test_3bis_verrou_le_profil_ne_transite_pas_par_le_canal_fact():
    """Verrou de CABLAGE : dans les 6 bots, aucun litteral ne melange le bloc de profil
    structurel et la balise <fact>.

    test_3 ne regarde que la sortie de la fonction — elle ne peut pas contenir <fact>
    par construction, donc il ne prouve rien. Le vrai risque est au cablage : injecter
    le profil DANS la consigne <fact> rendrait les faits structurels reinjectables par
    le LLM, et rouvrirait la boucle d'auto-attribution fermee en c3887a9.
    """
    import ast
    racine = Path(__file__).resolve().parent.parent
    bots = ["Alfred/bot_alfred.py", "JohnnyBot/bot_johnny.py", "MaiqBot/bot_maiq.py",
            "MalenaBot/bot_malena.py", "Sheogorath/bot_sheogorath.py",
            "SugarBot/bot_sugar.py"]
    for rel in bots:
        chemin = racine / rel
        arbre = ast.parse(chemin.read_text(encoding="utf-8"), filename=str(chemin))
        for n in ast.walk(arbre):
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                txt = n.value
                assert not ("<fact>" in txt and "PROFIL DISCORD" in txt), (
                    f"{rel} ligne {n.lineno} : le bloc de profil structurel est melange "
                    "a la consigne <fact>."
                )
            if isinstance(n, ast.JoinedStr):
                brut = "".join(v.value for v in n.values
                               if isinstance(v, ast.Constant) and isinstance(v.value, str))
                assert not ("<fact>" in brut and "PROFIL DISCORD" in brut), (
                    f"{rel} ligne {n.lineno} : f-string melangeant profil et <fact>."
                )


def test_4_surnom_omet_si_identique_au_nom():
    """Si nick == name ou nick is None, aucune ligne de surnom n'est générée."""
    now = datetime(2026, 9, 11, tzinfo=timezone.utc)
    mock_member = MagicMock(spec=discord.Member)
    mock_member.name = "Arthur"
    mock_member.nick = "Arthur"
    mock_member.created_at = now - timedelta(days=100)
    mock_member.joined_at = now - timedelta(days=50)
    mock_member.premium_since = None
    mock_member.roles = []

    bloc = construire_profil_discord(mock_member, now=now)
    assert "Surnom sur le serveur" not in bloc


def test_5_booster_omet_si_non_booster():
    """Si premium_since est None, aucune mention de booster n'apparaît."""
    now = datetime(2026, 9, 11, tzinfo=timezone.utc)
    mock_member = MagicMock(spec=discord.Member)
    mock_member.name = "Arthur"
    mock_member.nick = None
    mock_member.created_at = now - timedelta(days=100)
    mock_member.joined_at = now - timedelta(days=50)
    mock_member.premium_since = None
    mock_member.roles = []

    bloc = construire_profil_discord(mock_member, now=now)
    assert "Booster du serveur" not in bloc


def test_6_duree_lisible_calculs():
    """Vérification des paliers de durée lisible."""
    now = datetime(2026, 9, 11, tzinfo=timezone.utc)
    assert _duree_lisible(now, now) == "aujourd'hui"
    assert _duree_lisible(now - timedelta(days=5), now) == "5 jours"
    assert _duree_lisible(now - timedelta(days=45), now) == "1 mois"
    assert _duree_lisible(now - timedelta(days=365), now) == "1 an"
    assert _duree_lisible(now - timedelta(days=550), now) == "1 an et demi"
    assert _duree_lisible(now - timedelta(days=730), now) == "2 ans"


def test_7_les_bots_utilisent_construire_profil_discord():
    """Verrou : les SIX bots importent ET APPELLENT construire_profil_discord.

    La version precedente listait 5 bots (Malena manquait) et se contentait de
    `"construire_profil_discord" in texte` — vert sur un simple import non cable,
    ou sur une ligne commentee.
    """
    import ast
    racine = Path(__file__).resolve().parent.parent
    bots = {
        "Alfred": "Alfred/bot_alfred.py",
        "JohnnyBot": "JohnnyBot/bot_johnny.py",
        "MaiqBot": "MaiqBot/bot_maiq.py",
        "MalenaBot": "MalenaBot/bot_malena.py",
        "Sheogorath": "Sheogorath/bot_sheogorath.py",
        "SugarBot": "SugarBot/bot_sugar.py",
    }
    for nom, rel in bots.items():
        chemin = racine / rel
        arbre = ast.parse(chemin.read_text(encoding="utf-8"), filename=str(chemin))
        noeuds = list(ast.walk(arbre))

        importe = any(
            isinstance(n, ast.ImportFrom)
            and n.module == "core.profil_interlocuteur"
            and any(a.name == "construire_profil_discord" for a in n.names)
            for n in noeuds
        )
        assert importe, f"{nom} n'importe pas construire_profil_discord depuis core.profil_interlocuteur"

        appels = [
            n for n in noeuds
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == "construire_profil_discord"
        ]
        assert appels, f"{nom} importe construire_profil_discord mais ne l'appelle jamais"

        # Lot 3 : la reputation et les quetes doivent reellement etre passees
        for appel in appels:
            donnes = {kw.arg for kw in appel.keywords}
            assert {"reputation_data", "quests_data"} <= donnes, (
                f"{nom} appelle construire_profil_discord sans "
                f"{sorted({'reputation_data', 'quests_data'} - donnes)} — le lot 3 "
                "n'est pas cable."
            )


def test_8_reputation_et_enigmes_dans_le_bloc():
    """Lot 3 : La réputation et la série d'énigmes sont injectées dans le même bloc."""
    now = datetime(2026, 9, 11, tzinfo=timezone.utc)
    mock_member = MagicMock(spec=discord.Member)
    mock_member.id = 12345
    mock_member.name = "Joueur"
    mock_member.nick = None
    mock_member.created_at = now - timedelta(days=100)
    mock_member.joined_at = now - timedelta(days=50)
    mock_member.premium_since = None
    mock_member.roles = []

    rep_data = {"points": 250, "level": "Initié 📜", "riddle_streak": 4}
    bloc = construire_profil_discord(mock_member, now=now, reputation_data=rep_data)

    assert "Réputation sur le serveur : Initié 📜 (250 points)" in bloc
    assert "série d'énigmes : 4 victoires d'affilée" in bloc


def test_9_quetes_du_jour_dans_le_bloc():
    """Lot 3 : Le ratio de quêtes du jour accomplies est affiché."""
    now = datetime(2026, 9, 11, tzinfo=timezone.utc)
    mock_member = MagicMock(spec=discord.Member)
    mock_member.id = 12345
    mock_member.name = "Joueur"
    mock_member.nick = None
    mock_member.created_at = now - timedelta(days=100)
    mock_member.joined_at = now - timedelta(days=50)
    mock_member.premium_since = None
    mock_member.roles = []

    quetes = [
        {"completed": 1},
        {"completed": 0},
        {"completed": 1},
    ]
    bloc = construire_profil_discord(mock_member, now=now, quests_data=quetes)
    assert "Quêtes du jour : 2/3 accomplies" in bloc


def test_10_lecture_depuis_base_reelle(tmp_path, monkeypatch):
    """Lot 3 : Test de bout en bout avec shared_database réelle."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from shared import shared_database
    shared_database.init_database()

    user_id = 999888777
    shared_database.get_or_create_user(user_id, "Gamer", "GamerTag")
    shared_database.add_reputation(user_id, 120)
    shared_database.add_riddle_streak(user_id)
    shared_database.add_riddle_streak(user_id)

    now = datetime(2026, 9, 11, tzinfo=timezone.utc)
    mock_member = MagicMock(spec=discord.Member)
    mock_member.id = user_id
    mock_member.name = "Gamer"
    mock_member.nick = None
    mock_member.created_at = now - timedelta(days=200)
    mock_member.joined_at = now - timedelta(days=100)
    mock_member.premium_since = None
    mock_member.roles = []

    rep = shared_database.get_reputation(user_id)
    quests = shared_database.get_daily_quests(user_id)
    bloc = construire_profil_discord(mock_member, now=now, reputation_data=rep, quests_data=quests)
    assert "Réputation sur le serveur : Apprenti 🕯️ (120 points)" in bloc
    assert "série d'énigmes : 2 victoires d'affilée" in bloc


def test_11_tous_les_6_bots_ont_intents_members():
    """Lot 4 : les 6 bots posent `intents.members = True` — verrou AST, jamais textuel.

    `"intents.members = True" in src` etait vert sur une ligne COMMENTEE : le motif
    textuel survit au `#`. Or `members` est un intent privilegie — sans lui,
    on_member_join est du code mort (c'etait le cas de M'aiq et Sheogorath).
    """
    import ast
    racine = Path(__file__).resolve().parent.parent
    bots = {
        "Alfred": "Alfred/bot_alfred.py",
        "JohnnyBot": "JohnnyBot/bot_johnny.py",
        "MaiqBot": "MaiqBot/bot_maiq.py",
        "MalenaBot": "MalenaBot/bot_malena.py",
        "Sheogorath": "Sheogorath/bot_sheogorath.py",
        "SugarBot": "SugarBot/bot_sugar.py",
    }
    for nom, rel in bots.items():
        chemin = racine / rel
        arbre = ast.parse(chemin.read_text(encoding="utf-8"), filename=str(chemin))
        trouve = any(
            isinstance(n, ast.Assign)
            and isinstance(n.value, ast.Constant) and n.value.value is True
            and any(
                isinstance(c, ast.Attribute) and c.attr == "members"
                and isinstance(c.value, ast.Name) and c.value.id == "intents"
                for c in n.targets
            )
            for n in ast.walk(arbre)
        )
        assert trouve, (
            f"{nom} ({rel}) ne pose pas `intents.members = True` : on_member_join y est "
            "du code mort."
        )
