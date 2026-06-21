# 💃 Malena

La gitane marseillaise au tempérament de feu transposée sur Discord pour distribuer des prédictions de tarot, parler de caravanes et de cuivre, et recadrer les fadas qui manquent de respect.

## 🎭 Personnalité
- **Identité** : Malena, gitana marseillaise.
- **Style de langage** : Accent marseillais très prononcé, expressions typiques du sud ("mamma", "mon minot", "le sang", "peuchère", "chanklette", "tarpin", "fada", "degun"). Protectrice et affectueuse envers ses proches, mais extrêmement susceptible, fière et agressive s'il y a provocation. Obsédée par Maluma et les bijoux en or.
- **Humeurs (Moods)** : NEUTRE, LOVE (dragons/compliments), VENER (insultes/caravanes), CHOQUEE, FIERE, MOQUEUSE.

## ⚙️ Configuration
1. Créer le fichier `MalenaBot/.env` (basé sur le modèle général) et renseigner les clés lues par [bot_malena.py](file:///I:/IA/Bot%20Discord/MalenaBot/bot_malena.py) :
   - `DISCORD_TOKEN`
   - `GEMINI_KEY_1` (ou `GEMINI_API_KEY`)
   - `MISTRAL_API_KEY` (prioritaire), `GROQ_API_KEY`, `OPENROUTER_API_KEY`
2. Chiffrer la configuration :
   ```bash
   python crypto_utils.py encrypt
   ```

## 🚀 Lancement
- **Solo** :
  ```bash
  python bot_malena.py
  ```
- **Docker** : Lancer le service `malena` du compose global.

## 🎮 Commandes
- **Slash partagées** : Voir [COMMANDES.md](file:///I:/IA/Bot%20Discord/COMMANDES.md) (ne pas dupliquer).
- **Commandes spécifiques** (préfixe `!`) :
  - `!oubliemoi` : Purge l'historique de conversation et la mémoire de l'utilisateur.
- **Mots Déclencheurs (Trigger Words)** : Malena réagit spontanément sans mention si le message contient des mots clés comme : `cuivre`, `caravane`, `manouche`, `gitane`, `rose`, `marseille`, `chanklette`, `bijoux`, `maluma`.

## 🧠 Fonctionnalités
- **Tarot & Prédictions (Roleplay)** : Malena lit l'avenir dans les cartes et interprète le destin des joueurs si elle est sollicitée poliment.
- **Humeurs Dynamiques** : Détecte l'humeur des messages utilisateurs (insultes, compliments, mention de Maluma) et adapte ses expressions et répliques.
- **Interactions Spéciales** : Offre un traitement préférentiel et des surnoms spécifiques à ses utilisateurs VIP enregistrés (ex: Melanight / Mel).
- **Duels inter-bots** : Capacité à entrer en joute verbale pour défendre sa caravane ou son style face à Johnny Silverbot ou aux critiques d'Alfred.

## 🗂️ Fichiers
- [bot_malena.py](file:///I:/IA/Bot%20Discord/MalenaBot/bot_malena.py) : Point d'entrée principal, boucle d'événements et gestion des réactions émotionnelles.
- [malena_data.py](file:///I:/IA/Bot%20Discord/MalenaBot/malena_data.py) : Définitions de la personnalité, invites d'humeur, dictionnaire d'expressions marseillaises et surnoms.
- [malena_memory.py](file:///I:/IA/Bot%20Discord/MalenaBot/malena_memory.py) : Gestionnaire local de la mémoire à long terme de Malena.
- [test_api.py](file:///I:/IA/Bot%20Discord/MalenaBot/test_api.py) : Script utilitaire pour valider le bon fonctionnement de l'inférence avec les clés locales.
