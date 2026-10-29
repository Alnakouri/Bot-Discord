# 🎸 Johnny Silverbot

Le rockerboy anarchiste et légendaire de Night City (univers Cyberpunk 2077) transposé sur Discord pour prêcher la révolution anti-corpo, siffler du whisky et provoquer les mortels.

## 🎭 Personnalité
- **Identité** : Johnny Silverhand.
- **Style de langage** : Vulgaire, cynique, direct, rebelle. Utilise des expressions typiques de Night City ("choom", "eddies", "chrome"). Haine viscérale des corporations (Arasaka, Militech) et mépris pour l'autorité.

## ⚙️ Configuration
1. Copier [JohnnyBot/.env.example](.env.example) → `.env` et renseigner les clés lues par [bot_johnny.py](bot_johnny.py) :
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
  python bot_johnny.py
  ```
- **Docker** : Lancer le service `johnny` du compose global.

## 🎮 Commandes
- **Slash partagées** : Voir [COMMANDES.md](../docs/COMMANDES.md) (ne pas dupliquer).
- **Commandes spécifiques** (préfixe `!`) :
  - `!gig` (aliases: `job`, `mission`, `run`, `contrat`) : Johnny raconte un de ses braquages ou concerts mythiques.
  - `!loot` (aliases: `gift`, `chrome`, `eddies`) : Johnny offre un objet de pacotille ou une pièce de cyberware de la rue.
  - `!nightcity` (aliases: `samurai`, `anti-corpo`) : Johnny exprime son dégoût pour le système de Night City et ses corporations.
  - `!whisky` (aliases: `clope`, `drink`) : Consomme un verre de whisky Centurion ou allume une clope.
  - `!rant` (aliases: `corpo`, `systeme`) : Lance une diatribe virulente contre les mégacorporations et le capitalisme sauvage.
  - `!legends` (aliases: `leaderboard`) : Affiche le classement de réputation locale adapté au style mercenaire de l'Afterlife.
  - `!oubliemoi` : Purge l'historique et la mémoire de l'utilisateur.

## 🧠 Fonctionnalités
- **Mémoire à Long Terme** : Johnny se souvient des actions passées des utilisateurs qu'il apprécie ou méprise.
- **Routage Intelligent** : Analyse les messages multimédias (vision des images attachées et décodage de messages vocaux).
- **Duels inter-bots** : Cible particulièrement Alfred Pennyworth, qu'il considère comme le majordome corpo par excellence.
- **Statistiques** : Enregistre le nombre total de verres bus, de cadeaux distribués et de missions de mercenaires réussies.

## 🗂️ Fichiers
- [bot_johnny.py](bot_johnny.py) : Point d'entrée principal, boucle d'événements et gestion des interactions.
- [johnny_data.py](johnny_data.py) : Contient les traits de caractère, répliques types, anecdotes de concerts et de braquages.
- [johnny_memory.py](johnny_memory.py) : Gestionnaire local de la base de mémoire à long terme de Johnny (fichiers JSON).
