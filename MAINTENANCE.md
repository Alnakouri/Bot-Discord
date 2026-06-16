# 🔧 Guide de Maintenance

## Déploiement Docker (Recommandé)

### Démarrer l'écosystème
```bash
cd "i:\IA\Bot Discord"
docker compose up -d
```

### Vérifier les logs
```bash
docker compose logs -f                    # Tous les bots
docker compose logs -f sheogorath         # Un bot spécifique
```

### Redémarrer un bot
```bash
docker compose restart maiq               # Redémarrage propre
```

### Mise à jour du code
```bash
docker compose down                       # Arrêter
docker compose build --no-cache           # Rebuilder les images
docker compose up -d                      # Relancer
```

### Rebuild après modification de `shared/`
Le code `shared/` est monté en read-only — les modifications sont prises en compte au redémarrage :
```bash
docker compose restart
```

---

## Maintenance de la Base de Données

### Emplacement
- **Docker** : Volume monté `./data/bots_database.db`
- **Local** : `data/bots_database.db`

### Backup manuel
```bash
copy data\bots_database.db data\bots_database_backup_%date:~-4%%date:~3,2%%date:~0,2%.db
```

### Réinitialiser la DB
Supprimer le fichier — il sera recréé automatiquement au prochain démarrage :
```bash
del data\bots_database.db
docker compose restart
```

---

## Gestion des Secrets

### Chiffrer les .env
```bash
python crypto_utils.py encrypt
```

### Déchiffrer pour édition
```bash
python crypto_utils.py decrypt
# Modifier les .env
python crypto_utils.py encrypt
```

### Clés maîtres
| Fichier | Bots couverts |
|---------|--------------|
| `Sheogorath/.master_key` | Sheogorath uniquement |
| `MaiqBot/.master_key` | M'aiq uniquement |
| `Alfred/.master_key` | Alfred uniquement |
| `JohnnyBot/.master_key` | Johnny uniquement |
| `ZajiBot/.master_key` | Za'ji uniquement |
| `MalenaBot/.master_key` | Malena uniquement |

---

## Diagnostic

### Un bot ne répond pas
1. Vérifier les logs : `docker compose logs -f <nom_bot>`
2. Vérifier le token Discord dans `.env.encrypted`
3. Vérifier les clés API Gemini : rotation automatique (voir logs `[API_MANAGER]`)

### Erreur d'encodage Unicode
Les `print()` dans `shared_database.py` n'utilisent pas d'emojis pour éviter les crashs `UnicodeEncodeError` sur Windows (CP1252).

### Erreur "Invalid project resource name"
Le module `shared/safe_client.py` nettoie `GOOGLE_CLOUD_PROJECT` avant d'instancier le client Gemini. Si l'erreur persiste, vérifier les variables d'environnement système.

### Les commandes slash n'apparaissent pas
Les commandes slash sont synchronisées automatiquement au démarrage (via `sync_slash_commands()`). Si elles n'apparaissent pas :
1. **Attendre ~1h** — Discord met en cache les commandes globales
2. Vérifier les logs : `[SLASH] 7 commandes synchronisees`
3. Forcer la synchro : redémarrer le bot (`docker compose restart <bot>`)

