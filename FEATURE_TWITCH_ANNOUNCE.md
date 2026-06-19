# Configuration des Annonces de Live Twitch (Pingcord-like)

Cette fonctionnalité permet à chaque bot de surveiller de manière autonome des chaînes Twitch par polling (API Helix) et d'envoyer un message d'annonce avec un bel embed dans le salon Discord configuré lorsqu'elles passent en live.

## 1. Création de l'application Twitch

Pour que le bot puisse interroger l'API Twitch, vous devez obtenir des identifiants (Client ID et Client Secret) :

1. Rendez-vous sur la [Console des Développeurs Twitch](https://dev.twitch.tv/console/apps).
2. Connectez-vous avec votre compte Twitch (activez l'authentification à deux facteurs si demandé).
3. Cliquez sur **Enregistrer votre application** (*Register Your Application*).
4. Remplissez les champs :
   - **Nom** : Le nom de votre application (ex: `MonBot Discord Twitch`)
   - **OAuth Redirect URLs** : `http://localhost` (non utilisé mais requis par Twitch)
   - **Catégorie** : Choisir *Chat Bot* ou *Application Integration*
5. Cliquez sur **Créer** (*Create*).
6. Cliquez sur **Gérer** (*Manage*) à côté de votre application fraîchement créée.
7. Notez l'**ID client** (*Client ID*).
8. Cliquez sur **Nouveau secret** (*New Secret*) pour générer le **Secret client** (*Client Secret*). *Notez-le précieusement, il ne s'affichera qu'une seule fois.*

---

## 2. Configuration des secrets du Bot

Pour respecter les principes de sécurité du projet, ces secrets doivent être configurés dans le fichier `.env` de chaque bot (ou chiffrés dans son `.env.encrypted`).

### Option A : Fichier `.env` en clair (Développement)
Dans le dossier du bot concerné (ex: `JohnnyBot/.env`), ajoutez les lignes suivantes :
```env
TWITCH_CLIENT_ID=votre_client_id_twitch
TWITCH_CLIENT_SECRET=votre_client_secret_twitch
```

### Option B : Utilisation de l'outil de chiffrement du projet
Si vous utilisez la clé de chiffrement Fernet (`.master_key`), ajoutez ces variables dans votre configuration chiffrée.

---

## 3. Configuration de la fonctionnalité

La configuration globale se trouve dans le fichier `data/twitch_config.json`. Elle est gérable via l'interface du **Dashboard** mais peut aussi être éditée manuellement :

```json
{
  "johnny": {
    "enabled": true,
    "poll_interval_seconds": 90,
    "subscriptions": [
      {
        "twitch_login": "ninja",
        "discord_channel_id": 123456789012345678,
        "custom_message": "Hey ! {streamer} est en live sur {game} ! Viens voir : {url}"
      }
    ]
  }
}
```

### Variables disponibles pour `custom_message` :
- `{streamer}` : Le nom d'affichage du streamer (ex: `Ninja`)
- `{title}` : Le titre du stream actuel
- `{game}` : Le nom du jeu en cours
- `{url}` : L'URL de la chaîne Twitch (`https://twitch.tv/username`)

---

## 4. Fonctionnement technique

- **Pas de Webhooks (EventSub)** : Utilise un polling d'API Helix, ce qui évite d'exposer une URL publique pour recevoir des requêtes.
- **Indépendance des bots** : Chaque bot gère ses propres credentials et sa boucle. Si l'un n'a pas de credentials, il désactive simplement sa boucle de polling.
- **Anti-doublon intelligent** :
  1. *Niveau Bot* : Le bot garde en mémoire les streams déjà annoncés pour éviter le spam.
  2. *Inter-Bots* : Avant de poster, le bot vérifie l'historique du salon Discord. Si un embed Twitch identique a été posté dans les 30 dernières minutes par n'importe quel bot, le doublon est évité.
