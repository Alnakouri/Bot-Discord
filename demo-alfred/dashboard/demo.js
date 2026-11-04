// Faux backend de la démo publique du dashboard : charge AVANT app.js, il remplace fetch
// et WebSocket. Tout est inventé et vit en mémoire ; recharger la page remet tout à zéro.
// Aucune requête ne sort : la CSP de /dashboard/ interdit de toute façon le réseau.
(() => {
  const BOTS = ['sheogorath', 'maiq', 'alfred', 'johnny', 'sugar', 'malena'];
  const NOMS = {
    sheogorath: '🧀 Sheogorath', maiq: "🐱 M'aiq le Menteur", alfred: '☕ Alfred Pennyworth',
    johnny: '🔫 Johnny Silverbot', sugar: 'Sugar Bot', malena: '💃 Malena la Gitana',
  };
  const COULEURS = {
    sheogorath: '#d946ef', maiq: '#f97316', alfred: '#475569',
    johnny: '#22c55e', sugar: '#0ea5e9', malena: '#f43f5e',
  };

  const maintenant = () => Date.now();
  const iso = (ms) => new Date(ms - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 19);
  const minutes = (n) => n * 60000;
  const DEBUT = maintenant();

  // --- État ------------------------------------------------------------------------------

  const bots = Object.fromEntries(BOTS.map((id, i) => [id, {
    running: id !== 'malena',
    depuis: DEBUT - minutes([1460, 1385, 2890, 615, 4310, 0][i]),
    cpu: ['2.4%', '1.1%', '3.8%', '1.7%', '0.9%', '0%'][i],
    ram: ['182 Mo', '141 Mo', '205 Mo', '163 Mo', '128 Mo', '0 Mo'][i],
  }]));

  const erreurs = [
    { id: 41, bot_name: 'johnny', error_type: 'RateLimitError', severity: 'WARNING', il_y_a: 38, resolved: false,
      category: 'Quota API', auto_diagnosis: "Le fournisseur principal a répondu 429 : le quota de jetons par minute est atteint.",
      suggested_fix: "Rien à faire : la cascade est passée au modèle suivant. Si cela se répète, espacer les réponses automatiques.",
      context: { module: 'llm_cascade', funcName: 'appeler', lineno: 212 } },
    { id: 40, bot_name: 'sheogorath', error_type: 'TimeoutError', severity: 'CRITICAL', il_y_a: 170, resolved: false,
      category: 'Réseau', auto_diagnosis: "La synthèse vocale n'a pas répondu en 8 secondes ; le message est parti sans audio.",
      suggested_fix: "Vérifier que le conteneur de voix tourne, puis redémarrer le bot si le délai persiste.",
      context: { module: 'voix', funcName: 'synthetiser', lineno: 88 } },
    { id: 37, bot_name: 'alfred', error_type: 'JSONDecodeError', severity: 'WARNING', il_y_a: 1310, resolved: true,
      category: 'Données', auto_diagnosis: "Le fichier de mémoire était tronqué après un arrêt brutal.",
      suggested_fix: "La sauvegarde de la veille a été rechargée. Écrire dans un fichier temporaire puis renommer.",
      context: { module: 'memoire', funcName: 'charger', lineno: 47 } },
  ];

  const cles = [
    { api_name: 'groq', api_key_display: 'groq-1 ••••7Q2c', status: 'active', total_calls: 412, error_count: 3, last_error: '' },
    { api_name: 'groq', api_key_display: 'groq-2 ••••Lm8x', status: 'cooldown', total_calls: 268, error_count: 11, last_error: '429 Too Many Requests' },
    { api_name: 'groq', api_key_display: 'groq-3 ••••p0Za', status: 'active', total_calls: 197, error_count: 0, last_error: '' },
    { api_name: 'mistral', api_key_display: 'mistral-1 ••••Ww4e', status: 'active', total_calls: 84, error_count: 1, last_error: '' },
    { api_name: 'ollama', api_key_display: 'local', status: 'active', total_calls: 36, error_count: 0, last_error: '' },
  ];

  const audit = [
    { il_y_a: 12, action: 'BOT_RESTART', bot_name: 'johnny', details: 'Redémarrage après changement de configuration Twitch' },
    { il_y_a: 95, action: 'FEATURE_UPDATE', bot_name: 'sheogorath', details: 'decret_enabled → true' },
    { il_y_a: 240, action: 'BOT_STOP', bot_name: 'malena', details: 'Maintenance de la persona' },
    { il_y_a: 610, action: 'TESTMODE_UPDATE', bot_name: null, details: 'Mode test désactivé' },
    { il_y_a: 1440, action: 'LOGIN', bot_name: null, details: 'Connexion depuis le réseau local' },
  ];

  const twitch = Object.fromEntries(BOTS.map((id) => [id, { enabled: false, poll_interval_seconds: 120, subscriptions: [] }]));
  twitch.sheogorath = { enabled: true, poll_interval_seconds: 90, subscriptions: [
    { twitch_login: 'manoir_des_ombres', discord_channel_id: 'annonces-live', custom_message: 'Le fromage est servi : {streamer} est en direct !' },
    { twitch_login: 'atelier_pixel', discord_channel_id: 'annonces-live', custom_message: null },
  ] };
  twitch.alfred = { enabled: true, poll_interval_seconds: 120, subscriptions: [
    { twitch_login: 'manoir_des_ombres', discord_channel_id: 'le-salon', custom_message: 'Le Maître est en direct. Le thé est servi.' },
  ] };

  const chat = Object.fromEntries(BOTS.map((id) => [id, {
    events: true, interjections: id !== 'alfred', greetings: true, viewer_memory: true, game_qa: id === 'sheogorath', eventsub: false,
  }]));
  const canaux = Object.fromEntries(BOTS.map((id) => [id, id === 'sheogorath' ? ['manoir_des_ombres'] : []]));
  const cohosts = Object.fromEntries(BOTS.map((id) => [id, []]));
  const liens = Object.fromEntries(BOTS.map((id) => [id, [
    { cmd: 'github', url: 'https://github.com/Alnakouri', label: 'GitHub', message: 'Le code est par ici : {url}', aliases: ['code'], auto_minutes: 0, auto_min_messages: 5 },
  ]]));
  const recompenses = Object.fromEntries(BOTS.map((id) => [id, id === 'sheogorath' ? { 'Décret du jour': 'decret', 'Fromage gratuit': 'fromage' } : {}]));
  const classement = [
    { name: 'Lune_Rousse', points: 1840 }, { name: 'PixelNomade', points: 1325 },
    { name: 'CapitaineThe', points: 990 }, { name: 'Brindille42', points: 615 },
  ];
  const ecoute = Object.fromEntries(BOTS.map((id) => [id, { enabled: false, mode: 'C', device: 'cpu', chunk_ms: 160, min_interval: 45 }]));
  const fonctions = Object.fromEntries(BOTS.map((id) => [id, { decret_enabled: id === 'sheogorath', repartee_lessons_enabled: true, test_mode: false }]));
  const modeTest = { test_mode: false, test_guild_id: 'serveur-prive' };

  // --- Logs --------------------------------------------------------------------------------

  const MESSAGES = {
    INFO: [
      'Réponse envoyée en 1,4 s (groq, 312 jetons)', 'Message reçu dans #general', 'Mémoire sauvegardée (48 souvenirs)',
      'Cascade : modèle principal disponible', 'Statut Discord mis à jour', 'Vérification Twitch : aucun live en cours',
    ],
    WARNING: ['Quota proche de la limite : passage au modèle suivant', 'Réponse coupée par le filtre de sortie', 'Délai de synthèse vocale élevé (6,8 s)'],
    ERROR: ['Appel API refusé (429), nouvel essai dans 20 s'],
  };
  let graine = 7;
  const hasard = () => { graine = (graine * 16807) % 2147483647; return graine / 2147483647; };
  const choisir = (liste) => liste[Math.floor(hasard() * liste.length)];
  const faireLog = (ms) => {
    const actifs = BOTS.filter((id) => bots[id].running);
    const tirage = hasard();
    const level = tirage < 0.8 ? 'INFO' : tirage < 0.95 ? 'WARNING' : 'ERROR';
    return { timestamp: iso(ms), bot: choisir(actifs), level, message: choisir(MESSAGES[level]) };
  };
  const historique = Array.from({ length: 80 }, (_, i) => faireLog(DEBUT - (80 - i) * 37000));

  // --- Routes ------------------------------------------------------------------------------

  const ok = (corps = { success: true }) => ({ status: 200, corps });
  const statut = (id) => {
    const b = bots[id];
    return {
      id, display: NOMS[id], color: COULEURS[id], status: b.running ? 'running' : 'stopped',
      uptime: b.running ? Math.floor((maintenant() - b.depuis) / 1000) : 0, cpu: b.running ? b.cpu : '0%', ram: b.running ? b.ram : '0 Mo',
    };
  };
  const tracer = (action, bot_name, details) => audit.unshift({ il_y_a: 0, quand: maintenant(), action, bot_name, details });

  const routes = [
    ['GET', /^\/api\/me$/, () => ok({ authenticated: true })],
    ['GET', /^\/api\/health$/, () => ok({ status: 'ok' })],
    ['GET', /^\/api\/bots$/, () => ok(BOTS.map(statut))],
    ['POST', /^\/api\/bots\/(\w+)\/(start|stop|restart)$/, ([id, action]) => {
      const b = bots[id];
      if (!b) return { status: 404, corps: { detail: 'Bot inconnu' } };
      if (action === 'start' && b.running) return ok({ success: false, error: 'Bot déjà en cours' });
      if (action === 'stop' && !b.running) return ok({ success: false, error: 'Bot non en cours' });
      b.running = action !== 'stop';
      if (b.running) { b.depuis = maintenant(); if (b.cpu === '0%') { b.cpu = '1.3%'; b.ram = '150 Mo'; } }
      tracer(`BOT_${action.toUpperCase()}`, id, 'Action simulée (démo)');
      return ok();
    }],
    ['GET', /^\/api\/logs$/, (_, q) => ok({ data: historique
      .filter((l) => (!q.get('bot') || l.bot === q.get('bot')) && (!q.get('level') || l.level === q.get('level')))
      .slice(-200).reverse() })],
    ['GET', /^\/api\/errors\/count$/, () => ok(erreurs.filter((e) => !e.resolved && e.il_y_a < 1440).length)],
    ['GET', /^\/api\/errors$/, (_, q) => ok(erreurs
      .filter((e) => e.resolved === (q.get('resolved') === 'true'))
      .map((e) => ({ ...e, timestamp: iso(DEBUT - minutes(e.il_y_a)) })))],
    ['POST', /^\/api\/errors\/analyze$/, (_, q) => {
      const e = erreurs.find((x) => x.id === Number(q.get('error_id')));
      return e ? ok(e) : { status: 404, corps: { detail: 'Erreur inconnue' } };
    }],
    ['POST', /^\/api\/errors\/(\d+)\/resolve$/, ([id]) => {
      const e = erreurs.find((x) => x.id === Number(id));
      if (e) e.resolved = true;
      return ok();
    }],
    ['GET', /^\/api\/api-usage$/, () => {
      const by_api = {};
      for (const k of cles) {
        const p = (by_api[k.api_name] ??= { calls: 0, tentes: 0, errors: 0 });
        p.calls += k.total_calls; p.tentes += k.total_calls; p.errors += k.error_count;
      }
      return ok({ by_api });
    }],
    ['GET', /^\/api\/api-usage\/keys$/, () => ok(cles)],
    ['GET', /^\/api\/conversations\/activity$/, () => {
      const heure = new Date(); heure.setMinutes(0, 0, 0);
      return ok({ buckets: Array.from({ length: 24 }, (_, i) => {
        const h = new Date(heure.getTime() - (23 - i) * 3600000);
        const creux = Math.abs(((h.getHours() + 20) % 24) - 12) / 12;
        return { hour: iso(h.getTime()).slice(0, 16), count: Math.round(4 + 38 * (1 - creux) + hasard() * 6) };
      }) });
    }],
    ['GET', /^\/api\/conversations$/, () => ok({ unique_users: 37, by_bot: {
      sheogorath: { messages: 412 }, maiq: { messages: 268 }, alfred: { messages: 351 },
      johnny: { messages: 297 }, sugar: { messages: 143 }, malena: { messages: 86 },
    } })],
    ['POST', /^\/api\/reports\/generate$/, (_, q) => ok({ filename: `rapport-demo-${q.get('scope')}.md`, content: rapport(q) })],
    ['GET', /^\/api\/audit-logs$/, () => ok(audit.map((a) => ({
      timestamp: iso(a.quand ?? DEBUT - minutes(a.il_y_a)), user: 'admin', action: a.action, bot_name: a.bot_name, details: a.details,
    })))],
    ['GET', /^\/api\/twitch$/, () => ok(twitch)],
    ['PUT', /^\/api\/twitch\/all$/, (_, __, c) => { BOTS.forEach((id) => { twitch[id].enabled = !!c.enabled; }); return ok(); }],
    ['POST', /^\/api\/twitch\/all\/subscriptions$/, (_, __, c) => {
      const added = [], skipped = [];
      for (const id of BOTS) {
        if (twitch[id].subscriptions.some((s) => s.twitch_login === c.twitch_login)) { skipped.push(id); continue; }
        twitch[id].subscriptions.push(c); added.push(id);
      }
      return ok({ added, skipped });
    }],
    ['GET', /^\/api\/twitch\/chat\/(\w+)$/, ([id]) => ok(chat[id])],
    ['PUT', /^\/api\/twitch\/chat\/(\w+)$/, ([id], _, c) => { Object.assign(chat[id], c); return ok(); }],
    ['GET', /^\/api\/twitch\/channels\/(\w+)$/, ([id]) => ok({ chat_channels: canaux[id] })],
    ['PUT', /^\/api\/twitch\/channels\/(\w+)$/, ([id], _, c) => { canaux[id] = c.chat_channels; return ok({ chat_channels: canaux[id] }); }],
    ['GET', /^\/api\/twitch\/cohost\/(\w+)$/, ([id]) => ok({ cohost_channels: cohosts[id] })],
    ['PUT', /^\/api\/twitch\/cohost\/(\w+)$/, ([id], _, c) => { cohosts[id] = c.cohost_channels; return ok({ cohost_channels: cohosts[id] }); }],
    ['GET', /^\/api\/twitch\/links\/(\w+)$/, ([id]) => ok({ link_commands: liens[id] })],
    ['PUT', /^\/api\/twitch\/links\/(\w+)$/, ([id], _, c) => { liens[id] = c.link_commands; return ok({ link_commands: liens[id] }); }],
    ['GET', /^\/api\/twitch\/rewards\/(\w+)$/, ([id]) => ok({ ...recompenses[id] })],
    ['PUT', /^\/api\/twitch\/rewards\/(\w+)$/, ([id], _, c) => { recompenses[id] = c; return ok(); }],
    ['GET', /^\/api\/twitch\/leaderboard\/(\w+)$/, ([id]) => ok(id === 'sheogorath' || id === 'johnny' ? classement : [])],
    ['GET', /^\/api\/twitch\/listen\/(\w+)$/, ([id]) => ok(ecoute[id])],
    ['PUT', /^\/api\/twitch\/listen\/(\w+)$/, ([id], _, c) => { Object.assign(ecoute[id], c); return ok(); }],
    ['PUT', /^\/api\/twitch\/(\w+)$/, ([id], _, c) => { Object.assign(twitch[id], c); return ok(); }],
    ['POST', /^\/api\/twitch\/(\w+)\/subscriptions$/, ([id], _, c) => { twitch[id].subscriptions.push(c); return ok(); }],
    ['DELETE', /^\/api\/twitch\/(\w+)\/subscriptions\/(\d+)$/, ([id, i]) => { twitch[id].subscriptions.splice(Number(i), 1); return ok(); }],
    ['GET', /^\/api\/features\/(\w+)$/, ([id]) => ok(fonctions[id])],
    ['PUT', /^\/api\/features\/all$/, (_, __, c) => { BOTS.forEach((id) => { fonctions[id][c.feature] = c.value; }); return ok(); }],
    ['PUT', /^\/api\/features\/(\w+)$/, ([id], _, c) => {
      fonctions[id][c.feature] = c.value;
      tracer('FEATURE_UPDATE', id, `${c.feature} → ${c.value}`);
      return ok();
    }],
    ['GET', /^\/api\/testmode$/, () => ok({
      global: modeTest,
      guilds: [{ id: 'serveur-prive', name: 'Serveur de test (démo)', bots: BOTS }, { id: 'serveur-public', name: 'Le Manoir (démo)', bots: BOTS }],
      bots: Object.fromEntries(BOTS.map((id) => [id, fonctions[id].test_mode])),
      avertissement: null, bots_vus: BOTS,
    })],
    ['PUT', /^\/api\/testmode$/, (_, __, c) => { Object.assign(modeTest, c); return ok(); }],
    ['POST', /^\/api\/dashboard\/restart$/, () => ok()],
  ];

  function rapport(q) {
    const total = cles.reduce((s, k) => s + k.total_calls, 0);
    const lignes = [
      `# Rapport de diagnostic (démo)`, '', `Période : ${q.get('hours')} h · Périmètre : ${q.get('scope')}`, '',
      '## Bots', ...BOTS.map((id) => `- ${NOMS[id]} : ${bots[id].running ? 'en ligne' : 'hors ligne'}`), '',
      '## Erreurs ouvertes', ...erreurs.filter((e) => !e.resolved).map((e) => `- [${e.severity}] ${e.bot_name} : ${e.error_type} (${e.category})`), '',
      '## API', `- ${total} appels, ${cles.filter((k) => k.status !== 'active').length} clé(s) en pause`, '',
      '_Données fictives : ce rapport est généré dans le navigateur._',
    ];
    return lignes.join('\n');
  }

  window.fetch = async (entree, options = {}) => {
    const url = new URL(typeof entree === 'string' ? entree : entree.url, location.origin);
    const methode = (options.method || 'GET').toUpperCase();
    let corps = {};
    try { corps = options.body ? JSON.parse(options.body) : {}; } catch { /* corps non JSON : ignoré */ }
    await new Promise((r) => setTimeout(r, 120 + hasard() * 180));
    for (const [m, motif, traiter] of routes) {
      const trouve = m === methode && url.pathname.match(motif);
      if (!trouve) continue;
      const { status, corps: reponse } = traiter(trouve.slice(1), url.searchParams, corps);
      return new Response(JSON.stringify(reponse), { status, headers: { 'Content-Type': 'application/json' } });
    }
    return new Response(JSON.stringify({ detail: 'Indisponible dans la démo' }), { status: 404, headers: { 'Content-Type': 'application/json' } });
  };

  // Le flux live : une ligne toutes les 3 à 7 secondes, filtrée comme le vrai.
  window.WebSocket = class {
    constructor(adresse) {
      this.bot = new URL(adresse).searchParams.get('bot') || '';
      setTimeout(() => this.onopen?.(), 300);
      const suivant = () => {
        this.minuteur = setTimeout(() => {
          const log = faireLog(maintenant());
          historique.push(log);
          if (!this.bot || log.bot === this.bot) this.onmessage?.({ data: JSON.stringify(log) });
          suivant();
        }, 3000 + hasard() * 4000);
      };
      suivant();
    }
    close() { clearTimeout(this.minuteur); }
  };

  // app.js est déjà exécuté à ce stade : ces remplacements passent après ses définitions.
  document.addEventListener('DOMContentLoaded', () => {
    window.downloadGeneratedReport = () => {
      const texte = document.getElementById('report-preview-text')?.value;
      if (!texte) { window.toast('Aucun rapport généré.', 'error'); return; }
      const lien = document.createElement('a');
      lien.href = URL.createObjectURL(new Blob([texte], { type: 'text/markdown' }));
      lien.download = 'rapport-demo.md';
      lien.click();
      setTimeout(() => URL.revokeObjectURL(lien.href), 1000);
    };
  });
})();
