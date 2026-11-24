# -*- coding: utf-8 -*-
"""Verrou : la sonde de sante crie pour une vraie panne, et seulement pour elle.

Mesure du 2026-11-24 : quatre bots en boucle de redemarrage pendant deux jours, la
sauvegarde arretee depuis le 22/11, un lien `!discord` expire — et personne ne l'a vu.
Ces tests rejouent ces trois pannes sur la logique de decision de `tools/sonde_sante.py`,
sans Docker ni reseau, et verifient l'inverse : Docker arrete (AutoStart coupe expres)
et un service qui vient de demarrer ne sont PAS des pannes.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

import tools.sonde_sante as sonde

MAINTENANT = datetime(2026, 11, 24, 22, 0, tzinfo=timezone.utc)


def _etat(statut="running", demarre_il_y_a=timedelta(hours=2), redemarrages=0, sante=None):
    st = {"Status": statut, "Restarting": statut == "restarting", "ExitCode": 1 if statut == "exited" else 0,
          "StartedAt": (MAINTENANT - demarre_il_y_a).strftime("%Y-%m-%dT%H:%M:%S.123456789Z")}
    if sante:
        st["Health"] = {"Status": sante}
    return {"State": st, "RestartCount": redemarrages}


# ─── Conteneurs ──────────────────────────────────────────────────────────────

def test_un_conteneur_sain_ne_dit_rien():
    assert sonde.problemes_conteneur("alfred", "bot-alfred", _etat(), MAINTENANT) == []


def test_la_boucle_de_redemarrage_du_24_11_est_vue():
    # Statut « restarting » : ce que montrait `docker ps` pour Alfred, M'aiq, Johnny, Malena.
    p = sonde.problemes_conteneur("alfred", "bot-alfred", _etat("restarting", redemarrages=14), MAINTENANT)
    assert len(p) == 1 and "boucle" in p[0]["message"]


def test_la_boucle_est_vue_meme_entre_deux_plantages():
    # Le conteneur « tourne » quelques secondes avant de retomber.
    etat = _etat("running", demarre_il_y_a=timedelta(seconds=5), redemarrages=14)
    assert "boucle" in sonde.problemes_conteneur("maiq", "bot-maiq", etat, MAINTENANT)[0]["message"]


def test_des_redemarrages_ANCIENS_ne_sont_pas_une_boucle():
    etat = _etat("running", demarre_il_y_a=timedelta(days=3), redemarrages=14)
    assert sonde.problemes_conteneur("maiq", "bot-maiq", etat, MAINTENANT) == []


def test_un_conteneur_absent_ou_arrete_ou_malade_est_signale():
    assert sonde.problemes_conteneur("laya", "bots-laya", None, MAINTENANT)
    assert sonde.problemes_conteneur("sugar", "bot-sugar", _etat("exited"), MAINTENANT)
    assert sonde.problemes_conteneur("laya", "bots-laya", _etat(sante="unhealthy"), MAINTENANT)


def test_la_cle_d_un_probleme_ne_depend_pas_du_message():
    # La deduplication des notifications compare les CLES : un compteur de redemarrages
    # qui monte ne doit pas faire re-sonner la meme panne toutes les heures.
    a = sonde.problemes_conteneur("alfred", "bot-alfred", _etat("restarting", redemarrages=3), MAINTENANT)
    b = sonde.problemes_conteneur("alfred", "bot-alfred", _etat("restarting", redemarrages=40), MAINTENANT)
    assert a[0]["cle"] == b[0]["cle"] and a[0]["message"] != b[0]["message"]


def test_docker_arrete_n_est_PAS_une_panne(monkeypatch):
    # AutoStart coupe expres : la sonde ne doit rien dire des conteneurs.
    monkeypatch.setattr(sonde, "services_attendus", lambda: None)
    monkeypatch.setattr(sonde, "liens_configures", lambda: [])
    b = sonde.bilan(MAINTENANT)
    assert b["docker"] is False and b["problemes"] == []


# ─── Sauvegarde ──────────────────────────────────────────────────────────────

def test_la_sauvegarde_arretee_depuis_le_22_11_est_vue():
    derniere = datetime(2026, 11, 22, 18, 36, tzinfo=timezone.utc)
    p = sonde.problemes_sauvegarde(derniere, MAINTENANT - timedelta(days=5), MAINTENANT)
    assert len(p) == 1 and "il y a 51 h" in p[0]["message"]


def test_une_sauvegarde_du_jour_ne_dit_rien():
    assert sonde.problemes_sauvegarde(MAINTENANT - timedelta(hours=20), None, MAINTENANT) == []


def test_un_service_qui_vient_de_demarrer_a_le_temps_de_sauvegarder():
    # Docker relance apres trois jours d'arret : la derniere copie est vieille, mais le
    # service en fait une tout de suite. Ce n'est pas une panne.
    vieille = MAINTENANT - timedelta(days=3)
    assert sonde.problemes_sauvegarde(vieille, MAINTENANT - timedelta(minutes=5), MAINTENANT) == []


def test_la_derniere_sauvegarde_est_lue_dans_le_NOM_du_dossier(tmp_path):
    for nom in ("2026-11-20_1858", "2026-11-24_2202", "2026-11-22_1836", "pas-une-sauvegarde"):
        (tmp_path / nom).mkdir()
    (tmp_path / "2026-11-25_0000.partiel").mkdir()   # copie en cours : ne compte pas
    assert sonde.derniere_sauvegarde(tmp_path) == datetime(2026, 11, 24, 22, 2, tzinfo=timezone.utc)


def test_le_montage_docker_desktop_est_ramene_au_chemin_windows(monkeypatch):
    etat = {"Mounts": [{"Destination": "/app/sauvegardes", "Source": "/run/desktop/mnt/host/d/Sauvegardes/bases"}]}
    # Jamais `os.name` : patcher le module os global fait planter pathlib (CI rouge du 24/11).
    monkeypatch.setattr(sonde, "_WINDOWS", True)
    assert sonde.dossier_sauvegardes(etat) == Path("D:/Sauvegardes/bases")


# ─── Liens d'invitation ──────────────────────────────────────────────────────

def test_le_lien_mort_de_johnny_est_vu():
    p = sonde.problemes_lien("johnny", "discord", "exemple", "morte", None, MAINTENANT)
    assert len(p) == 1 and "expire ou supprime" in p[0]["message"]


def test_un_lien_qui_expire_bientot_est_signale_avant_de_mourir():
    p = sonde.problemes_lien("sugar", "discord", "exemple", "vivante", MAINTENANT + timedelta(days=3), MAINTENANT)
    assert len(p) == 1 and "invitation permanente" in p[0]["message"]


def test_un_lien_permanent_ou_lointain_ne_dit_rien():
    assert sonde.problemes_lien("sugar", "discord", "exemple", "vivante", None, MAINTENANT) == []
    assert sonde.problemes_lien("sugar", "discord", "exemple", "vivante", MAINTENANT + timedelta(days=20), MAINTENANT) == []


def test_discord_injoignable_n_est_pas_un_lien_mort():
    # Une coupure reseau ne doit pas faire croire que tous les liens sont morts.
    assert sonde.problemes_lien("sugar", "discord", "exemple", "inconnu", None, MAINTENANT) == []


def test_les_liens_sont_lus_dans_la_config_du_dashboard(tmp_path, monkeypatch):
    (tmp_path / "twitch_config.json").write_text(json.dumps({
        "sugar": {"link_commands": [{"cmd": "discord", "url": "https://discord.gg/AbC-12"},
                                    {"cmd": "site", "url": "https://exemple.org"}]},
        "johnny": {"link_commands": [{"cmd": "!serveur", "url": "https://discord.com/invite/XyZ"}]},
        "alfred": {},
    }), encoding="utf-8")
    monkeypatch.setattr(sonde, "DATA_DIR", tmp_path)
    assert sorted(sonde.liens_configures()) == [("johnny", "serveur", "XyZ"), ("sugar", "discord", "AbC-12")]


# ─── Notifications et fichier de bilan ───────────────────────────────────────

def test_seul_un_probleme_NOUVEAU_notifie():
    avant = {"problemes": [{"cle": "lien:johnny:discord", "message": "ancien"}]}
    apres = {"problemes": [{"cle": "lien:johnny:discord", "message": "ancien"},
                           {"cle": "conteneur:alfred", "message": "nouveau"}]}
    assert [p["cle"] for p in sonde.nouveaux(avant, apres)] == ["conteneur:alfred"]
    assert len(sonde.nouveaux(None, apres)) == 2


def test_le_bilan_est_ecrit_hors_du_depot_en_test(tmp_path, monkeypatch):
    monkeypatch.setattr(sonde, "FICHIER_SANTE", tmp_path / "sante.json")
    sonde.ecrire_bilan({"verifie_le": "x", "docker": True, "problemes": []})
    assert json.loads((tmp_path / "sante.json").read_text(encoding="utf-8"))["docker"] is True
    assert not (tmp_path / "sante.json.tmp").exists()


def test_le_bandeau_du_dashboard_affiche_le_bilan():
    # Un bilan que personne n'affiche ne previent personne : la route lit le fichier
    # de la sonde, et le bandeau d'alerte de l'accueil appelle la route.
    app_py = (RACINE / "dashboard" / "backend" / "app.py").read_text(encoding="utf-8")
    app_js = (RACINE / "dashboard" / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
    assert '@app.get("/api/sante")' in app_py and '"sante.json"' in app_py
    assert "fetch('/api/sante')" in app_js
    bandeau = app_js[app_js.index("function updateOverviewAlertBanner"):]
    assert "globalSante" in bandeau and "perime" in bandeau


def test_la_sonde_n_importe_que_la_bibliotheque_standard():
    # Elle tourne avec le Python de l'hote, sans le venv des bots (tache planifiee).
    import ast
    arbre = ast.parse((RACINE / "tools" / "sonde_sante.py").read_text(encoding="utf-8"))
    modules = {a.name.split(".")[0] for n in ast.walk(arbre) if isinstance(n, ast.Import) for a in n.names}
    modules |= {n.module.split(".")[0] for n in ast.walk(arbre) if isinstance(n, ast.ImportFrom) and n.module}
    assert modules <= set(sys.stdlib_module_names), modules - set(sys.stdlib_module_names)
