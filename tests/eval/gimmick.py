import re
from collections import Counter

from shared.llm_cascade import _est_degenere

# Liste de stopwords français courants pour filtrer les mots non significatifs
STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "ce", "cet", "cette", "ces",
    "mon", "ton", "son", "ma", "ta", "sa", "mes", "tes", "ses", "nos", "vos", "leurs",
    "je", "tu", "il", "elle", "on", "nous", "vous", "ils", "elles", "lui", "leur", "eux",
    "me", "te", "se", "y", "en", "le", "la", "les", "moi", "toi", "soi",
    "qui", "que", "quoi", "dont", "où", "quel", "quels", "quelle", "quelles",
    "du", "au", "aux", "de", "à", "en", "dans", "par", "pour", "avec", "sans", "sous", "sur", "chez",
    "et", "ou", "mais", "donc", "car", "ni", "si", "or", "soit",
    "est", "sont", "était", "étaient", "suis", "es", "sommes", "êtes", "avez", "ont", "a", "as",
    "fait", "faire", "fais", "faites", "font", "peux", "peut", "pouvez", "peuvent",
    "plus", "moins", "très", "tout", "tous", "toute", "toutes", "bien", "mal", "comme", "alors",
    "dans", "quelque", "quelques", "chose", "autre", "autres", "aussi", "encore", "ici", "là",
    "mais", "donc", "sinon", "dans", "avec", "pour", "plus", "tout", "cette", "comme", "sans"
}

def detect_gimmick(responses: list[str]) -> tuple[bool, str]:
    """
    Détecte de manière déterministe si un mot significatif (de 4 lettres ou plus) 
    est répété d'une réponse à l'autre ou trop de fois au sein d'une même réponse.
    Retourne (detected, detail).
    """
    if not responses:
        return False, ""

    # ⚠️ La dégénérescence d'abord, et sous son propre nom. Le 2026-09-16, Malena a rendu
    # « Oh là là là là… » x201 et ce détecteur a répondu **False** : il ne retient que les
    # mots de 4 lettres ou plus, et « là » en fait deux. Le scénario est donc sorti noté 0
    # sans qu'une seule ligne ne dise que la réponse était CASSÉE, pas mauvaise.
    # Un tic de style et une panne de génération ne se soignent pas pareil.
    for resp in responses:
        if _est_degenere(resp):
            return True, "Réponse DÉGÉNÉRÉE (boucle de répétition), pas un tic de style"

    word_sets = []
    all_words_flat = []
    
    for resp in responses:
        # Nettoyage simple : minuscules et suppression de la ponctuation
        cleaned = resp.lower()
        cleaned = re.sub(r'[^\w\s]', ' ', cleaned)
        words = cleaned.split()
        
        # Conservation des mots significatifs de 4 lettres ou plus
        filtered_words = [w for w in words if len(w) >= 4 and w not in STOPWORDS]
        word_sets.append(set(filtered_words))
        all_words_flat.extend(filtered_words)
        
    # Cas 1 : Multi-tours (plusieurs réponses dans le même scénario)
    if len(responses) > 1:
        # Compter dans combien de réponses différentes apparaît chaque mot
        word_response_counts = {}
        for w_set in word_sets:
            for w in w_set:
                word_response_counts[w] = word_response_counts.get(w, 0) + 1
                
        # Trouver les mots apparaissant dans au moins 2 réponses distinctes
        repeated_across = [w for w, count in word_response_counts.items() if count >= 2]
        if repeated_across:
            # Trier par le nombre total d'apparitions dans tout le transcript
            repeated_across.sort(key=lambda x: all_words_flat.count(x), reverse=True)
            return True, f"Répétition mot: '{repeated_across[0]}'"
            
    # Cas 2 : Répétition interne (au sein d'une seule et même réponse)
    for resp in responses:
        cleaned = resp.lower()
        cleaned = re.sub(r'[^\w\s]', ' ', cleaned)
        words = [w for w in cleaned.split() if len(w) >= 4 and w not in STOPWORDS]
        counts = Counter(words)
        
        # Si un mot significatif apparaît 3 fois ou plus dans le même tour
        for w, count in counts.items():
            if count >= 3:
                return True, f"Répétition interne mot: '{w}' ({count} fois)"
                
    return False, ""
