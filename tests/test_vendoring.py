"""Le vendoring du noyau : personne ne verifiait qu'il etait a jour.

`tools/sonde_core_drift.py` existe depuis la decision d'independance stricte, mais
**rien ne le lancait**. Le 2026-09-03, `shared/llm_cascade.py` a ete corrige sans que les
6 copies soient regenerees : les bots auraient tourne avec l'ancienne version, et la suite
etait verte. Une convention que seule la discipline protege finit toujours par ceder.
"""
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
BOTS = ["Alfred", "JohnnyBot", "MaiqBot", "MalenaBot", "Sheogorath", "SugarBot"]


def _modules_vendorises():
    """Les modules de `shared/` qui sont effectivement copies dans les bots."""
    sys.path.insert(0, str(RACINE / "tools"))
    try:
        import sonde_core_drift
    finally:
        sys.path.pop(0)
    return [m for m in sonde_core_drift.MODULES if (RACINE / "shared" / m).exists()]


def test_les_copies_vendorisees_sont_a_jour():
    modules = _modules_vendorises()
    # ⚠️ Prouver que le test a trouve sa matiere : sans cette borne, une sonde qui
    # n'inspecterait plus rien passerait au vert.
    assert len(modules) >= 8, f"Trop peu de modules vendorises trouves : {modules}"

    presentes = [
        RACINE / bot / "core" / module
        for bot in BOTS
        for module in modules
    ]
    manquantes = [p for p in presentes if not p.exists()]
    assert not manquantes, f"Copies vendorisees absentes : {manquantes}"
    assert len(presentes) == 6 * len(modules)

    res = subprocess.run(
        [sys.executable, str(RACINE / "tools" / "sonde_core_drift.py")],
        cwd=RACINE,               # ⚠️ la sonde lit `shared/` en chemin RELATIF
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, (
        "Le noyau vendorise a derive de `shared/`. Relancer :\n"
        "    python tools/vendor_core.py\n\n" + res.stdout + res.stderr
    )
