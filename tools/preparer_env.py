# -*- coding: utf-8 -*-
"""Ouvre les .env chiffres, les PREPARE pour la saisie, puis les referme.

Les cles vivent dans `<Bot>/.env.encrypted`, illisibles a l'oeil. Pour poser une cle
neuve il faut ouvrir, saisir, refermer — et c'est la que ca derape : on oublie de
refermer, on ecrase un .env.encrypted sans sauvegarde, ou on recopie la cle du voisin
parce que le champ n'existe pas. Cet outil fait les trois etapes proprement.

    python tools/preparer_env.py --etat     # qui a quoi (noms, jamais les valeurs)
    python tools/preparer_env.py --ouvrir   # .env.encrypted -> .env en clair, PRET a saisir
    python tools/preparer_env.py --sceller  # .env -> .env.encrypted, verifie, puis efface le clair

⚠️ Cet outil n'affiche JAMAIS une valeur de cle. Ni en clair, ni tronquee. Les
empreintes, c'est `tools/sonde_cles_partagees.py`.

⚠️ Entre --ouvrir et --sceller, des cles en CLAIR trainent sur le disque. `.gitignore`
couvre `.env` a tous les niveaux (verifie), mais ne laissez pas trainer : --sceller
efface le fichier clair une fois le chiffre relu et compare.

CE QUE --ouvrir PREPARE, et pourquoi
------------------------------------
1. Il RETIRE les variables mortes (cf. MORTES) : une cle qui rend 401 ne se voit pas,
   le bot bascule sur l'echelon suivant et personne ne remarque rien.
2. Il AJOUTE les emplacements du SOCLE qui manquent — et rien d'autre.
   ⚠️ PAS de `GEMINI_KEY_2/3/4`. Les bots savent tourner sur 4 cles Gemini, mais
   UNE SEULE PAR BOT SUFFIT (decision utilisateur, 2026-08-31) : une 2e cle
   demanderait un 2e compte Google, et quand le quota de la premiere tombe la cascade
   bascule deja sur Groq ou Mistral, dont les quotas sont independants. Proposer ces
   champs, c'est reclamer une saisie qui ne sert a rien — et un champ reclame finit
   toujours rempli avec la cle du voisin.
   Une cle GEMINI_KEY_2 deja saisie n'est PAS retiree pour autant : les bots la lisent
   toujours, on cesse simplement d'en demander.
3. Il SIGNALE les cles partagees entre deux bots, la ou il faut saisir la neuve.
   Une variable laissee vide est filtree par les bots (`[k for k in ... if k]`), donc
   un emplacement non rempli ne casse rien.

Regle du depot : UNE CLE PAR BOT, PAS DE PARTAGE (cf. AGENTS.md). Ne recopiez jamais
la cle d'un autre bot pour depanner — c'est exactement comme ca qu'une cle finit
mutualisee sans que personne ne l'ait decide.
"""
import argparse
import shutil
import sys
import time
from collections import defaultdict
from pathlib import Path

try:
    from cryptography.fernet import Fernet
except ImportError:
    print("cryptography manquant : pip install cryptography")
    sys.exit(1)

RACINE = Path(__file__).resolve().parent.parent
BOTS = ["Alfred", "JohnnyBot", "MaiqBot", "MalenaBot", "Sheogorath", "SugarBot"]

# Variables a RETIRER a l'ouverture, avec la raison. Elles restent dans les sauvegardes
# horodatees : rien n'est perdu, seulement sorti du fichier actif.
MORTES = {
    "Alfred": {
        "ELEVENLABS_API_KEY": "401 au 2026-08-30, et la voix est parquee (pas de GPU)",
        "ELEVENLABS_VOICE_ID": "sans la cle ci-dessus, cet identifiant ne sert a rien",
    },
    "Sheogorath": {
        "HF_TOKEN": "401 au 2026-08-30, et AUCUN code du depot ne le lit",
    },
}

# Variables identiques chez plusieurs bots PAR CONSTRUCTION : ce ne sont pas des
# secrets. La liste des salons Twitch ecoutes, les bots pairs du pont anti-doublon,
# l'URL du TTS. Les signaler comme « partagees » serait un faux positif permanent, et
# une alerte qui crie tous les jours n'est plus une alerte.
NON_SECRETES = {"TWITCH_CHAT_CHANNELS", "TWITCH_PEER_BOTS", "PIPER_TTS_URL",
                "ELEVENLABS_VOICE_ID", "TWITCH_BOT_USERNAME"}

