# 🏴‍☠️ Za'ji Bot - Le Capitaine Corsaire de Discord

**Za'ji**, le plus grand capitaine Khajiit de toute Tamriel, commande maintenant votre serveur Discord comme son navire !

## 🎭 Personnalité

Za'ji est un **capitaine corsaire** charismatique de The Elder Scrolls Online :
- ⚓ **Vantard et Confiant** - Le meilleur capitaine des mers !
- 🏴‍☠️ **Pirate Aventureux** - Toujours prêt pour le prochain trésor
- 🍺 **Amoureux du Rhum** - La boisson des vrais marins
- 😎 **Charmeur** - Flirte avec élégance (mais respectueusement)
- 🎵 **Chanteur** - Adore les chansons de marin
- 💪 **Loyal** - Protège son équipage (le serveur)

Il parle **toujours de lui à la troisième personne** : "Za'ji est le meilleur !", "Ce bon Za'ji navigue..."

## 🚀 Installation

### 1. Prérequis
- Python 3.9+
- Un bot Discord (https://discord.com/developers/applications)
- Clés API Gemini (https://aistudio.google.com/apikey)

### 2. Configuration des Clés

```bash
# Copiez le template
cp .env.example .env

# Éditez .env avec vos vraies clés
nano .env

# Chiffrez les clés (utilise .master_key du dossier parent)
cd ..
python crypto_utils.py encrypt

# Le fichier .env.encrypted sera créé, l'original .env supprimé
```

### 3. Installation des Dépendances

```bash
pip install -r requirements.txt
```

### 4. Lancer Za'ji

```bash
python bot_zaji.py
```

## 🎮 Commandes

### Commandes Standard
- `/reputation` - Voir votre réputation de matelot
- `/top` - Classement de l'équipage
- `/anniversaire JJ/MM` - Enregistrer votre date de naissance
- `/quetes` - Vos quêtes quotidiennes

### Commandes Spéciales Za'ji
- `!exploit` - Za'ji raconte un de ses exploits légendaires
- `!chanson` ou `!shanty` - Chante une chanson de marin
- `!rhum` - Za'ji parle de sa passion pour le rhum
- `!equipage` - Liste les membres actifs du navire

### Interactions
- Mentionnez Za'ji avec `@Za'ji` pour parler directement
- Dites "rhum", "trésor", "navire" pour déclencher des réactions spéciales
- Za'ji peut intervenir dans les conversations (10% de chance)

## 🤖 Mode Duel

Za'ji interagit avec les autres bots :
- **vs Sheogorath** : Se moque de la folie du Prince Daedra
- **vs M'aiq** : Essaie de recruter son frère Khajiit
- **vs Alfred** : Trouve le majordome trop coincé

## 📊 Système de Réputation Maritime

Gagnez des points pour monter en grade :
- **Cadet** (0-49 pts)
- **Matelot** (50-149 pts)
- **Maître d'Équipage** (150-299 pts)
- **Quartier-Maître** (300-499 pts)
- **Capitaine** (500+ pts)

## 🔒 Sécurité

- ✅ Clés API chiffrées avec Fernet
- ✅ Protection DoS (images max 10 MB)
- ✅ Rate limiting
- ✅ `.env` jamais committé

## 🛠️ Architecture

- `bot_zaji.py` - Fichier principal du bot
- `zaji_data.py` - Personnalité et données
- `requirements.txt` - Dépendances
- `.env.encrypted` - Configuration sécurisée
- `shared_database.py` - Base de données partagée (dossier parent)

## 📝 Licence

Projet personnel - The Elder Scrolls © Bethesda Softworks

---

**Za'ji vous souhaite bon vent et bonne fortune, moussaillons !** ⚓🏴‍☠️
