"""OpenRouter est retire. Ce fichier fige la decision, pour qu'elle ne se defasse pas.

Historique : le free tier OpenRouter a rendu **12 echecs sur 12** (429 en rafale, 60 a
120 s de latence). L'echelon a donc ete sorti des cascades le 2026-08-30 — mais **tout le
code est reste** : 12 clients construits au demarrage pour rien, une branche
`elif client_type == "openrouter"` dans le noyau et ses 6 copies vendorisees, et
`OPENROUTER_API_KEY` reclame par `tools/preparer_env.py` a tous les bots.

⚠️ Le vrai motif du retrait n'est pas le menage, c'est un **piege arme** :
`_fuite_de_raisonnement()` — la garde qui a empeche Malena de reciter son raisonnement en
Discord — n'etait appelee QUE dans la branche OpenRouter de `shared/llm_cascade.py`.
Alfred, M'aiq et Sheogorath ont leur cascade **inline** et ne l'appelaient nulle part. Le
jour ou quelqu'un remettait OpenRouter dans une cascade, ces trois-la recitaient leur
raisonnement en clair. Un code mort qui redevient vivant est plus dangereux qu'un code
vivant, parce que personne ne le relit.

Le sort d'OpenRouter etait la question ouverte n°1 de l'audit du 2026-09-04. Reponse :
**retire**. Si quelqu'un veut le remettre, il devra supprimer ces tests — c'est-a-dire
prendre la decision sciemment, et recabler la garde anti-fuite dans les 3 cascades inline
AVANT de le faire.
"""
import ast
import re
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

BOTS = {
    "Alfred": "bot_alfred.py",
    "JohnnyBot": "bot_johnny.py",
    "MaiqBot": "bot_maiq.py",
    "MalenaBot": "bot_malena.py",
    "Sheogorath": "bot_sheogorath.py",
    "SugarBot": "bot_sugar.py",
}

NOYAU = ["shared/llm_cascade.py", "shared/smart_router.py", "shared/models.py"]
VENDORISES = [f"{b}/core/{m}.py" for b in BOTS for m in ("llm_cascade", "smart_router", "models")]

# Ce qui serait du code VIVANT. Les commentaires et docstrings gardent le droit
# d'expliquer pourquoi OpenRouter n'est plus la : c'est meme le but de ce fichier.
CODE_VIVANT = re.compile(
    r'client_type\s*==\s*"openrouter"'
    r'|openrouter_client'
    r'|OPENROUTER_API_KEY'
    r'|openrouter\.ai',
    re.IGNORECASE,
)


def _lignes_de_log(chemin):
    """Rend les lignes qui ECRIVENT dans les logs, commentaires exclus.

    ⚠️ Un filet pose sur les IDENTIFIANTS ne protege pas la PROSE. Le 2026-09-05, tout le
    code OpenRouter etait parti et les tests etaient verts — mais Sheogorath annoncait
    encore « ✅ [SYSTEM] Cerveau OpenRouter connecté. » a chaque demarrage, depuis un
    `try:` orphelin dont ce log etait devenu le seul corps. Il compilait, donc rien ne
    le voyait. Meme piege que [[gotcha-repartee-cascade-fantome]] : en retirant un
    fournisseur, chercher AUSSI son nom de marque.
    """
    src = (RACINE / chemin).read_text(encoding="utf-8")
    return [
        f"{chemin}:{n} {l.strip()}"
        for n, l in enumerate(src.split("\n"), 1)
        if re.search(r"logger\.(info|warning|error|debug)\(", l)
        and "openrouter" in l.lower()
    ]


def test_aucun_bot_n_annonce_encore_openrouter_dans_ses_logs():
    menteurs = []
    for dossier, fichier in BOTS.items():
        menteurs += _lignes_de_log(f"{dossier}/{fichier}")
    for chemin in NOYAU + VENDORISES:
        menteurs += _lignes_de_log(chemin)
    assert not menteurs, (
        "Ces lignes annoncent un fournisseur qui n'existe plus. Un log qui ment est pire "
        "qu'un log absent : il fait chercher au mauvais endroit.\n  " + "\n  ".join(menteurs)
    )


