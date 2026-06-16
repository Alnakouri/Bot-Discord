# 🛠️ Guide du Développeur — Écosystème Agentique

Ce document est destiné aux futurs développeurs souhaitant maintenir ou étendre l'intelligence des bots (`Sheogorath`, `M'aiq`, `Alfred`, etc.).

## 🏗️ Philosophie de l'Architecture

Le système a évolué d'un simple chatbot vers une architecture de **Native Agents**. Les bots ne se contentent plus de répondre, ils interagissent avec le serveur via des **Tools (Function Calling)**.

### 1. La Boucle d'Exécution des Outils
Lorsqu'un message est reçu, le bot utilise Gemini pour décider s'il doit utiliser un outil.
1. **Pass 1 (Intent)** : L'IA reçoit le message et les définitions de fonctions.
2. **Action** : Si l'IA renvoie un `function_call`, le bot exécute le code Python associé.
3. **Pass 2 (Response)** : Le résultat de l'outil est renvoyé à l'IA pour qu'elle génère la réponse finale en restant dans son personnage.

---

## ⚠️ Avertissements Techniques Critiques

### 🚫 Erreur 400 (Bad Request)
L'erreur la plus fréquente avec le SDK `google-genai` survient lorsque vous envoyez plusieurs objets `Content` avec le rôle `user` de manière consécutive.
- **Règle d'or** : Toujours fusionner le système, le contexte et le message utilisateur dans un **seul bloc unique** `user` contenant plusieurs `Part` (texte, images, audio).

### 🔑 Rotation des Clés (MultiAPIKeyManager)
N'importez jamais `os.getenv("GEMINI_KEY")` directement pour faire un appel. Utilisez toujours l'objet `key_manager` partagé. Il gère :
- La rotation des clés pour éviter les quotas.
- La mise en quarantaine automatique des clés en cas d'erreur `429` (Quota) ou `400`.

---

## 🪄 Ajouter un Nouvel Outil (Tool)

Pour ajouter une capacité à un bot :
1. **Définition Python** : Créez une fonction `async def tool_nom_action(...)` au début du fichier `bot_*.py`.
2. **Schéma JSON** : Ajoutez la définition de la fonction dans la liste `*_TOOLS_DEFINITION` (Standard Google Tool format).
3. **Dispatch** : Ajoutez la condition dans le bloc `if response.candidates[0].content.parts[0].function_call` du bot.

---

## 💾 Persistance & Base de Données

- **Database** : Un fichier SQLite unique (`data/bots_database.db`) est accessible par tous. Utilisez `shared/shared_database.py` pour toute interaction.
- **Punitions** : Les transformations (Wabbajack) sont persistées dans `sheo_punishments.json`. Si le bot redémarre, il reprendra le compte à rebours là où il s'est arrêté.

---

## 🎭 Style & Sarcasme

- **Sheogorath** : Doit rester imprévisible. Ne jamais utiliser de descriptions narratives (pas d'astérisques `*grimace*`).
- **Alfred** : Sarcastique, jamais de "je".
- **M'aiq** : Toujours à la 3ème personne.

> [!TIP]
> Si vous modifiez le code de génération de message, testez toujours avec une image. C'est là que les erreurs de format (Multipart) sont les plus visibles.
