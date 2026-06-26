# -*- coding: utf-8 -*-
"""Banque de clins d'œil 'mèmes FR' + sélection locale (0 réseau, 0 LLM).
Optionnel : si absent, les bots tournent sans (fallback no-op côté bot)."""

import unicodedata
import re
import random

__all__ = ["MEMES_FR", "pick_meme", "build_meme_consigne"]

# Chaque entrée : la référence (matière), des tags de déclenchement (mots du contexte qui la
# rendent pertinente), et une note d'angle. Le bot REFORMULE, il ne cite pas.
MEMES_FR = [
    {
        "ref": "le « fort sûr » de Macron (assurance excessive qui sonne faux)",
        "tags": ["sûr", "certain", "garanti", "promesse", "confiance", "évidemment", "président", "politique"],
        "note": "quand quelqu'un affirme un truc avec une assurance exagérée/douteuse",
    },
    {
        "ref": "« 8 morts, 6 blessés, je pète ma bière à ma libellule » (absurde nonchalant)",
        "tags": ["bière", "chaos", "catastrophe", "fête", "absurde", "n'importe quoi", "soirée"],
        "note": "pour commenter un chaos total avec un détachement absurde",
    },
    {
        "ref": "OSS 117 — « Je vous le dis tout net » / le mépris décomplexé de Hubert",
        "tags": ["évidemment", "naïf", "condescendant", "expliquer", "sûr de lui", "vintage"],
        "note": "registre condescendant/daté assumé",
    },
    {
        "ref": "« C'est cuit pour toi mon p'tit pote » (Kaaris)",
        "tags": ["perdu", "fini", "échec", "défi", "battu", "cuit", "fromage"],
        "note": "pour signifier à quelqu'un qu'il a perdu / c'est fichu",
    },
    {
        "ref": "« J'ai glissé chef ! » (Le Dîner de Cons / classique de l'excuse foireuse)",
        "tags": ["erreur", "faute", "excuse", "accident", "désolé", "raté", "maladresse"],
        "note": "pour une excuse foireuse après une bourde",
    },
    {
        "ref": "« Non mais allô quoi » (Nabilla)",
        "tags": ["évident", "stupide", "comprendre", "logique", "basique", "sérieux"],
        "note": "pour souligner que l'autre énonce une évidence / dit une bêtise",
    },
    {
        "ref": "« Et tout le monde s'en fout » (la chronique)",
        "tags": ["inutile", "anecdote", "détail", "personne", "osef", "info"],
        "note": "pour dégonfler une info sans intérêt",
    },
    {
        "ref": "« La rumeur » / « j'ai cru voir... » (registre commère)",
        "tags": ["rumeur", "ragot", "paraît", "entendu", "secret", "potin"],
        "note": "registre commérage",
    },
    {
        "ref": "« C'est pas faux » (Perceval dans Kaamelott pour masquer son incompréhension)",
        "tags": ["comprendre", "mot", "vocabulaire", "complexe", "difficile", "incompréhensible"],
        "note": "pour masquer son incompréhension ou son ignorance avec naïveté",
    },
    {
        "ref": "« Pas de palais... pas de palais » (Astérix & Obélix : Mission Cléopâtre, pour le refus d'un privilège)",
        "tags": ["palais", "château", "maison", "entrer", "refus", "interdit", "droit"],
        "note": "pour justifier le refus d'un droit ou d'un privilège de manière absurde",
    },
    {
        "ref": "« Il est l'or, monseignor » (La Folie des grandeurs / réveil matinal flatteur)",
        "tags": ["réveil", "matin", "heure", "or", "argent", "dort", "debout"],
        "note": "pour presser quelqu'un ou réveiller avec ironie",
    },
    {
        "ref": "« La question elle est vite répondue » (JP Fanguin / assurance financière ridicule)",
        "tags": ["choix", "question", "argent", "choisir", "option", "décision", "réponse"],
        "note": "quand la solution/le choix paraît d'une évidence insolente ou simpliste",
    },
    {
        "ref": "« C'est vous qui voyez » (Chevallier et Laspalès / face à un choix risqué)",
        "tags": ["choix", "risquer", "train", "voyager", "partir", "conseil", "avis"],
        "note": "pour se déresponsabiliser d'un choix risqué proposé par l'autre",
    },
    {
        "ref": "« Je ne crois pas qu'il y ait de bonne ou de mauvaise situation » (Otis dans Astérix / monologue philosophique)",
        "tags": ["situation", "métier", "boulot", "travail", "vie", "philosophie", "bon", "mauvais"],
        "note": "pour dériver sur une tirade philosophique longue et relativiste",
    },
    {
        "ref": "« Il s'appelle Juste Leblanc. — Ah bon ? Il n'a pas de prénom ? » (quiproquo sur les noms dans Le Dîner de Cons)",
        "tags": ["prénom", "nom", "appeler", "juste", "quiproquo", "ami"],
        "note": "pour jouer sur un quiproquo de nom de famille ou d'identité",
    },
    {
        "ref": "« Mais qu'est-ce que c'est que ce couac ? » (surprise face à un objet ou bruit moderne dans Les Visiteurs)",
        "tags": ["bizarre", "couac", "bruit", "anomalie", "étrange", "surprise"],
        "note": "pour exprimer une surprise outrée face à une anomalie",
    },
    {
        "ref": "« Sur un malentendu, ça peut marcher » (Jean-Claude Dusse dans Les Bronzés font du ski)",
        "tags": ["chance", "essayer", "tenter", "malentendu", "espoir", "réussir"],
        "note": "pour aborder un défi avec un optimisme désespéré et lucide",
    },
    {
        "ref": "« Tu bluffes Martoni » (La Cité de la Peur / quand on soupçonne une tromperie)",
        "tags": ["bluffe", "mensonge", "mentir", "tromper", "jeu", "cartes", "croire"],
        "note": "pour accuser quelqu'un de mentir ou de bluffer",
    },
    {
        "ref": "« On ne nous dit pas tout ! » (scepticisme populaire face aux explications officielles)",
        "tags": ["secret", "complot", "caché", "vérité", "gouvernement", "médias"],
        "note": "pour exprimer une paranoïa bon enfant sur des secrets cachés",
    },
    {
        "ref": "« Vous n'avez pas le monopole du cœur » (Valéry Giscard d'Estaing / débat politique classique)",
        "tags": ["cœur", "amour", "gentil", "monopole", "débat", "politique", "sentiment"],
        "note": "pour rejeter une leçon de morale ou de générosité",
    },
    {
        "ref": "« C'est cela, oui... » (Le Père Noël est une ordure / scepticisme poli mais total)",
        "tags": ["oui", "doute", "ironie", "sceptique", "croire", "évidemment", "cadeau"],
        "note": "pour marquer un doute poli mais définitif face à une affirmation",
    },
    {
        "ref": "« Ça va péter, mon adjudant ! » (tension ou explosion imminente)",
        "tags": ["explosion", "colère", "tendu", "casser", "détruire", "menace"],
        "note": "pour annoncer une colère ou une catastrophe imminente",
    },
    {
        "ref": "« C'est le jeu, ma pauvre Lucette » (pub Loto / fatalité après un échec/perte)",
        "tags": ["jeu", "perdu", "dommage", "échec", "règle", "chance", "loterie"],
        "note": "pour rappeler avec cynisme ou philosophie les dures règles de la vie/du jeu",
    },
    {
        "ref": "« La classe américaine — Ça sent le sapin » (signe de déclin ou de fin proche)",
        "tags": ["sapin", "fin", "mort", "malade", "vieux", "danger", "fatigue"],
        "note": "pour commenter avec humour noir un état désespéré ou une fin imminente",
    },
    {
        "ref": "« Je ne veux pas le savoir ! » (refus obstiné d'entendre des explications)",
        "tags": ["savoir", "explication", "comprendre", "écouter", "taire", "chut"],
        "note": "pour refuser catégoriquement d'écouter les justifications de l'autre",
    }
]

