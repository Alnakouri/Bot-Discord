# Guide de Déploiement sur Oracle Cloud Free Tier (ARM64) (ARCHIVÉ)

> [!WARNING]
> **Déploiement serveur PARKÉ** (Oracle abandonné, Hetzner annulé 2026-06-21). Ce document est conservé uniquement à titre de référence historique.

Ce guide décrit la procédure pas-à-pas pour déployer et faire tourner les 6 bots Discord et le dashboard 24/7 de manière sécurisée et robuste sur une instance **Oracle Cloud Always Free (Ampere A1)**.

---

## 🏗️ 1. Architecture cible & Décisions

- **Matériel** : Instance `VM.Standard.A1.Flex` (ARM64, jusqu'à 4 OCPU et 24 Go de RAM).
- **OS** : Ubuntu 22.04 LTS.
- **Images Docker** : Bâties directement sur l'instance cible (`docker compose build`) pour éviter les soucis de cross-compilation ou le besoin d'un registry.
- **Réseau & Sécurité** : 
  - Aucun port entrant ouvert sur internet excepté le port **22 (SSH)**.
  - Le dashboard FastAPI/uvicorn reste lié en local (`127.0.0.1:8501`) et est accédé via un **tunnel SSH**.
  - Pas de dépendances GPU (TTS local et vision locale sont désactivés/parkés).
- **Secrets** : Les fichiers `.master_key` ne sont pas versionnés. Ils sont copiés manuellement depuis la machine locale via SCP. Les fichiers `.env.encrypted` (chiffrés) sont déjà inclus dans le dépôt Git.

---

## 🚀 2. Runbook de Déploiement (Opérations Cloud)

> [!IMPORTANT]
> Avant de commencer, assurez-vous d'avoir commité et poussé tous vos changements locaux récents sur votre dépôt Git distant.

### Étape 2.1 : Créer l'instance sur Oracle Cloud
1. Connectez-vous à la console d'administration Oracle Cloud.
2. Allez dans **Compute** ➔ **Instances** ➔ **Create Instance**.
3. Configurez les options suivantes :
   - **Image** : `Ubuntu 22.04` (ou version LTS la plus récente disponible).
   - **Shape** : `VM.Standard.A1.Flex` (Ampere). Configurez par exemple **2 OCPU** et **12 Go de RAM** (Always Free).
   - **Networking** : Laissez la création d'un sous-réseau public par défaut.
   - **SSH Keys** : Ajoutez ou téléchargez votre clé SSH publique.
   - **Boot volume** : Conservez la taille par défaut (ou augmentez jusqu'à la limite gratuite de 200 Go).
4. Cliquez sur **Create** et patientez jusqu'à ce que l'instance soit active (`Running`).

### Étape 2.2 : Configurer le Pare-feu Oracle
Dans la liste de sécurité (**Security List**) du sous-réseau associé à votre instance :
- Vérifiez qu'il n'y a que le port **22/tcp (SSH)** d'ouvert en entrée (`Ingress`).
- Ne rajoutez aucun autre port (pas de 8501, pas de 80, pas de 443). L'accès se fera via tunnel.

### Étape 2.3 : Connexion SSH et initialisation
Connectez-vous à l'instance (remplacez `<IP_PUBLIQUE>` par l'adresse IP publique de votre VM) :
```bash
ssh ubuntu@<IP_PUBLIQUE>
```

### Étape 2.4 : Cloner le dépôt et préparer les secrets locaux
1. Clonez votre dépôt sur la VM :
   - Utilisez une clé de déploiement SSH (`deploy key`) ou un Token d'Accès Personnel (PAT) pour cloner le repo privé :
     ```bash
     git clone git@github.com:Alnakouri/Bot-Discord.git bots
     cd bots
     ```
2. Créez le fichier de configuration du Dashboard sur l'hôte en y définissant un mot de passe fort :
   ```bash
   mkdir -p dashboard
   cat <<EOF > dashboard/.env
   DASHBOARD_PASSWORD=MonMotDePasseTresSecuriseEtLong
   DASHBOARD_TRUST_DAYS=30
   EOF
   ```

### Étape 2.5 : Lancer le script d'amorçage
Exécutez le script d'amorçage fourni pour installer Docker Engine, Docker Compose et configurer les permissions des répertoires persistants :
```bash
bash deploy/setup_oracle.sh
```
Une fois le script terminé, **déconnectez-vous et reconnectez-vous** à votre session SSH pour appliquer le groupe d'utilisateurs `docker` :
```bash
exit
ssh ubuntu@<IP_PUBLIQUE>
cd bots
```

### Étape 2.6 : Transférer les clés de chiffrement (.master_key)
Depuis votre machine locale (sous Windows Git Bash ou Linux/macOS), exécutez le script d'aide pour copier toutes les clés maîtres nécessaires au déchiffrement des variables d'environnement des bots :
```bash
./deploy/transfer_secrets.sh ubuntu@<IP_PUBLIQUE> /home/ubuntu/bots
```
Ensuite, sur la VM distante, restreignez les permissions de ces fichiers sensibles :
```bash
chmod 600 */.master_key dashboard/.env
```

### Étape 2.7 : Builder et démarrer les conteneurs
Sur la VM Oracle, lancez la compilation des conteneurs (qui prendra un peu de temps la première fois car elle s'effectue sur l'ARM) et démarrez-les en tâche de fond :
```bash
docker compose build
docker compose up -d
```
Vérifiez l'état des services et examinez les logs de Sheogorath par exemple :
```bash
docker compose ps
docker compose logs -f sheogorath
```

### Étape 2.8 : Configurer et démarrer le service Dashboard (systemd)
Le dashboard s'exécute directement sur l'hôte de la VM Oracle pour pouvoir orchestrer Docker (via commandes système) et servir l'application FastAPI/uvicorn.

1. Créez un environnement virtuel Python pour le dashboard et installez ses dépendances :
   ```bash
   python3 -m venv .venv-dashboard
   .venv-dashboard/bin/pip install -r dashboard/backend/requirements.txt
   ```
2. Adaptez le fichier de service systemd :
   - Copiez le gabarit vers l'emplacement final :
     ```bash
     cp deploy/dashboard.service deploy/dashboard.service.local
     ```
   - Modifiez `deploy/dashboard.service.local` pour remplacer les placeholders par vos valeurs réelles :
     - Remplacer `__USER__` par `ubuntu`.
     - Remplacer `__REPO__` par `/home/ubuntu/bots`.
     *(Vous pouvez faire cela rapidement avec sed)* :
     ```bash
     sed -i 's/__USER__/ubuntu/g' deploy/dashboard.service.local
     sed -i 's|__REPO__|/home/ubuntu/bots|g' deploy/dashboard.service.local
     ```
3. Installez et lancez le service :
   ```bash
   sudo cp deploy/dashboard.service.local /etc/systemd/system/dashboard.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now dashboard.service
   ```
4. Vérifiez que le service tourne correctement :
   ```bash
   sudo systemctl status dashboard.service
   ```

### Étape 2.9 : Accéder au Dashboard
Depuis votre poste local, ouvrez un tunnel SSH temporaire pour rediriger le trafic du dashboard local :
```bash
ssh -L 8501:127.0.0.1:8501 ubuntu@<IP_PUBLIQUE>
```
Ouvrez ensuite votre navigateur internet local à l'adresse [http://localhost:8501](http://localhost:8501). Entrez le mot de passe défini à l'étape 2.4.

---

## 🛠️ 3. Dépannage & Résolution de problèmes (Troubleshooting)

### a) Erreur de compilation de dépendances (wheel aarch64 manquant)
Certaines bibliothèques Python peuvent ne pas avoir de roue précompilée (`wheel`) disponible pour l'architecture ARM64 (aarch64). Si le build Docker échoue sur une compilation C/C++ :
1. Modifiez le `Dockerfile` à la racine pour installer temporairement un compilateur GCC.
   Ajoutez `gcc g++` à la ligne `apt-get install` :
   ```dockerfile
   RUN apt-get update && apt-get install -y --no-install-recommends \
       ffmpeg \
       libsodium-dev \
       libffi-dev \
       gcc \
       g++ \
       && rm -rf /var/lib/apt/lists/*
   ```
2. Relancez `docker compose build`.
3. Une fois le build réussi, vous pouvez annuler cette modification locale dans le `Dockerfile` pour conserver une image propre si vous le souhaitez.

### b) Erreur d'écriture dans `data/` ou `logs/` (Permission Denied)
Contrairement aux environnements de développement (comme Windows avec Docker Desktop) où les volumes bind-mount se voient attribuer automatiquement des droits de lecture/écriture complets pour le conteneur, Linux conserve les permissions et l'UID de l'hôte.
Le conteneur tourne sous l'utilisateur `botuser` (UID `10001`). Si un bot crash au démarrage en indiquant qu'il ne peut pas écrire dans `/app/data` ou `/app/bot/logs` :
- Exécutez sur l'hôte :
  ```bash
  sudo chown -R 10001:10001 /home/ubuntu/bots/data /home/ubuntu/bots/logs
  ```

### c) Pare-feu `iptables` natif d'Oracle Linux / Ubuntu
Si à l'avenir vous décidez d'exposer un service web directement sur un port public (par exemple le port 80 ou 443 pour un serveur web de reverse proxy) et que la connexion échoue malgré la configuration de la Security List Oracle :
- Ubuntu chez Oracle intègre des règles de pare-feu `iptables` par défaut très strictes qui rejettent tout trafic entrant non initié.
- Pour ouvrir proprement un port (par exemple 443) :
  ```bash
  sudo iptables -I INPUT 6 -p tcp --dport 443 -j ACCEPT
  sudo netfilter-persistent save
  ```

### d) Le bot ne démarre pas sans message d'erreur clair
Si un conteneur bot s'arrête en boucle (`Restarting`) :
1. Affichez les logs spécifiques du bot :
   ```bash
   docker compose logs sheogorath
   ```
2. Si vous lisez une erreur liée à l'impossibilité de déchiffrer les variables d'environnement, assurez-vous que :
   - Le fichier `.master_key` est bien présent dans le répertoire de ce bot (ex: `/home/ubuntu/bots/Sheogorath/.master_key`).
   - Le fichier `.master_key` a le bon contenu (copié sans retour chariot additionnel ou altération).
   - Les permissions sur la clé maître sont bien restreintes (`chmod 600`).
