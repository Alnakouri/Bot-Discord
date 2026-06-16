# 🔫 Johnny Silverbot - Le Rockerboy de Discord

**Johnny Silverbot**, légende rockerboy de Night City, débarque sur votre serveur Discord avec sa rage anti-corpo et son cynisme légendaire (inspiré de Johnny Silverhand, Cyberpunk 2077).

## 🎭 Personnalité

Johnny est un **rockerboy anarchiste** de Night City :
- 🎸 **Anti-Corpo Viscéral** - Crame Arasaka, crame le système
- 🔫 **Cynique & Provocateur** - Une vérité brutale dans chaque phrase
- 🥃 **Whisky & Clopes** - Carburant de la révolution
- 🎤 **Légende Vivante** - Samurai n'est jamais vraiment mort
- 😤 **Loyal à sa manière** - Une grande gueule au grand cœur
- 🌃 **Esprit de Night City** - Wake the f*** up, samurai

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

### 4. Lancer Johnny

```bash
python bot_johnny.py
```

Ou utilisez le fichier batch :
```bash
start_johnny.bat
```

## 🎮 Commandes

### Commandes Standard
- `/reputation` - Voir votre réputation à Night City
- `/top` - Classement des légendes
- `/anniversaire JJ/MM` - Enregistrer votre date de naissance
- `/quetes` - Vos quêtes quotidiennes

### Commandes Spéciales Johnny
- `!gig` (alias `!job !mission !run !contrat`) - Johnny raconte un gig
- `!loot` (alias `!gift !chrome !eddies`) - Johnny balance du loot / chrome
- `!nightcity` (alias `!samurai !anti-corpo`) - Johnny crache sur le système
- `!whisky` (alias `!clope !drink`) - Johnny picole et fume
- `!rant` (alias `!corpo !systeme`) - Johnny part en rant anti-corpo
- `!legends` (alias `!leaderboard`) - Les légendes de Night City

### Interactions
- Mentionnez Johnny avec `@Johnny` (ou dites "johnny", "silverhand", "samurai", "silverbot")
- Johnny peut intervenir dans les conversations (10% de chance)

## 🤖 Mode Duel

Johnny interagit avec les autres bots :
- **vs Sheogorath** : Méfiance face au Prince de la Folie
- **vs Khajiit (M'aiq/Za'ji)** : Trafiquants, comme à Night City
- **vs Alfred** : Le majordome corpo par excellence — cible idéale

## 📊 Système de Réputation

Gagnez des points pour monter en grade à Night City :
- **🔰 Newbie** (0-49 pts)
- **🎸 Mercs** (50-149 pts)
- **🔫 Solo** (150-299 pts)
- **🌃 Légende de la Rue** (300-499 pts)
- **💀 Légende Vivante** (500+ pts)

## 🔒 Sécurité

- ✅ Clés API chiffrées avec Fernet
- ✅ Protection DoS (images max 10 MB)
- ✅ Rate limiting
- ✅ `.env` jamais committé

## 🛠️ Architecture

- `bot_johnny.py` - Fichier principal du bot
- `johnny_data.py` - Personnalité et données
- `requirements.txt` - Dépendances
- `.env.encrypted` - Configuration sécurisée
- `shared_database.py` - Base de données partagée (dossier parent)

## 📊 Statistiques Suivies

Johnny suit ses exploits :
- 🎸 **Gigs accomplis**
- 🔫 **Loot récupéré**
- 🥃 **Verres sifflés**

## 📝 Licence

Projet personnel - Cyberpunk 2077 © CD Projekt RED

---

**Johnny Silverbot — Wake the f*** up, samurai. On a une ville à brûler.** 🔫🎸
