# 🐱 M'aiq

Le Khajiit vagabond légendaire (univers The Elder Scrolls) transposé sur Discord pour partager ses mensonges absurdes et voler les pinces des utilisateurs.

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
  - `!oubliemoi` : Purge l'historique et la mémoire de l'utilisateur.

## 🎲 Réactions de M'aiq (Easter Eggs)
M'aiq réagit de manière unique à certaines réactions ajoutées sur ses messages :
- 📏 (Pince) : M'aiq vole votre pince (Incrémente son compteur de pinces).
- 🐴 (Cheval) : M'aiq mange votre cheval.
- 🌕 (Lune) : Heure du skooma !

## 🧠 Fonctionnalités
- **Duels inter-bots** : Se chamaille fréquemment avec Sheogorath ou d'autres bots lorsqu'ils se mentionnent mutuellement.

## 🗂️ Fichiers
- [bot_maiq.py](bot_maiq.py) : Point d'entrée principal et boucle d'événements.
- [maiq_data.py](maiq_data.py) : Personnalité de M'aiq et invites système.
- [maiq_memory.py](maiq_memory.py) : Système de mémoire à long terme (Conversations / Profils utilisateurs).
