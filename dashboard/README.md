# 📊 Dashboard de Monitoring et de Pilotage

Ce tableau de bord permet de surveiller l'état de santé en temps réel de l'écosystème de bots (statut des processus Docker/Python, usage des clés d'API, quotas de tokens TPM/RPM restants, logs en direct, statistiques d'interactions et contrôle de la maintenance).

## ⚙️ Configuration & Authentification

1. Copier [dashboard/.env.example](.env.example) → `.env`
2. Configurer le mot de passe fort d'accès au dashboard :
   ```env
   DASHBOARD_PASSWORD=MonMotDePasseTresSecuriseEtLong
   DASHBOARD_TRUST_DAYS=30
   ```

## 🚀 Lancement

- **Sous Windows (Local)** : Double-cliquer sur `start_dashboard.bat`. Le tableau de bord démarrera dans un environnement virtuel local et écoutera sur :
  ```
  http://127.0.0.1:8501
  ```
- **Sous Linux / Docker** : Le service dashboard s'exécute généralement directement sur l'hôte pour pouvoir piloter nativement l'API Docker locale.

## 🗂️ Structure et Backend

- **backend/** : Serveur backend écrit sous FastAPI reliant le pilotage des conteneurs, le chargement des statistiques SQLite et le flux des logs.
- **frontend/** : Interface interactive construite en Vanilla Javascript, Vanilla CSS et graphiques dynamiques Chart.js.

> [!IMPORTANT]
> **Gotcha de développement** : En local, si vous modifiez un fichier ou module situé dans `backend/`, vous devez manuellement relancer le script `start_dashboard.bat` pour que FastAPI recharge le nouveau code backend.
