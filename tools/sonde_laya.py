# -*- coding: utf-8 -*-
r"""Sonde : Laya sait-il prendre les decisions que nos regex prennent aujourd'hui ?

Laya (convaiinnovations/laya, Apache 2.0) est un modele de decision « System One » :
il ne genere pas de texte, il rend une reponse TYPEE avec des probabilites calibrees,
en un seul passage. Aucune cle, aucun reseau une fois les poids telecharges.

    py -3 -m venv %TEMP%\venv_laya
    %TEMP%\venv_laya\Scripts\python -m pip install --index-url https://download.pytorch.org/whl/cpu "torch>=2.5"
    %TEMP%\venv_laya\Scripts\python -m pip install laya "transformers>=4.48"
    %TEMP%\venv_laya\Scripts\python tools/sonde_laya.py

⚠️ VENV SANS `--system-site-packages`, ET C'EST OBLIGATOIRE. `transformers` 5.x exige
torch >= 2.5 quand le global est en 2.2.2, et le `torchvision` global compile pour
l'ancien torch fait echouer l'import (« operator torchvision::nms does not exist »),
ce qui se traduit plus loin par un « Could not import module ModernBertModel »
incomprehensible. Un venv herite = deux heures perdues.

⚠️ NE PAS l'installer dans l'environnement principal : `chatterbox-server` et
`faster_whisper` tournent sur le torch 2.2.2 global. Les six bots Discord, eux,
n'importent ni torch ni transformers — verifie.

⚠️ CE QUE CETTE SONDE NE PROUVE PAS. Elle porte sur 24 cas que J'AI ECRITS. Un jeu
d'essai ecrit par celui qui interprete le resultat penche toujours du meme cote
([[gotcha-test-qui-retape-la-logique]]). Les chiffres ci-dessous sont des INDICATIONS ;
le corpus reel viendra du journal des decisions, pas d'ici.

RESULTATS DU 2026-09-20 (checkpoint multilingue, CPU, chargement 37 s une fois) :

    1. TON (classify_tone)        7/10   mediane 104 ms
    2. INTENTION (Alfred)         8/8    mediane 105 ms
    3. PERTINENCE (noul)          3/6    mediane 110 ms

⚠️ LA CONFIANCE N'EST PAS UN GARDE-FOU ICI. Elle ne suit pas la justesse : 0.91 sur une
erreur (« quelqu'un sait a quelle heure commence le stream ? » -> aggro), 0.15 sur une
reussite. L'usage evident — « n'agir que si conf > 0.7 » — est donc ferme.

⚠️ Le `noul` (oui/non) rend une probabilite et dit NON a presque tout : inutilisable
tel quel pour « ce message merite-t-il une reponse ».
"""
import time

import laya

MODELE, REVISION = laya.DEFAULT_MODELS["multilingual"]

# ── 1. Le ton d'un message adresse a Sugar ────────────────────────────────────
Q_TON = {
    "ton": {
        "type": "choice",
        "instructions": "Quel est le ton du message adresse au bot ?",
        "criteria": {
            "aggro": "insulte, mepris, rejet, ordre de se taire, moquerie blessante",
            "apology": "la personne s'excuse ou reconnait un tort",
            "kind": "compliment, remerciement, salutation chaleureuse, affection",
            "neutral": "message banal, question ordinaire, ni agressif ni affectueux",
        },
    }
}
CAS_TON = [
    ("t'es vraiment nulle comme bot", "aggro"),
    ("desole mais t'es nulle", "aggro"),          # la regex dit apology : cas documente
    ("desole pour tout a l'heure, j'ai ete con", "apology"),
    ("merci Sugar t'es la meilleure <3", "kind"),
    ("coucou, ca va ?", "kind"),
    ("il fait quel temps chez toi ?", "neutral"),
    ("ferme-la un peu", "aggro"),
    ("je t'adore meme quand tu dis n'importe quoi", "kind"),
    ("c'est pas contre toi mais la t'abuses", "aggro"),
    ("quelqu'un sait a quelle heure commence le stream ?", "neutral"),
]

