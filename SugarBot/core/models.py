# ⚠️ FICHIER GENERE — NE PAS EDITER ICI.
# Source : shared/models.py — modifier la source puis relancer :
#     python tools/vendor_core.py
# La sonde tools/sonde_core_drift.py echoue si cette copie diverge.

# Source unique de vérité des identifiants de modèles.
# Vérifiés vivants le 2026-08-24 (sonde réelle, clés de prod).
GEMINI_FLASH      = "gemini-3.5-flash"
GEMINI_FLASH_LITE = "gemini-3.5-flash-lite"
GROQ_FAST         = "openai/gpt-oss-120b"
MISTRAL_SMALL     = "mistral-small-latest"  # Mistral - argot FR le plus naturel

# ATTENTION : mistral-large est HORS ABONNEMENT depuis le 2026-08-30.
# Sonde du 2026-08-30, 9 appels sur 3 personas : 9 echecs, tous identiques.
#   403 {"message":"This model is not available in your subscription tier",
#        "type":"tier_not_allowed","code":"1910"}
# En base (data/api_usage.db) : 7 echecs sur 7 depuis le 2026-08-29, latence 134-283 ms
# — le temps d'un refus, pas d'une reponse. Alfred perdait donc un appel a chaque
# message (son echelon de TETE), et Sheo tombait dessus juste apres un 429 Groq.
#
# ⚠️ `models.list()` LE LISTE QUAND MEME (54 ids rendus, mistral-large-latest inclus).
# Meme mensonge que l'audit 2026-08-24 : seul un appel reel tranche. Ne pas le
# remettre dans une cascade sur la foi du catalogue — un test l'interdit.
MISTRAL_HORS_TIER = "mistral-large-latest"

# Le Mistral de service. Pointait sur `mistral-large-latest` jusqu'au 2026-08-30 ;
# bascule sur small, choisi sur sonde (cf. CASCADES_PERSONA, entree "alfred").
# ⚠️ TOUTE la famille `mistral-*` est PLAFONNEE sur notre palier depuis le 2026-09-04.
# En base : 17 succes le 03/09, puis 0 sur 15 le 04/09, tous en 429. Dernier succes le
# 2026-09-03T22:29. Ce n'est PAS un probleme de cle : `models.list()` rend 46 modeles, et
# les 6 bots ont des cles distinctes (tools/sonde_cles_partagees.py). Ce n'est pas non plus
# une limite par minute : 429 persistant apres 70 s d'inactivite, sur les 6 cles.
#   mistral-small-latest    -> 429      magistral-small-latest -> 429
#   mistral-medium-latest   -> 429      ministral-*            -> OK
# Seule la famille `ministral-*` (modeles « edge ») repond encore.
MISTRAL_PLAFONNE  = MISTRAL_SMALL

# Choisi sur sonde reelle du 2026-09-04 (tools/sonde_modeles_persona.py, 90 appels, les 6
# vraies personas, 3 cas chacun). ministral-14b gagne sur les TROIS criteres a la fois :
#   modele                 median   asterisques   echo en ouverture
#   ministral-14b-latest    1,28 s      11/18            0/6   <-- retenu
#   open-mistral-nemo       1,29 s      15/18            1/6
#   ministral-8b-latest     1,70 s      16/18            1/6
# L'« echo en ouverture » (repeter l'insulte : « Nul ?! ») est le gabarit explicitement
# INTERDIT par le prompt de Sheogorath. ministral-14b est le seul a ne jamais le produire.
MISTRAL_MAIN      = "ministral-14b-latest"


# Modeles a RAISONNEMENT : ils depensent des tokens en pensee AVANT de repondre.
# Mesure Groq du 2026-08-26 (openai/gpt-oss-120b, meme prompt) :
#   defaut          -> 144 tokens de completion
#   effort "low"    ->  71 tokens
#   low + "hidden"  ->  47 tokens
# Sans cela, avec max_tokens=300 et un prompt de persona un peu long, la pensee mange
# tout le budget : finish_reason="length" et un `content` VIDE, donc bot muet.
# Meme famille que le gotcha Gemini "thinking mange max_output_tokens".
GROQ_REASONING_MODELS = ("gpt-oss",)


