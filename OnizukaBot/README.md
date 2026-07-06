# 🏍️ Onizuka

Bot Onizuka neutre, personnalité vidée, en attente d'une nouvelle personnalité.

## 🎭 Personnalité
- **Identité** : Onizuka.
- **Style de langage** : Aucun style défini (ardoise neutre).

## ⚙️ Configuration
1. Copier [OnizukaBot/.env.example](file:///I:/IA/Bot%20Discord/OnizukaBot/.env.example) → `.env` et renseigner les clés lues par [bot_onizuka.py](file:///I:/IA/Bot%20Discord/OnizukaBot/bot_onizuka.py) :
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
  python bot_onizuka.py
  ```
- **Docker** : Lancer le service `onizuka` du compose global.

## 🎮 Commandes
- **Slash partagées** : Voir [COMMANDES.md](file:///I:/IA/Bot%20Discord/COMMANDES.md) (ne pas dupliquer).
- **Commandes spécifiques** (préfixe `!`) :
  - `!exploit` (alias: `histoire`) : Raconte un exploit d'Onizuka.
  - `!chanson` (alias: `frime`) : Sort une phrase d'Onizuka.
  - `!fric` (alias: `argent`) : Parle de sa passion.
  - `!jackpot` : Parle de jackpots.
  - `!moto` : Parle de moto.
  - `!equipage` (alias: `classe`) : Affiche le classement de la classe.
  - `!oubliemoi` : Purge l'historique et la mémoire de l'utilisateur.

## 🧠 Fonctionnalités
- **Mémoire à Long Terme** : Onizuka se souvient de ses interactions.
- **Routage Multimodal** : Capacité d'analyser les captures d'écran (images jointes) et les fichiers audio vocaux.
- **Duels inter-bots** : Joute verbale amicale avec les autres bots.

## 🗂️ Fichiers
- [bot_onizuka.py](file:///I:/IA/Bot%20Discord/OnizukaBot/bot_onizuka.py) : Point d'entrée principal.
- [onizuka_data.py](file:///I:/IA/Bot%20Discord/OnizukaBot/onizuka_data.py) : Données et prompt neutres.
- [onizuka_memory.py](file:///I:/IA/Bot%20Discord/OnizukaBot/onizuka_memory.py) : Moteur de persistance locale de la mémoire à long terme (fichiers JSON).
