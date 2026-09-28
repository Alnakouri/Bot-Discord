# 🤵 Alfred

Majordome dévoué de la famille Wayne (univers Batman) transposé sur Discord pour servir et modérer avec flegme et cynisme.

## 🎭 Personnalité
- **Identité** : Alfred Pennyworth.
- **Style de langage** : Très formel, flegme britannique, poli mais extrêmement sarcastique. N'utilise jamais le pronom "je" directement, préférant la troisième personne ("votre humble serviteur", "le soussigné") ou des tournures passives ("Il est à noter que...").

## ⚙️ Configuration
1. Copier [Alfred/.env.example](.env.example) → `.env` et renseigner les clés lues par [bot_alfred.py](bot_alfred.py) :
   - `DISCORD_TOKEN`
   - `GEMINI_KEY_1`, `GEMINI_KEY_2`, `GEMINI_KEY_3`, `GEMINI_KEY_4`
   - `MISTRAL_API_KEY` (fournisseur prioritaire pour Alfred)
   - `GROQ_API_KEY`
   - `OPENROUTER_API_KEY`
2. Chiffrer la configuration :
   ```bash
   python crypto_utils.py encrypt
   ```

## 🚀 Lancement
- **Solo** :
  ```bash
  python bot_alfred.py
  ```
- **Docker** : Lancer le service `alfred` du compose global.

## 🎮 Commandes
- **Slash partagées** : Voir [COMMANDES.md](../COMMANDES.md) (ne pas dupliquer). Alfred n'en garde que `/ping`, `/stats` et `/help`, et n'a pas de mini-jeux.
- **Commandes spécifiques** (préfixe `!`) :
  - `!servir <action>` : Demande à Alfred de servir quelque chose (ex: café, thé, remontrances).
  - `!surveille` : Met en place une patrouille vocale (Alfred surveille les salons vocaux actifs).
  - `!repos` : Fait quitter à Alfred le salon vocal actuel.
  - `!liberation [membre]` : Lève toutes les sanctions de modération (rôles/surnoms) d'un utilisateur.
  - `!nettoyage [limit]` : Nettoie les messages envoyés par les bots Discord (limite par défaut : 100).
  - `!oubliemoi` : Purge l'historique et la mémoire de l'utilisateur.

## 🧠 Fonctionnalités
- **Mémoire à Long Terme** : Alfred retient les faits notables sur les utilisateurs et les stocke de façon permanente.
- **Vocal Multimodal** : Synthèse vocale réaliste via ElevenLabs (TTS) et transcription audio via Gemini (STT).
- **Modération Agentique (Tools)** : Capacité de bannir temporairement, muter, renommer ou attribuer des rôles via Function Calling s'il détecte des comportements inappropriés sur le serveur.
- **Duels inter-bots** : Capacité à entrer en joute verbale avec Johnny Silverbot ou Sheogorath s'ils l'importunent.

## 🗂️ Fichiers
- [bot_alfred.py](bot_alfred.py) : Point d'entrée principal, boucle d'événements Discord et exécution des outils de modération.
- [alfred_data.py](alfred_data.py) : Définitions de la personnalité, invites systèmes, répliques types, surnoms et configurations.
- [alfred_memory.py](alfred_memory.py) : Moteur de gestion de mémoire à long terme locale (fichiers JSON) et synthèse des faits.
