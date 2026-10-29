# Instructions pour les agents IA (Cursor, Gemini, Claude, Copilot, etc.)

> **LIRE EN PREMIER avant toute modification de code.**
> **Lire docs/ARCHITECTURE.md pour le contexte complet du projet.**

---

## 🚨 INTERDICTIONS ABSOLUES

1. **NE JAMAIS supprimer, écraser ou modifier un fichier `.env`** — ils contiennent des clés API de production
2. **NE JAMAIS supprimer ou modifier un fichier `.master_key`** — clés de chiffrement Fernet
3. **NE JAMAIS créer d'import direct entre deux bots** (ex: `from Alfred.bot_alfred import ...` dans Sheogorath)
4. **NE JAMAIS factoriser le code "dupliqué" entre bots** — l'indépendance est VOULUE
5. **NE JAMAIS passer une base de `data/` en WAL** — `shared_database.py` pose TRUNCATE, et c'est voulu : la base est partagée entre l'hôte Windows et six conteneurs Linux, et WAL exige une mémoire partagée (`-shm`) que les deux mondes ne peuvent pas partager. Live du 2026-09-13 : WAL a rendu les six bots MUETS. Verrou : `tests/test_base_partagee.py`.
6. **NE JAMAIS commiter de fichiers `.env`, `.master_key`, ou `*.db`** dans Git
7. **NE JAMAIS faire partager une clé API par deux bots** — voir la règle ci-dessous
8. **NE JAMAIS écrire un vrai pseudo (streameur, viewer, propriétaire) ni un vrai ID Discord dans le dépôt** — il est public. Code, tests, commentaires, docs et messages de commit n'emploient que des noms fictifs (`ma_streameuse`, `streameuse_amie`, `LeDev`, `bob`…). Les vraies valeurs vivent dans `data/identites_locales.json` (non versionné), lues par `shared/identites.py`. Un hook gitleaks local refuse le commit sinon.

## 🔑🔑 UNE CLÉ PAR BOT. PAS DE PARTAGE. JAMAIS.

> [!CAUTION]
> **CHAQUE BOT A SA PROPRE CLÉ API.**
> **PAS DE CLÉ PARTAGÉE ENTRE DEUX BOTS.**
> **AUCUNE EXCEPTION — ni Gemini, ni Mistral, ni Groq, ni OpenRouter, ni Discord.**

Cela vaut pour **chaque** fournisseur et **chaque** variable, `GEMINI_KEY_1` à
`GEMINI_KEY_4` comprises. Six bots = six jeux de clés distincts, point.

**Pourquoi ce n'est pas une préférence de style :**

- **Quota commun** — deux bots sur la même clé se volent leur propre débit. Le 429 de
  l'un rend l'autre muet, et rien dans les logs ne dit pourquoi.
- **Révocation en chaîne** — une clé compromise ou expirée abat *deux* bots au lieu d'un.
- **Traçabilité perdue** — `data/api_usage.db` enregistre l'index de clé par bot ; deux
  bots sur la même clé rendent la mesure inexploitable, et c'est justement cette mesure
  qui sert à trancher.
- Elle contredit la règle mère du dépôt : **chaque bot doit pouvoir tourner seul.**

**Il manque une clé ? ON PRÉVIENT L'UTILISATEUR. On ne pioche pas chez le voisin.**

> [!CAUTION]
> Dès qu'un bot a besoin d'une clé qu'il n'a pas — nouveau fournisseur, clé révoquée,
> quota à séparer, palier d'abonnement fermé — **le dire à l'utilisateur et s'arrêter
> là.** Ne JAMAIS recopier la clé d'un autre bot pour « débloquer » la situation, même
> temporairement, même « juste pour tester ».
>
> Le message doit dire : **quel bot**, **quel fournisseur**, **quelle variable**
> (ex. `GEMINI_KEY_1`), et **pourquoi** elle est nécessaire.
>
> C'est exactement comme ça qu'une clé finit partagée : personne ne décide de
> mutualiser, quelqu'un dépanne une fois et ça reste. Un agent n'a pas à créer un compte
> ni à choisir un abonnement — **c'est une décision de l'utilisateur, pas la sienne.**

**Comment on le vérifie — la règle existait déjà, et elle était violée :**

```bash
python tools/sonde_cles_partagees.py            # rapport lisible
python tools/sonde_cles_partagees.py --strict   # sortie 1 si une clé est partagée
```

La sonde n'affiche **jamais** une clé, seulement une empreinte SHA-256 tronquée. Elle
n'est pas dans `pytest` à dessein : les clés ne sont pas dans le dépôt, la CI ne peut pas
la jouer. **À lancer à la main après toute modification d'un `.env`.**

> Mesure du 2026-08-30 : `JohnnyBot` et `MalenaBot` tournaient sur la **même** clé
> Gemini. La règle était écrite dans `docs/API_KEYS_SETUP.md` depuis toujours ; personne ne
> la vérifiait, donc elle ne tenait pas. **Une règle qu'aucun outil ne contrôle n'est pas
> une règle, c'est un vœu.**

## 🏗️ Règles architecturales

- **Chaque bot est indépendant** : il peut tourner seul, sans les 5 autres, et sans `shared/`
- **`shared/` est optionnel** : tous les imports `shared.*` doivent avoir un `try/except ImportError`
- **Chaque bot a ses propres** : `.env`, `requirements.txt`, `discloud.config`, **et ses
  propres clés API — aucune n'est partagée avec un autre bot** (cf. la règle ci-dessus)
- **Le code identique entre bots est normal** — ne pas le fusionner dans un module commun
- Si tu modifies `shared/`, ça affecte les 6 bots — teste avec prudence

## 📝 Conventions de code

- Logger : utiliser `shared.bot_logger.setup_logger("nom_bot")` (avec fallback `logging.getLogger`)
- Tâches périodiques : utiliser `@tasks.loop()` de discord.py (pas `asyncio.create_task` avec boucle while)
- Pattern `load_secure_env` : toujours appeler avec `Path(__file__).parent` et utiliser `os.getenv()` après
- Variables `keyword_boost` et `duel_context` : toujours initialiser à `""` en début de `on_message`

## 🔑 Fichiers sensibles (ne pas toucher)

```
Alfred/.env
Sheogorath/.env
MaiqBot/.env
JohnnyBot/.env
SugarBot/.env
MalenaBot/.env
.master_key
MalenaBot/.master_key
data/bots_database.db
data/api_usage.db
data/identites_locales.json
```