# Les cles qui doivent exister chez tout le monde. Le reste (Twitch, TTS) depend des
# fonctions activees bot par bot : on ne le reclame pas.
SOCLE = ["DISCORD_TOKEN", "GEMINI_KEY_1", "GROQ_API_KEY", "MISTRAL_API_KEY",
         "OPENROUTER_API_KEY"]

ENTETE = """\
# ------------------------------------------------------------------------------
# {bot} — fichier EN CLAIR, ouvert par tools/preparer_env.py le {date}
#
# Saisissez les valeurs manquantes ci-dessous, puis REFERMEZ :
#     python tools/preparer_env.py --sceller
# Le chiffre est sauvegarde et relu avant que ce fichier en clair soit efface.
#
# UNE CLE PAR BOT. PAS DE PARTAGE. Un emplacement laisse vide est ignore par le bot,
# ce qui vaut toujours mieux que la cle d'un voisin.
# ------------------------------------------------------------------------------
"""


def fernet_du_bot(dossier):
    cle = dossier / ".master_key"
    if not cle.exists():
        return None
    return Fernet(cle.read_bytes().strip())


def lire_chiffre(dossier):
    """Rend le contenu en clair du .env.encrypted, ou None."""
    chiffre = dossier / ".env.encrypted"
    f = fernet_du_bot(dossier)
    if not chiffre.exists() or f is None:
        return None
    return f.decrypt(chiffre.read_bytes()).decode("utf-8")


def lire_env(dossier):
    """Le contenu qui FAIT FOI pour ce bot, clair ou chiffre.

    ⚠️ Meme ordre de priorite que `shared/secure_env.py` : le .env en clair l'emporte
    des qu'il existe. Lire le chiffre pendant qu'un clair traine, c'est decrire l'etat
    d'AVANT la saisie — l'outil a signale un partage deja corrige, ce qui est aussi
    nuisible que de rater un vrai partage : on apprend a ne plus le croire.
    """
    clair = dossier / ".env"
    if clair.exists():
        return clair.read_text(encoding="utf-8")
    return lire_chiffre(dossier)


def variables(texte):
    """[(nom, valeur)] dans l'ordre du fichier, commentaires ignores."""
    trouvees = []
    for ligne in texte.splitlines():
        nue = ligne.strip()
        if not nue or nue.startswith("#") or "=" not in nue:
            continue
        nom, valeur = nue.split("=", 1)
        trouvees.append((nom.strip(), valeur.strip()))
    return trouvees


def partagees():
    """{(nom_var, bot)} pour toute cle portee par deux bots ou plus.

    Compare des empreintes en memoire — aucune valeur n'est conservee ni affichee.
    """
    import hashlib
    par_valeur = defaultdict(list)
    for bot in BOTS:
        texte = lire_env(RACINE / bot)
        if texte is None:
            continue
        for nom, valeur in variables(texte):
            if valeur and nom not in NON_SECRETES:
                empreinte = hashlib.sha256(valeur.encode()).hexdigest()
                par_valeur[(nom, empreinte)].append(bot)
    return {(nom, bot) for (nom, _), bots in par_valeur.items()
            if len(bots) > 1 for bot in bots}


def ouvrir(selection=None):
    conflits = partagees()
    for bot in (selection or BOTS):
        dossier = RACINE / bot
        clair = dossier / ".env"
        if clair.exists():
            print(f"[{bot}] .env en clair deja present — laisse tel quel "
                  f"(--sceller pour le refermer)")
            continue

        texte = lire_chiffre(dossier)
        if texte is None:
            print(f"[{bot}] (!) .env.encrypted ou .master_key manquant — ignore")
            continue

        existantes = dict(variables(texte))
        lignes, retirees = [], []
        for nom, valeur in variables(texte):
            raison = MORTES.get(bot, {}).get(nom)
            if raison:
                retirees.append((nom, raison))
                continue
            # ⚠️ Le marqueur va sur la ligne du DESSUS, jamais en fin de ligne :
            # secure_env fait `nom, valeur = ligne.split("=", 1)` sans retirer les
            # commentaires. Un « # ... » apres la valeur finirait DANS la cle.
            if (nom, bot) in conflits:
                lignes.append("# (!) PARTAGEE avec un autre bot "
                              "— remplacez la ligne suivante par une cle NEUVE")
            lignes.append(f"{nom}={valeur}")

        manquantes = [n for n in SOCLE if n not in existantes]

        corps = ENTETE.format(bot=bot, date=time.strftime("%Y-%m-%d %H:%M"))
        if retirees:
            corps += "\n# RETIRE a l'ouverture (conserve dans les sauvegardes .bak_*) :\n"
            corps += "".join(f"#   {nom} — {raison}\n" for nom, raison in retirees)
        corps += "\n" + "\n".join(lignes) + "\n"
        if manquantes:
            corps += ("\n# ---- A REMPLIR (emplacements lus par ce bot, vides aujourd'hui) ----\n"
                      "# Un emplacement laisse vide est simplement ignore.\n")
            corps += "".join(f"{nom}=\n" for nom in manquantes)

        clair.write_text(corps, encoding="utf-8")
        detail = []
        if retirees:
            detail.append(f"{len(retirees)} morte(s) retiree(s)")
        if manquantes:
            detail.append("a remplir : " + ", ".join(manquantes))
        if any((n, bot) in conflits for n in existantes):
            detail.append("(!) porte une cle PARTAGEE")
        print(f"[{bot}] .env ouvert" + (" — " + " ; ".join(detail) if detail else ""))

    print("\nSaisissez les valeurs, puis : python tools/preparer_env.py --sceller")


