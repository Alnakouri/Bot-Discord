# 🔑 Configuration des Clés API

> [!IMPORTANT]
> **RÈGLE D'OR : INDÉPENDANCE TOTALE**
> Il est FORMELLEMENT INTERDIT de supprimer l'indépendance des bots au niveau de leurs clés API. Chaque bot DOIT conserver son propre système de gestion, ses propres fichiers `.env` et ses propres clés. La mutualisation des clés est bannie pour garantir la résilience et l'isolation.

## 🧠 Stratégie de Routage

> [!IMPORTANT]
> Les identifiants de modèles ne se recopient PAS ici. La source unique est
> [`shared/models.py`](shared/models.py) ; ce document décrit seulement **quels
> fournisseurs** il faut provisionner en clés. Un identifiant dupliqué dans la doc finit
> périmé sans que personne ne s'en aperçoive — c'était le cas de ce paragraphe.

Quatre fournisseurs sont sollicités, et chaque cascade en **mélange plusieurs** :
leurs quotas étant indépendants, si l'un limite, l'échelon suivant répond quand même.

| Fournisseur | Sert à | Clé requise |
|---|---|---|
| **Google Gemini** | Vision et audio (seul à les traiter), plus du texte | `GEMINI_KEY_1`, `GEMINI_KEY_2`… |
| **Mistral** | Texte — le français le plus sûr | `MISTRAL_API_KEY` |
| **Groq** | Texte — le plus rapide | `GROQ_API_KEY` |
| **OpenRouter** | Dernier recours uniquement | `OPENROUTER_API_KEY` |

> [!WARNING]
> Le **free-tier OpenRouter** a été mesuré inutilisable (12 échecs sur 12 : quotas
> dépassés en rafale, 60 à 120 s de latence, raisonnement recopié dans la réponse).
> Aucune cascade n'en dépend aujourd'hui ; la clé ne sert que si l'on y revient un jour.

## Variables d'Environnement (Indépendantes par Bot)

**IMPORTANT** : Chaque bot possède son propre fichier `.env` (chiffré en `.env.encrypted`). 
Il est vivement conseillé de configurer des clés d'IA (Gemini, Groq, etc.) **différentes** et propres à chaque bot afin de répartir les quotas de requêtes.

### Clés IA (Indépendantes dans chaque `.env`)
```env
# Clés utilisées uniquement par ce bot précis
GEMINI_KEY_1=AIzaSy...
GEMINI_KEY_2=AIzaSy...
GEMINI_KEY_3=AIzaSy...
GEMINI_KEY_4=AIzaSy...
GROQ_API_KEY=gsk_...
MISTRAL_API_KEY=...
OPENROUTER_API_KEY=sk-or-v1-...
```

### Clés spécifiques
```env
# Sécurité Discord
DISCORD_TOKEN=...

# Alfred uniquement
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=ErXwobaYiN019PkySvjV
```

## Chiffrement / Déchiffrement

```bash
python crypto_utils.py encrypt   # .env → .env.encrypted (supprime le .env)
python crypto_utils.py decrypt   # .env.encrypted → .env
python crypto_utils.py generate  # Nouvelle clé maître
```

## Rotation des Clés (Gestion Indépendante)

Le module `shared/api_manager.py` gère la rotation automatique des clés :
- Bien que le module de gestion soit partagé ("shared"), **chaque bot exécute sa propre instance du root de gestion** au démarrage.
- **Isolation Totale** : La rotation, les délais (cooldowns) liés aux erreurs 429/503 et le basculement vers de nouveaux modèles de secours se font indépendamment pour chaque bot sans jamais affecter le pool de clés des autres bots !
- **Mécanique** : 4 clés Gemini en pool par bot, cooldown dynamique sur échec, et fallback automatique vers Groq → Mistral → OpenRouter.
