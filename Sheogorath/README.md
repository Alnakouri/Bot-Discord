# 🧀 Sheogorath Bot

Le Prince Daedra de la Folie pour Discord.

## 🎭 Personnalité
- **Identité** : Sheogorath, Seigneur des Îles Trémensides
- **Style** : Chaotique, menaçant, obsédé par le fromage
- **Moods** : Mania (joyeux/créatif) ↔ Dementia (sombre/cruel)

## ⚙️ Configuration
1. Copier `.env.example` → `.env`
2. Remplir les clés API :
   - `DISCORD_TOKEN` (obligatoire)
   - `GEMINI_KEY_1/2/3` (au moins une)
   - `GROQ_API_KEY`, `OPENROUTER_API_KEY` (fallbacks)

## 🚀 Lancement
```bash
pip install -r requirements.txt
python bot_sheogorath.py
```

## 🎮 Commandes
| Commande | Description |
|----------|-------------|
| `!quete` | Donne une quête absurde |
| `!wabbajack @user` | (Legacy) Préférer l'usage IA |

## 🪄 Intelligence Agentique (Outils)
Sheogorath est un **Agent Cognitif**. Il décide de lui-même d'utiliser ses pouvoirs via des outils Gemini :
- **wabbajack** : Transforme un utilisateur selon l'humeur du Prince.
- **set_mood** : Change de personnalité (Mania/Dementia) selon le contexte.
- **mod_reputation** : Récompense ou punit les mortels avec des points de faveur.
- **start_identity_theft** : Vole le visage d'un utilisateur pour semer le chaos (Webhook).

## 🧠 Fonctionnalités
- **Persistance des Punitions** : Les Wabbajacks durent 10 minutes et survivent au redémarrage du bot.
- **Anti-répétition** : Mémoire de 10 réponses pour éviter les cycles.
- **Réponses contextuelles** : Analyse multimodale (images et audio vocal).
- **Duels** : Clash automatique avec M'aiq (probabilité 50%).
