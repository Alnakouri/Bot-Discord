# 🤖 Écosystème de Bots Discord — TES / Batman

Écosystème de **6 bots Discord** à personnalités distinctes, partageant une architecture centralisée et exécutés via **Docker**.

## 🎭 Les Bots

| Bot | Personnalité | Spécialités |
|-----|-------------|-------------|
| **Sheogorath** | Prince de la Folie (TES) | Chaos, punitions, décrets, Wabbajack, humeurs (manie / démence / félicité) |
| **M'aiq** | Khajiit menteur (TES) | Énigmes, rumeurs, mensonges |
| **Alfred** | Majordome de Batman | Vocal TTS (ElevenLabs), cynisme, service, modération |
| **Johnny Silverbot** | Rockerboy (Cyberpunk 2077) | Anti-corpo, cynisme, provocation, duels |
| **Sugar Bot** | Douce puis venimeuse | Compliments qui piquent, vannes qui fondent ; traite les malpolis de « péteur / péteuse » |
| **Malena** | Gitana marseillaise | Tarot, prédictions, style gitane |

---

## 📚 Documentation de l'Écosystème

Pour naviguer dans l'écosystème de documentation technique et utilisateur :

- **[ARCHITECTURE.md](ARCHITECTURE.md)** : Constitution technique globale, arborescence des fichiers et conventions de développement. **Source de vérité.**
- **[DEV_GUIDE.md](DEV_GUIDE.md)** : Guide d'onboarding pour développeurs (venv, boucle d'outils, persistance, historique des modifications).
- **[COMMANDES.md](COMMANDES.md)** : Guide utilisateur complet (slash commands communes et déclencheurs spécifiques par bot).
- **[API_KEYS_SETUP.md](API_KEYS_SETUP.md)** : Gestion et chiffrement des clés d'API (Gemini, Groq, Mistral, OpenRouter).
- **[MAINTENANCE.md](MAINTENANCE.md)** : Guide opérationnel (sauvegardes, redémarrages, logs, dépannage).
- **[DEPLOY_ORACLE.md](DEPLOY_ORACLE.md)** : *(Archivé)* Guide historique du déploiement VM cloud (Oracle Always Free).
- **Documentation par bot** :
  - [Alfred/README.md](Alfred/README.md)
  - [Sheogorath/README.md](Sheogorath/README.md)
  - [MaiqBot/README.md](MaiqBot/README.md)
  - [JohnnyBot/README.md](JohnnyBot/README.md)
  - [SugarBot/README.md](SugarBot/README.md)
  - [MalenaBot/README.md](MalenaBot/README.md)

---

## 🚀 Démarrage

### Prérequis
- Docker + Docker Compose
- Fichiers `.env.encrypted` configurés dans chaque dossier bot
- Fichier `.master_key` propre présent dans chaque dossier bot

> [!NOTE]
> **Déploiement en Production** : La mise en production sur serveur cloud (Hetzner/Oracle) est actuellement **parquée**. L'écosystème tourne localement sur Docker Compose.

### Lancer les bots (Docker Compose)
```bash
docker compose up -d          # Démarrage en arrière-plan
docker compose logs -f        # Suivre les logs de tous les conteneurs
docker compose down           # Arrêter proprement
```

### Sans Docker (Développement Local)
```bash
pip install -r requirements.txt
python Alfred/bot_alfred.py   # Lancer Alfred individuellement
```

---

## 🧠 Stack IA

`shared/models.py` est la **source unique** des identifiants de modèles ;
`shared/smart_router.py` décide quelle cascade utiliser. Chaque cascade essaie ses
échelons dans l'ordre et descend d'un cran si l'un échoue, rend un contenu vide ou
recopie son raisonnement dans la réponse.

### Une voix par bot

Le texte et la répartie passent par une cascade **propre à chaque persona**, choisie
sur mesures réelles (`tools/sonde_modeles_persona.py` envoie le vrai prompt de persona
à chaque modèle candidat) :

| Bot | Tête de cascade | Pourquoi |
|-----|-----------------|----------|
| **Alfred** | `mistral-small-latest` | Ironie sèche de majordome, registre « Monsieur » tenu |
| **Johnny** | `mistral-small-latest` | Seul à sortir l'argot de rue sans l'édulcorer |
| **Sheogorath** | `openai/gpt-oss-120b` (Groq) | Sort Wabbajack, Haskill et le fromage de lui-même |
| **Sugar Bot** | `gemini-3.5-flash-lite` | Tranche sans meubler, garde le vocabulaire maison |
| **M'aiq** | `gemini-3.5-flash-lite` | Les meilleures faussetés cryptiques |
| **Malena** | `mistral-small-latest` | L'argot marseillais sort tout seul |

Chaque cascade mélange des **fournisseurs différents** : leurs quotas sont indépendants,
donc si l'un limite, l'échelon suivant répond quand même.

