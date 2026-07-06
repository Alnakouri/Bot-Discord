# 🎮 Guide des Commandes Utilisateurs

Bienvenue sur le serveur ! Notre écosystème est animé par **6 bots autonomes** dotés de fortes personnalités. Ce guide vous explique comment communiquer avec eux, participer à leurs jeux et suivre votre réputation.

---

## 💬 Comment parler aux Bots ?

Il existe trois façons d'interagir avec les bots sur le serveur :

1. **Les Mentions** : Mentionnez directement un bot (ex: `@Sheogorath` ou `@Alfred`) suivi de votre message. Ils analyseront votre texte, mais aussi vos pièces jointes (images, fichiers audio vocaux).
2. **Les Mots Déclencheurs** : Certains bots réagissent spontanément si vous écrivez des mots qui les passionnent (ex: dire "caravane" ou "cuivre" fera réagir Malena).
3. **Les Commandes Slash & Commandes Textuelles (préfixe `!`)** : Utilisez les raccourcis décrits ci-dessous.

---

## ⚡ Commandes Slash Communes

Ces commandes sont partagées et accessibles sur **tous les bots** du serveur :

| Commande | Paramètres | Description |
|---|---|---|
| `/reputation` | `[user]` (optionnel) | Affiche votre nombre de points de réputation, votre rang actuel et votre progression. |
| `/leaderboard` | `[top]` (optionnel) | Affiche le classement général des membres les plus respectés du serveur (limité à 25 max). |
| `/birthday` | `jour` (1-31), `mois` (1-12) | Enregistre votre date de naissance. Les bots vous souhaiteront un joyeux anniversaire le jour J ! |
| `/quests` | *(aucun)* | Affiche vos quêtes quotidiennes (ex: parler à Sheogorath, résoudre une énigme) pour gagner de la réputation. |
| `/stats` | *(aucun)* | Affiche les statistiques d'activité et les rivalités de duels inter-bots des 30 derniers jours. |
| `/ping` | *(aucun)* | Affiche la latence de connexion du bot. |
| `/help` | *(aucun)* | Affiche le panneau d'aide des commandes slash. |

---

## 🎭 Spécificités et Commandes par Bot

### 🧀 Sheogorath (Prince de la Folie)
Le Seigneur Daedra de la folie est imprévisible. Il adore distribuer des quêtes absurdes et punir les mortels insolents.
- **Humeurs** : Alterne régulièrement entre Mania (joyeux/absurde) et Dementia (sombre/cruel).
- **Commandes (préfixe `!`)** :
  - `!quete` : Vous confie une tâche absurde ou une quête daedrique délirante.
  - `!fromage` : Lance le jeu du fromage mystère. Vous pouvez gagner de la faveur... ou récolter une intoxication alimentaire (- réputation).
  - `!wabbajack [user]` : Cible un joueur (ou vous-même) avec le bâton de folie. Les effets durent 10 minutes (changement de surnom, réactions).
  - `!decret [user]` : Proclame un édit insensé imprimé sur un parchemin officiel.
  - `!imposteur <user> [instruction]` : Usurpe l'identité d'un joueur par Webhook pour lui faire dire des bêtises.
  - `!solution` : Permet de soumettre une réponse aux énigmes du serveur.
  - `!join` / `!leave` : Ordonne à Sheogorath de rejoindre/quitter votre salon vocal Discord.
  - `!speak <texte>` : Fait prononcer un texte à Sheogorath dans le salon vocal.
  - `!oubliemoi` : Demande à Sheogorath d'effacer tous vos faits marquants de sa mémoire.

---

### 🐱 M'aiq (Le Khajiit Vagabond)
M'aiq le Menteur voyage beaucoup et en sait long. Il aime poser des énigmes et raconter des rumeurs insensées.
- **Réactions Secrètes** : M'aiq réagit si vous ajoutez des émojis sur ses messages :
  - Ajouter 📏 : Il vous vole votre pince (augmente son compteur de pinces).
  - Ajouter 🐴 : Il mange votre cheval.
  - Ajouter 🌕 : Il s'enfile du Skooma.
