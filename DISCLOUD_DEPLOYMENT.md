# ⚠️ Discloud Deployment (ARCHIVÉ)

> [!WARNING]
> **Ce guide est archivé.** Le déploiement se fait désormais via **Docker** en local.
> Voir `README.md` et `MAINTENANCE.md` pour les instructions actuelles.

---

## Commandes Docker (remplacement)

```bash
# Démarrer tous les bots
docker compose up -d

# Voir les logs
docker compose logs -f

# Arrêter
docker compose down
```

---

*Ancien contenu Discloud conservé ci-dessous pour référence historique.*

## Ancienne procédure Discloud

1. Créer les ZIPs avec `create_discloud_zips.py` (supprimé)
2. Uploader sur discloud.app
3. Configurer les variables d'environnement
4. Démarrer les bots

### RAM nécessaire (référence)
| Bot | RAM min |
|-----|---------|
| Sheogorath | 512MB |
| M'aiq | 512MB |
| Alfred | 768MB (vocal) |
| Johnny | 256MB |
| Onizuka | 256MB |
| Malena | 256MB |
