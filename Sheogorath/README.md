# 🧀 Sheogorath

Le Prince Daedra de la Folie (univers The Elder Scrolls) transposé sur Discord pour semer le chaos, distribuer du fromage et punir les mortels insolents.

## 🎭 Personnalité
- **Identité** : Sheogorath, Seigneur Souverain des Îles Trémensides.
- **Style de langage** : Excentrique, imprévisible, passant brusquement de l'amabilité chaleureuse à la menace de mort théâtrale. Obsédé par le fromage, les papillons et les quêtes absurdes.
- **Humeurs (Moods)** : Mania (joyeux, coloré, absurde) ↔ Dementia (sombre, suspicieux, colérique).

## ⚙️ Configuration
1. Copier [Sheogorath/.env.example](file:///I:/IA/Bot%20Discord/Sheogorath/.env.example) → `.env` et renseigner les clés lues par [bot_sheogorath.py](file:///I:/IA/Bot%20Discord/Sheogorath/bot_sheogorath.py) :
   - `DISCORD_TOKEN`
   - `GEMINI_KEY_1`, `GEMINI_KEY_2`, `GEMINI_KEY_3`
   - `MISTRAL_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY` (fallbacks)
2. Chiffrer la configuration :
   ```bash
   python crypto_utils.py encrypt
   ```

## 🚀 Lancement
- **Solo** :
  ```bash
  python bot_sheogorath.py
  ```
- **Docker** : Lancer le service `sheogorath` du compose global.

## 🎮 Commandes
- **Slash partagées** : Voir [COMMANDES.md](file:///I:/IA/Bot%20Discord/COMMANDES.md) (ne pas dupliquer).
- **Commandes spécifiques** (préfixe `!`) :
  - `!quete` : Donne une tâche absurde ou une quête daedrique délirante.
  - `!fromage` : Lance le mini-jeu du fromage mystique (récompenses ou punitions de réputation).
  - `!wabbajack [cible]` : Déclenche manuellement le Wabbajack sur une cible pour modifier son surnom ou lui attribuer un rôle ridicule.
  - `!decret [cible]` : Proclame un décret absurde (génère une image de parchemin signée).
  - `!imposteur <cible> [instruction]` : usurpe l'identité d'un utilisateur Discord par Webhook (Identity Theft).
  - `!solution` : Permet de donner la solution d'une énigme active.
  - `!join` : Demande à Sheogorath de rejoindre le salon vocal.
  - `!leave` : Fait partir Sheogorath du salon vocal.
  - `!speak [texte]` : Demande à Sheogorath de lire à haute voix un texte dans le salon vocal.
  - `!oubliemoi` : Purge l'historique et la mémoire de l'utilisateur.

## 🧠 Fonctionnalités
- **Agent Autonome (Outils)** : Décide seul de lancer le Wabbajack, de modifier la réputation d'un joueur, ou d'activer une usurpation d'identité en réponse aux messages des utilisateurs.
- **Humeurs Dynamiques** : Altération périodique de son tempérament (Mania / Dementia) influençant son vocabulaire.
- **Système Vocal (Parqué)** : Support vocal de Philippe Bozo (clonage vocal Chatterbox) désactivé par défaut (mode dégradé textuel).
- **Persistance des sanctions** : Les métamorphoses et surnoms temporaires durent 10 minutes et survivent au reboot.

## 🗂️ Fichiers
- [bot_sheogorath.py](file:///I:/IA/Bot%20Discord/Sheogorath/bot_sheogorath.py) : Point d'entrée principal, boucle d'événements et dispatch des outils daedriques.
- [sheo_voice.py](file:///I:/IA/Bot%20Discord/Sheogorath/sheo_voice.py) : Pipeline de synthèse vocale Piper / Chatterbox.
- [sheo_data.py](file:///I:/IA/Bot%20Discord/Sheogorath/sheo_data.py) : Base de données textuelle de la personnalité, invites systèmes, quêtes et répliques.
- [sheo_memory.py](file:///I:/IA/Bot%20Discord/Sheogorath/sheo_memory.py) : Logique de mémoire à long terme (Faits / Conversations).
- [sheo_punishments.py](file:///I:/IA/Bot%20Discord/Sheogorath/sheo_punishments.py) : Gestionnaire des sanctions Wabbajack et restauration au boot.
- [sheo_llm.py](file:///I:/IA/Bot%20Discord/Sheogorath/sheo_llm.py) : Post-processing de la mise en forme du texte généré par l'IA.
- [sheo_mentions.py](file:///I:/IA/Bot%20Discord/Sheogorath/sheo_mentions.py) : Traducteur d'identifiants textuels en mentions Discord cliquables.
- [sheo_faveur.py](file:///I:/IA/Bot%20Discord/Sheogorath/sheo_faveur.py) : Calculateur et gestionnaire des gains et pertes de Faveur du Prince.
- [sheo_imposter.py](file:///I:/IA/Bot%20Discord/Sheogorath/sheo_imposter.py) : Logique d'usurpation d'identité via les Webhooks Discord.
- [sheo_decrees.py](file:///I:/IA/Bot%20Discord/Sheogorath/sheo_decrees.py) : Module de génération d'images de parchemins de décrets.
- [minigames.py](file:///I:/IA/Bot%20Discord/Sheogorath/minigames.py) : Implémentation du mini-jeu `!fromage`.
- [backup_manager.py](file:///I:/IA/Bot%20Discord/Sheogorath/backup_manager.py) : Gère la sauvegarde automatisée de la base de données.