> [!WARNING]
> **Mistral Large a été retiré de toutes les cascades le 2026-08-30** : il rend
> `403 tier_not_allowed` — hors abonnement. Il apparaît pourtant toujours dans
> `models.list()` : ne le remettre qu'après un appel réel réussi. Un test l'interdit.
> (Son identifiant n'est volontairement pas écrit en code ici : le test qui vérifie
> les modèles cités le lirait comme un modèle en service.)

### Ce qui n'est PAS personnalisé

Là, c'est la **capacité** du modèle qui commande, pas le ton :

| Rôle | Cascade |
|------|---------|
| 🖼️ Vision & audio | `gemini-3.5-flash` → `gemini-3.5-flash-lite` |
| 🧠 Raisonnement complexe | `gemini-3.5-flash` → `mistral-small-latest` → `openai/gpt-oss-120b` |
| 📢 Annonces de live | `gemini-3.5-flash-lite` → `mistral-small-latest` → `openai/gpt-oss-120b` |

> [!NOTE]
> Les annonces de live sont **publiques** : c'est la qualité de langue qui prime, pas le
> ton. La persona reste audible, elle vient du prompt système et non du modèle.

> [!WARNING]
> Le **free-tier OpenRouter** a été mesuré inutilisable (12 échecs sur 12 : quotas
> dépassés en rafale, 60 à 120 s de latence, raisonnement recopié dans la réponse).
> Aucune cascade n'en dépend, et un test l'interdit.

> [!IMPORTANT]
> Les fonctionnalités GPU locales (TTS voice-cloning Chatterbox pour Sheogorath et vision locale Moondream) sont actuellement **parquées** (désactivées par défaut pour compatibilité avec les architectures CPU-only). Les pipelines basculent automatiquement en mode dégradé sur le texte cloud ou les fallback Gemini. Voir [FEATURE_VOIX_VISION_GPU.md](FEATURE_VOIX_VISION_GPU.md).

---

## 🧩 Chaque bot est déployable seul

Un dossier de bot doit pouvoir tourner **sans `shared/`**. Le noyau technique
(10 modules : routeur, cascade LLM, gestion des clés, journalisation…) est donc **copié**
dans `<Bot>/core/` par `tools/vendor_core.py`.

> [!IMPORTANT]
> `shared/` reste la **source de maintenance** : on corrige là, puis on relance
> `python tools/vendor_core.py`, et les 6 copies suivent. Corriger une copie directement
> serait perdu au prochain vendoring — les fichiers générés le disent en en-tête.

Il existe donc **7 exemplaires** du routeur (`shared/` plus les 6 copies), parce que la
pile Twitch de `shared/` en dépend et ne peut pas être migrée. C'est tenable à une seule
condition : que les copies restent **identiques**. `tools/sonde_core_drift.py` échoue dès
qu'une diverge, et la CI l'exécute à chaque push — sans quoi deux routeurs différents
pourraient cohabiter dans le même processus sans que personne ne le voie.

Ce qui reste **partagé** et volontairement non dupliqué : `shared_database.py` (état commun
— réputation, anniversaires, énigmes : le dupliquer casserait sa raison d'être) et
`server_events.py`. Ces deux-là sont importés sous garde, et **chaque appel teste le
drapeau** `DATABASE_AVAILABLE` : un drapeau posé mais jamais lu produit un bot vivant mais
inerte, panne déjà rencontrée deux fois.

---

## 🧪 Mode test

Le dashboard porte un interrupteur **Mode test** : les bots ne publient plus que sur un
serveur Discord privé, que l'on choisit dans un menu déroulant alimenté par les serveurs
que les bots remontent eux-mêmes. Twitch et les messages privés sont coupés aussi.

- Réglable **globalement** (les 6 d'un geste) ou **bot par bot** — l'un des deux suffit.
- Relu toutes les 5 s : basculer ne demande **aucun redémarrage**.
- **Fermé par défaut** : mode actif sans serveur choisi = silence total, jamais
  « publie partout ». Le dashboard prévient avant d'activer.

---

## ✅ Vérifications automatiques

`.github/workflows/ci.yml` tourne à chaque push et à chaque pull request :

```bash
python tools/sonde_blocking_calls.py   # aucun appel LLM synchrone dans la boucle asyncio
python tools/sonde_core_drift.py       # les 6 copies du noyau n'ont pas divergé
python tools/vendor_core.py            # ... et le vendoring est bien à jour
python -m pytest -q                    # la suite complète
```

En local, avant de pousser, la même séquence suffit.

---

## 🔒 Sécurité et Chiffrement

Les jetons Discord et clés API sont chiffrés localement dans le dépôt Git.

```bash
python crypto_utils.py encrypt   # Chiffre les .env → .env.encrypted
python crypto_utils.py decrypt   # Déchiffre les fichiers pour modification
```

Pour plus de détails sur le cycle de vie des clés et la rotation, consultez [API_KEYS_SETUP.md](API_KEYS_SETUP.md).
