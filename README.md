# 🤖 Écosystème de Bots Discord — TES / Batman

Écosystème de **6 bots Discord** à personnalités distinctes, partageant une architecture centralisée et exécutés via **Docker**.

## 🎭 Les Bots

| Bot | Personnalité | Spécialités |
|-----|-------------|-------------|
| **Sheogorath** | Prince de la Folie (TES) | Chaos, punitions, Wabbajack, voix française clonée (Philippe Bozo) |
| **M'aiq** | Khajiit menteur (TES) | Énigmes, rumeurs, mensonges |
| **Alfred** | Majordome de Batman | Vocal TTS (ElevenLabs), cynisme, service, modération |
| **Johnny Silverbot** | Rockerboy (Cyberpunk 2077) | Anti-corpo, cynisme, provocation, duels |
| **Onizuka** | (personnalité vidée) | — |
| **Malena** | Gitana marseillaise | Tarot, prédictions, style gitane |

---

## 📚 Documentation de l'Écosystème

Pour naviguer dans l'écosystème de documentation technique et utilisateur :

- **[ARCHITECTURE.md](file:///I:/IA/Bot%20Discord/ARCHITECTURE.md)** : Constitution technique globale, arborescence des fichiers et conventions de développement. **Source de vérité.**
- **[DEV_GUIDE.md](file:///I:/IA/Bot%20Discord/DEV_GUIDE.md)** : Guide d'onboarding pour développeurs (venv, boucle d'outils, persistance, historique des modifications).
- **[COMMANDES.md](file:///I:/IA/Bot%20Discord/COMMANDES.md)** : Guide utilisateur complet (slash commands communes et déclencheurs spécifiques par bot).
- **[API_KEYS_SETUP.md](file:///I:/IA/Bot%20Discord/API_KEYS_SETUP.md)** : Gestion et chiffrement des clés d'API (Gemini, Groq, Mistral, OpenRouter).
- **[MAINTENANCE.md](file:///I:/IA/Bot%20Discord/MAINTENANCE.md)** : Guide opérationnel (sauvegardes, redémarrages, logs, dépannage).
- **[DEPLOY_ORACLE.md](file:///I:/IA/Bot%20Discord/DEPLOY_ORACLE.md)** : *(Archivé)* Guide historique du déploiement VM cloud (Oracle Always Free).
- **Documentation par bot** :
  - [Alfred/README.md](file:///I:/IA/Bot%20Discord/Alfred/README.md)
  - [Sheogorath/README.md](file:///I:/IA/Bot%20Discord/Sheogorath/README.md)
  - [MaiqBot/README.md](file:///I:/IA/Bot%20Discord/MaiqBot/README.md)
  - [JohnnyBot/README.md](file:///I:/IA/Bot%20Discord/JohnnyBot/README.md)
  - [OnizukaBot/README.md](file:///I:/IA/Bot%20Discord/OnizukaBot/README.md)
  - [MalenaBot/README.md](file:///I:/IA/Bot%20Discord/MalenaBot/README.md)

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

Les requêtes sont routées via le module intelligent `shared/smart_router.py` pour optimiser l'utilisation des quotas :

| Rôle | Modèle principal | Fournisseur / Fallback |
|------|------------------|------------------------|
| 🧠 Raisonnement complexe | `gemini-2.0-pro-exp` | Google AI |
| 🖼️ Vision & Audio | `gemini-2.0-flash` / `lite` | Google AI |
| 🎭 Humour & Répartie | `x-ai/grok-4.20` | OpenRouter |
| 💬 Texte standard / Fallback | `mistral-large-latest` | Mistral / Groq / OpenRouter |

> [!IMPORTANT]
> Les fonctionnalités GPU locales (TTS voice-cloning Chatterbox pour Sheogorath et vision locale Moondream) sont actuellement **parquées** (désactivées par défaut pour compatibilité avec les architectures CPU-only). Les pipelines basculent automatiquement en mode dégradé sur le texte cloud ou les fallback Gemini. Voir [FEATURE_VOIX_VISION_GPU.md](file:///I:/IA/Bot%20Discord/FEATURE_VOIX_VISION_GPU.md).

---

## 🔒 Sécurité et Chiffrement

Les jetons Discord et clés API sont chiffrés localement dans le dépôt Git.

```bash
python crypto_utils.py encrypt   # Chiffre les .env → .env.encrypted
python crypto_utils.py decrypt   # Déchiffre les fichiers pour modification
```

Pour plus de détails sur le cycle de vie des clés et la rotation, consultez [API_KEYS_SETUP.md](file:///I:/IA/Bot%20Discord/API_KEYS_SETUP.md).
