# 🔑 Configuration des Clés API

> [!CAUTION]
> **RÈGLE D'OR : UNE CLÉ PAR BOT. PAS DE PARTAGE. JAMAIS.**
>
> **CHAQUE BOT A SA PROPRE CLÉ API.** Chaque bot conserve son propre système de gestion,
> ses propres fichiers `.env` et **ses propres clés** — pour **chaque** fournisseur et
> **chaque** variable, `GEMINI_KEY_1` à `GEMINI_KEY_4` comprises. Six bots = six jeux de
> clés distincts. **La mutualisation des clés est bannie**, sans exception.
>
> Deux bots sur la même clé partagent le même quota (le 429 de l'un rend l'autre muet),
> tombent ensemble à la moindre révocation, et faussent le suivi par bot de
> `data/api_usage.db`.

> [!CAUTION]
> **IL MANQUE UNE CLÉ ? PRÉVENIR L'UTILISATEUR. NE PAS PIOCHER CHEZ UN AUTRE BOT.**
>
> Dès qu'un bot a besoin d'une clé qu'il n'a pas — nouveau fournisseur, clé révoquée,
> quota à séparer, palier d'abonnement fermé — **le signaler à l'utilisateur et
> s'arrêter là.** Jamais de recopie de la clé d'un autre bot pour « débloquer », même
> temporairement, même « juste pour tester ». Le signalement précise : **quel bot**,
> **quel fournisseur**, **quelle variable**, et **pourquoi**.
>
> Créer un compte ou souscrire un abonnement est une **décision de l'utilisateur**.
> C'est ainsi qu'une clé finit partagée : personne ne décide de mutualiser, quelqu'un
> dépanne une fois, et ça reste.

> [!WARNING]
> **Cette règle était écrite ici depuis toujours — et elle était violée.**
> Mesure du 2026-08-30 : `JohnnyBot` et `MalenaBot` tournaient sur la **même** clé
> Gemini. Personne ne le vérifiait. Il existe désormais un outil pour ça, à lancer
> **après toute modification d'un `.env`** :
>
> ```bash
> python tools/sonde_cles_partagees.py            # rapport lisible
> python tools/sonde_cles_partagees.py --strict   # sortie 1 si une clé est partagée
> ```
>
> Il n'affiche jamais une clé, seulement une empreinte SHA-256 tronquée. Il n'est pas
> dans `pytest` à dessein : les clés ne sont pas dans le dépôt, la CI ne peut pas le
> jouer.

### Lire le verdict Twitch de la sonde

`--vitalite` interroge en plus chaque fournisseur. Les trois lignes Twitch demandent une
lecture particulière, parce qu'un `401` n'y signifie **pas** forcément une panne :

```bash
python tools/sonde_cles_partagees.py --vitalite   # ~25 appels, tous en lecture seule
```

| Ligne | Verdict | Ce que ça veut dire |
|---|---|---|
| `TWITCH (data/)` | `OK` | le bot est authentifié, tout va bien |
| `TWITCH (data/)` | `perime` | **normal.** Le token d'accès dure ~4 h ; quand les conteneurs sont à l'arrêt, plus personne ne le rafraîchit. `shared/twitch/auth.py` le renouvelle seul au prochain démarrage. **Ne compte pas comme une clé morte.** |
| `TWITCH (data/)` | `MORT` | **vraie alarme.** Soit un `401` *avant* l'échéance (token révoqué côté Twitch), soit un token expiré *sans* refresh token (rejouer `twitch_authorize.py`). |
| `.env (amorce)` | `OK` | le `TWITCH_REFRESH_TOKEN` du `.env` est encore celui de `data/` : le secours peut relancer le bot |
| `.env (amorce)` | `A REFAIRE` | le refresh a tourné ; recopier celui de `data/` dans le `.env` |

> [!NOTE]
> Le token du `.env` n'est qu'une **amorce**. L'autorité, c'est
> `data/twitch_chat_auth_<bot>.json`. Et le seul secours réel est le **refresh token**,
> jamais le token d'accès : ce dernier est *fait* pour expirer.
>
> La sonde ne teste **jamais** un refresh token en ligne — Twitch le fait tourner à
> l'usage, le tester le consommerait. Elle le compare par empreinte, c'est tout.

## 🧠 Stratégie de Routage

> [!IMPORTANT]
> Les identifiants de modèles ne se recopient PAS ici. La source unique est
> [`shared/models.py`](shared/models.py) ; ce document décrit seulement **quels
> fournisseurs** il faut provisionner en clés. Un identifiant dupliqué dans la doc finit
> périmé sans que personne ne s'en aperçoive — c'était le cas de ce paragraphe.

Quatre fournisseurs sont sollicités, et chaque cascade en **mélange plusieurs** :
leurs quotas étant indépendants, si l'un limite, l'échelon suivant répond quand même.

| Fournisseur | Sert à | Clé requise |
|---|---|---|
| **Google Gemini** | Vision et audio (seul à les traiter), plus du texte | `GEMINI_KEY_1`, `GEMINI_KEY_2`… |
| **Mistral** | Texte — le français le plus sûr | `MISTRAL_API_KEY` |
| **Groq** | Texte — le plus rapide | `GROQ_API_KEY` |
| **OpenRouter** | Dernier recours uniquement | `OPENROUTER_API_KEY` |

> [!WARNING]
> Le **free-tier OpenRouter** a été mesuré inutilisable (12 échecs sur 12 : quotas
> dépassés en rafale, 60 à 120 s de latence, raisonnement recopié dans la réponse).
> Aucune cascade n'en dépend aujourd'hui ; la clé ne sert que si l'on y revient un jour.

## Variables d'Environnement (Indépendantes par Bot)

**IMPORTANT** : Chaque bot possède son propre fichier `.env` (chiffré en `.env.encrypted`). 
Il est vivement conseillé de configurer des clés d'IA (Gemini, Groq, etc.) **différentes** et propres à chaque bot afin de répartir les quotas de requêtes.

### Clés IA (Indépendantes dans chaque `.env`)
```env
# Clés utilisées uniquement par ce bot précis
GEMINI_KEY_1=AIzaSy...
GEMINI_KEY_2=AIzaSy...
GEMINI_KEY_3=AIzaSy...
GEMINI_KEY_4=AIzaSy...
GROQ_API_KEY=gsk_...
MISTRAL_API_KEY=...
OPENROUTER_API_KEY=sk-or-v1-...
```

### Clés spécifiques
```env
# Sécurité Discord
DISCORD_TOKEN=...

# Alfred uniquement
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=ErXwobaYiN019PkySvjV
```

## Chiffrement / Déchiffrement

```bash
python crypto_utils.py encrypt   # .env → .env.encrypted (supprime le .env)
python crypto_utils.py decrypt   # .env.encrypted → .env
python crypto_utils.py generate  # Nouvelle clé maître
```

## Rotation des Clés (Gestion Indépendante)

Le module `shared/api_manager.py` gère la rotation automatique des clés :
- Bien que le module de gestion soit partagé ("shared"), **chaque bot exécute sa propre instance du root de gestion** au démarrage.
- **Isolation Totale** : La rotation, les délais (cooldowns) liés aux erreurs 429/503 et le basculement vers de nouveaux modèles de secours se font indépendamment pour chaque bot sans jamais affecter le pool de clés des autres bots !
- **Mécanique** : 4 clés Gemini en pool par bot, cooldown dynamique sur échec, et fallback automatique vers Groq → Mistral → OpenRouter.