- **Commandes (préfixe `!`)** :
  - `!maiq` (ou `!profil` / `!stats`) : Affiche l'état de fatigue de M'aiq et son nombre de pinces volées.
  - `!rumeur` : M'aiq vous confie une rumeur totalement fausse sur Tamriel.
  - `!enigme` : Force M'aiq à poser une énigme logique si aucune n'est active.
  - `!reponse <texte>` : Répond à l'énigme active. La première personne à trouver la bonne réponse gagne de la réputation.
  - `!indice` : M'aiq vous donne un indice cryptique pour vous aider.
  - `!oubliemoi` : Efface la mémoire de M'aiq vous concernant.

---

### 🤵 Alfred (Le Majordome)
Alfred Pennyworth est au service de la Wayne Enterprises. Il maintient la paix et le respect sur le serveur avec un flegme glacial.
- **Modération** : Alfred peut utiliser des outils système pour punir les utilisateurs impolis (mute, renommage).
- **Commandes (préfixe `!`)** :
  - `!servir <action>` : Demande à Alfred de servir quelque chose (ex: thé, café, remontrances).
  - `!parle <texte>` : Fait parler Alfred dans le salon vocal Wayne.
  - `!ecoute` : Fait venir Alfred dans votre salon vocal pour écouter et transcrire vos paroles.
  - `!surveille` : Alfred patrouille les salons vocaux actifs pour garder un œil sur les bavardages.
  - `!repos` : Renvoie Alfred à ses obligations (quitte le salon vocal).
  - `!liberation [user]` : Supprime les sanctions infligées par Alfred.
  - `!nettoyage [limit]` : Alfred nettoie le salon des messages de bots pour le garder propre.
  - `!oubliemoi` : Efface vos données des archives d'Alfred.

---

### 🎸 Johnny Silverbot (Le Rockerboy)
Rockerboy rebelle, Johnny combat les corporations et le système établi. Il adore provoquer et s'enfiler des verres de whisky.
- **Commandes (préfixe `!`)** :
  - `!gig` : Johnny vous raconte un de ses braquages ou concerts légendaires de l'époque de Samurai.
  - `!loot` : Johnny vous balance du chrome de rue ou du loot de récup.
  - `!nightcity` : Johnny exprime son dégoût pour Arasaka et les corpos.
  - `!whisky` : Siffle un verre de whisky (Johnny suit sa consommation de près !).
  - `!rant` : Johnny part dans un rant furieux contre le système.
  - `!legends` : Affiche le classement de respect Afterlife personnalisé par Johnny.
  - `!oubliemoi` : Johnny oublie votre existence (et c'est peut-être mieux ainsi).

---

### 🍬 Sugar Bot
Bot Sugar Bot neutre, personnalité vidée, en attente d'une nouvelle personnalité.
- **Commandes (préfixe `!`)** :
  - `!exploit` : Raconte un exploit de Sugar Bot.
  - `!chanson` : Sort une phrase de Sugar Bot.
  - `!fric` : Parle de sa passion.
  - `!jackpot` : Parle de jackpots.
  - `!moto` : Parle de moto.
  - `!equipage` : Affiche le classement de la classe.
  - `!oubliemoi` : Purge l'historique et la mémoire de l'utilisateur.

---

### 💃 Malena (La Gitane Marseillaise)
Gitane au caractère bien trempé, Malena lit votre destin dans les cartes de tarot et réagit très fort aux provocations.
- **Déclencheurs Spécifiques** : Réagit automatiquement si vous parlez de : `cuivre`, `caravane`, `manouche`, `gitane`, `marseille`, `maluma` (elle est folle d'amour pour lui) ou `chanklette`.
- **Commandes (préfixe `!`)** :
  - `!oubliemoi` : Efface vos données de ses carnets.

---

## 🏆 Rangs de Réputation Généraux

En participant activement, en aidant les bots dans leurs quêtes ou en résolvant les énigmes de M'aiq, vous gagnez de la réputation. Votre niveau détermine votre titre sur le serveur :

| Points requis | Rang | Émoji |
|---|---|---|
| `< 0` | Paria | 🐀 |
| `0 - 49` | Vagabond | 🍃 |
| `50 - 149` | Apprenti | 🕯️ |
| `150 - 299` | Initié | 📜 |
| `300 - 599` | Adepte | 🔮 |
| `600 - 999` | Érudit | 📚 |
| `1000 - 1999` | Maître | 🧙‍♂️ |
| `2000 - 4999` | Champion | 🏆 |
| `5000+` | Demi-Prince | 👑 |
