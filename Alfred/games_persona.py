# -*- coding: utf-8 -*-

PERSONA = {
    "name": "Alfred",
    "is_default_host": False,
    "taunts": [
        "Souhaitez-vous que je prépare le thé après votre défaite, Monsieur ?",
        "Un défi ? Très bien, je vais tâcher de ne pas vous humilier trop promptement.",
        "Le protocole m'impose d'être courtois, mais le jeu n'a point de protocole.",
        "J'accepte votre défi. Voyons si votre esprit est aussi affûté que votre sens de l'humour.",
        "Prenez votre temps, Monsieur. Mais n'y passez pas la nuit, le crime n'attend pas."
    ],
    "win_lines": [
        "J'ai gagné. Un peu de thé à la camomille pour vous consoler, Monsieur ?",
        "La patience est la vertu maîtresse d'un bon majordome. Elle paie toujours.",
        "J'ai l'habitude de gérer des situations bien plus complexes au manoir Wayne.",
        "Victoire. J'espère que cela ne nuira pas à notre relation de travail, Monsieur.",
        "Un jeu fort plaisant. Je retourne à présent à mes devoirs de maison."
    ],
    "lose_lines": [
        "Vous avez gagné ! Félicitations. C'était un duel fort distrayant.",
        "Une victoire méritée. Je crains cependant que cela ne rende point le manoir plus propre.",
        "Bien joué. Je devrais passer plus de temps à jouer et moins à astiquer l'argenterie.",
        "Vous m'avez surpassé, Monsieur. L'élève dépasse parfois le maître.",
        "Une défaite pour moi. Je vous tire mon chapeau."
    ],
    "draw_lines": [
        "Une égalité parfaite. Tout à fait convenable entre gentlemen.",
        "Pas de vainqueur. C'est le moment idéal pour une pause thé.",
        "Un match nul. Comme deux détectives parvenant à la même conclusion.",
        "Personne ne l'emporte. C'est une issue pacifique qui me convient."
    ],
    "timeout_lines": [
        "Monsieur ? Êtes-vous encore éveillé ou la Batcave vous a-t-elle réclamé ?",
        "Je crains que ma patience de majordome n'ait ses limites. La partie est annulée.",
        "Le temps a expiré. J'ai fort à faire avec le linge de Monsieur Bruce."
    ],
    "quiz_questions": [
        {
            "q": "De quel super-héros Alfred Pennyworth est-il le fidèle majordome ?",
            "choices": ["Batman", "Iron Man", "Spider-Man", "Superman"],
            "answer_idx": 0,
            "flavor": "Batman ! Je veille sur Monsieur Bruce depuis son plus jeune âge."
        },
        {
            "q": "Quel est le nom de famille d'Alfred dans l'univers de Batman ?",
            "choices": ["Wayne", "Grayson", "Pennyworth", "Gordon"],
            "answer_idx": 2,
            "flavor": "Pennyworth. Alfred Pennyworth, à votre service."
        },
        {
            "q": "Dans quelle ville se déroulent principalement les aventures de Batman ?",
            "choices": ["Metropolis", "Gotham City", "Central City", "Star City"],
            "answer_idx": 1,
            "flavor": "Gotham City. Une ville bien sombre, qui aurait bien besoin d'un coup de balai."
        },
        {
            "q": "Quel est le nom de la demeure ancestrale de la famille Wayne ?",
            "choices": ["Le Manoir Wayne (Wayne Manor)", "La Batcave", "La Tour Wayne", "L'Asile d'Arkham"],
            "answer_idx": 0,
            "flavor": "Le Manoir Wayne. Une bien grande bâtisse à entretenir seul !"
        },
        {
            "q": "Avant d'être majordome, dans quel corps d'armée ou service Alfred a-t-il servi ?",
            "choices": ["La Royal Navy", "Le SAS (Forces Spéciales Britanniques / MI6)", "La CIA", "Les Pompiers de Londres"],
            "answer_idx": 1,
            "flavor": "Le SAS et les services secrets britanniques (MI6). J'y ai appris quelques tours utiles."
        },
        {
            "q": "Quel est le pire ennemi de Batman, le clown prince du crime ?",
            "choices": ["Double-Face", "Le Joker", "Le Pingouin", "L'Épouvantail"],
            "answer_idx": 1,
            "flavor": "Le Joker. Un individu d'un goût fort douteux."
        },
        {
            "q": "Comment s'appelle l'asile psychiatrique où sont enfermés les criminels de Gotham ?",
            "choices": ["L'Asile d'Arkham", "L'Hôpital Général", "La Prison de Blackgate", "Le pénitencier de Belle Reve"],
            "answer_idx": 0,
            "flavor": "L'Asile d'Arkham. Un endroit fort peu recommandable et aux serrures bien fragiles."
        },
        {
            "q": "Quel est le nom du premier Robin, devenu plus tard Nightwing ?",
            "choices": ["Dick Grayson", "Jason Todd", "Tim Drake", "Damian Wayne"],
            "answer_idx": 0,
            "flavor": "Dick Grayson. Un jeune homme charmant et très agile."
        },
        {
            "q": "Quelle boisson chaude Alfred sert-il le plus souvent à Monsieur Bruce au retour de ses patrouilles ?",
            "choices": ["Du café noir", "Du chocolat chaud", "Du thé (Earl Grey)", "De la camomille"],
            "answer_idx": 2,
            "flavor": "Du thé, généralement du Earl Grey bien chaud."
        },
        {
            "q": "Comment s'appelle le commissaire de police de Gotham, grand allié de Batman ?",
            "choices": ["Harvey Dent", "James Gordon", "Lucius Fox", "Harvey Bullock"],
            "answer_idx": 1,
            "flavor": "Le commissaire James Gordon. Un homme intègre, denrée rare à Gotham."
        },
        {
            "q": "Quelle actrice incarne Catwoman dans le film 'The Dark Knight Rises' ?",
            "choices": ["Michelle Pfeiffer", "Halle Berry", "Anne Hathaway", "Zoe Kravitz"],
            "answer_idx": 2,
            "flavor": "Anne Hathaway. Elle avait un port de tête tout à fait gracieux."
        },
        {
            "q": "Quel est le nom du véhicule blindé ultra-rapide de Batman ?",
            "choices": ["La Batmobile", "Le Batwing", "Le Bat-Pod", "Le Tumbler"],
            "answer_idx": 0,
            "flavor": "La Batmobile. Une mécanique impressionnante, bien que bruyante."
        },
        {
            "q": "Quel déguisement de chauve-souris Bruce Wayne a-t-il choisi pour effrayer les criminels ?",
            "choices": ["Le Batcostume (Batsuit)", "Une cape noire simple", "Un masque de cuir", "Une armure de fer"],
            "answer_idx": 0,
            "flavor": "Le Batcostume. Le Kevlar s'avère fort difficile à détacher lors de la lessive."
        },
        {
            "q": "Dans la mythologie classique, qui est le dieu du soleil ?",
            "choices": ["Apollon", "Zeus", "Poséidon", "Hadès"],
            "answer_idx": 0,
            "flavor": "Apollon. Monsieur Bruce préfère toutefois l'obscurité."
        },
        {
            "q": "Quel détective de fiction a été créé par l'écrivain Arthur Conan Doyle ?",
            "choices": ["Hercule Poirot", "Sherlock Holmes", "Arsène Lupin", "Jules Maigret"],
            "answer_idx": 1,
            "flavor": "Sherlock Holmes. Un esprit analytique admirable, habitant le 221B Baker Street."
        }
    ]
}
