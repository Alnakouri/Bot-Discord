# -*- coding: utf-8 -*-
"""Relance le dashboard apres son propre arret.

Un processus ne peut pas se redemarrer lui-meme : tant qu'il vit, il tient le port
8501 ; s'il meurt d'abord, il n'y a plus personne pour relancer quoi que ce soit.
D'ou ce petit programme detache, lance PAR le dashboard juste avant qu'il ne quitte.

Il attend deux choses, dans cet ordre :
  1. que le processus parent ait reellement disparu ;
  2. que le port soit reellement libre — relancer trop tot donne un « address already
     in use » qui laisse l'utilisateur sans dashboard du tout.

Puis il relance, et surtout **il verifie que ca a marche** : le dashboard est revenu
si et seulement si le port est repris. Sans cette verification, un lancement qui
echoue silencieusement laisse l'utilisateur devant un navigateur qui tourne dans le
vide, sans la moindre trace de ce qui s'est passe.

Deux facons de lancer, essayees dans cet ordre :
  - CREATE_NEW_CONSOLE : rend les logs du dashboard visibles, comme quand on lance
    start_dashboard.bat a la main. C'est le confort normal.
  - DETACHED_PROCESS : marche partout, y compris sans session de bureau (mesure du
    2026-08-26 : CREATE_NEW_CONSOLE et `cmd /c start` restent bloques sans console
    interactive, sans lever la moindre erreur).

Usage (interne) :
    python relauncher.py <pid_parent> <port> <repertoire> <commande...>
"""
import os
import socket
import subprocess
import sys
import time

DELAI_MORT_PARENT = 30.0
DELAI_PORT_LIBRE = 30.0
DELAI_RETOUR = 25.0      # temps laisse au dashboard pour reprendre le port
PAS = 0.25

_JOURNAL = None


def journaliser(message: str) -> None:
    """Trace dans un fichier : ce programme n'a ni console ni interlocuteur."""
    ligne = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}"
    print(ligne)
    if _JOURNAL:
        try:
            with open(_JOURNAL, "a", encoding="utf-8") as f:
                f.write(ligne + "\n")
        except Exception:
            pass


def processus_vivant(pid: int) -> bool:
    """Vrai si le processus tourne encore."""
    if sys.platform == "win32":
        try:
            sortie = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, timeout=5,
            ).stdout
            return str(pid) in sortie
        except Exception:
            return False
    try:
        os.kill(pid, 0)          # signal 0 : ne tue rien, teste l'existence
        return True
    except (OSError, ProcessLookupError):
        return False


def port_libre(port: int, hote: str = "127.0.0.1") -> bool:
    """Le port peut-il etre REELLEMENT repris ?

    On tente une reservation, pas une connexion. Deux raisons :
      - c'est exactement la question posee — « le dashboard pourra-t-il se rebinder
        ici ? » — et non un indice indirect ;
      - se connecter sans jamais accepter remplit la file d'attente du processus
        d'en face ; sondee en boucle, la methode par connexion finit par se mentir
        a elle-meme (mesure : avec un listen(1), la 2e sonde declare le port libre
        alors qu'il est toujours pris).

    Pas de SO_REUSEADDR : on veut justement qu'un port deja pris fasse echouer.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((hote, port))
            return True
        except OSError:
            return False


def attendre(condition, delai_max: float) -> bool:
    limite = time.time() + delai_max
    while time.time() < limite:
        if condition():
            return True
        time.sleep(PAS)
    return condition()


def _options_lancement(mode: str) -> dict:
    """Options de lancement du dashboard relance.

    Detail qui a coute une CI rouge : sans console (POSIX, ou DETACHED_PROCESS),
    le processus lance HERITE des tuyaux standard du relanceur. Il les tient alors
    ouverts aussi longtemps qu'il vit, c'est-a-dire indefiniment pour un dashboard :
    quiconque lit la sortie du relanceur reste bloque, meme apres sa mort, parce que
    le tuyau n'atteint jamais EOF. On coupe donc net l'heritage sur DEVNULL — de
    toute facon, sans console, cette sortie n'irait nulle part.
    Le mode console est la seule exception : Windows lui alloue une vraie console,
    et c'est precisement pour y VOIR les logs qu'on le prefere.
    """
    if sys.platform == "win32" and mode == "console":
        return {"creationflags": subprocess.CREATE_NEW_CONSOLE}

    sans_heritage = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform != "win32":
        return {"start_new_session": True, **sans_heritage}
    return {
        "creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        **sans_heritage,
    }


def tenter_lancement(commande, repertoire, port, mode) -> bool:
    """Lance, puis verifie que le port est bien repris. Nettoie si ca a echoue."""
    journaliser(f"lancement ({mode}) : {' '.join(commande)}")
    try:
        proc = subprocess.Popen(commande, cwd=repertoire, **_options_lancement(mode))
    except Exception as e:
        journaliser(f"  echec du lancement : {type(e).__name__}: {e}")
        return False

    if attendre(lambda: not port_libre(port), DELAI_RETOUR):
        journaliser(f"  OK — port {port} repris (pid {proc.pid})")
        return True

    journaliser(f"  le port {port} n'a pas ete repris en {DELAI_RETOUR:.0f} s")
    try:
        if proc.poll() is None:
            proc.kill()        # ne pas laisser un processus fantome tenir le port
            journaliser("  processus fantome supprime")
    except Exception:
        pass
    return False


def main() -> int:
    global _JOURNAL

    if len(sys.argv) < 5:
        print("usage: relauncher.py <pid_parent> <port> <repertoire> <commande...>")
        return 2

    pid = int(sys.argv[1])
    port = int(sys.argv[2])
    repertoire = sys.argv[3]
    commande = sys.argv[4:]

    _JOURNAL = os.path.join(repertoire, "relaunch.log")
    journaliser(f"=== relance demandee (parent {pid}, port {port}) ===")

    if not attendre(lambda: not processus_vivant(pid), DELAI_MORT_PARENT):
        journaliser(f"parent {pid} toujours vivant apres {DELAI_MORT_PARENT:.0f} s — abandon")
        return 1
    journaliser(f"parent {pid} termine")

    if not attendre(lambda: port_libre(port), DELAI_PORT_LIBRE):
        journaliser(f"port {port} toujours occupe apres {DELAI_PORT_LIBRE:.0f} s — abandon")
        return 1
    journaliser(f"port {port} libere")

    # Le mode a console est prefere (logs visibles), mais il reste bloque sans
    # session de bureau : on verifie, et on retombe sur le mode detache.
    modes = ["detache"] if os.environ.get("DASHBOARD_RELANCE_SANS_CONSOLE") else ["console", "detache"]
    for mode in modes:
        if tenter_lancement(commande, repertoire, port, mode):
            journaliser("=== dashboard relance ===")
            return 0

    journaliser("=== ECHEC : dashboard non relance, lancer start_dashboard.bat a la main ===")
    return 1


if __name__ == "__main__":
    sys.exit(main())
