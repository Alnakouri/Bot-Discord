# -*- coding: utf-8 -*-
"""Laya garde ses poids CHAUDS, sinon son premier appel retombe au repli.

⚠️ MESURE DU 2026-09-22 qui justifie tout ce fichier. Apres 45 h sans trafic, la
premiere rafale depuis le conteneur d'Alfred a donne **5 appels sur 6 repartis au
repli** : 694 ms, puis quatre timeouts a la borne de 300 ms. Une fois chaud : mediane
135 ms. Et apres 3 min de pause seulement, le premier appel remontait deja a 292 ms.

En production Laya est appele rarement — le PREMIER appel est donc souvent le SEUL, et
c'est exactement celui qui ratait la borne. Le healthcheck du compose ne corrigeait rien :
`/health` ne fait aucune inference, et un ping HTTP ne rechauffe pas des poids.
"""
import importlib.util
import threading
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SERVEUR = RACINE / "laya-server" / "server.py"


def _module():
    """`laya-server` n'est pas un paquet (tiret dans le nom) : on charge le fichier."""
    spec = importlib.util.spec_from_file_location("laya_server_sous_test", SERVEUR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # `import laya` est DANS _charger(), pas ici
    return mod


class _AgentBidon:
    def __init__(self, leve=False):
        self.appels = []
        self.leve = leve

    def system_one(self, etat, questions):
        self.appels.append((etat, questions))
        if self.leve:
            raise RuntimeError("inference refusee")
        return {"answers": {}}


def test_la_chauffe_fait_une_vraie_inference():
    """Un ping HTTP ne rechauffe rien : il FAUT passer par le modele."""
    mod = _module()
    agent = _AgentBidon()
    mod._chauffe(agent)
    assert len(agent.appels) == 1, "la chauffe doit appeler system_one, pas se contenter d'exister"
    etat, questions = agent.appels[0]
    assert etat and questions, "une inference a vide ne chauffe rien"


def test_une_chauffe_qui_echoue_ne_tue_pas_le_service():
    """Le service est CONSULTATIF : un fil de confort n'a pas le droit de le faire tomber."""
    mod = _module()
    agent = _AgentBidon(leve=True)
    mod._boucle_de_chauffe(agent, 0.01, une_seule_fois=True)   # ne doit pas lever
    assert len(agent.appels) == 1


def test_la_boucle_repete_et_s_arrete():
    mod = _module()
    agent = _AgentBidon()
    arret = threading.Event()
    fil = threading.Thread(target=mod._boucle_de_chauffe, args=(agent, 0.01, arret), daemon=True)
    fil.start()
    for _ in range(200):                      # au plus 2 s, sans dormir bêtement
        if len(agent.appels) >= 3:
            break
        threading.Event().wait(0.01)
    arret.set()
    fil.join(timeout=2)
    assert not fil.is_alive(), "la boucle doit s'arreter quand on le lui demande"
    assert len(agent.appels) >= 3, f"la boucle ne repete pas (appels={len(agent.appels)})"


def test_le_fil_de_chauffe_est_bien_lance_au_demarrage():
    """Le defaut a corriger etait justement du code present mais jamais appele."""
    import ast
    arbre = ast.parse(SERVEUR.read_text(encoding="utf-8"))
    charger = next(n for n in ast.walk(arbre)
                   if isinstance(n, ast.FunctionDef) and n.name == "_charger")
    fils = [n for n in ast.walk(charger)
            if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "start"]
    assert fils, "_charger() doit demarrer le fil de chauffe"
    threads = [n for n in ast.walk(charger)
               if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "Thread"]
    assert threads, "le fil de chauffe doit etre un threading.Thread"
    daemon = [k for t in threads for k in t.keywords if k.arg == "daemon"]
    assert daemon and daemon[0].value.value is True, (
        "le fil doit etre daemon, sinon il retient l'arret du conteneur")


def test_l_intervalle_reste_sous_le_refroidissement_mesure():
    """3 min de pause suffisaient a remonter a 292 ms, 8 ms sous la borne du client.

    Un intervalle qui s'approcherait de ce delai rouvrirait le defaut EN SILENCE :
    aucune erreur nulle part, juste des decisions qui repartent au repli.
    """
    mod = _module()
    assert 0 < mod.CHAUFFE_S <= 60, (
        f"intervalle de chauffe {mod.CHAUFFE_S}s : le refroidissement est mesure a "
        f"~180 s. Remesurer avant de monter cette valeur.")
