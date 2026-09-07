# -*- coding: utf-8 -*-
"""Redémarrage du dashboard par lui-même.

Un processus ne peut pas se relancer seul : tant qu'il vit, il tient le port ; s'il
meurt d'abord, plus personne ne peut le rallumer. D'où `relauncher.py`, détaché.

Ce qu'il faut vraiment vérifier, c'est **l'ordre** : le relanceur ne doit surtout pas
redémarrer le dashboard tant que l'ancien tient encore le port, sinon on obtient un
« address already in use » et l'utilisateur se retrouve sans dashboard du tout.
Ces tests exercent le vrai programme, sur un vrai port, avec de vrais processus.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

_racine = Path(__file__).resolve().parent.parent
_backend = _racine / "dashboard" / "backend"
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from relauncher import port_libre, processus_vivant  # noqa: E402

RELANCEUR = _backend / "relauncher.py"
PORT_TEST = 8599        # pas 8501 : on ne touche jamais au dashboard réel


# ---------------------------------------------------------------------------
# Briques
# ---------------------------------------------------------------------------

def test_processus_vivant_dit_vrai_sur_soi_meme():
    assert processus_vivant(os.getpid()) is True


def test_processus_vivant_dit_faux_sur_un_pid_inexistant():
    assert processus_vivant(999999) is False


def test_port_libre_detecte_un_port_occupe():
    occupant = subprocess.Popen([
        sys.executable, "-c",
        f"import socket,time;s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);"
        f"s.bind(('127.0.0.1',{PORT_TEST}));s.listen(50);time.sleep(30)"
    ], stderr=subprocess.PIPE, text=True)
    try:
        limite = time.time() + 10
        while time.time() < limite and port_libre(PORT_TEST):
            time.sleep(0.1)
        if port_libre(PORT_TEST):
            code = occupant.poll()
            erreur = occupant.stderr.read()[:500] if code is not None else "(processus toujours vivant)"
            pytest.fail(f"port jamais occupé — code retour={code}, stderr={erreur!r}")
    finally:
        occupant.kill()
        occupant.wait(timeout=10)

    limite = time.time() + 10
    while time.time() < limite and not port_libre(PORT_TEST):
        time.sleep(0.1)
    assert port_libre(PORT_TEST) is True, "le port devait être vu libéré"


# ---------------------------------------------------------------------------
# Le relanceur, de bout en bout
# ---------------------------------------------------------------------------

SERVEUR_FACTICE = (
    "import socket,time,sys;"
    "s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);"
    "s.bind(('127.0.0.1',int(sys.argv[1])));s.listen(50);time.sleep(int(sys.argv[2]))"
)


def _lancer_serveur(port, duree=60):
    return subprocess.Popen([sys.executable, "-c", SERVEUR_FACTICE, str(port), str(duree)])


def test_le_relanceur_attend_la_mort_du_parent_avant_de_relancer(tmp_path):
    """Le coeur du mecanisme : ne PAS relancer tant que l'ancien tient le port.

    La cible de relance est un vrai serveur qui reprend le port — c'est le seul
    critere de reussite qui veuille dire quelque chose pour un dashboard.
    """
    env = dict(os.environ, DASHBOARD_RELANCE_SANS_CONSOLE="1")

    ancien = _lancer_serveur(PORT_TEST)
    relanceur = None
    try:
        limite = time.time() + 10
        while time.time() < limite and port_libre(PORT_TEST):
            time.sleep(0.1)
        assert not port_libre(PORT_TEST), "le faux dashboard n'a pas pris le port"

        relanceur = subprocess.Popen([
            sys.executable, str(RELANCEUR),
            str(ancien.pid), str(PORT_TEST), str(tmp_path),
            sys.executable, "-c", SERVEUR_FACTICE, str(PORT_TEST), "20",
        ], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # Tant que l'ancien vit, le relanceur doit patienter, pas tenter un bind.
        time.sleep(3.0)
        assert relanceur.poll() is None, "le relanceur a abandonne trop tot"

        ancien.kill()
        ancien.wait(timeout=10)

        code = relanceur.wait(timeout=60)
        # Le port se verifie AVANT toute lecture : le serveur relance ne vit que
        # 20 s, et une lecture qui traine ferait constater un port deja relache.
        assert not port_libre(PORT_TEST), "le port devait etre repris par le nouveau"
        sortie = relanceur.stdout.read()
        assert code == 0, "relanceur en echec (code %s) : %s" % (code, sortie)
        assert "port %d libere" % PORT_TEST in sortie
    finally:
        for proc in (ancien, relanceur):
            if proc is not None and proc.poll() is None:
                proc.kill()
        # Ne pas laisser le nouveau serveur tenir le port pour les tests suivants.
        # Il a ete lance detache : il ne descend pas avec le relanceur.
        if not port_libre(PORT_TEST):
            time.sleep(21)   # le serveur factice s'arrete de lui-meme (20 s)


def test_le_processus_relance_ne_retient_pas_les_tuyaux_du_relanceur(tmp_path):
    """Le relance ne doit pas garder la sortie du relanceur ouverte derriere lui.

    Sans console, un processus lance HERITE des descripteurs standard de son
    lanceur. Le dashboard relance les tiendrait donc ouverts pour toujours, et
    `stdout.read()` sur le relanceur ne rendrait la main qu'a la mort du dashboard
    — alors que le relanceur, lui, est mort depuis longtemps.

    Mesure du 2026-08-26 (CI Linux) : la lecture rendait la main 20 s trop tard,
    et le test constatait un port deja relache. Invisible sous Windows, ou
    l'heritage ne se fait pas de la meme facon : seule la CI l'a vu.
    """
    env = dict(os.environ, DASHBOARD_RELANCE_SANS_CONSOLE="1")
    duree_du_relance = 30          # bien plus long que la lecture attendue

    relanceur = subprocess.Popen([
        sys.executable, str(RELANCEUR),
        "999999", str(PORT_TEST), str(tmp_path),
        sys.executable, "-c", SERVEUR_FACTICE, str(PORT_TEST), str(duree_du_relance),
    ], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert relanceur.wait(timeout=60) == 0
        depart = time.monotonic()
        relanceur.stdout.read()        # doit atteindre EOF tout de suite
        lecture = time.monotonic() - depart
        assert lecture < 5.0, (
            "la sortie du relanceur n'a atteint EOF qu'apres %.1f s : le processus "
            "relance retient encore le tuyau" % lecture
        )
    finally:
        if relanceur.poll() is None:
            relanceur.kill()
        limite = time.time() + duree_du_relance + 10
        while time.time() < limite and not port_libre(PORT_TEST):
            time.sleep(0.5)


def test_le_relanceur_journalise_dans_un_fichier(tmp_path):
    """Il n'a ni console ni interlocuteur : sans trace, un echec est invisible."""
    env = dict(os.environ, DASHBOARD_RELANCE_SANS_CONSOLE="1")
    r = subprocess.run([
        sys.executable, str(RELANCEUR),
        "999999", str(PORT_TEST), str(tmp_path),
        sys.executable, "-c", "pass",
    ], env=env, capture_output=True, text=True, timeout=120)

    journal = tmp_path / "relaunch.log"
    assert journal.exists(), "aucun journal ecrit"
    contenu = journal.read_text(encoding="utf-8")
    assert "relance demandee" in contenu
    # La cible ne prend pas le port : l'echec doit etre dit, pas tu.
    assert r.returncode == 1
    assert "ECHEC" in contenu


