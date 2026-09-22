# 🛠️ Guide du Développeur — Écosystème Agentique

Ce document est destiné aux développeurs souhaitant maintenir, déboguer ou étendre l'intelligence et les capacités des bots (`Sheogorath`, `M'aiq`, `Alfred`, `Johnny`, `Sugar`, `Malena`).

---

## 🏗️ Philosophie de l'Architecture

Le système a évolué d'un simple chatbot vers une architecture de **Native Agents**. Les bots ne se contentent plus de répondre aux messages, ils interagissent de manière autonome avec le serveur Discord via des **Tools (Function Calling)**.

### 1. La Boucle d'Exécution des Outils (Function Calling)
Lorsqu'un message est reçu, le bot utilise l'IA pour décider s'il doit appeler un outil :
1. **Pass 1 (Intent)** : L'IA reçoit l'historique du salon, les données de contexte et la liste des outils déclarés.
2. **Action** : Si l'IA renvoie un appel de fonction (`function_call`), le bot intercepte la requête, exécute le code Python associé localement et effectue les modifications (modification de réputation, kick, mise à jour de rôle, etc.).
3. **Pass 2 (Response)** : Le résultat de l'exécution est renvoyé à l'IA sous forme de message système/outil. L'IA génère ensuite la réponse textuelle finale en restant dans son personnage et en commentant son action.

---

## 🚀 Workflow de Développement & Prise en Main

### 1. Environnement Local
Pour tester et exécuter un bot individuellement hors Docker :
```bash
# 1. Créer et activer l'environnement virtuel (recommandé)
python -m venv .venv
.venv\Scripts\activate

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Lancer un bot spécifique
python Alfred/bot_alfred.py
```

### 2. Validation Rapide
Avant de déployer, vous pouvez valider vos imports et votre connexion à la base de données :
```bash
python -c "from shared.shared_database import get_connection; print('DB Connection: OK')"
```

---

## 🛠️ Scripts Utilitaires Actifs

À la racine du projet, plusieurs utilitaires facilitent le développement et l'administration :

| Script | Fonction | Usage |
|---|---|---|
| [crypto_utils.py](crypto_utils.py) | Chiffrer/déchiffrer les `.env` locaux via Fernet. | `python crypto_utils.py encrypt` ou `decrypt` |
| `start_all_bots.bat` | Script batch pour lancer simultanément les 6 bots en local dans des fenêtres distinctes. | Double-clic / Lancement shell |
| `test_bot.bat` | Menu interactif permettant de choisir et démarrer un seul bot en développement local. | Double-clic / Lancement shell |

---

## 🐳 Gestion avec Docker Compose (Recommandé)

Docker Compose orchestre la totalité de l'écosystème (les 6 bots et le conteneur Ollama local).

```bash
docker compose up -d            # Démarrer tous les services en arrière-plan
docker compose logs -f          # Suivre les logs de tous les bots
docker compose logs -f maiq     # Suivre les logs d'un service spécifique (ex: Maiq)
docker compose restart maiq     # Redémarrer un bot spécifique (les modifications dans shared/ sont lues au reboot)
docker compose down             # Arrêter proprement tous les conteneurs (SIGTERM intercepté)
docker compose build --no-cache # Recompiler l'image en cas de changement de dépendances
```

---

## ⚠️ Avertissements Techniques Critiques

### 🚫 Erreur 400 Gemini (Bad Request)
Le SDK `google-genai` lève systématiquement une erreur 400 si vous lui soumettez plusieurs messages consécutifs avec le même rôle (ex: deux blocs `user` de suite).
- **Règle d'or** : Fusionnez toujours le système, le contexte et le message utilisateur dans un **seul bloc unique** `user` contenant plusieurs `Part` (texte, images, audio).

### 🔑 Rotation des Clés (MultiAPIKeyManager)
N'interrogez jamais `os.getenv("GEMINI_KEY")` en direct pour vos appels d'inférence. Passez exclusivement par le `key_manager` partagé. Il assure :
- La rotation des clés de manière équilibrée (Round-Robin).
- Le cooldown automatique temporaire (quarantaine) des clés renvoyant des erreurs `429` (Quota dépassé) — seul un 429 écarte la clé ; un 503 fait descendre d'un échelon sans quarantaine.
- Le basculement transparent vers les API de secours (Groq, Mistral).

---

## 🪄 Ajouter un Outil (Tool) à un Bot

Pour doter un bot d'une nouvelle capacité (ex: interroger une API météo, donner un rôle) :

1. **Définition Python** : Écrivez une fonction asynchrone au début du fichier `bot_*.py` du bot (ex: `async def tool_ban_user(user_id_str: str, reason: str)`).
2. **Schéma JSON** : Déclarez cette fonction et ses paramètres attendus dans la liste `*_TOOLS_DEFINITION` du bot (format standard Google Tool Definition).
3. **Dispatch** : Dans la boucle de traitement de réponse (souvent dans la fonction d'envoi ou de génération du bot), interceptez le `function_call` retourné par Gemini, exécutez la fonction correspondante, puis injectez le résultat dans la suite du prompt.

---

## 💾 Persistance des Données

- **Base de Données Commune** : Une base SQLite unique (`data/bots_database.db`, générée au premier démarrage, hors dépôt) est partagée par tous les processus. Les requêtes s'effectuent via [shared/shared_database.py](shared/shared_database.py). NE JAMAIS passer une base de `data/` en WAL — `shared_database.py` pose TRUNCATE, et c'est voulu : la base est partagée entre l'hôte Windows et six conteneurs Linux, et WAL exige une mémoire partagée (`-shm`) que les deux mondes ne peuvent pas partager. Live du 2026-09-13 : WAL a rendu les six bots MUETS. Verrou : `tests/test_base_partagee.py`.
- **Base de suivi des appels API** : `data/api_usage.db`, écrite par [shared/api_tracking.py](shared/api_tracking.py). Un unique thread écrivain dépile une file bornée, pour ne jamais bloquer la boucle asyncio d'un bot ni retarder une réponse. Elle est en **TRUNCATE**, pas en WAL : le dashboard la lit en `mode=ro`, et un lecteur read-only sur WAL a besoin du `-shm`.
- **Sauvegarde de l'état (Punitions)** : Les métamorphoses temporaires infligées par Sheogorath (Wabbajack) sont sauvegardées dans `sheo_punishments.json`. En cas de crash ou de redémarrage du conteneur, le bot reprend le décompte des sanctions sur le serveur au démarrage.
- **Règles Sensibles** : Ne modifiez ni ne supprimez jamais les fichiers secrets `.master_key` ou les bases de données SQLite existantes (se référer aux consignes de sécurité dans [AGENTS.md](AGENTS.md)).

---

## 🎭 Lignes Directrices de Personnalité et de Style

Pour maintenir la cohérence de l'écosystème lors de l'édition des prompts système :
- **Sheogorath** : Imprévisible, excentrique, obsédé par le fromage. Ne jamais utiliser de descriptions narratives d'actions entre astérisques (`*grimace*`).
- **Alfred** : Flegme britannique, majordome dévoué mais extrêmement sarcastique. N'utilise jamais le pronom "je" (préfère la troisième personne ou des tournures passives).
- **M'aiq** : Parle exclusivement de lui à la troisième personne ("M'aiq pense...", "M'aiq dit..."). Mélange de vérités évidentes et de mensonges absurdes.

---

## 📊 Historique des Changements & Optimisations

> [!NOTE]
> Les identifiants de modèles cités dans les entrées ci-dessous sont ceux **en vigueur à
> l'époque** de chaque changement. Ils ne décrivent pas l'état actuel : la source unique
> est [`shared/models.py`](shared/models.py).

### Août 2026 — Indépendance, voix par bot, garde-fous

- **Chaque bot embarque son noyau** : les 10 modules techniques sont copiés dans
  `<Bot>/core/` par `tools/vendor_core.py`, `shared/` restant la source de maintenance.
  Un bot se déploie désormais seul. Contrepartie assumée : 7 exemplaires du routeur, donc
  `tools/sonde_core_drift.py` en CI, obligatoire.
- **31 appels LLM synchrones** sortis de la boucle asyncio (`asyncio.to_thread`) : ils
  gelaient le bot pendant chaque génération.
- **Une cascade de modèles par persona**, choisie sur mesures réelles
  (`tools/sonde_modeles_persona.py`, qui envoie le vrai prompt de persona aux candidats).
  Les annonces de live font exception : publiques, elles passent par une cascade choisie
  pour la **qualité de langue**, pas pour le ton.
- **Robustesse des cascades** : une réponse vide ou un raisonnement recopié dans le
  contenu ne cassent plus la génération, ils font descendre d'un échelon. Un succès HTTP
  200 ne veut pas dire qu'il y a une réponse dedans.
- **Mode test** (dashboard) : les bots ne publient plus que sur un serveur privé. La garde
  entoure `abc.Messageable.send`, point de passage unique de toutes les sorties Discord —
  poser une garde dans chacune des ~35 boucles aurait garanti d'en oublier une.
- **CI** (`.github/workflows/ci.yml`) : compilation, sondes, vendoring à jour, suite de
  tests. Sans elle, les sondes ne tournent que si quelqu'un y pense.

### Avril 2026 — Refactoring & Dockerisation
- **Modularisation & DRY** : Déplacement de la DB dans `shared/shared_database.py`, de l'anti-répétition dans `shared/response_memory.py`, et des commandes slash dans `shared/slash_commands.py`.
- **Intégration Multimodale** : Support des images et des messages vocaux Discord (.ogg) sur l'ensemble des bots via `shared/media_handler.py` et `shared/smart_router.py`.
- **Routage Intelligent** : Les requêtes textuelles simples sont envoyées en priorité vers des API économiques/gratuites (Mistral, Groq, OpenRouter), préservant le quota Gemini pour le raisonnement complexe (`gemini-2.0-pro-exp`), la vision et l'audio (`gemini-2.0-flash`).
- **Performance & Stabilité** :
  - Standardisation sur `gemini-2.0-flash` en remplacement de `gemini-1.5-flash`.
  - Intégration de `gemma-4-26b-a4b-it:free` via OpenRouter en fallback.
  - Ajout de `graceful_shutdown.py` pour intercepter les signaux Docker de coupure propre.
  - Tracking de l'état des clés d'API dans `api_usage.db`.

### Janvier 2026 — Corrections Gemini
- **Fix Erreur 404 (Vertex AI/Google Cloud)** : Le module `shared/safe_client.py` nettoie dynamiquement la variable `GOOGLE_CLOUD_PROJECT` pour forcer le SDK Gemini à utiliser la clé d'API classique.
- **Gestion des Quotas (Rate Limiting)** : Initialisation de `MultiAPIKeyManager` avec une quarantaine automatique de 60s pour toute clé ayant atteint sa limite.
- **Réduction de Contexte** : Limite stricte de l'historique conversationnel à 15 messages pour optimiser la mémoire de travail des bots.