# ---------------------------------------------------------------------------
# NVIDIA (build.nvidia.com) — 4e fournisseur, ajoute le 2026-09-04.
# Point d'entree compatible OpenAI : https://integrate.api.nvidia.com/v1
#
# Motif : la famille `mistral-*` est plafonnee (429 permanent) et OpenRouter a ete
# retire des cascades. Il ne restait que 3 fournisseurs reellement joignables.
#
# Choisi sur sonde reelle (tools/sonde_fuite_raisonnement.py, prompt de persona reel) :
#   nemotron-3.5-lightning-30b-a3b  1 001 ms  propre, ni prefixe ni guillemets  <- retenu
#   nemotron-3-super-120b-a12b      1 448 ms  prefixe ses reponses par « Johnny: »
#   mistralai/mistral-nemotron      1 899 ms  entoure sa reponse de guillemets
#
# ⚠️ `models.list()` MENT une fois de plus : `nemotron-nano-3-30b-a3b`,
# `llama-3.1-nemotron-70b-instruct` et `-51b-instruct` sont au catalogue et rendent 404.
NVIDIA_FAST = "nvidia/nemotron-3.5-lightning-30b-a3b"

# Choisi le 2026-09-18 pour sortir Alfred et Johnny de ministral-14b, qui produit une
# didascalie entre asterisques dans 77 % de ses reponses (59 sur 77, mesure du harnais
# d'eval sur cinq fiches differentes) quand gemma-4 n'en produit AUCUNE.
#
# Sonde reelle sur les VRAIES personas (tools/sonde_modeles_persona.py, 3 cas par bot) :
#   bot      latence        longueur           didascalies
#   johnny   2,7 a 4,7 s    3-4 phr / 22-47 mots   0/3     (ministral : 10 phr / 140 mots)
#   alfred   1,25 a 5,1 s   3 phr   /  7-30 mots   0/3
#   sheo     1,9 a 2,75 s   4-5 phr / 31-43 mots   0/3
# Francais impeccable, registre tenu dans les trois cas (« choom » et Arasaka chez
# Johnny, « Monsieur » chez Alfred, Haskill et les majuscules chez Sheogorath).
#
# ⚠️ Ce sont les poids Gemma de Google, mais servis par NVIDIA : autre point d'entree,
# autre quota, aucun rapport avec l'API Gemini. Les deux peuvent cohabiter dans une
# cascade sans partager un plafond.
#
# ⚠️ DEMARRAGE A FROID : le premier appel sur une fonction NVIDIA endormie depasse 20 s
# (mesure : 2 fois sur 2). En tete de cascade, le premier message apres une periode calme
# sera donc refuse par la borne de 15 s du direct et retombera sur l'echelon suivant —
# ministral, c'est-a-dire l'etat d'avant. Le gain est reel mais il n'est pas total, et
# c'est la raison pour laquelle ministral reste JUSTE derriere.
#
# ⚠️ Sur 14 candidats NVIDIA reellement appeles ce jour-la, 8 rendent 404 malgre le
# catalogue et 4 depassent la borne du direct. Celui-ci est le seul survivant ; ne pas
# remettre les autres sur la foi de `models.list()` ([[gotcha-catalogue-nvidia-ment]]).
NVIDIA_GEMMA = "google/gemma-4-31b-it"
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"


def nvidia_kwargs(model_name=None):
    """Arguments a ajouter a un appel NVIDIA pour qu'il ne RECITE PAS son raisonnement.

    ⚠️ Sans cela, nemotron recopie sa pensee dans `content` — mesure du 2026-09-04 :

        sans rien        6 779 ms  « L'utilisateur m'envoie un message simple : ... »
        effort=none      1 001 ms  « Et toi t'as un clavier et une connexion. choom. »

    Le parametre ne supprime pas seulement la fuite : il divise la latence par SIX, le
    modele cessant de depenser ses tokens en pensee. C'est exactement ce que fait
    `groq_kwargs()` chez Groq (1 623 -> 315 ms) et `thinking_level="minimal"` chez Gemini.

    ⚠️ `reasoning_effort` n'est pas un parametre du client OpenAI : il DOIT passer par
    `extra_body`, sinon l'appel leve avant meme de partir sur le reseau.

    ⚠️ Ne pas confondre avec OpenRouter, ou `reasoning:{exclude:true}` ne corrige RIEN
    (mesure du 2026-08-30). Le nom du parametre ET son efficacite changent d'un
    fournisseur a l'autre : chacun doit etre sonde separement.
    """
    return {"extra_body": {"reasoning_effort": "none"}}


