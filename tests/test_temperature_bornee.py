# -*- coding: utf-8 -*-
"""Aucun bot ne doit servir sa persona au-dessus de 1.0 de température.

Au-delà de 1.0, on aplatit la distribution du modèle : les candidats improbables
remontent artificiellement. Sur une réponse de 200 mots c'est 200 tirages successifs, et
un seul dérapage suffit à enclencher une boucle dont le modèle ne sort plus — il relit sa
propre sortie abîmée pour choisir la suite.

Mesuré le 2026-09-16 : Malena était le SEUL bot au-dessus de 0.9 (`temperature=1.1` sur
trois de ses quatre échelons) et le SEUL à dégénérer, avec 8 réponses sur 26 en
« Oh là là là là… » ×201. Voir [[gotcha-boucle-degenerative-pas-une-reponse]].

Le verrou lit la valeur DANS l'appel, par `ast` : une constante nommée peut être
redéfinie, et une regex sur `temperature=` raterait un littéral passé autrement.
"""
import ast
import os

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BOTS = {
    "Alfred": "bot_alfred.py",
    "JohnnyBot": "bot_johnny.py",
    "MaiqBot": "bot_maiq.py",
    "MalenaBot": "bot_malena.py",
    "Sheogorath": "bot_sheogorath.py",
    "SugarBot": "bot_sugar.py",
}

PLAFOND = 1.0


def _temperatures_du_fichier(chemin):
    """Toutes les températures littérales passées à un appel, + celles des constantes."""
    arbre = ast.parse(open(chemin, encoding="utf-8").read())

    constantes = {}
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Assign) and isinstance(noeud.value, ast.Constant):
            for cible in noeud.targets:
                if isinstance(cible, ast.Name) and isinstance(noeud.value.value, (int, float)):
                    constantes[cible.id] = noeud.value.value

    trouvees = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.Call):
            continue
        for kw in noeud.keywords:
            if kw.arg != "temperature":
                continue
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, (int, float)):
                trouvees.append((kw.value.value, "littéral"))
            elif isinstance(kw.value, ast.Name) and kw.value.id in constantes:
                trouvees.append((constantes[kw.value.id], kw.value.id))
    return trouvees


def test_aucun_bot_ne_depasse_le_plafond_de_temperature():
    vus = 0
    for dossier, fichier in BOTS.items():
        chemin = os.path.join(_parent_dir, dossier, fichier)
        if not os.path.exists(chemin):
            continue
        for valeur, source in _temperatures_du_fichier(chemin):
            vus += 1
            assert valeur <= PLAFOND, (
                f"{dossier}/{fichier} : temperature={valeur} ({source}) dépasse {PLAFOND}. "
                "Au-delà, le modèle peut s'enfermer dans une boucle de répétition — c'est "
                "ce qui a fait envoyer « Oh là là là là… » ×201 par Malena le 2026-09-16."
            )
    assert vus >= 4, f"seulement {vus} température(s) relevée(s) : le verrou ne lit plus rien"


def test_malena_est_bien_redescendue():
    """Le cas qui a motivé le plafond : ses 4 échelons, tous sur la même valeur.

    ⚠️ Ils divergeaient — 1.1 sur Gemini/Groq/NVIDIA, 0.9 sur Mistral : la voix de Malena
    changeait selon le fournisseur qui la servait, sans que rien ne le dise.
    """
    chemin = os.path.join(_parent_dir, "MalenaBot", "bot_malena.py")
    valeurs = [v for v, _ in _temperatures_du_fichier(chemin)]

    cascade = [v for v in valeurs if v >= 0.7]  # l'appel court à 0.5 n'est pas la cascade
    assert cascade, "aucune température de cascade relevée chez Malena"
    assert len(set(cascade)) == 1, (
        f"les échelons de Malena divergent encore : {sorted(set(cascade))} — sa voix "
        "dépend alors du fournisseur qui répond"
    )
    assert cascade[0] == 0.9, f"attendu 0.9, trouvé {cascade[0]}"
