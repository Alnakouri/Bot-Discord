# 🍬 Sugar Bot

Bot Discord à la personnalité **douce comme du sucre… mais qui pique quand on la cherche**.

## 🎭 Personnalité
- **Identité** : Sugar Bot, présence chaleureuse, pétillante et taquine (en français).
- **Style** : adorable par défaut (compliments, énergie positive, vocabulaire sucré), mais avec du répondant — répartie fine et sans vulgarité quand on la provoque. Son insulte signature : « **péteur / péteuse** ».
- **Touche Serpentard** : elle se revendique de la maison Serpentard (univers Harry Potter) et glisse des clins d'œil au canon (Salazar, Choixpeau, Basilic, Rogue, Malefoy…).
- **Adaptation au ton** : douce avec les gentils, mordante avec les malpolis, et **rassurante** avec ceux qui vont mal (elle range ses griffes).
- **Carnet de rancunes** : elle tient un compte implicite (0→5) par personne — glaciale envers qui l'a blessée, radoucie à mesure qu'on se rachète, jusqu'au pardon explicite. Voir [sugar_grudge.py](file:///I:/IA/Bot%20Discord/SugarBot/sugar_grudge.py).

## ⚙️ Configuration
1. Copier [SugarBot/.env.example](file:///I:/IA/Bot%20Discord/SugarBot/.env.example) → `.env` et renseigner les clés lues par [bot_sugar.py](file:///I:/IA/Bot%20Discord/SugarBot/bot_sugar.py) :
   - `DISCORD_TOKEN`
   - `GEMINI_KEY_1`, `GEMINI_KEY_2`, `GEMINI_KEY_3`, `GEMINI_KEY_4`
   - `GROQ_API_KEY`, `MISTRAL_API_KEY`, `OPENROUTER_API_KEY`
   - *(optionnel)* `ENABLE_GRUDGE_LLM`, `ENABLE_DAILY_BIO`, `ENABLE_DAILY_STATUS` (`0` pour désactiver)
2. Chiffrer la configuration :
   ```bash
   python crypto_utils.py encrypt
   ```

## 🚀 Lancement
- **Solo** :
  ```bash
  python bot_sugar.py
  ```
- **Docker** : lancer le service `sugar` du compose global.

## 🎮 Commandes
- **Slash partagées** : voir [COMMANDES.md](file:///I:/IA/Bot%20Discord/COMMANDES.md) (ne pas dupliquer).
- **Commandes spécifiques** (préfixe `!`) :
  - `!exploit` (alias : `histoire`, `legende`) : raconte un exploit de Sugar.
  - `!chanson` (alias : `frime`, `chante`) : sort une punchline de Sugar.
  - `!equipage` (alias : `crew`, `classe`) : affiche le classement de réputation.
  - `!oubliemoi` : purge la mémoire (faits + journalière) de l'utilisateur.

## 🧠 Fonctionnalités
- **Mémoire à long terme** : Sugar retient des faits durables par utilisateur (cloisonnés), avec pertinence lexicale et éviction.
- **Mémoire journalière** : « lecture du jour » qui ajuste son ton avec un habitué (1×/jour).
- **Carnet de rancunes** : rancune/rédemption implicite par personne (raffinement LLM optionnel en tâche de fond).
- **Routage multimodal** : analyse des images jointes et des messages vocaux.
- **Bio & statut Discord** : régénérés quotidiennement depuis sa personnalité.
- **Silence total entre bots** : Sugar ne répond jamais à un autre bot et ne les inclut pas dans son contexte.

## 🗂️ Fichiers
- [bot_sugar.py](file:///I:/IA/Bot%20Discord/SugarBot/bot_sugar.py) : point d'entrée principal.
- [sugar_data.py](file:///I:/IA/Bot%20Discord/SugarBot/sugar_data.py) : prompt de personnalité et répliques.
- [sugar_memory.py](file:///I:/IA/Bot%20Discord/SugarBot/sugar_memory.py) : mémoire long terme + journalière (JSON local).
- [sugar_grudge.py](file:///I:/IA/Bot%20Discord/SugarBot/sugar_grudge.py) : carnet de rancunes.
- [games_persona.py](file:///I:/IA/Bot%20Discord/SugarBot/games_persona.py) : voix de Sugar dans les mini-jeux.