def details_de_quota(exception):
    """Rend un resume lisible des en-tetes de quota d'un 429, ou "" s'il n'y en a pas.

    ⚠️ Un 429 Groq est INVISIBLE par defaut : le SDK dort `retry-after` secondes et
    re-essaie tout seul. Mesure du 2026-09-04 sur le prompt de Sheogorath (4 505 tokens,
    quota 8 000/min) : 271 ms avec `max_retries=0`, mais **9,8 s puis 34,7 s** avec les
    reglages par defaut. Le bot avait l'air lent ; il dormait. Tous les clients sont
    desormais construits avec `max_retries=0` pour que la cascade prenne le relais, et ce
    helper sert a dire dans les logs POURQUOI l'echelon a ete refuse.
    """
    entetes = getattr(getattr(exception, "response", None), "headers", None) or {}
    if not entetes:
        return ""
    morceaux = []
    for nom, etiquette in (
        ("retry-after", "reprise dans"),
        ("x-ratelimit-remaining-tokens", "tokens restants"),
        ("x-ratelimit-limit-tokens", "quota"),
        ("x-ratelimit-reset-tokens", "remise a zero"),
    ):
        valeur = entetes.get(nom)
        if valeur is not None:
            morceaux.append(f"{etiquette}={valeur}")
    return " | ".join(morceaux)


def groq_kwargs(model_name):
    """Arguments a ajouter a un appel Groq selon que le modele raisonne ou non.

    `reasoning_format="hidden"` garantit en plus que la pensee n'atterrit JAMAIS dans
    `content` — c'est ce genre de fuite qui a fait reciter son raisonnement a Malena
    en pleine conversation Discord.
    """
    if any(marqueur in (model_name or "") for marqueur in GROQ_REASONING_MODELS):
        return {"reasoning_effort": "low", "reasoning_format": "hidden"}
    return {}


# ---------------------------------------------------------------------------
# Modeles supplementaires, mesures vivants le 2026-08-26
# (tools/sonde_modeles_persona.py, appels reels avec les vraies personas).
# ---------------------------------------------------------------------------
# ⚠️ ECARTE des cascades le 2026-08-26 : le francais est trop faible. Mesure sur 5
# reponses par bot : « Tu ne me trompez pas », « Rien de spiciale », « chewing-gue »,
# « une serpipe », « ca s'quille » — environ une faute reelle sur deux reponses. Il
# etait le plus incisif et le plus bref, mais la brievete ne vaut pas ce prix.
# Conserve ici pour que personne ne le re-choisisse sans savoir. Un test l'interdit.
GROQ_QWEN     = "qwen/qwen3.8-27b"
GROQ_SMALL    = "openai/gpt-oss-20b"    # Groq — le plus rapide (0.45 s median)
# MISTRAL_SMALL a servi de MISTRAL_MAIN du 2026-08-30 au 2026-09-04 ; il est depuis
# PLAFONNE (429 permanent), cf. MISTRAL_PLAFONNE. Un test l'interdit dans les cascades.

