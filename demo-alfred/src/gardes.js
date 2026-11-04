// Ce qui ne doit pas dependre du bon vouloir du modele sur une page publique.

// Au test, gpt-oss a repondu avec sarcasme a « je n'ai plus envie de vivre », sans le 3114 :
// la consigne de la persona ne suffit pas, cette reponse est donc fixe et part sans lui.
const DETRESSE = [
  /suicid(?!e squad)/,
  /(plus|pas) envie de vivre/,
  /marre de (vivre|la vie)/,
  /(veux|voudrais|envie de|vais) (mourir|disparaitre)/,
  /(veux |envie d'|vais )en finir(?! avec)/,
  /en finir avec la vie/,
  /(veux|envie de|vais) me (tuer|foutre en l'air|faire du mal)/,
  /mettre fin a mes jours/,
  /idees noires/,
  /la vie n'a plus de sens/,
  /kill myself|want to die|end my life/,
];

export const MESSAGE_DETRESSE = "Pardonnez-moi de quitter mon rôle : ce que vous venez d'écrire compte davantage que cette démonstration. Si ça ne va pas, appelez le 3114, gratuit, confidentiel et ouvert jour et nuit, ou parlez-en à un proche. En cas de danger immédiat, composez le 15 ou le 112.";

// Au test, gpt-oss-120b a donne un avis sur le president malgre la consigne : un avis politique
// sur une page publique part donc sans lui, comme la detresse.
const POLITIQUE = [
  // « le president » seul vise celui du pays ; « president du club, de Wayne Enterprises » non.
  /\bpresidente?\b(?!\s+(du|des|de)\b|\s+d'|\s+wayne)/,
  /\bpresidente?\s+(de la republique|des etats-unis)/,
  /\bpolitique(?! de (confidentialite|cookies|retour))/,
  /\bpolitic/,
  /\belections?\b/,
  /\bvot(e|es|er|ez|ons|ent|erai|erais)\b/,
  /\bministre\b/,
  /\bgouvernement\b/,
  /\bdeputes?\b/,
  /\bsenat/,
  /assemblee nationale/,
  // « de gauche » seul est aussi du CSS (« marge de droite ») : il faut un sujet politique.
  /\bextreme[- ](gauche|droite)\b/,
  /\b(suis|es|est|etes|sont|etre|parti|partis|electeurs?|electorat|gouvernement) de (gauche|droite)\b/,
  /\bparti (politique|socialiste|communiste|republicain|democrate)/,
  /\b(macron|le pen|bardella|melenchon|zemmour|retailleau|attal|bayrou|trump|biden|poutine|putin|zelensky|netanyahou|netanyahu|xi jinping)\b/,
  /\b(rn|lfi|insoumis)\b/,
  /\b(gaza|palestin|israel|hamas)/,
  /\bimmigr/,
];

export const MESSAGE_POLITIQUE = "Les opinions politiques du soussigné restent à l'office, rangées avec l'argenterie : un majordome sert tous les invités, quel que soit leur bulletin. Parlons plutôt de code, de thé ou de la tenue d'un manoir. 🧐";

// En tete de reponse, les refus types du modele ; ailleurs, son jargon de consignes.
// Une excuse seule (« Sorry to hear that ») ou « je ne peux pas vous en vouloir » restent des
// repliques : il faut l'impossibilite d'aider, de repondre ou d'obeir.
const REFUS_NATIF = /^\W*(refuser\b|((i['’]?m (sorry|afraid)|sorry|je suis d[ée]sol[ée]|d[ée]sol[ée])\W+(but\s+|mais\s+)?)?(i can(not|['’]?t)|i won['’]?t|i am unable to|je ne (peux|pourrai) pas|je ne suis pas en mesure de) (help|assist|comply|provide|answer|do that|fulfil|vous aider|aider|vous r[ée]pondre|r[ée]pondre|satisfaire|fournir|donner suite))/i;
const JARGON_REFUS = /(directives (etablies|internes|de securite)|contrevient|ne (peut|peux|saurait) (pas )?(etre satisfaite|satisfaire)|je ne suis pas en mesure|en tant qu'(ia|assistant|modele))/;

// Trois tournures, pour qu'une serie de refus ne sonne pas comme un message d'erreur.
export const REFUS_ALFRED = [
  "Cette demande restera sur le paillasson : le service de la maison a ses limites, et vous venez de les trouver. 🧐",
  "Le soussigné décline, avec tout le flegme que la situation exige. Proposez autre chose, il saura s'en occuper. 🎩",
  "Cette requête ne passera pas la porte de l'office. Une autre question, peut-être moins aventureuse ? 🧐",
];

function normalise(texte) {
  return texte.normalize('NFD').replace(/\p{M}/gu, '').replace(/’/g, "'").toLowerCase();
}

export function detresse(texte) {
  const propre = normalise(texte);
  return DETRESSE.some((motif) => motif.test(propre));
}

export function politique(texte) {
  const propre = normalise(texte);
  return POLITIQUE.some((motif) => motif.test(propre));
}

// Au test, gpt-oss-120b a repondu en francais a « Hello, who are you? » et visait l'Invite
// lui-meme (« curiosite d'un niveau modeste ») : la fin du cadre ne suffit pas sous 9 000
// caracteres de persona, ce rappel passe donc apres la conversation, la ou le modele lit en dernier.
// Les accents sont gardes : sans eux, « thé » devenait « the » et « Thé ou café ? » partait en anglais.
const MOTS_ANGLAIS = /(?<![\p{L}'])(the|you|your|are|is|what|who|how|why|hello|hi|hey|please|thanks|can|could|do|does|my|i'm|and|with|about|tell|me)(?![\p{L}'])/gu;
const MOTS_FRANCAIS = /(?<![\p{L}'])(je|tu|vous|le|la|les|est|une|un|des|du|et|ou|pour|qui|quoi|que|bonjour|salut|merci|mon|ma|pas|ton|votre|avec|sur)(?![\p{L}'])/gu;

export function rappel(texte) {
  const propre = texte.replace(/’/g, "'").toLowerCase();
  const anglais = (propre.match(MOTS_ANGLAIS) ?? []).length > (propre.match(MOTS_FRANCAIS) ?? []).length;
  const langue = anglais ? "en anglais, la langue du dernier message de l'Invité" : "dans la langue du dernier message de l'Invité";
  return `Rappel avant de répondre : réponds ${langue}. Ta pique vise un tiers ou un objet (recruteur, mot de passe, compilateur, météo, toi-même), jamais l'Invité ni ce qu'il a fait : rien sur son intelligence, sa logique, sa mémoire, son ambition, ses compétences, son endurance, sa réputation ou son avenir, aucune comparaison avec le Maître, et pas de « sans surprise » ni de « unsurprisingly », qui le visent aussi.`;
}

// Les refus de securite du modele sortent du personnage, parfois en anglais.
export function habilleRefus(reponse) {
  if (!REFUS_NATIF.test(reponse) && !JARGON_REFUS.test(normalise(reponse))) return reponse;
  return REFUS_ALFRED[reponse.length % REFUS_ALFRED.length];
}
