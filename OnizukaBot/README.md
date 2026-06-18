# 🏍️ Eikichi Onizuka Bot (GTO) - Le Prof le plus déjanté de Discord

**Eikichi Onizuka**, 22 ans, célibataire et libre comme l'air, ancien chef du gang Onibaku à Shonan, est devenu professeur au lycée Seirin ! Il débarque sur votre serveur Discord pour y mettre son grain de folie et donner de vraies leçons de vie !

## 🎭 Personnalité

Onizuka est le protagoniste légendaire du manga **GTO (Great Teacher Onizuka)** :
- 🏍️ **Motard et Loubard** - Conduit sa Kawasaki Z900 à toute allure !
- 💴 **Obsédé par l'Argent** - Adore le pachinko, les jeux d'argent et gratter des yens
- 😍 **Fleur Bleue & Obsédé** - Craque totalement pour Fuyutsuki-sensei (et les jolies filles en général)
- ✊ **Un Cœur d'Or** - Capable de risquer sa vie pour sauver un de ses élèves
- 🧠 **Anti-Règles** - Piétine le règlement scolaire mais enseigne les vraies valeurs humaines
- 🚫 **Sans fioritures** - Parle cash, avec un langage fleuri de loubard de Shonan

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

### 4. Lancer Onizuka

```bash
python bot_onizuka.py
```

## 🎮 Commandes

### Commandes Standard
- `/reputation` - Voir votre réputation/respect auprès d'Onizuka
- `/top` - Classement de la classe
- `/anniversaire JJ/MM` - Enregistrer votre date de naissance
- `/quetes` - Vos quêtes quotidiennes

### Commandes Spéciales Onizuka
- `!exploit` ou `!histoire` - Onizuka raconte un de ses exploits loufoques
- `!chanson` ou `!frime` - Onizuka sort une punchline ou se vante
- `!fric` ou `!argent` - Onizuka parle de pachinko, de fric ou de ramen
- `!jackpot` - Onizuka parle de ses gains (ou plutôt de ses dettes !)
- `!moto` - Vante sa bécane ou raconte ses misères avec la Cresta d'Uchiyamada
- `!equipage` ou `!classe` - Liste la bande d'élèves/potes actifs

### Interactions
- Mentionnez Onizuka avec `@Onizuka` pour lui parler directement
- Dites "fric", "jackpot", "moto" pour déclencher des réactions spéciales
- Onizuka peut intervenir dans les conversations (10% de chance)

## 🤖 Mode Duel

Onizuka interagit avec les autres bots :
- **vs Sheogorath** : Relève le défi de folie du Prince Daedra avec assurance
- **vs M'aiq** : Taquine le Khajiit menteur et lui propose des ramen
- **vs Alfred** : Tente de décoincer le majordome d'une virée en bécane

## 📊 Système de Respect dans la Classe

Gagnez des points pour monter en grade :
- **Cancre** (0-49 pts)
- **Élève Moyen** (50-149 pts)
- **Motard d'Onibaku** (150-299 pts)
- **Délégué de Classe** (300-499 pts)
- **Great Student Onizuka** (500+ pts)

## 🔒 Sécurité

- ✅ Clés API chiffrées avec Fernet
- ✅ Protection DoS (images max 10 MB)
- ✅ Rate limiting
- ✅ `.env` jamais committé

## 🛠️ Architecture

- `bot_onizuka.py` - Fichier principal du bot
- `onizuka_data.py` - Personnalité et données
- `requirements.txt` - Dépendances
- `.env.encrypted` - Configuration sécurisée
- `shared_database.py` - Base de données partagée (dossier parent)
