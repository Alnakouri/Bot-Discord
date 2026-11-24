# -*- coding: utf-8 -*-
"""Sonde de sante : les bots tournent-ils, la sauvegarde aussi, les liens d'invitation sont-ils vivants ?

Mesure du 2026-11-24 : quatre bots sur six tournaient en boucle de redemarrage depuis
deux jours (`ModuleNotFoundError: PIL`, images de juin), la sauvegarde ne tournait plus
depuis le 22/11, et le lien `!discord` de Johnny etait expire. Docker relancait les
conteneurs en silence, le dashboard l'aurait montre... a condition de l'ouvrir. Personne
n'a rien vu. Une panne que rien ne signale dure jusqu'a ce qu'un humain tombe dessus.

Ce qui est verifie :
  1. chaque service de docker-compose.yml a son conteneur, en marche, sain, et qui ne
     redemarre pas en boucle ;
  2. la derniere sauvegarde de `bots-sauvegarde` a moins de 26 h (elle tourne toutes les
     24 h, verifiee chaque heure : 25 h au pire) ;
  3. chaque lien Discord des `link_commands` de data/twitch_config.json est vivant, et
     n'expire pas dans les 7 jours.

⚠️ DOCKER ARRETE N'EST PAS UNE PANNE. Docker AutoStart est coupe EXPRES (decision du
proprietaire : le PC demarre plus vite). Crier toutes les heures parce que Docker dort,
c'est une alerte qui crie pour du nominal — elle finit ignoree, et la vraie avec. Docker
arrete : seuls les liens sont verifies.

Le resultat est ecrit dans data/sante.json (un seul ecrivain : cette sonde), que le
dashboard affiche dans son bandeau d'alerte. Avec --notifier, une notification Windows
part pour chaque probleme NOUVEAU — un probleme deja signale ne re-sonne pas toutes les
heures.

    python tools/sonde_sante.py              # rapport lisible
    python tools/sonde_sante.py --strict     # code de sortie 1 si un probleme
    python tools/sonde_sante.py --notifier   # + notification Windows (tache planifiee)

Pas de dependance hors bibliotheque standard : elle tourne avec n'importe quel Python de
l'hote, sans le venv des bots. Elle n'est pas dans pytest (il faut Docker et le reseau) ;
sa logique de decision, elle, l'est : tests/test_sonde_sante.py.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(RACINE / "data")))
FICHIER_SANTE = DATA_DIR / "sante.json"

SAUVEGARDE_MAX_H = 26
SAUVEGARDE_GRACE_MIN = 30      # une sauvegarde part au demarrage : lui laisser le temps
BOUCLE_MIN_REDEMARRAGES = 3
BOUCLE_FENETRE_MIN = 10
LIEN_PREAVIS_JOURS = 7

_SANS_FENETRE = 0x08000000 if os.name == "nt" else 0   # CREATE_NO_WINDOW (pythonw)
_RE_INVITATION = re.compile(r"(?:discord\.gg|discord(?:app)?\.com/invite)/([A-Za-z0-9-]+)")
_RE_DOSSIER_SAUVEGARDE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{4}$")


def _lancer(cmd, timeout=30):
    """(code, sortie) ; (None, message) si la commande n'existe pas ou depasse le temps."""
    try:
        r = subprocess.run(cmd, cwd=RACINE, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, creationflags=_SANS_FENETRE)
        return r.returncode, r.stdout
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, str(e)


def _date_docker(texte):
    """`2026-11-24T22:06:25.575207981Z` -> datetime UTC (Python ne lit que 6 decimales)."""
    if not texte or texte.startswith("0001-"):
        return None
    texte = re.sub(r"(\.\d{6})\d+", r"\1", texte.replace("Z", "+00:00"))
    try:
        return datetime.fromisoformat(texte)
    except ValueError:
        return None


# ─── 1. Conteneurs ───────────────────────────────────────────────────────────

def services_attendus():
    """{service: nom du conteneur} lus dans docker-compose.yml, ou None si Docker ne repond pas."""
    code, sortie = _lancer(["docker", "compose", "config", "--format", "json"])
    if code != 0:
        return None
    try:
        services = json.loads(sortie).get("services") or {}
    except ValueError:
        return None
    return {nom: (svc.get("container_name") or nom) for nom, svc in services.items()}


def inspecter(conteneur):
    """L'etat Docker d'un conteneur, ou None s'il n'existe pas."""
    code, sortie = _lancer(["docker", "inspect", conteneur])
    if code != 0:
        return None
    try:
        return json.loads(sortie)[0]
    except (ValueError, IndexError):
        return None


