# 🐱 M'aiq

Le Khajiit vagabond légendaire (univers The Elder Scrolls) transposé sur Discord pour partager ses énigmes cryptiques, ses rumeurs absurdes et voler les pinces des utilisateurs.

## 🎭 Personnalité
- **Identité** : M'aiq le Menteur.
- **Style de langage** : Évasif, cryptique, fatigué de ses longs voyages. S'exprime exclusivement à la troisième personne ("M'aiq pense...", "M'aiq dit..."). Mélange de vérités évidentes et de mensonges absurdes.

## ⚙️ Configuration
1. Copier [MaiqBot/.env.example](.env.example) → `.env` et renseigner les clés lues par [bot_maiq.py](bot_maiq.py) :
   - `DISCORD_TOKEN`
   - `GEMINI_KEY_1`, `GEMINI_KEY_2`, `GEMINI_KEY_3`
   - `MISTRAL_API_KEY`, `GROQ_API_KEY` (fournisseur prioritaire pour M'aiq), `OPENROUTER_API_KEY`
2. Chiffrer la configuration :
   ```bash
   python crypto_utils.py encrypt
   ```

## 🚀 Lancement
- **Solo** :
  ```bash
  python bot_maiq.py
  ```
- **Docker** : Lancer le service `maiq` du compose global.

## 🎮 Commandes
- **Slash partagées** : Voir [COMMANDES.md](../COMMANDES.md) (ne pas dupliquer).
- **Commandes spécifiques** (préfixe `!`) :
  - `!maiq` (aliases: `profil`, `stats`) : Affiche les statistiques de M'aiq (pinces volées, état de fatigue).
  - `!rumeur` : Lance une rumeur ou un mensonge farfelu.
  - `!enigme` : Force M'aiq à poser une énigme (si aucune énigme n'est active dans le salon).
  - `!reponse <texte>` : Permet de soumettre une réponse à l'énigme active (alternative au Reply).
  - `!indice` : Demande un indice sur l'énigme en cours.
  - `!oubliemoi` : Purge l'historique et la mémoire de l'utilisateur.

## 🎲 Réactions de M'aiq (Easter Eggs)
M'aiq réagit de manière unique à certaines réactions ajoutées sur ses messages :
- 📏 (Pince) : M'aiq vole votre pince (Incrémente son compteur de pinces).
- 🐴 (Cheval) : M'aiq mange votre cheval.
- 🌕 (Lune) : Heure du skooma !

## 🧠 Fonctionnalités
- **Énigmes Persistantes** : Les énigmes de M'aiq sont suivies en base de données SQLite partagée. Les utilisateurs gagnent de la réputation en trouvant la bonne réponse.
- **Agent Cognitif (Outils)** : Décide de lui-même d'inventer et de lancer une énigme unique s'il sent que le salon s'ennuie.
- **Duels inter-bots** : Se chamaille fréquemment avec Sheogorath ou d'autres bots lorsqu'ils se mentionnent mutuellement.

## 🗂️ Fichiers
- [bot_maiq.py](bot_maiq.py) : Point d'entrée principal, boucle d'événements et gestion des énigmes.
- [maiq_data.py](maiq_data.py) : Personnalité de M'aiq, invites système et liste de rumeurs prédéfinies.
- [maiq_memory.py](maiq_memory.py) : Système de mémoire à long terme (Conversations / Profils utilisateurs).
- [minigames.py](minigames.py) : Logique de validation et de distribution des récompenses d'énigmes.