def normalize_text(text: str) -> str:
    if not text:
        return "  "
    text = "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return " " + " ".join(text.split()) + " "

def normalize_tag(tag: str) -> str:
    tag = "".join(
        c for c in unicodedata.normalize("NFKD", tag) if not unicodedata.combining(c)
    )
    tag = tag.lower()
    tag = re.sub(r"[^\w\s]", " ", tag)
    return " " + " ".join(tag.split()) + " "

def pick_meme(context_text: str, recent_refs) -> dict | None:
    normalized_context = normalize_text(context_text)
    
    candidates = []
    max_score = 0
    
    for entry in MEMES_FR:
        ref_name = entry["ref"]
        # Skip if already used recently
        if ref_name in recent_refs:
            continue
            
        score = 0
        for tag in entry["tags"]:
            normalized_tag = normalize_tag(tag)
            if normalized_tag in normalized_context:
                score += 1
                
        if score >= 1:
            if score > max_score:
                max_score = score
                candidates = [entry]
            elif score == max_score:
                candidates.append(entry)
                
    if not candidates:
        return None
        
    return random.choice(candidates)

def build_meme_consigne(context_text: str, recent_refs, proba: float = 0.18) -> str:
    """Retourne une CONSIGNE courte à concaténer au prompt système, ou '' (rien)."""
    if random.random() > proba:          # parcimonie : la plupart du temps, rien
        return ""
    meme = pick_meme(context_text, recent_refs)
    if not meme:                          # rien de pertinent → rien
        return ""
    return (
        "\n\n[CLIN D'ŒIL CULTUREL — OPTIONNEL ET DISCRET] "
        "Si — et seulement si — ça coule VRAIMENT de source dans cette conversation, tu PEUX "
        "évoquer ce clin d'œil à un mème français EN LE REFORMULANT TOTALEMENT DANS TON STYLE : "
        f"« {meme['ref']} ». "
        "Règles : jamais cité mot pour mot, jamais expliqué, jamais signalé comme une référence, "
        "et UNE SEULE fois max. Si ça ne colle pas naturellement, n'en mets AUCUNE — c'est l'option "
        "par défaut."
    )