def test_un_lancement_qui_ne_reprend_pas_le_port_est_signale(tmp_path):
    """Le piege trouve le 2026-08-26 : Popen rend la main sans erreur alors que rien
    ne tourne. Sans verification du port, l'echec passait pour un succes."""
    env = dict(os.environ, DASHBOARD_RELANCE_SANS_CONSOLE="1")
    r = subprocess.run([
        sys.executable, str(RELANCEUR),
        "999999", str(PORT_TEST), str(tmp_path),
        sys.executable, "-c", "pass",       # ne prend jamais le port
    ], env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 1, "un lancement sans reprise du port doit etre un echec"


def test_le_relanceur_refuse_des_arguments_incomplets():
    r = subprocess.run([sys.executable, str(RELANCEUR), "123"],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 2
    assert "usage" in r.stdout.lower()


# ---------------------------------------------------------------------------
# Câblage
# ---------------------------------------------------------------------------

def test_la_route_repond_avant_de_mourir():
    """Si le processus mourait avant d'avoir répondu, le navigateur afficherait une
    erreur réseau au lieu d'une confirmation : l'ordre compte."""
    src = (_backend / "app.py").read_text(encoding="utf-8")
    bloc = src.split('@app.post("/api/dashboard/restart")')[1].split("@app.")[0]
    position_reponse = bloc.index("return {")
    position_mort = bloc.index("os._exit(0)")
    assert position_mort < position_reponse, \
        "la sortie doit être différée dans un thread, PAS exécutée avant le return"
    assert "threading.Thread" in bloc and "daemon=True" in bloc
    assert "time.sleep" in bloc, "il faut laisser la réponse partir avant de couper"


def test_la_route_est_protegee_par_authentification():
    """Redémarrer le dashboard est une action privilégiée."""
    src = (_backend / "app.py").read_text(encoding="utf-8")
    publics = src.split("_PUBLIC_PATHS = {")[1].split("}")[0]
    assert "/api/dashboard/restart" not in publics


def test_le_relanceur_est_lance_detache():
    """Il doit survivre à la mort de son parent — c'est tout son rôle."""
    src = (_backend / "app.py").read_text(encoding="utf-8")
    bloc = src.split('@app.post("/api/dashboard/restart")')[1].split("@app.")[0]
    assert "DETACHED_PROCESS" in bloc
    assert "start_new_session" in bloc


def test_le_bouton_existe_et_est_distinct_des_boutons_de_bots():
    """Un bouton « redémarrer » près de ceux des bots doit dire clairement qu'il ne
    touche PAS aux bots, sinon on croit couper Discord."""
    html = (_racine / "dashboard" / "frontend" / "index.html").read_text(encoding="utf-8")
    assert 'id="btn-restart-dashboard"' in html
    assert "restartDashboard()" in html
    bloc = html.split('id="btn-restart-dashboard"')[1][:400]
    assert "bots continuent" in bloc.lower() or "ne touche pas" in bloc.lower()


def test_le_front_attend_le_retour_avant_de_recharger():
    """Recharger tout de suite donnerait une page blanche : le serveur n'est pas
    encore revenu."""
    js = (_racine / "dashboard" / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
    bloc = js.split("async function attendreRetourDashboard()")[1]
    assert "/health" in bloc
    assert "location.reload" in bloc
    position_sondage = bloc.index("/health")
    position_recharge = bloc.index("location.reload")
    assert position_sondage < position_recharge


def test_le_contexte_de_lancement_est_fige_au_demarrage():
    """`sys.argv[0]` est RELATIF au répertoire de départ (start_dashboard.bat fait
    « cd dashboard » puis « python backend\app.py »). Le relire au moment du clic
    donnerait un chemin faux si le répertoire courant avait changé entre-temps."""
    src = (_backend / "app.py").read_text(encoding="utf-8")
    assert "_LANCEMENT_CWD = os.getcwd()" in src
    assert "_LANCEMENT_ARGV = list(sys.argv)" in src

    bloc = src.split('@app.post("/api/dashboard/restart")')[1].split("@app.")[0]
    assert "_LANCEMENT_CWD" in bloc and "_LANCEMENT_ARGV" in bloc
    assert "os.getcwd()" not in bloc, "la route doit utiliser le contexte figé"

    # Figé avant tout import lourd, donc avant qu'un module puisse changer de dossier.
    assert src.index("_LANCEMENT_CWD = os.getcwd()") < src.index("from fastapi import FastAPI")


# ---------------------------------------------------------------------------
# Le garde de port au DEMARRAGE : uvicorn se lie trop tard
# ---------------------------------------------------------------------------

def test_le_lancement_verifie_le_port_avant_de_demarrer_l_application():
    """⚠️ Constate le 2026-09-07, deux fenetres ouvertes sur le meme dashboard :

        INFO:     Application startup complete.
        ERROR:    [Errno 10048] error while attempting to bind on address ...

    Uvicorn joue les hooks de demarrage de l'application AVANT d'echouer a se lier.
    La 2e instance s'ouvre donc a demi — elle touche `data/` et les journaux que les
    six bots live partagent — puis meurt sur un winerror brut. L'utilisateur lit
    « startup complete » suivi d'une erreur et croit a une panne du dashboard.

    ⚠️ On exige l'APPEL, pas la presence du nom : un simple import passerait le test
    alors que rien ne garderait le port.
    """
    import ast

    source = (_backend / "app.py").read_text(encoding="utf-8")
    arbre = ast.parse(source, filename="app.py")

    principal = [
        n for n in arbre.body
        if isinstance(n, ast.If) and ast.unparse(n.test).replace('"', "'") == "__name__ == '__main__'"
    ]
    assert principal, "app.py n'a plus de bloc `if __name__ == \"__main__\"`"
    bloc = principal[0]

    appels = [n for n in ast.walk(bloc)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
              and n.func.id == "port_libre" and n.args]
    assert appels, (
        "Le lancement n'interroge pas `port_libre()` : une 2e instance demarrera "
        "l'application avant d'echouer a se lier."
    )

    # Et le garde doit COUPER, pas seulement prevenir.
    sorties = [n for n in ast.walk(bloc)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and n.func.attr == "exit"]
    assert sorties, "Le garde previent mais ne coupe pas : uvicorn demarrera quand meme."

    # Le garde doit precede `uvicorn.run`, sinon il ne sert a rien.
    ligne_garde = min(a.lineno for a in appels)
    lancements = [n.lineno for n in ast.walk(bloc)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                  and n.func.attr == "run"]
    assert lancements and ligne_garde < min(lancements), (
        "Le garde de port doit passer AVANT `uvicorn.run`."
    )


def test_le_garde_de_port_teste_par_bind_et_non_par_connexion():
    """`port_libre` est la bonne fonction, et elle reserve au lieu de se connecter.

    Se connecter sans jamais accepter remplit la file d'attente d'en face : sondee en
    boucle, la methode par connexion finit par declarer libre un port toujours pris.
    """
    import inspect

    source = inspect.getsource(port_libre)
    assert ".bind(" in source
    assert ".connect(" not in source