def _sans_commentaires(chemin):
    """Rend la source privee de ses commentaires et de ses docstrings.

    Sans ce filtrage le test interdirait d'ECRIRE la decision, donc se retournerait
    contre lui-meme : ce fichier-ci ne passerait pas son propre controle.
    """
    src = (RACINE / chemin).read_text(encoding="utf-8")
    lignes = src.split("\n")

    # ⚠️ Uniquement les DOCSTRINGS, c'est-a-dire les chaines seules sur leur instruction.
    # Blanchir toute chaine litterale mangerait `client_type == "gemini"` et le test se
    # rendrait vert tout seul en n'inspectant plus une ligne de cascade.
    arbre = ast.parse(src)
    a_blanchir = set()
    for noeud in ast.walk(arbre):
        if (isinstance(noeud, ast.Expr) and isinstance(noeud.value, ast.Constant)
                and isinstance(noeud.value.value, str)):
            a_blanchir.update(range(noeud.lineno, (noeud.end_lineno or noeud.lineno) + 1))

    propres = []
    for numero, ligne in enumerate(lignes, 1):
        if numero in a_blanchir:
            propres.append("")
            continue
        propres.append(ligne.split("#", 1)[0])
    return propres


def _coupables(fichiers):
    trouves = []
    for chemin in fichiers:
        if not (RACINE / chemin).exists():
            continue
        for numero, ligne in enumerate(_sans_commentaires(chemin), 1):
            if CODE_VIVANT.search(ligne):
                trouves.append(f"{chemin}:{numero} {ligne.strip()}")
    return trouves


def test_le_noyau_n_a_plus_de_branche_openrouter():
    coupables = _coupables(NOYAU)
    assert not coupables, (
        "OpenRouter a ete retire des cascades le 2026-08-30 et du code le 2026-09-05.\n"
        "Ces lignes le font revivre :\n  " + "\n  ".join(coupables)
    )


def test_les_6_copies_vendorisees_non_plus():
    """⚠️ Corriger `shared/` ne suffit jamais : chaque bot embarque SA copie du noyau."""
    coupables = _coupables(VENDORISES)
    assert not coupables, "\n  " + "\n  ".join(coupables)


def test_aucun_bot_ne_construit_de_client_openrouter():
    coupables = _coupables([f"{d}/{f}" for d, f in BOTS.items()])
    assert not coupables, (
        "Un client construit au demarrage est un echelon qui n'attend qu'une ligne de "
        "cascade pour redevenir vivant, sans sa garde anti-fuite :\n  "
        + "\n  ".join(coupables)
    )


def test_preparer_env_ne_reclame_plus_la_cle():
    """`tools/preparer_env.py` la reclamait aux 6 bots pour un fournisseur retire."""
    coupables = _coupables(["tools/preparer_env.py"])
    assert not coupables, "\n  " + "\n  ".join(coupables)

    for dossier in BOTS:
        exemple = RACINE / dossier / ".env.example"
        assert exemple.exists(), f"{dossier}/.env.example manquant"
        assert "OPENROUTER_API_KEY" not in exemple.read_text(encoding="utf-8"), (
            f"{dossier}/.env.example reclame encore une cle OpenRouter"
        )


def test_ce_test_a_trouve_sa_matiere():
    """⚠️ Sans cette borne, une erreur de chemin rendrait tout le fichier vert a vide.

    C'est le piege de `.gitignore` non ancre : la CI etait rouge et personne ne
    regardait, parce que le garde-fou ne gardait plus rien.
    """
    fichiers = NOYAU + VENDORISES + [f"{d}/{f}" for d, f in BOTS.items()] + ["tools/preparer_env.py"]
    presents = [c for c in fichiers if (RACINE / c).exists()]
    assert len(presents) == 28, (
        f"On attendait 28 fichiers inspectes (3 noyau + 18 vendorises + 6 bots + "
        f"preparer_env), on en a trouve {len(presents)}"
    )

    # Et la source doit vraiment etre lue : au moins un `client_type ==` par cascade.
    for chemin in ["shared/llm_cascade.py"] + [f"{b}/core/llm_cascade.py" for b in BOTS]:
        lignes = _sans_commentaires(chemin)
        assert any('client_type ==' in l for l in lignes), (
            f"{chemin} : aucune branche de cascade trouvee, le filtrage a trop mange"
        )