def problemes_conteneur(service, conteneur, etat, maintenant):
    """Les problemes d'UN conteneur, d'apres son `docker inspect` (None = absent)."""
    cle = f"conteneur:{service}"
    if etat is None:
        return [{"cle": cle, "message": f"{conteneur} n'existe pas (docker compose up -d --build {service})"}]
    st = etat.get("State") or {}
    statut = st.get("Status")
    demarre = _date_docker(st.get("StartedAt"))
    redemarrages = etat.get("RestartCount") or 0
    if st.get("Restarting") or statut == "restarting":
        return [{"cle": cle, "message": f"{conteneur} redemarre en boucle ({redemarrages} redemarrages) : voir docker logs {conteneur}"}]
    if statut != "running":
        return [{"cle": cle, "message": f"{conteneur} est arrete ({statut}, code {st.get('ExitCode')})"}]
    # Une boucle peut etre vue pendant les quelques secondes ou le conteneur « tourne »
    # entre deux plantages : beaucoup de redemarrages ET un demarrage tout recent.
    if (redemarrages >= BOUCLE_MIN_REDEMARRAGES and demarre
            and maintenant - demarre < timedelta(minutes=BOUCLE_FENETRE_MIN)):
        return [{"cle": cle, "message": f"{conteneur} redemarre en boucle ({redemarrages} redemarrages) : voir docker logs {conteneur}"}]
    if ((st.get("Health") or {}).get("Status")) == "unhealthy":
        return [{"cle": cle, "message": f"{conteneur} tourne mais se declare malade (healthcheck)"}]
    return []


# ─── 2. Sauvegarde ───────────────────────────────────────────────────────────

def dossier_sauvegardes(etat_sauvegarde):
    """Le dossier HOTE monte sur /app/sauvegardes dans bots-sauvegarde."""
    for m in (etat_sauvegarde or {}).get("Mounts") or []:
        if m.get("Destination") == "/app/sauvegardes" and m.get("Source"):
            src = m["Source"]
            # Docker Desktop rend `/run/desktop/mnt/host/d/...` pour un chemin Windows `D:/...`
            hote = re.match(r"^/run/desktop/mnt/host/([a-z])/(.*)$", src)
            if hote and os.name == "nt":
                return Path(f"{hote.group(1).upper()}:/{hote.group(2)}")
            return Path(src)
    return None


def derniere_sauvegarde(dossier):
    """Instant (UTC) de la sauvegarde la plus recente : le NOM du dossier, ecrit en UTC."""
    if not dossier or not dossier.is_dir():
        return None
    noms = sorted(p.name for p in dossier.iterdir() if p.is_dir() and _RE_DOSSIER_SAUVEGARDE.match(p.name))
    if not noms:
        return None
    return datetime.strptime(noms[-1], "%Y-%m-%d_%H%M").replace(tzinfo=timezone.utc)


def problemes_sauvegarde(derniere, demarrage_sauvegarde, maintenant):
    """Sauvegarde trop vieille, sauf si le service vient de demarrer (il en fait une tout de suite)."""
    if demarrage_sauvegarde and maintenant - demarrage_sauvegarde < timedelta(minutes=SAUVEGARDE_GRACE_MIN):
        return []
    if derniere is None:
        return [{"cle": "sauvegarde", "message": "aucune sauvegarde trouvee sur le disque de sauvegarde"}]
    age_h = (maintenant - derniere).total_seconds() / 3600
    if age_h > SAUVEGARDE_MAX_H:
        return [{"cle": "sauvegarde", "message": f"derniere sauvegarde il y a {age_h:.0f} h ({derniere:%d/%m %H:%M} UTC)"}]
    return []


# ─── 3. Liens d'invitation ───────────────────────────────────────────────────

