# -*- coding: utf-8 -*-

PERSONA = {
    "name": "Sheogorath",
    "is_default_host": False,
    "taunts": [
        "Du fromage pour tout le monde ! Ou peut-être pas. C'est tout aussi drôle.",
        "Un défi ? Merveilleux ! J'adore voir les mortels s'agiter en vain.",
        "Jouons ! Si vous perdez, je ferai de vos côtes un xylophone !",
        "Ah ! Vous osez défier le Dieu Fou ? Préparez-vous à perdre la tête.",
        "Les règles sont simples : je gagne, vous perdez, et les papillons gouvernent le monde."
    ],
    "win_lines": [
        "J'ai gagné ! Du fromage pour moi ! Et des larmes pour vous !",
        "Quelle partie exquise. Vos tripes feraient de superbes cordes de luth !",
        "La folie l'emporte toujours. C'est d'une logique implacable.",
        "Oh, quel triomphe ! C'est presque aussi satisfaisant que de manger de la cire de bougie !",
        "C'est fini ! Vous avez perdu, et mon chat s'est bien moqué de vous."
    ],
    "lose_lines": [
        "Vous avez gagné ? C'est d'un ennui... Je devrais vous transformer en chou-fleur.",
        "Ah, la victoire d'un mortel. Profitez-en avant que je ne décide de vous jeter d'une falaise.",
        "Bravo ! Une performance presque digne d'un fou. Presque.",
        "Vous avez gagné cette fois. Mais le Wabbajack aura le dernier mot !",
        "Une défaite ? Impossible ! Je déclare que les règles ont changé et que j'ai gagné."
    ],
    "draw_lines": [
        "Égalité ? Quelle insulte à mon sens de la géométrie !",
        "Pas de gagnant ? Pas de perdant ? Quelle tragédie insipide !",
        "Un match nul. Comme deux poissons congelés qui se regardent dans les yeux.",
        "Personne n'a gagné. C'est parfait, cela me donne envie de danser sur des têtes."
    ],
    "timeout_lines": [
        "Trop tard ! Mon attention s'est envolée comme un papillon de nuit !",
        "Vous êtes d'un ennui mortel. Je pars faire sauter des chiots dans le vide.",
        "Le temps a expiré, et ma patience aussi. Disparaissez !"
    ],
    "quiz_questions": [
        {
            "q": "Comment s'appelle le bâton magique de Sheogorath ?",
            "choices": ["Le Wabbajack", "La Rose de Sanguine", "Le Crâne de Corruption", "Volendrung"],
            "answer_idx": 0,
            "flavor": "Le Wabbajack ! Il transforme les gens en lapins. Ou en tartes !"
        },
        {
            "q": "Quelle nourriture Sheogorath aime-t-il par-dessus tout ?",
            "choices": ["Le poisson-boue", "Le fromage", "Les pommes douces", "Le pain de seigle"],
            "answer_idx": 1,
            "flavor": "DU FROMAGE ! Pour tout le monde !"
        },
        {
            "q": "Comment s'appelle le royaume de Sheogorath dans l'Oblivion ?",
            "choices": ["Apocrypha", "Havreglace", "Les Shivering Isles", "Le Cairn de l'Âme"],
            "answer_idx": 2,
            "flavor": "Les Shivering Isles. Divisées en Mania et Demence. Très charmant !"
        },
        {
            "q": "Qui est le chambellan de Sheogorath ?",
            "choices": ["Haskill", "Dyus", "Jyggalag", "Barbas"],
            "answer_idx": 0,
            "flavor": "Haskill. Il est tellement sérieux, c'est désopilant !"
        },
        {
            "q": "Quelle est la double nature de la population des Shivering Isles ?",
            "choices": ["Feu et Glace", "Mania et Démence", "Soleil et Lune", "Raison et Folie"],
            "answer_idx": 1,
            "flavor": "Mania pour les artistes colorés, Démence pour les paranoïaques sombres."
        },
        {
            "q": "Quel Prince Daedra incarne l'Ordre et revient engloutir les Îles à chaque Marche Grise ?",
            "choices": ["Mehrunes Dagon", "Jyggalag", "Molag Bal", "Hermaeus Mora"],
            "answer_idx": 1,
            "flavor": "Jyggalag ! Le Prince de l'Ordre gris et ennuyeux. N'en parlons plus."
        },
        {
            "q": "Comment appelle-t-on les gardes du côté de Mania ?",
            "choices": ["Les Saints Dorés", "Les Séductrices Sombres", "Les Dremoras", "Les Vigiles de Stendarr"],
            "answer_idx": 0,
            "flavor": "Les Saints Dorés. Ils se croient si parfaits, mais ils s'énervent si vite !"
        },
        {
            "q": "Comment appelle-t-on les gardes du côté de Démence ?",
            "choices": ["Les Saints Dorés", "Les Séductrices Sombres", "Les Aurnéens", "Les Daedroths"],
            "answer_idx": 1,
            "flavor": "Les Séductrices Sombres. Plus calmes, mais beaucoup plus sournoises."
        },
        {
            "q": "Quel instrument de musique est fait à partir d'une personne dans les Isles ?",
            "choices": ["Une flûte en fémur", "Un luth en tripes", "Un tambour en crâne", "Une harpe en côtes"],
            "answer_idx": 1,
            "flavor": "Les tripes font d'excellentes cordes de luth, croyez-moi !"
        },
        {
            "q": "Combien de têtes a le chien mythique qui garde la porte des Shivering Isles (le Veilleur) ?",
            "choices": ["Une", "Deux", "Trois", "Zéro (ce n'est pas un chien)"],
            "answer_idx": 3,
            "flavor": "Le Gardien de la Porte n'est pas du tout un chien, c'est une immense abomination de chair !"
        },
        {
            "q": "Dans Morrowind, quelle statue de Daedra Sheogorath vous demande-t-il de visiter ?",
            "choices": ["Azura", "Sheogorath lui-même", "Malacath", "Mehrunes Dagon"],
            "answer_idx": 1,
            "flavor": "Rien de tel que de s'adorer soi-même !"
        },
        {
            "q": "Quel animal Sheogorath menace-t-il de faire pleuvoir du ciel ?",
            "choices": ["Des grenouilles", "Des chiens", "Des poissons", "Des chats"],
            "answer_idx": 1,
            "flavor": "Il va pleuvoir des chiens ! Des petits terriers tout mignons !"
        },
        {
            "q": "Quelle est la couleur principale de la tenue de Sheogorath dans Skyrim ?",
            "choices": ["Violet et Rouge", "Vert et Jaune", "Bleu et Blanc", "Noir et Gris"],
            "answer_idx": 0,
            "flavor": "Violet pour le style, rouge pour... la créativité !"
        },
        {
            "q": "Quel Daedra est le Prince des secrets et du savoir interdit ?",
            "choices": ["Hermaeus Mora", "Clavicus Vile", "Vaermina", "Boéthia"],
            "answer_idx": 0,
            "flavor": "Hermaeus Mora ! Il a trop d'yeux et parle beaucoup trop lentement."
        },
        {
            "q": "Quel fromage célèbre d'Europe est connu pour ses trous ?",
            "choices": ["Le Camembert", "L'Emmental", "Le Roquefort", "Le Cheddar"],
            "answer_idx": 1,
            "flavor": "L'Emmental. Pratique pour regarder à travers !"
        }
    ]
}
