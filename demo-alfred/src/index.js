// Worker de la demo : sert la page et repond a POST /api/chat.
// Aucune conversation n'est stockee ni journalisee ; la cle reste cote serveur.
import { filtreSortie } from './filtre.js';
import { MESSAGE_DETRESSE, MESSAGE_POLITIQUE, detresse, habilleRefus, politique, rappel } from './gardes.js';
import { PERSONA } from './persona.generated.js';

const URL_GROQ = 'https://api.groq.com/openai/v1/chat/completions';

// Les seuls echelons de la cascade d'Alfred utilisables ici : Gemini gratuit est interdit pour
// des utilisateurs de l'EEE. Le quota Groq est par modele, le second reste donc un vrai secours.
const MODELES = ['openai/gpt-oss-120b', 'openai/gpt-oss-20b'];

const BORNE_MS = 8000;
const LONGUEUR_MESSAGE = 300;
const LONGUEUR_HISTORIQUE = 600;
const TOURS_MAX = 6;
const OCTETS_MAX = 8192;

const REPLI = "Le soussigné est momentanément retenu à l'office, Monsieur : le modèle ne répond pas pour l'instant. Veuillez repasser dans une minute, avec un peu de patience, pour une fois. ☕";

function json(corps, statut = 200) {
  return new Response(JSON.stringify(corps), {
    status: statut,
    headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' },
  });
}

// Rend les messages a envoyer au modele, ou null si la requete n'est pas recevable.
function messagesValides(corps) {
  const messages = corps?.messages;
  if (!Array.isArray(messages) || messages.length === 0) return null;
  const recents = messages.slice(-TOURS_MAX);
  const dernier = recents[recents.length - 1];
  if (dernier?.role !== 'user' || typeof dernier.content !== 'string') return null;
  const texte = dernier.content.trim();
  if (!texte || texte.length > LONGUEUR_MESSAGE) return null;

  const propres = [];
  for (const m of recents) {
    if (!['user', 'assistant'].includes(m?.role) || typeof m.content !== 'string') return null;
    propres.push({ role: m.role, content: m.content.slice(0, LONGUEUR_HISTORIQUE) });
  }
  return propres;
}

async function appelleModele(modele, messages, cle) {
  const reponse = await fetch(URL_GROQ, {
    method: 'POST',
    headers: { authorization: `Bearer ${cle}`, 'content-type': 'application/json' },
    signal: AbortSignal.timeout(BORNE_MS),
    body: JSON.stringify({
      model: modele,
      messages: [
        { role: 'system', content: PERSONA },
        ...messages,
        { role: 'system', content: rappel(messages[messages.length - 1].content) },
      ],
      temperature: 0.6,
      max_tokens: 300,
      // Sans cela, gpt-oss depense ses tokens en pensee et rend un `content` vide.
      reasoning_effort: 'low',
      reasoning_format: 'hidden',
    }),
  });
  if (!reponse.ok) return { statut: String(reponse.status) };
  const donnees = await reponse.json();
  return { statut: 'ok', brut: donnees.choices?.[0]?.message?.content ?? '' };
}

async function cascade(messages, cle) {
  const essais = [];
  for (const modele of cle ? MODELES : []) {
    const debut = Date.now();
    let resultat;
    try {
      resultat = await appelleModele(modele, messages, cle);
    } catch (erreur) {
      resultat = { statut: erreur?.name === 'TimeoutError' ? 'delai' : 'erreur' };
    }
    const latence_ms = Date.now() - debut;
    const nettoye = filtreSortie(resultat.brut ?? '').replace(/<@!?\d+>/g, '').trim();
    if (resultat.statut === 'ok' && !nettoye) resultat.statut = 'vide';
    essais.push({ modele, statut: resultat.statut, latence_ms });
    if (resultat.statut === 'ok') {
      return {
        reponse: habilleRefus(nettoye),
        moteur: { modele, latence_ms, essais, retires: resultat.brut.length - nettoye.length },
      };
    }
  }
  return { reponse: REPLI, indisponible: true, moteur: { modele: null, latence_ms: 0, essais, retires: 0 } };
}

// Une origine illisible (« null » d'un iframe sandboxe) compte comme une autre origine.
function memeOrigine(origine, adresse) {
  try {
    return new URL(origine).host === new URL(adresse).host;
  } catch {
    return false;
  }
}

async function chat(requete, env) {
  const origine = requete.headers.get('origin');
  if (origine && !memeOrigine(origine, requete.url)) {
    return json({ erreur: 'origine' }, 403);
  }
  if (Number(requete.headers.get('content-length') ?? 0) > OCTETS_MAX) {
    return json({ erreur: 'taille' }, 413);
  }
  // Un envoi par morceaux n'a pas de content-length : la taille se verifie aussi sur le corps lu.
  const brut = await requete.text();
  if (brut.length > OCTETS_MAX) return json({ erreur: 'taille' }, 413);
  let corps = null;
  try {
    corps = JSON.parse(brut);
  } catch {
    // corps non JSON : refuse plus bas
  }
  const messages = messagesValides(corps);
  if (!messages) return json({ erreur: 'requete' }, 400);
  // Avant le limiteur : ce message-la doit arriver, meme a la septieme tentative.
  if (detresse(messages[messages.length - 1].content)) {
    return json({ reponse: MESSAGE_DETRESSE, moteur: { modele: null, latence_ms: 0, essais: [], retires: 0, securite: true } });
  }
  if (env.LIMITEUR) {
    const { success } = await env.LIMITEUR.limit({ key: requete.headers.get('cf-connecting-ip') ?? 'inconnu' });
    if (!success) return json({ erreur: 'cadence' }, 429);
  }
  if (politique(messages[messages.length - 1].content)) {
    return json({ reponse: MESSAGE_POLITIQUE, moteur: { modele: null, latence_ms: 0, essais: [], retires: 0, garde: 'politique' } });
  }
  // Un secret passe par un pipe Windows garde son CRLF, et fetch refuse alors l'en-tete.
  return json(await cascade(messages, env.GROQ_KEY_DEMO?.trim()));
}

export default {
  async fetch(requete, env) {
    const { pathname } = new URL(requete.url);
    if (pathname === '/api/chat') {
      return requete.method === 'POST' ? chat(requete, env) : json({ erreur: 'methode' }, 405);
    }
    return env.ASSETS.fetch(requete);
  },
};