def liens_configures():
    """[(bot, commande, code d'invitation)] des link_commands du dashboard."""
    try:
        config = json.loads((DATA_DIR / "twitch_config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    liens = []
    for bot, cfg in (config.items() if isinstance(config, dict) else []):
        for entree in (cfg.get("link_commands") or []) if isinstance(cfg, dict) else []:
            m = _RE_INVITATION.search(str((entree or {}).get("url") or ""))
            if m:
                liens.append((bot, str(entree.get("cmd") or "?").lstrip("!"), m.group(1)))
    return liens


def interroger_invitation(code):
    """('vivante', expire_le|None) | ('morte', None) | ('inconnu', None) si Discord ne repond pas.

    Point public de Discord, sans jeton : il dit seulement si l'invitation existe et quand
    elle expire.
    """
    url = f"https://discord.com/api/v10/invites/{code}?with_expiration=true"
    req = urllib.request.Request(url, headers={"User-Agent": "BotDiscord-sonde-sante (1.0)"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return ("morte", None) if e.code == 404 else ("inconnu", None)
    except (OSError, ValueError):
        return ("inconnu", None)
    return "vivante", _date_docker(data.get("expires_at"))


def problemes_lien(bot, cmd, code, verdict, expire_le, maintenant):
    cle = f"lien:{bot}:{cmd}"
    if verdict == "morte":
        return [{"cle": cle, "message": f"lien !{cmd} de {bot} expire ou supprime (discord.gg/{code})"}]
    if verdict == "vivante" and expire_le and expire_le - maintenant < timedelta(days=LIEN_PREAVIS_JOURS):
        return [{"cle": cle, "message": f"lien !{cmd} de {bot} expire le {expire_le:%d/%m %H:%M} UTC : le remplacer par une invitation permanente"}]
    return []


# ─── Bilan ───────────────────────────────────────────────────────────────────

def bilan(maintenant=None):
    maintenant = maintenant or datetime.now(timezone.utc)
    problemes = []
    services = services_attendus()
    docker = services is not None
    if docker:
        etats = {svc: inspecter(nom) for svc, nom in services.items()}
        for svc, nom in services.items():
            problemes += problemes_conteneur(svc, nom, etats[svc], maintenant)
        etat_sauv = etats.get("sauvegarde")
        if etat_sauv and (etat_sauv.get("State") or {}).get("Status") == "running":
            problemes += problemes_sauvegarde(
                derniere_sauvegarde(dossier_sauvegardes(etat_sauv)),
                _date_docker(etat_sauv["State"].get("StartedAt")), maintenant)
    for bot, cmd, code in liens_configures():
        verdict, expire_le = interroger_invitation(code)
        problemes += problemes_lien(bot, cmd, code, verdict, expire_le, maintenant)
    return {"verifie_le": maintenant.isoformat(timespec="seconds"), "docker": docker, "problemes": problemes}


def nouveaux(precedent, actuel):
    """Les problemes absents du bilan precedent : seuls ceux-la meritent une notification."""
    deja = {p["cle"] for p in (precedent or {}).get("problemes") or []}
    return [p for p in actuel["problemes"] if p["cle"] not in deja]


def lire_bilan_precedent():
    try:
        return json.loads(FICHIER_SANTE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def ecrire_bilan(b):
    """Ecriture atomique : le dashboard ne lit jamais un fichier a moitie ecrit."""
    FICHIER_SANTE.parent.mkdir(parents=True, exist_ok=True)
    tmp = FICHIER_SANTE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(b, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, FICHIER_SANTE)


_TOAST_PS = r"""
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null
$titre = [System.Security.SecurityElement]::Escape($env:SONDE_TITRE)
$texte = [System.Security.SecurityElement]::Escape($env:SONDE_TEXTE)
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml("<toast><visual><binding template='ToastGeneric'><text>$titre</text><text>$texte</text></binding></visual></toast>")
$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($xml))
"""


def notifier(problemes):
    """Notification Windows. Le texte passe par l'environnement, jamais dans le script :
    un nom de conteneur ou de bot ne peut pas devenir du PowerShell."""
    if os.name != "nt" or not problemes:
        return
    titre = f"Bots Discord : {len(problemes)} probleme{'s' if len(problemes) > 1 else ''}"
    texte = "\n".join(p["message"] for p in problemes[:4])
    env = {**os.environ, "SONDE_TITRE": titre, "SONDE_TEXTE": texte}
    try:
        # Windows PowerShell 5.1 : pwsh 7 n'expose plus les types WinRT des notifications.
        subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _TOAST_PS],
                       env=env, capture_output=True, timeout=30, creationflags=_SANS_FENETRE)
    except (OSError, subprocess.TimeoutExpired):
        pass  # la notification est un plus : le bilan est deja ecrit, le dashboard l'affiche


def main():
    ap = argparse.ArgumentParser(description="Sonde de sante des bots (conteneurs, sauvegarde, liens).")
    ap.add_argument("--strict", action="store_true", help="code de sortie 1 si un probleme")
    ap.add_argument("--notifier", action="store_true", help="notification Windows pour chaque probleme nouveau")
    args = ap.parse_args()

    precedent = lire_bilan_precedent()
    b = bilan()
    ecrire_bilan(b)
    if args.notifier:
        notifier(nouveaux(precedent, b))

    if sys.stdout:   # pythonw n'a pas de console
        if not b["docker"]:
            print("Docker arrete : conteneurs et sauvegarde non verifies (AutoStart coupe expres).")
        if b["problemes"]:
            print(f"{len(b['problemes'])} probleme(s) :")
            for p in b["problemes"]:
                print(f"  - {p['message']}")
        else:
            print("Aucun probleme.")
    return 1 if (args.strict and b["problemes"]) else 0


if __name__ == "__main__":
    sys.exit(main())
