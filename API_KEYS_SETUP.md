# 🔑 Configuration des Clés API

> [!IMPORTANT]
> **RÈGLE D'OR : INDÉPENDANCE TOTALE**
> Il est FORMELLEMENT INTERDIT de supprimer l'indépendance des bots au niveau de leurs clés API. Chaque bot DOIT conserver son propre système de gestion, ses propres fichiers `.env` et ses propres clés. La mutualisation des clés est bannie pour garantir la résilience et l'isolation.

## 🧠 Stratégie de Routage (Expertise par Modèle)

Chaque bot utilise l'IA la plus performante dans son domaine de spécialité :
- **Humour & Répartie** : Priorité à **Grok (xAI)**. Idéal pour le chaos, le sarcasme et la personnalité.
- **Raisonnement & Logique** : Priorité à **Gemini 2.5 Pro**. Utilisé pour les tâches complexes, le codage et les explications détaillées.
- **Vision & Audio** : Priorité à **Gemini 2.5 Flash**. Rapide et efficace pour l'analyse multimédia.
- **Réponse Rapide & Fallback** : **Llama 3.3 (Groq)** ou **Mistral**.

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