# ── 2. Ce qu'on demande a Alfred quand on l'interpelle ────────────────────────
Q_INTENT = {
    "intention": {
        "type": "choice",
        "instructions": "Que demande-t-on au majordome dans ce message ?",
        "criteria": {
            "repos": "lui demander de quitter le salon vocal, d'arreter de surveiller, de se mettre en repos",
            "nettoyage": "lui demander d'effacer ou de nettoyer des messages du salon",
            "question": "lui poser une question ou lui demander un renseignement",
            "bavardage": "lui parler sans rien lui demander de precis",
        },
    }
}
CAS_INTENT = [
    ("Alfred, tu peux partir du vocal", "repos"),
    ("Alfred repos", "repos"),
    ("Alfred arrete de parler la", "bavardage"),   # la regex declenche `repos` : faux positif
    ("Alfred, nettoie les messages des bots", "nettoyage"),
    ("Alfred c'est quoi le meilleur the ?", "question"),
    ("Alfred tu sais que t'es le seul bot supportable ici", "bavardage"),
    ("arrete de me suivre en vocal Alfred", "repos"),
    ("Alfred supprime tout ca s'il te plait", "nettoyage"),
]

# ── 3. Le message appelle-t-il une intervention spontanee ? ───────────────────
Q_PERTINENCE = {
    "intervenir": {
        "type": "noul",
        "instructions": ("Ce message de salon appelle-t-il une remarque spontanee d'un bot "
                         "de personnage ? Reponds oui s'il y a matiere a rebondir (opinion, "
                         "provocation, sujet vivant), non si c'est une conversation privee "
                         "entre humains, un detail logistique ou un message technique."),
    }
}
CAS_PERTINENCE = [
    ("OK MERCI ALFRED", False),                    # is_shouting le prend pour du chaos
    ("PUTAIN CE JEU EST NUL", True),
    ("on se retrouve a 21h alors ?", False),
    ("franchement les gens qui jouent healer sont des laches", True),
    ("j'ai push le commit, ca build", False),
    ("qui veut faire un raid ce soir", True),
]


def main():
    t0 = time.perf_counter()
    agent = laya.agent.load(MODELE, subfolder=REVISION, device="cpu")
    t_charge = time.perf_counter() - t0
    print(f"chargement du modele : {t_charge:.1f} s  ({MODELE} / {REVISION}, CPU)\n")

    for titre, questions, cas, cle in [
        ("1. TON (classify_tone, SugarBot)", Q_TON, CAS_TON, "ton"),
        ("2. INTENTION (Alfred, declenche une ACTION)", Q_INTENT, CAS_INTENT, "intention"),
        ("3. PERTINENCE (intervention spontanee)", Q_PERTINENCE, CAS_PERTINENCE, "intervenir"),
    ]:
        print("=" * 78)
        print(titre)
        print("=" * 78)
        bons, latences = 0, []
        for texte, attendu in cas:
            t = time.perf_counter()
            out = agent.system_one(texte, questions)
            latences.append((time.perf_counter() - t) * 1000)
            # ⚠️ `answers[q]` est un DICT, pas une chaine : {type, <type>: valeur,
            # probabilities, confidence}. Ma premiere version lisait le dict entier et
            # rendait 0/24 — un score de zero, plus bas que le hasard, accuse la SONDE
            # avant d'accuser le modele.
            brut = out["answers"][cle]
            rep = brut[brut["type"]] if isinstance(brut, dict) else brut
            conf = brut.get("confidence") if isinstance(brut, dict) else None
            ok = (rep == attendu) if not isinstance(attendu, bool) else (
                bool(rep) is attendu if isinstance(rep, bool)
                else str(rep).lower() in ("true", "yes", "oui", "1")) is attendu
            bons += ok
            marque = "OK  " if ok else "FAUX"
            c = f" conf {conf:.2f}" if isinstance(conf, float) else ""
            print(f"  {marque} attendu={str(attendu):10s} rendu={str(rep):10s}{c}  « {texte[:52]} »")
        lat = sorted(latences)
        print(f"\n  -> {bons}/{len(cas)} corrects   latence mediane {lat[len(lat)//2]:.0f} ms "
              f"(min {lat[0]:.0f}, max {lat[-1]:.0f})\n")


if __name__ == "__main__":
    main()
