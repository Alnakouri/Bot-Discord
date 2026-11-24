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

> ⚠️ `restart` garde l'IMAGE d'origine. Le code est monté, pas les paquets : un code qui
> importe une dépendance ajoutée depuis le dernier build plante au démarrage et tourne en
> boucle. Mesure du 2026-11-24 : quatre bots en `ModuleNotFoundError: PIL` sur des images
> de juin. Dès que `requirements.txt` a bougé : `docker compose up -d --build`.

### Dépendances figées
`requirements.txt` est la liste voulue, écrite à la main. `requirements.lock` fige les
versions exactes qu'elle a données ; l'image (`Dockerfile`) et la CI installent le lock, donc
la CI teste exactement les versions de la production. Les images de base sont figées au
correctif près (`python:3.11.18-slim`), et `laya-server/Dockerfile` fige chaque paquet
(`laya==0.3.4` : les 0.4 et 0.5 n'ont plus `laya.agent`).

Pour mettre à jour (nouvelle dépendance, correctif de sécurité) :
```bash
# 1. modifier requirements.txt, puis regénérer le lock dans la MÊME image de base :
docker run --rm -v "$PWD/requirements.txt:/r.txt:ro" python:3.11.18-slim \
  sh -c "pip install -q -r /r.txt && pip freeze" > requirements.lock
# 2. remettre l'en-tête du fichier, pousser, attendre la CI verte, puis :
docker compose up -d --build
```
`tests/test_dependances_figees.py` refuse une dépendance de `requirements.txt` absente du lock.

### Sonde de santé
`tools/sonde_sante.py` vérifie toutes les heures que chaque service de `docker-compose.yml`
tourne sans boucler, que la dernière sauvegarde a moins de 26 h, et que chaque lien
`!discord` du dashboard est vivant (et n'expire pas dans les 7 jours). Le bilan va dans
`data/sante.json`, affiché par le bandeau d'alerte de l'accueil du dashboard ; un problème
NOUVEAU déclenche une notification Windows. Docker arrêté n'est pas signalé (AutoStart
coupé exprès).
```bash
python tools/sonde_sante.py --strict                       # à la main
powershell -File tools\installer_sonde_sante.ps1           # tâche planifiée \BotDiscord\Sonde sante
powershell -File tools\installer_sonde_sante.ps1 -Retirer  # la retirer
```

### Changer un lien `!discord`
L'adresse est relue à chaque `!discord` : la changer dans le dashboard suffit, sans
redémarrer. Ajouter ou retirer une commande, en revanche, demande toujours un redémarrage du
bot. Préférer une invitation **permanente** (« Expire après : Jamais »).

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
| `SugarBot/.master_key` | Sugar Bot uniquement |
| `MalenaBot/.master_key` | Malena uniquement |

---

## Diagnostic

### Un bot ne répond pas
0. `python tools/sonde_sante.py` : boucle de redémarrage, conteneur absent, sauvegarde arrêtée ?
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

