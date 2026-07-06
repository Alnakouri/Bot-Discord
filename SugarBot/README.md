# 🍬 Sugar Bot

Bot Sugar Bot neutre, personnalité vidée, en attente d'une nouvelle personnalité.

## 🎭 Personnalité
- **Identité** : Sugar Bot.
- **Style de langage** : Aucun style défini (ardoise neutre).

## ⚙️ Configuration
1. Copier [SugarBot/.env.example](file:///I:/IA/Bot%20Discord/SugarBot/.env.example) → `.env` et renseigner les clés lues par [bot_sugar.py](file:///I:/IA/Bot%20Discord/SugarBot/bot_sugar.py) :
   - `DISCORD_TOKEN`
   - `GEMINI_KEY_1`, `GEMINI_KEY_2`, `GEMINI_KEY_3`, `GEMINI_KEY_4`
   - `GROQ_API_KEY`, `MISTRAL_API_KEY`, `OPENROUTER_API_KEY`
2. Chiffrer la configuration :
   ```bash
   python crypto_utils.py encrypt
   ```

## 🚀 Lancement
- **Solo** :
  ```bash
  python bot_sugar.py
  ```
- **Docker** : Lancer le service `sugar` du compose global.

## 🎮 Commandes
- **Slash partagées** : Voir [COMMANDES.md](file:///I:/IA/Bot%20Discord/COMMANDES.md) (ne pas dupliquer).
- **Commandes spécifiques** (préfixe `!`) :
  - `!exploit` (alias: `histoire`) : Raconte un exploit de Sugar Bot.
  - `!chanson` (alias: `frime`) : Sort une phrase de Sugar Bot.
  - `!fric` (alias: `argent`) : Parle de sa passion.
  - `!jackpot` : Parle de jackpots.
  - `!moto` : Parle de moto.
  - `!equipage` (alias: `classe`) : Affiche le classement de la classe.
  - `!oubliemoi` : Purge l'historique et la mémoire de l'utilisateur.

## 🧠 Fonctionnalités
- **Mémoire à Long Terme** : Sugar Bot se souvient de ses interactions.
- **Routage Multimodal** : Capacité d'analyser les captures d'écran (images jointes) et les fichiers audio vocaux.
- **Duels inter-bots** : Joute verbale amicale avec les autres bots.

## 🗂️ Fichiers
- [bot_sugar.py](file:///I:/IA/Bot%20Discord/SugarBot/bot_sugar.py) : Point d'entrée principal.
- [sugar_data.py](file:///I:/IA/Bot%20Discord/SugarBot/sugar_data.py) : Données et prompt neutres.
- [sugar_memory.py](file:///I:/IA/Bot%20Discord/SugarBot/sugar_memory.py) : Moteur de persistance locale de la mémoire à long terme (fichiers JSON).
