# -*- coding: utf-8 -*-
"""Verrou : une image reconstruite est celle qu'on a testee, pas celle du jour.

Mesure du 2026-11-24 : LAYA ne se construisait plus — `laya>=0.3.4` avait tire la 0.5.0,
sortie cinq jours plus tot, qui avait retire `laya.agent`. Le meme jour, quatre bots
tournaient en boucle sur des images de juin sans Pillow. Les deux viennent de la meme
faiblesse : des versions laissees libres, donc une image qui depend de la DATE du build.

requirements.txt reste la liste voulue, ecrite a la main ; requirements.lock fige ce
qu'elle a donne. L'image et la CI installent le second : la CI teste donc exactement les
versions de la production.
"""
import re
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def _nom(spec):
    """`discord.py[voice]>=2.7` -> `discord-py` (normalisation PEP 503)."""
    nom = re.split(r"[\s\[<>=!~;]", spec.strip(), maxsplit=1)[0]
    return re.sub(r"[-_.]+", "-", nom).lower()


def _lignes(fichier):
    return [l.strip() for l in (RACINE / fichier).read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.strip().startswith("#")]


def test_chaque_ligne_du_lock_est_une_version_exacte():
    for ligne in _lignes("requirements.lock"):
        assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*==[A-Za-z0-9.+!-]+", ligne), ligne


def test_chaque_dependance_voulue_est_figee():
    figes = {_nom(l.split("==")[0]) for l in _lignes("requirements.lock")}
    manquants = {_nom(l) for l in _lignes("requirements.txt")} - figes
    assert not manquants, f"ajoutees a requirements.txt mais pas figees : {sorted(manquants)}"


def test_l_image_des_bots_installe_le_lock():
    dockerfile = (RACINE / "Dockerfile").read_text(encoding="utf-8")
    assert "pip install --no-cache-dir -r requirements.lock" in dockerfile
    assert "-r requirements.txt" not in dockerfile


def test_la_ci_installe_le_lock():
    ci = (RACINE / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "pip install -r requirements.lock" in ci
    assert "-r requirements.txt" not in ci


def test_les_images_de_base_sont_figees_au_correctif_pres():
    for dockerfile in ("Dockerfile", "laya-server/Dockerfile"):
        froms = re.findall(r"^FROM\s+(\S+)", (RACINE / dockerfile).read_text(encoding="utf-8"), re.M)
        assert froms, dockerfile
        for image in froms:
            assert re.fullmatch(r"python:\d+\.\d+\.\d+-slim", image), f"{dockerfile} : {image}"


def test_laya_server_fige_chaque_paquet():
    texte = (RACINE / "laya-server" / "Dockerfile").read_text(encoding="utf-8")
    bloc = texte[texte.index("RUN pip install"):texte.index("ENV HF_HOME")]
    paquets = re.findall(r'"([^"]+)"', bloc)
    assert {_nom(p) for p in paquets} >= {"torch", "laya", "transformers", "fastapi", "uvicorn"}
    for p in paquets:
        assert "==" in p and not re.search(r"[<>~]", p), p
    assert '"laya==0.3.4"' in texte   # 0.4 et 0.5 n'ont plus `laya.agent`