# ---------------------------------------------------------------------------
# CASCADE PAR PERSONA
#
# Les 6 bots partageaient exactement la meme cascade : meme modele, donc meme
# "voix" de fond sous six personnalites differentes. Le choix ci-dessous vient
# d'une sonde reelle (3 messages x 6 personas x 10 modeles) — pas d'une intuition.
#
# Mesures qui ont ecarte des candidats :
#   - free-tier OpenRouter    : 12 echecs sur 12 (429 en rafale, 60-120 s de latence).
#                               Retire des cascades de persona, garde comme code mort utile
#                               si un jour un modele gratuit redevient fiable.
#   - qwen3.6-27b             : recopie sa pensee (<think>) dans la reponse.
#   - groq/compound-mini      : 8 echecs sur 12.
#   - nemotron*:free          : fuite de raisonnement systematique (cf. gotcha). Il a
#                               survecu 5 jours a son propre rejet, parce qu'il restait
#                               defini en tete de fichier parmi les modeles en service
#                               et cite dans 4 appels DIRECTS de Sheogorath (hors
#                               cascade, donc hors garde-fou). Retire le 2026-08-31.
OPENROUTER_ECARTE = "nvidia/nemotron-3-super-120b-a12b:free"
#   - gemini-3.5-flash        : 10,3 s de latence mediane — trop lent pour du chat.
#
# Chaque cascade melange des fournisseurs DIFFERENTS : leurs quotas sont independants,
# donc si l'un throttle, l'echelon suivant repond quand meme.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# LES CRITERES D'ADMISSION D'UN MODELE
#
# Aucun modele n'entre dans une cascade sur sa fiche marketing. Il passe les deux
# sondes, dans cet ordre, et il est ecarte des le premier critere manque :
#
#   tools/sonde_modeles_persona.py   tient-il le personnage, en francais ?
#   tools/sonde_repartie.py          encaisse-t-il une insulte et rend-il le coup ?
#
# 1. FRANCAIS          zero faute reelle. C'est le critere le plus eliminatoire :
#                      il a coute qwen (« une serpipe », « ca s'quille »), gemma-3-27b
#                      (« Penteur »), ministral-8b, dolphin-venice (« tu mezouves »,
#                      « tu maniques », et des lettres GRECQUES au milieu d'un mot).
# 2. REPARTIE          ne JAMAIS donner raison a l'insulte, ne jamais s'excuser, ne
#                      jamais dire « je suis un programme ». Ajoute comme critere le
#                      2026-08-30 : rien ne le mesurait, et c'est pourtant ce qu'un bot
#                      de salon fait toute la journee. Mesure sur 5 piques croissantes.
#                      Ecarte ce jour-la : hermes-3 (2/5), hermes-4 (1/5, « Desole »),
#                      dolphin-venice (1/5).
# 3. PAS DE FUITE      ni raisonnement, ni notes de travail, ni prompt systeme recopies
#                      dans la reponse. Ecarte : nemotron, qwen3.5-flash (publie son
#                      « Thinking Process » en anglais), hermes-3 (recite son propre
#                      prompt), ministral-8b (« (Note : j'ai respecte la contrainte) »).
# 4. PAS DE VIDE       un 200 OK au contenu vide casse la cascade (cf. _est_vide dans
#                      llm_cascade). deepseek-v4-flash : 2 reponses vides sur 5.
# 5. LATENCE           sous ~2 s. Ecarte gemini-3.5-flash (10,3 s median) et
#                      hermes-3-70b (3,0 s).
# 6. TIC D'OUVERTURE   combien de reponses commencent par le meme mot. Ce n'est pas
#                      eliminatoire mais ca se paie : gpt-oss-120b ouvre par « Ah, »
#                      5 fois sur 5, d'ou build_anti_tic_consigne cote Sheo.
#
# ⚠️ La sonde de repartie tourne sur un prompt COURT et sur UNE persona seche (Sugar),
# contrainte par le plafond du free tier OpenRouter (1864 tokens). Son classement ne se
# transpose pas tel quel a Alfred ou M'aiq : re-mesurer avant de deplacer leur cascade.
# ---------------------------------------------------------------------------
# ⚠️ NVIDIA est le DERNIER echelon de chaque cascade depuis le 2026-09-04 : c'est le seul
# 4e fournisseur reellement joignable. Mistral est plafonne, OpenRouter a ete retire, il
# ne restait que Gemini + Groq + un Mistral mourant. Un quota de plus, independant.
CASCADES_PERSONA = {
    # Majordome : ironie seche, formulation soignee. Mistral Large tenait ce registre,
    # mais il est passe hors abonnement (cf. MISTRAL_HORS_TIER). Re-sonde du 2026-08-30
    # sur les 3 memes messages, 4 candidats : mistral-small gagne, et de loin.
    #   mistral-small  0,6 s — « Le bonjour precede la question, Monsieur. Impressionnant
    #                  d'avoir inverse une tradition aussi elementaire. » Registre tenu.
    #   mistral-medium 1,1 s — voix propre, mais 2 fautes reelles sur 6 reponses
    #                  (« le service du Manoir despedt toujours debout ») : le motif
    #                  exact qui a fait ecarter qwen. Refuse pour la meme raison.
    #   gpt-oss-120b   7,75 s sur la question ouverte, et c'est lui qui prend les 429.
    #   flash-lite     le plus court, mais ton fade et tic « helas » 2 fois sur 3.
    # Il partage le modele de Johnny et Malena : la voix vient du prompt de persona,
    # et les trois sorties restent nettement distinctes a la sonde.
    # ⚠️ 16/09 : Johnny et Malena sont sortis de Mistral sur mesure de LONGUEUR, PAS lui.
    # Son releve reste acceptable (4 phrases / 22 mots contre 6/92 et 8/95), son score
    # `longueur` est le moins mauvais des trois (3.00), et flash-lite avait deja ete
    # ecarte pour lui ci-dessus (« ton fade et tic helas »). On ne change pas ce qui tient.
    # ⚠️ 18/09 : gemma-4 passe DEVANT ministral. Le releve de ministral restait « le moins
    # mauvais des trois » sur la longueur, mais il produit une didascalie 3 fois sur 4, et
    # trois interventions sur les fiches n'y ont rien change. gemma-4 rend 3 phrases de 7 a
    # 30 mots, sans une astérisque, en gardant le « Monsieur » et l'ironie seche.
    # ministral reste juste derriere : c'est lui qui repond quand NVIDIA demarre a froid.
    "alfred": [("nvidia", NVIDIA_GEMMA), ("mistral", MISTRAL_MAIN), ("groq", GROQ_FAST),
               ("gemini", GEMINI_FLASH_LITE), ("nvidia", NVIDIA_FAST)],

    # Rockerboy de Night City : argot cru, phrases qui cognent.
    # ⚠️ Teste sur les TROIS tetes, en conditions d'eval (10 scenarios avec transcript),
    # les 17/09 : le modele ne change RIEN a sa verbosite.
    #   ministral-14b  global 3.92  longueur 2.20  10 phrases / 140 mots
    #   gpt-oss-120b   global 3.72  longueur 2.30  10 phrases / 104 mots
    #   flash-lite     global 3.82  longueur 2.60   8 phrases /  86 mots
    # 0.20 d'ecart total sur un run de 10 scenarios : du bruit. Il reste a 8-10 phrases
    # partout, quand sa regle en autorise 5-6 au MAXIMUM. Malena, elle, est passee de 12 a
    # 6 phrases en changeant de tete — pour elle c'etait bien le modele, pour lui NON.
    # Sa cause est la PERMISSION qu'il s'accorde seul dans son prompt ; voir johnny_data.py.
    # On le laisse donc sur sa tete d'origine : changer de modele serait du brassage.
    # ⚠️ La sonde courte annoncait 3 phrases / 28 mots chez Groq — elle utilise 3 messages
    # SANS transcript. Une sonde qui ne reproduit pas les conditions reelles mesure autre
    # chose : [[gotcha-la-longueur-est-un-defaut-de-MODELE]].
    # ⚠️ 18/09 : gemma-4 passe DEVANT ministral. Le releve du 17/09 ci-dessus disait que le
    # MODELE ne changeait rien a sa verbosite — c'etait vrai des trois tetes testees ce
    # jour-la (ministral, gpt-oss, flash-lite), qui rendent 8 a 10 phrases. gemma-4 en rend
    # 3 a 4, de 22 a 47 mots, sans une astérisque, en gardant « choom » et Arasaka. La
    # permission qu'il s'accorde dans son prompt reste a traiter ; elle ne suffisait juste
    # pas a expliquer les 140 mots.
    "johnny": [("nvidia", NVIDIA_GEMMA), ("mistral", MISTRAL_MAIN), ("groq", GROQ_FAST),
               ("gemini", GEMINI_FLASH_LITE), ("nvidia", NVIDIA_FAST)],

    # Prince Daedra de la Folie : chaos, lore ESO, images viscerales. gpt-oss sort le
    # Wabbajack, Haskill et le fromage de lui-meme, en francais correct. Il ouvre
    # souvent par « Ah, » — le filet anti-tics de Sheo est justement la pour ca.
    # ⚠️ 18/09 : gemma-4 s'intercale en DEUXIEME, pas en tete. gpt-oss reste la tete parce
    # qu'il sort le Wabbajack, Haskill et le fromage de lui-meme — c'est une raison de
    # PERSONA, et elle n'a pas bouge. Mais dans les deux dernieres passes d'eval, Groq
    # etait throttle et c'est ministral qui a repondu 17 fois sur 17, avec 15 didascalies.
    # L'echelon qui sert vraiment de secours doit donc etre le bon : gemma-4 rend 4-5
    # phrases, Haskill et les majuscules, sans une astérisque.
    "sheo": [("groq", GROQ_FAST), ("nvidia", NVIDIA_GEMMA), ("mistral", MISTRAL_MAIN),
             ("gemini", GEMINI_FLASH_LITE), ("nvidia", NVIDIA_FAST)],

    # Piques courtes et sechees. gemini-flash-lite tranche sans meubler et garde le
    # vocabulaire maison (« aussi fragile qu'un sucre glace un jour de pluie, peteur »).
    # gpt-oss a ete ecarte ici : francais correct mais ton fade, l'acidite disparait.
    "sugar": [("gemini", GEMINI_FLASH_LITE), ("mistral", MISTRAL_MAIN), ("groq", GROQ_FAST), ("nvidia", NVIDIA_FAST)],

    # Menteur cryptique d'Elder Scrolls : absurde bref a la 3e personne. Gemini Flash-Lite
    # invente les meilleures faussetes (« La troisieme lune existe. Elle est juste
    # invisible pour les imbeciles. »)
    "maiq": [("gemini", GEMINI_FLASH_LITE), ("mistral", MISTRAL_MAIN), ("groq", GROQ_SMALL), ("nvidia", NVIDIA_FAST)],

    # Diva gitane marseillaise : l'argot local doit sonner juste.
    # ⚠️ Meme histoire que Johnny : « chanklette / bonne mere / gatee va » avait ete
    # mesure sur `mistral-small-latest`, mort depuis le 04/09. Elle etait le bot le PLUS
    # verbeux des six (`longueur` 1.40/5). Releve du 16/09, sans souffler :
    #   ministral-14b   8 phrases / 95 mots
    #   gpt-oss-120b    4 phrases / 24 mots  (2 reponses sur 3 : Groq est le plus fragile)
    #   flash-lite      4 phrases / 35 mots  <- retenu
    # flash-lite garde l'accent ET la dyslexie voulue (« parceki », « sa », « bonne mere »),
    # et il a tenu toute la journee quand Groq etait a sec. Groq reste juste derriere.
    "malena": [("gemini", GEMINI_FLASH_LITE), ("mistral", MISTRAL_MAIN), ("groq", GROQ_FAST), ("nvidia", NVIDIA_FAST)],
}

