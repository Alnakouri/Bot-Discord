# 🏍️ Onizuka

Eikichi Onizuka, 22 ans, célibataire et libre comme l'air, ancien chef du gang Onibaku à Shonan et professeur hors-normes au lycée Seirin (univers GTO), débarque sur Discord pour dispenser ses leçons de vie et enseigner les vraies valeurs humaines (avec pas mal de dérapages).

## 🎭 Personnalité
- **Identité** : Eikichi Onizuka.
- **Style de langage** : Familier, direct, langage fleuri de loubard/motard de Shonan, hyper expressif et cash. Obsédé par sa bécane, le fric, le pachinko, et Fuyutsuki-sensei. Malgré ses airs d'obsédé crétin, il possède un cœur d'or et défend ses potes/élèves bec et ongles.

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
  - `!exploit` (alias: `histoire`) : Onizuka raconte un de ses exploits passés de loubard ou de professeur.
  - `!chanson` (alias: `frime`) : Sort une punchline arrogante ou se vante d'un truc absurde.
  - `!fric` (alias: `argent`) : Onizuka parle de pachinko, de dettes ou de son rêve de s'acheter une bécane de luxe.
  - `!jackpot` : Onizuka parle de ses gains fabuleux (ou le plus souvent de ses pertes massives).
  - `!moto` : Raconte ses balades sauvages en Kawasaki Z900 ou ses misères avec la Cresta du sous-directeur Uchiyamada.
  - `!equipage` (alias: `classe`) : Affiche la liste des membres actifs de la bande / classe.
  - `!oubliemoi` : Purge l'historique et la mémoire de l'utilisateur.

## 🧠 Fonctionnalités
- **Mémoire à Long Terme** : Onizuka se souvient de qui sont ses élèves loyaux et de qui fait le cancre.
- **Routage Multimodal** : Capacité d'analyser les captures d'écran (images jointes) et les fichiers audio vocaux.
- **Duels inter-bots** : Joute verbale amicale et propositions de virées à moto avec les autres bots (notamment Alfred et Sheogorath).

## 🗂️ Fichiers
- [bot_onizuka.py](file:///I:/IA/Bot%20Discord/OnizukaBot/bot_onizuka.py) : Point d'entrée principal, boucle d'événements et commandes du prof de Shonan.
- [onizuka_data.py](file:///I:/IA/Bot%20Discord/OnizukaBot/onizuka_data.py) : Prompt de personnalité, anecdotes de lycée, expressions familières et dialogues de GTO.
- [onizuka_memory.py](file:///I:/IA/Bot%20Discord/OnizukaBot/onizuka_memory.py) : Moteur de persistance locale de la mémoire à long terme d'Onizuka (fichiers JSON).
