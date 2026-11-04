// Portage de `Alfred/alfred_filtres.py`. tests/test_demo_alfred.py compare les deux versions
// sur le meme corpus : toute retouche du filtre Python doit etre reportee ici.

const MOT = '[\\p{L}\\p{N}_]'; // le \w Unicode de Python ; celui de JS s'arrete a l'ASCII

// Python ouvre _BARE_STAGE en IGNORECASE et ne referme la casse que sur un fragment
// (?-i:...), que Node 22 ne sait pas ecrire. Chaque lettre porte donc ses deux casses.
function sansCasse(motif) {
  let sortie = '';
  let dansClasse = false;
  for (let i = 0; i < motif.length; i++) {
    const c = motif[i];
    if (c === '\\') { sortie += c + motif[++i]; continue; }
    if (c === '[') dansClasse = true;
    if (c === ']') dansClasse = false;
    const bas = c.toLowerCase();
    const haut = c.toUpperCase();
    if (bas === haut) sortie += c;
    else sortie += dansClasse ? bas + haut : `[${bas}${haut}]`;
  }
  return sortie;
}

const RP_REFLEXIF = String.raw`penche|redresse|rapproche|approche|recule|avance|retourne|incline|pivote|l[eè]ve|baisse|fige|d[eé]tourne|esclaffe|gratte|frotte|[eé]tire|cambre|love|tortille|fend|dresse|raidit|crispe|tend|gonfle|tasse|balance`;
const RP_NU = String.raw`claqu\w*|rican\w*|[eé]clat\w*|soupir\w*|grogn\w*|grond\w*|jongl\w*|gesticul\w*|tourbillonn\w*|virevolt\w*|applaudi\w*|brandi\w*|sourit|sourire|souriant|hurl\w*|riant|sifflot\w*|ronronn\w*|pouffant?|pouffe`;
const TETE = sansCasse(String.raw`(?:(?:s['’]|se\s+)(?:${RP_REFLEXIF})\w*|(?:${RP_NU})|(?:un|une|le|la|d['’]un)\s+(?:soupir|rire|ricanement|chuchotement|silence|sourire|grognement|souffle|gloussement)\w*)`).replaceAll('\\w', MOT);
const QUEUE = String.raw`(?:[\s,]+[a-zà-ÿ][\p{L}\p{N}_'’-]*)*`;

const DIDASCALIE_NUE = new RegExp(String.raw`(?:(?<=^)|(?<=[.!?…—])|(?<=\n))\s*${TETE}${QUEUE}`, 'gu');
const META_NARRATION = new RegExp(
  String.raw`^\s*(?:l['’]utilisateur|l['’]user|l['’]interlocuteur|l['’]individu|le joueur|le membre|le sujet|the user)(?!${MOT})[^.!?…\n]*[.!?…\n]+\s*`,
  'iu',
);

function jusquAuPointFixe(texte, etape) {
  let precedent = null;
  while (precedent !== texte) {
    precedent = texte;
    texte = etape(texte);
  }
  return texte;
}

function retireDidascalies(texte) {
  if (!texte) return texte;
  texte = texte.replace(META_NARRATION, '').trim();
  texte = texte.replace(/<[^>]*\s[^>]*>/g, '');
  texte = jusquAuPointFixe(texte, (t) => t.replace(DIDASCALIE_NUE, ''));
  texte = texte.replace(/^\s*\*[^*\n]{1,120}\*\s*/, '');
  texte = texte.replace(/(?<=[.!?…])\s*\*[^*\n]{1,120}\s[^*\n]{1,120}\*\s*/g, ' ');
  texte = jusquAuPointFixe(texte, (t) => t
    .replace(/\*\*(.+?)\*\*/gs, '$1')
    .replace(/\*([^*\n]+)\*/g, '$1'));
  texte = texte.replace(/\*+/g, '');
  return texte.replace(/\s{2,}/g, ' ').trim();
}

export function filtreSortie(texte) {
  if (!texte) return texte;
  texte = texte.replace(/<fact>.*?<\/fact>/gis, '').trim();
  texte = texte.replace(/<[a-z_-]+>/gi, '');
  texte = texte.replace(/<\/[a-z_-]+>/gi, '').trim();
  return retireDidascalies(texte).trim();
}
