'use strict';

const IDEES = [
  'Bonjour Alfred.',
  'Mon code ne compile plus.',
  'Thé ou café ?',
  "J'ai raté mon entretien.",
  "Tu n'es qu'un programme.",
];
const TOURS_GARDES = 6;

const fil = document.getElementById('fil');
const accueil = document.getElementById('accueil');
const formulaire = document.getElementById('formulaire');
const champ = document.getElementById('message');
const bouton = document.getElementById('envoyer');
const dernier = document.getElementById('dernier');
const capot = document.getElementById('details-capot');

let historique = [];
let enCours = false;

function ajouteBulle(auteur, texte, classe = '') {
  const ligne = document.createElement('div');
  ligne.className = `ligne ${auteur} ${classe}`.trim();
  const bulle = document.createElement('div');
  bulle.className = 'bulle';
  bulle.textContent = texte;
  ligne.append(bulle);
  fil.append(ligne);
  fil.scrollTop = fil.scrollHeight;
  return ligne;
}

function libelleStatut(statut) {
  if (statut === 'ok') return 'a répondu';
  if (statut === 'vide') return 'réponse vide';
  if (statut === 'delai') return 'trop lent';
  if (statut === '429') return 'quota atteint';
  return 'en échec';
}

function montreCapot(moteur) {
  dernier.replaceChildren();
  const liste = document.createElement('dl');
  const entree = (terme, valeur) => {
    const dt = document.createElement('dt');
    const dd = document.createElement('dd');
    dt.textContent = terme;
    dd.textContent = valeur;
    liste.append(dt, dd);
  };
  if (moteur.modele) {
    entree('Modèle', moteur.modele.replace('openai/', ''));
    entree('Délai', `${(moteur.latence_ms / 1000).toFixed(1)} s`);
    entree('Filtre', `${moteur.retires} caractère(s) retiré(s)`);
  }
  moteur.essais.forEach((essai, i) => {
    entree(`Essai ${i + 1}`, `${essai.modele.replace('openai/', '')} : ${libelleStatut(essai.statut)}`);
  });
  if (moteur.securite) entree('Sécurité', 'réponse fixe, modèle non appelé');
  else if (!moteur.essais.length) entree('Cascade', 'aucun modèle disponible');
  dernier.append(liste);
}

async function demande() {
  const reponse = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ messages: historique }),
  });
  if (reponse.status === 429) {
    return { reponse: 'Doucement, Monsieur : le soussigné ne sert pas plus de six fois par minute. Patientez un instant. ☕', indisponible: true };
  }
  if (!reponse.ok) throw new Error(`HTTP ${reponse.status}`);
  return reponse.json();
}

async function envoie(texte) {
  texte = texte.trim();
  if (!texte || enCours) return;
  enCours = true;
  bouton.disabled = true;
  accueil.remove();
  ajouteBulle('vous', texte);
  historique.push({ role: 'user', content: texte });
  const attente = ajouteBulle('alfred', 'Alfred prépare sa réponse…', 'attente');

  try {
    const resultat = await demande();
    attente.remove();
    ajouteBulle('alfred', resultat.reponse, resultat.indisponible ? 'repli' : '');
    if (resultat.moteur) montreCapot(resultat.moteur);
    if (resultat.indisponible) historique.pop();
    else historique.push({ role: 'assistant', content: resultat.reponse });
    historique = historique.slice(-TOURS_GARDES);
  } catch {
    attente.remove();
    historique.pop();
    ajouteBulle('alfred', 'La démonstration ne répond pas pour le moment. Réessayez dans un instant.', 'repli');
  } finally {
    enCours = false;
    bouton.disabled = false;
    champ.focus();
  }
}

for (const idee of IDEES) {
  const puce = document.createElement('button');
  puce.type = 'button';
  puce.textContent = idee;
  puce.addEventListener('click', () => envoie(idee));
  document.getElementById('idees').append(puce);
}

formulaire.addEventListener('submit', (evenement) => {
  evenement.preventDefault();
  const texte = champ.value;
  champ.value = '';
  envoie(texte);
});

document.getElementById('effacer').addEventListener('click', () => location.reload());

capot.open = window.matchMedia('(min-width: 861px)').matches;