def sceller(selection=None):
    """Rechiffre, RELIT le chiffre et le compare avant d'effacer le clair.

    Sans cette relecture, une erreur de chiffrement laisserait un .env.encrypted
    illisible et le clair supprime : les cles seraient perdues pour de bon.
    """
    for bot in (selection or BOTS):
        dossier = RACINE / bot
        clair = dossier / ".env"
        if not clair.exists():
            continue

        f = fernet_du_bot(dossier)
        if f is None:
            print(f"[{bot}] (!) .master_key manquante — NON scelle, le clair reste en place")
            continue

        donnees = clair.read_bytes()
        chiffre = dossier / ".env.encrypted"
        if chiffre.exists():
            sauvegarde = dossier / f".env.encrypted.bak_{int(time.time())}"
            shutil.copy2(chiffre, sauvegarde)

        chiffre.write_bytes(f.encrypt(donnees))
        if f.decrypt(chiffre.read_bytes()) != donnees:
            print(f"[{bot}] (!) relecture DIFFERENTE — le clair est conserve, rien n'est efface")
            continue

        clair.unlink()
        n = len([1 for _, v in variables(donnees.decode("utf-8")) if v])
        print(f"[{bot}] scelle ({n} variables renseignees), .env en clair efface")


def etat(selection=None):
    conflits = partagees()
    for bot in (selection or BOTS):
        dossier = RACINE / bot
        clair = dossier / ".env"
        texte = lire_env(dossier)
        if texte is None:
            print(f"{bot:<12} (!) illisible")
            continue
        vars_ = variables(texte)
        vides = [n for n, v in vars_ if not v]
        partage = [n for n, _ in vars_ if (n, bot) in conflits]
        manque = [n for n in SOCLE if n not in dict(vars_) or not dict(vars_)[n]]
        etiquette = "EN CLAIR" if clair.exists() else "chiffre "
        print(f"{bot:<12} {etiquette}  {len(vars_)} variables"
              + (f" | vides : {', '.join(vides)}" if vides else "")
              + (f" | (!) PARTAGEE : {', '.join(partage)}" if partage else "")
              + (f" | (!) SOCLE ABSENT : {', '.join(manque)}" if manque else ""))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--etat", action="store_true", help="qui a quoi (noms seulement)")
    g.add_argument("--ouvrir", action="store_true", help="dechiffre et prepare la saisie")
    g.add_argument("--sceller", action="store_true", help="rechiffre, verifie, efface le clair")
    p.add_argument("--bot", help="ne traiter que ce bot (les autres restent chiffres)")
    a = p.parse_args()
    if a.bot:
        correspond = [b for b in BOTS if b.lower() == a.bot.lower()]
        if not correspond:
            p.error(f"bot inconnu : {a.bot} (connus : {', '.join(BOTS)})")
        # `partagees()` compare TOUJOURS les 6 : restreindre la comparaison ferait
        # disparaitre le partage qu'on cherche justement a voir.
        BOTS_A_TRAITER = correspond
    else:
        BOTS_A_TRAITER = list(BOTS)
    if a.etat:
        etat(BOTS_A_TRAITER)
    elif a.ouvrir:
        ouvrir(BOTS_A_TRAITER)
    else:
        sceller(BOTS_A_TRAITER)
