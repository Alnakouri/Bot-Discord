# 🐱 M'aiq le Menteur Bot

Le Khajiit vagabond légendaire pour Discord.

## 🎭 Personnalité
- **Identité** : M'aiq le Menteur, Khajiit vagabond
- **Style** : Évasif, cryptique, fatigué
- **Particularité** : Ne dit jamais "je", toujours "M'aiq"

## ⚙️ Configuration
1. Copier `.env.example` → `.env`
2. Remplir les clés API :
   - `DISCORD_TOKEN` (obligatoire)
   - `GEMINI_KEY_1/2/3` (au moins une)
   - `GROQ_API_KEY` (prioritaire pour M'aiq)

## 🚀 Lancement
```bash
pip install -r requirements.txt
python bot_maiq.py
```

## 🎮 Commandes
| Commande | Description |
|----------|-------------|
| `!rumeur` | Lance une rumeur absurde |
| `!maiq` | Affiche les stats de M'aiq |

## 🎲 Easter Eggs
- Réagis avec 📏 sur un message de M'aiq → Il vole ta pince !
- Réagis avec 🐴 → Il mange ton cheval
- Réagis avec 🌕 → Skooma time

## 🧩 Intelligence Agentique (Outils)
M'aiq peut désormais utiliser des outils pour interagir avec le monde :
- **start_custom_riddle** : M'aiq invente une énigme unique et le système la suit automatiquement.
- **set_lie_density** : L'IA ajuste son niveau de mensonge (0-100%).

## 🧠 Fonctionnalités
- **Énigmes Dynamiques** : Les énigmes de M'aiq sont suivies en base de données pour permettre la résolution via `!reponse`.
- **Anti-répétition** : Mémoire de 10 réponses pour un dialogue varié.
- **Réponses contextuelles** : Analyse les images (vision) et l'audio.
- **Esquive** : Système de répliques calmes face aux insultes.
- **Duels** : Interaction automatique avec Sheogorath.