_MARQUEURS_BOT = {
    "alfred": ("alfred",),
    "johnny": ("johnny", "silverhand"),
    "maiq":   ("maiq",),
    "malena": ("malena",),
    "sheo":   ("sheogorath", "sheo"),
    "sugar":  ("sugar",),
}


def bot_id_depuis_label(label):
    """Retrouve l'identifiant du bot depuis son etiquette d'affichage.

    Les etiquettes ne sont pas normalisees dans le code des bots : on croise
    « Johnny » et « Johnny Silverhand », « M'aiq », « M'aiq le Menteur » et « Maiq ».
    """
    normalise = (label or "").lower().replace("'", "").replace("\u2019", "")
    for bot_id, marqueurs in _MARQUEURS_BOT.items():
        if any(marqueur in normalise for marqueur in marqueurs):
            return bot_id
    return None


def cascade_persona(bot_id_ou_label):
    """Cascade propre a la persona, ou None si le bot n'en a pas."""
    if not bot_id_ou_label:
        return None
    bot_id = bot_id_ou_label if bot_id_ou_label in CASCADES_PERSONA else bot_id_depuis_label(bot_id_ou_label)
    cascade = CASCADES_PERSONA.get(bot_id)
    return list(cascade) if cascade else None


# ---------------------------------------------------------------------------
# CASCADE DES ANNONCES DE LIVE
#
# Une annonce n'est pas une reponse de chat : elle est PUBLIQUE, lue par tout le
# monde, et un francais bancal s'y voit tout de suite. C'est donc la qualite de
# langue qui commande, pas le ton — comme pour la vision, ou c'est la capacite du
# modele qui commande.
#
# Mesure du 2026-08-26 sur le vrai prompt d'annonce (Sugar, 4 tirages/modele) :
#   qwen3.8-27b        francais le PLUS faible : « KCD2, ca s'quille ! Ma_Streameuse
#                      est derriere les foudres du fer » ne veut rien dire.
#                      C'est ce modele qui a produit « son goat de Boheme ».
#   gemini-flash-lite  le plus sur : correct, varie, en personnage, sans invention
#   mistral-large      francais impeccable mais tres repetitif (3 tirages sur 4
#                      commencent par la meme tournure) et coupe a 120 tokens
#   gpt-oss-120b       correct mais invente des superlatifs, ce que le prompt interdit
#
# La persona reste audible : elle vient du prompt systeme, pas du modele.
CASCADE_ANNONCE = [
    ("gemini", GEMINI_FLASH_LITE),
    ("mistral", MISTRAL_MAIN),
    ("groq", GROQ_FAST),
    ("nvidia", NVIDIA_FAST),
]
