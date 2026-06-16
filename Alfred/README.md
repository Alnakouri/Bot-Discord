# 🦇 Alfred Pennyworth Bot

Le majordome cynique de la famille Wayne pour Discord.

## 🎭 Personnalité
- **Identité** : Alfred Pennyworth (Version TAS 1989)
- **Style** : Britannique, sarcastique, flegmatique
- **Particularité** : N'utilise jamais "je" directement

## ⚙️ Configuration
1. Copier `.env.example` → `.env`
2. Remplir les clés API :
   - `DISCORD_TOKEN` (obligatoire)
   - `GEMINI_KEY_1/2/3` (au moins une)
   - `MISTRAL_API_KEY` (prioritaire pour Alfred)
   - `ELEVENLABS_API_KEY` + `ELEVENLABS_VOICE_ID` (vocal)

## 🚀 Lancement
```bash
pip install -r requirements.txt
python bot_alfred.py
```

## 🎮 Commandes
| Commande | Description |
|----------|-------------|
| `!servir` | Alfred sert le thé |
| `!ecoute` | Alfred rejoint le vocal et écoute |
| `!nettoyer` | Nettoie les messages bots |

## 👔 Intelligence Agentique (Outils)
Alfred peut désormais gérer le manoir (système) par le dialogue :
- **set_maintenance** : Alfred peut activer ou désactiver le mode maintenance global.
- **get_user_stats** : Alfred consulte les archives pour connaître le rang et la réputation d'un invité.

## 🧠 Fonctionnalités
- **Anti-répétition** : Mémoire de 10 réponses pour un service toujours impeccable.
- **Réponses contextuelles** : Analyse vision (médias) et audio vocal.
- **Sarcasme Glacial** : Répliques automatiques face à l'impolitesse.
- **Mémoire** : Persistance des interactions via la base de donnée partagée.
- **Vocal** : Capacité de réponse vocale (ElevenLabs/STT) via les commandes `!ecoute`.
