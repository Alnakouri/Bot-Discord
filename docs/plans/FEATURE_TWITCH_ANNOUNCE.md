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

---

## 5. Voir une annonce sans attendre un live : `!annonce`

    !annonce                     # les SIX bots répondent, sur le streamer configuré
    !annonce johnny              # Johnny seul
    !annonce streameuse_amie           # les six, sur cette chaîne
    !annonce johnny streameuse_amie    # Johnny seul, sur cette chaîne

Noms acceptés : `alfred` · `johnny` (`silverbot`, `silverhand`) · `maiq` (`m'aiq`, `khajiit`) ·
`malena` (`gitane`) · `sugar` · `sheogorath` (`sheo`). Accents, apostrophes et tirets sont
ignorés — `M'aiq`, `Maïq` et `maiq` désignent le même bot.

Un mot qui ne nomme aucun bot est lu comme un **login Twitch** : la liste des bots est
fermée et connue, celle des streamers non. Un streamer qui s'appellerait « sugar » serait
donc pris pour le bot — il reste `!annonce sugar sugar`.

Réservée aux **gérants du serveur** (permission « Gérer le serveur » ou administrateur) ;
pour tout le monde d'autre la commande ne répond pas, et le refus part dans le journal.

Elle rejoue le **vrai** chemin d'annonce — même embed, même accroche écrite par le modèle
en personnage, même repli statique si le modèle se tait — avec trois différences voulues :

- **La commande s'efface.** Le message `!annonce…` est supprimé avant l'envoi : il ne
  reste que l'annonce. À six bots, cinq tombent forcément sur un « message déjà
  supprimé » — c'est le cas nominal, il ne crie pas dans le journal et n'empêche
  aucune annonce. Sans la permission « Gérer les messages », le bot le note une fois
  et annonce quand même. Un refus, lui, n'efface rien : une commande qui disparaît
  sans rien produire serait pire que la laisser.
- **Elle poste dans le salon d'où la commande part**, jamais dans le salon configuré :
  un test n'a rien à faire chez la communauté.
- **L'anti-doublon est sauté.** Sinon, les six bots répondant à la même commande, un seul
  parlerait et les cinq autres auraient l'air cassés. C'est justement l'intérêt : six
  accroches côte à côte, six personas.
- **Ce qui est faux est signalé.** Si la chaîne n'est pas en direct, le titre et le jeu
  restent les VRAIS (lus sur `/helix/channels`, qui répond hors ligne) ; seuls le nombre
  de spectateurs et la vignette manquent, et le pied de l'embed dit « simulation ». Une
  annonce de test indistinguable d'une vraie ferait croire à un live.

Les six bots l'ont parce que la commande est enregistrée dans `setup_twitch_announcer`,
que tous appellent — pas dans six fichiers de bots. Verrous : `tests/test_twitch_commande_annonce.py`.
