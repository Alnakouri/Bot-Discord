# 🛠️ Scripts Utilitaires

## Scripts Actifs

| Script | Fonction | Usage |
|--------|----------|-------|
| `crypto_utils.py` | Chiffrer/déchiffrer les `.env` | `python crypto_utils.py encrypt` |
| `start_all_bots.bat` | Lancer tous les bots en local (sans Docker) | Double-clic |
| `test_bot.bat` | Lancer un bot au choix (menu interactif) | Double-clic |

## Docker (Recommandé)

```bash
docker compose up -d          # Démarrer tous les bots
docker compose logs -f        # Suivre les logs
docker compose down           # Arrêter
docker compose restart maiq   # Redémarrer un bot
docker compose build          # Rebuilder après modif
```

## Workflow de Développement

```bash
# 1. Modifier le code dans shared/ ou dans un bot
# 2. Tester localement
python Alfred/bot_alfred.py

# 3. Vérifier les imports
python -c "from shared.shared_database import get_connection; print('OK')"

# 4. Déployer via Docker
docker compose build && docker compose up -d
```
