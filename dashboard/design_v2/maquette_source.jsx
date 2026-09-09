
const REG = {
  sheogorath: { display: "🧀 Sheogorath", name: "Sheogorath", glyph: "🧀", color: "#d946ef" },
  maiq: { display: "🐱 M'aiq le Menteur", name: "M'aiq le Menteur", glyph: "🐱", color: "#f97316" },
  alfred: { display: "☕ Alfred Pennyworth", name: "Alfred Pennyworth", glyph: "☕", color: "#475569", textColor: "#94a3b8" },
  johnny: { display: "🔫 Johnny Silverhand", name: "Johnny Silverhand", glyph: "🔫", color: "#22c55e" },
  sugar: { display: "Sugar Bot", name: "Sugar Bot", glyph: "S", color: "#0ea5e9" },
  malena: { display: "💃 Malena la Gitana", name: "Malena la Gitana", glyph: "💃", color: "#f43f5e" }
};

const STATE = [
  { id: "malena", status: "stopped", msgs: 488 },
  { id: "alfred", status: "stopped", msgs: 214 },
  { id: "johnny", status: "degraded", uptime: "2h 03m", cpu: "2.1%", ram: "211 MB", msgs: 761 },
  { id: "sheogorath", status: "running", uptime: "5h 12m", cpu: "1.4%", ram: "184 MB", msgs: 1284 },
  { id: "maiq", status: "running", uptime: "5h 12m", cpu: "0.9%", ram: "162 MB", msgs: 902 },
  { id: "sugar", status: "running", uptime: "5h 11m", cpu: "1.1%", ram: "173 MB", msgs: 1533 }
];

const ERRORS = [
  { bot: "johnny", type: "RateLimitError", severity: "CRITIQUE", time: "09:10:44", occurrences: "14", source: "core/api_router.py:212", category: "Quota API", diagnosis: "les 5 clés du round-robin sont entrées en cooldown au même moment (429). Le bot a servi 3 réponses en erreur avant le backoff.", fix: "ajouter une clé au pool ou porter le délai minimum entre appels à 1,5 s dans api_tracker.py.", trace1: "  File \"core/api_router.py\", line 212, in call_model", trace2: "    resp = client.generate_content(prompt)", trace3: "google.api_core.exceptions.ResourceExhausted: 429 Too Many Requests" },
  { bot: "sugar", type: "KeyError: 'viewers'", severity: "ERREUR", time: "23:55:12", occurrences: "3", source: "backend/twitch_config.py:88", category: "Données", diagnosis: "le payload Twitch d'un stream hors ligne ne contient pas la clé 'viewers'.", fix: "remplacer l'accès direct par .get('viewers', 0) dans twitch_config.py.", trace1: "  File \"backend/twitch_config.py\", line 88, in poll_channel", trace2: "    count = payload['viewers']", trace3: "KeyError: 'viewers'" },
  { bot: "sheogorath", type: "ConnectionResetError", severity: "ALERTE", time: "07:12:35", occurrences: "1", source: "discord/gateway.py", category: "Réseau", diagnosis: "la gateway Discord a fermé la connexion pendant un heartbeat.", fix: "aucune action : la reconnexion automatique a réussi en 2,1 s. Surveiller la latence de l'hôte.", trace1: "  File \"discord/gateway.py\", line 601, in received_message", trace2: "    await self.received_message(msg)", trace3: "ConnectionResetError: [Errno 104] Connection reset by peer" }
];

const KEYS = [
  { bot: "johnny", provider: "Gemini", slot: "GEMINI_KEY_1", display: "AIza…c03d", status: "COOLDOWN", errors: 14, calls: 477, pct: "96%", lastUsed: "il y a 32 min", lastError: "429 Too Many Requests" },
  { bot: "johnny", provider: "Gemini", slot: "GEMINI_KEY_2", display: "AIza…4f2c", status: "ACTIVE", errors: 0, calls: 402, pct: "81%", lastUsed: "il y a 12 s", lastError: "aucune erreur" },
  { bot: "johnny", provider: "Mistral", slot: "MISTRAL_API_KEY", display: "1rTz…8dd0", status: "PLAFONNÉE", errors: 37, calls: 96, pct: "100%", lastUsed: "04/09", lastError: "429 permanent sur mistral-*" },
  { bot: "johnny", provider: "NVIDIA", slot: "NVIDIA_API_KEY", display: "nvapi…7e58", status: "ACTIVE", errors: 1, calls: 118, pct: "24%", lastUsed: "il y a 3 min", lastError: "aucune erreur" },

  { bot: "sheogorath", provider: "Gemini", slot: "GEMINI_KEY_1", display: "AIza…9b71", status: "ACTIVE", errors: 2, calls: 388, pct: "78%", lastUsed: "il y a 41 s", lastError: "aucune erreur" },
  { bot: "sheogorath", provider: "Gemini", slot: "GEMINI_KEY_2", display: "AIza…2ec4", status: "ACTIVE", errors: 0, calls: 214, pct: "43%", lastUsed: "il y a 6 min", lastError: "aucune erreur" },
  { bot: "sheogorath", provider: "Groq", slot: "GROQ_API_KEY", display: "gsk_…b17f", status: "ACTIVE", errors: 0, calls: 91, pct: "18%", lastUsed: "il y a 14 min", lastError: "aucune erreur" },

  { bot: "maiq", provider: "Gemini", slot: "GEMINI_KEY_1", display: "AIza…d5a2", status: "ACTIVE", errors: 1, calls: 302, pct: "61%", lastUsed: "il y a 2 min", lastError: "aucune erreur" },
  { bot: "maiq", provider: "Groq", slot: "GROQ_API_KEY", display: "gsk_…04ce", status: "ACTIVE", errors: 0, calls: 76, pct: "15%", lastUsed: "il y a 22 min", lastError: "aucune erreur" },
  { bot: "maiq", provider: "xAI", slot: "XAI_API_KEY", display: "xai-…9f31", status: "NON CONFIGURÉE", errors: 0, calls: 0, pct: "0%", lastUsed: "jamais", lastError: "champ vide, ignoré par le bot" },

  { bot: "sugar", provider: "Gemini", slot: "GEMINI_KEY_1", display: "AIza…1a90", status: "DÉSACTIVÉE", errors: 37, calls: 40, pct: "8%", lastUsed: "06/09", lastError: "400 API key not valid" },
  { bot: "sugar", provider: "Gemini", slot: "GEMINI_KEY_2", display: "AIza…6b8e", status: "ACTIVE", errors: 3, calls: 431, pct: "87%", lastUsed: "il y a 30 s", lastError: "aucune erreur" },
  { bot: "sugar", provider: "ElevenLabs", slot: "ELEVENLABS_API_KEY", display: "el_…c72a", status: "ACTIVE", errors: 0, calls: 58, pct: "12%", lastUsed: "il y a 51 min", lastError: "aucune erreur" },

  { bot: "alfred", provider: "Gemini", slot: "GEMINI_KEY_1", display: "AIza…8c14", status: "INACTIVE", errors: 0, calls: 61, pct: "12%", lastUsed: "hier 21:30", lastError: "bot arrêté" },
  { bot: "alfred", provider: "NVIDIA", slot: "NVIDIA_API_KEY", display: "nvapi…3b07", status: "NON CONFIGURÉE", errors: 0, calls: 0, pct: "0%", lastUsed: "jamais", lastError: "champ vide, ignoré par le bot" },

  { bot: "malena", provider: "Gemini", slot: "GEMINI_KEY_1", display: "AIza…f440", status: "INACTIVE", errors: 0, calls: 88, pct: "18%", lastUsed: "hier 23:58", lastError: "bot arrêté (exit 1)" },
  { bot: "malena", provider: "Mistral", slot: "MISTRAL_API_KEY", display: "1rTz…a6b2", status: "PLAFONNÉE", errors: 12, calls: 24, pct: "100%", lastUsed: "04/09", lastError: "429 permanent sur mistral-*" }
];

const KEY_TONE = {
  "ACTIVE": { color: "#34d399", bg: "rgba(16,185,129,.15)" },
  "COOLDOWN": { color: "#fbbf24", bg: "rgba(245,158,11,.15)" },
  "PLAFONNÉE": { color: "#fbbf24", bg: "rgba(245,158,11,.15)" },
  "DÉSACTIVÉE": { color: "#f87171", bg: "rgba(239,68,68,.15)" },
  "INACTIVE": { color: "#8f99ad", bg: "rgba(143,153,173,.14)" },
  "NON CONFIGURÉE": { color: "#8f99ad", bg: "rgba(143,153,173,.14)" }
};

const AUDIT = [
  { time: "09:02:11 · 09/09", user: "admin", action: "BOT_RESTART", bot: "johnny", details: "Redémarrage manuel après RateLimitError" },
  { time: "08:44:57 · 09/09", user: "admin", action: "FEATURE_UPDATE", bot: "sheogorath", details: "decret_enabled → true" },
  { time: "08:12:03 · 09/09", user: "admin", action: "TWITCH_SUB_ADD", bot: "sugar", details: "chaîne « ninja » → salon 1122334455" },
  { time: "23:57:40 · 08/09", user: "admin", action: "ERROR_RESOLVE", bot: "sugar", details: "Erreur #418 marquée comme résolue" },
  { time: "21:30:15 · 08/09", user: "admin", action: "BOT_STOP", bot: "alfred", details: "Arrêt planifié (maintenance)" },
  { time: "20:05:02 · 08/09", user: "admin", action: "LOGIN", bot: null, details: "Session ouverte depuis 192.168.1.24" }
];

const LOGS = [
  { time: "09:12:41", bot: "sheogorath", level: "INFO", message: "Décret publié dans #folie : « Que nul ne dorme »" },
  { time: "09:12:03", bot: "maiq", level: "INFO", message: "Réponse générée en 1.42 s (gemini-2.0-flash, 812 tokens)" },
  { time: "09:11:58", bot: "johnny", level: "WARNING", message: "Clé AIza…c03d en cooldown, bascule round-robin sur AIza…4f2c" },
  { time: "09:11:12", bot: "sugar", level: "INFO", message: "Twitch : 3 chaînes surveillées, 1 live détecté (annonce envoyée)" },
  { time: "09:10:44", bot: "johnny", level: "ERROR", message: "RateLimitError: 429 Too Many Requests — retry dans 30 s" },
  { time: "09:09:31", bot: "SYSTEM", level: "INFO", message: "Snapshot mémoire écrit : data/johnny_memory.json (412 entrées)" },
  { time: "09:08:20", bot: "maiq", level: "INFO", message: "Fait mémorisé pour l'utilisateur 447… : « joue à Skyrim »" },
  { time: "09:07:02", bot: "sheogorath", level: "WARNING", message: "ConnectionResetError sur heartbeat gateway — reconnexion OK" },
  { time: "09:06:15", bot: "sugar", level: "INFO", message: "Faveur +5 pour le viewer « lyra_ttv » (total 130)" },
  { time: "09:05:00", bot: "SYSTEM", level: "INFO", message: "Collecte API : 1 842 appels sur 24 h, 98.6 % de succès" },
  { time: "09:04:22", bot: "malena", level: "CRITICAL", message: "Process terminé (exit 1) — voir logs/malena_2026-09-09.log" },
  { time: "09:03:47", bot: "alfred", level: "INFO", message: "Arrêt propre du bot demandé par le dashboard" },
  { time: "09:02:11", bot: "johnny", level: "INFO", message: "Bot connecté en tant que JohnnyBot#4412 (3 guilds)" },
  { time: "09:01:05", bot: "SYSTEM", level: "INFO", message: "Dashboard backend prêt sur http://127.0.0.1:8501" }
];

const NAV = [
  { key: "overview", label: "Vue d'ensemble", icon: "fa-solid fa-chart-pie", title: "Vue d'ensemble de l'écosystème", sub: "6 bots · 2 hors ligne · dernière collecte il y a 12 s", group: "sup" },
  { key: "logs", label: "Logs en direct", icon: "fa-solid fa-terminal", title: "Logs en direct", sub: "Flux agrégé des 6 bots et du backend", group: "sup" },
  { key: "errors", label: "Analyse erreurs", icon: "fa-solid fa-triangle-exclamation", title: "Analyse des erreurs", sub: "3 erreurs non résolues sur 24 h", count: 3, group: "sup" },
  { key: "api-keys", label: "Clés API", icon: "fa-solid fa-key", title: "Gestion des clés API", sub: "18 clés traquées sur 6 bots · 6 fournisseurs", count: 1, group: "sup" },
  { key: "conversations", label: "Conversations", icon: "fa-solid fa-comments", title: "Conversations", sub: "Volume de messages et interlocuteurs", group: "sup" },
  { key: "reports", label: "Rapports GenAI", icon: "fa-solid fa-file-export", title: "Rapports GenAI", sub: "Export Markdown prêt à coller dans un LLM", group: "sup" },
  { key: "audit-logs", label: "Journal d'audit", icon: "fa-solid fa-clock-rotate-left", title: "Journal d'audit", sub: "Traçabilité des actions opérateur", group: "sup" },
  { key: "bot-config", label: "Configuration", icon: "fa-solid fa-sliders", title: "Configuration des bots", sub: "Fonctionnalités Discord et modules Twitch", group: "cfg" }
];

const REPORT = `# Rapport de diagnostic — écosystème 6 bots
Généré : 2026-09-09 09:14 · fenêtre 24 h · périmètre complet

## 1 · État des processus
| Bot        | Statut   | Uptime | CPU  | RAM    |
|------------|----------|--------|------|--------|
| sheogorath | running  | 5h12m  | 1.4% | 184 MB |
| maiq       | running  | 5h12m  | 0.9% | 162 MB |
| johnny     | degraded | 2h03m  | 2.1% | 211 MB |
| sugar      | running  | 5h11m  | 1.1% | 173 MB |
| alfred     | stopped  | —      | —    | —      |
| malena     | stopped  | —      | —    | —      |

## 2 · Erreurs (3 non résolues)
- [CRITIQUE] johnny · RateLimitError — 5 clés en cooldown simultané (429), 14 occurrences
- [ERREUR]   sugar  · KeyError 'viewers' — payload Twitch incomplet, 3 occurrences
- [ALERTE]   sheogorath · ConnectionResetError — heartbeat gateway, reconnexion OK

## 3 · Clés API
5 clés traquées · 1 en cooldown · 1 désactivée · 1 842 appels · 98.6 % de succès
Recommandation : ajouter une 6e clé au pool ou porter le délai minimum à 1,5 s.

## 4 · Activité
Pic à 19 h (96 msg/h) · 27 utilisateurs uniques sur 7 j · 5 182 messages traités.
`;

const FEATURES = [
  { name: "Décret activé", desc: "Sheogorath publie un décret quotidien dans le salon dédié.", on: true, locked: false, only: "sheogorath" },
  { name: "Mode test", desc: "Le bot ne publie que dans le serveur privé sélectionné.", on: false, locked: false },
  { name: "Carnet de repartie", desc: "Le bot apprend de ses défaites et enrichit ses réponses.", on: true, locked: false }
];

const TWITCH_TABS = [
  { key: "presence", label: "Présence & connexion" },
  { key: "events", label: "Événements & rewards" },
  { key: "economy", label: "Habitués & éco" },
  { key: "listen", label: "Écoute live" },
  { key: "announces", label: "Annonces" }
];

const TWITCH_PANELS = {
  presence: { title: "Présence sur le chat", badge: "CONNECTÉ", ok: true, sub: "Chaîne ciblée : twitch.tv/ma_streameuse · appliqué au redémarrage du bot.", rows: [
    { name: "Événements Sub / Follow / Bits", desc: "Le bot réagit aux événements du chat.", on: true },
    { name: "Interjections spontanées", desc: "Le bot intervient de lui-même dans les temps morts.", on: true },
    { name: "Accueil des nouveaux de session", desc: "Message de bienvenue au premier message d'un viewer.", on: false },
    { name: "Mémoire long terme", desc: "Le bot retient les faits appris sur les viewers.", on: true },
    { name: "Réponses questions jeu (IGDB)", desc: "Réponses passives aux questions sur le jeu en cours.", on: true },
    { name: "EventSub", desc: "Channel points, raids et hype trains (token broadcaster requis).", on: false }
  ] },
  events: { title: "Récompenses de chaîne", badge: "4 MAPPÉES", ok: true, sub: "Associez les titres exacts de vos récompenses Twitch à des commandes du bot.", rows: [
    { name: "« Décret de la Folie » → decret", desc: "Déclenche un décret dans le chat et le salon Discord.", on: true },
    { name: "« Question à M'aiq » → question", desc: "Le bot répond en persona au demandeur.", on: true },
    { name: "« Faveur x2 » → faveur_double", desc: "Double les points de faveur pendant 10 min.", on: true },
    { name: "« Silence » → mute_bot", desc: "Met le bot en sourdine pendant 5 min.", on: false }
  ] },
  economy: { title: "Habitués & économie", badge: "130 PTS MAX", ok: true, sub: "Classement de la faveur / street cred accumulée par les viewers.", rows: [
    { name: "lyra_ttv — 130 pts", desc: "42 sessions · dernier passage aujourd'hui.", on: true },
    { name: "korvax — 96 pts", desc: "31 sessions · dernier passage hier.", on: true },
    { name: "mira_plays — 74 pts", desc: "22 sessions · dernier passage il y a 3 j.", on: true },
    { name: "n0va — 51 pts", desc: "14 sessions · dernier passage il y a 6 j.", on: true }
  ] },
  listen: { title: "Écoute micro (ASR)", badge: "DÉSACTIVÉE", ok: false, sub: "Kill-switch et configuration de l'ASR partagé. Mode NIM (Docker localhost), CPU, chunks de 560 ms.", rows: [
    { name: "Activer l'écoute micro", desc: "Kill-switch global de la transcription live.", on: false },
    { name: "GPU (CUDA) pour l'ASR", desc: "Sinon calcul CPU, plus lent mais sans VRAM.", on: false },
    { name: "Intervalle min entre réponses : 45 s", desc: "Évite que le bot monopolise le live.", on: true }
  ] },
  announces: { title: "Annonces de live", badge: "3 SURVEILLÉES", ok: true, sub: "Polling toutes les 90 s · message IA automatique si aucun texte personnalisé.", rows: [
    { name: "Surveillance Twitch active", desc: "Vérifie l'état des chaînes suivies en continu.", on: true },
    { name: "Message généré par l'IA", desc: "Sinon le message personnalisé de l'abonnement est utilisé.", on: true },
    { name: "Mentionner @everyone", desc: "Ping le salon à chaque passage en live.", on: false }
  ] }
};

const SUBS = [
  { login: "ninja", channel: "annonces-live", state: "EN LIGNE", ok: true },
  { login: "ma_streameuse", channel: "le-manoir", state: "HORS LIGNE", ok: false },
  { login: "korvax", channel: "annonces-live", state: "HORS LIGNE", ok: false }
];

const TOP_USERS = [
  { name: "lyra_ttv", msgs: 412, bot: "sugar" },
  { name: "korvax", msgs: 388, bot: "sheogorath" },
  { name: "Mathis", msgs: 301, bot: "maiq" },
  { name: "n0va", msgs: 264, bot: "johnny" },
  { name: "mira_plays", msgs: 219, bot: "sugar" },
  { name: "Elodie", msgs: 187, bot: "malena" }
];

const LEVELS = ["TOUS", "INFO", "WARNING", "ERROR", "CRITICAL"];
const TIMEFRAMES = ["1 h", "6 h", "24 h", "7 j"];

const SEV = {
  CRITIQUE: { color: "#f87171", bg: "rgba(239,68,68,.16)" },
  ERREUR: { color: "#fb923c", bg: "rgba(249,115,22,.16)" },
  ALERTE: { color: "#fbbf24", bg: "rgba(245,158,11,.16)" }
};

const STATUS = {
  running: { label: "ACTIF", color: "#34d399", bg: "rgba(16,185,129,.15)", dot: "#10b981", glow: "0 0 10px rgba(16,185,129,.8)" },
  degraded: { label: "DÉGRADÉ", color: "#fbbf24", bg: "rgba(245,158,11,.15)", dot: "#f59e0b", glow: "0 0 10px rgba(245,158,11,.8)" },
  stopped: { label: "HORS LIGNE", color: "#f87171", bg: "rgba(239,68,68,.15)", dot: "#4b5563", glow: "none" }
};

class Component extends DCLogic {
  state = { view: "overview", err: 0, level: "TOUS", tf: "24 h", rail: true,
            platform: "discord", twitchTab: "presence", login: false, clock: "09:14:07" };

  componentDidMount() {
    this._t = setInterval(() => {
      const d = new Date(), p = n => String(n).padStart(2, "0");
      this.setState({ clock: `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}` });
    }, 1000);
    this._onResize = () => {
      const narrow = window.innerWidth < 940;
      if (narrow === this.state.rail) this.setState({ rail: !narrow });
    };
    window.addEventListener("resize", this._onResize);
    this._onResize();
    this.draw();
  }
  componentDidUpdate() { this.draw(); }
  componentWillUnmount() { clearInterval(this._t); window.removeEventListener("resize", this._onResize); }

  draw() {
    if (!window.Chart) { setTimeout(() => this.draw(), 200); return; }
    const grid = "rgba(255,255,255,.05)";
    const base = { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } };
    const tick = { color: "#7c8699", font: { size: 10 } };
    if (this._actEl && this._actEl !== this._actDrawn) {
      this._actDrawn = this._actEl;
      new Chart(this._actEl, {
        type: "line",
        data: { labels: Array.from({ length: 24 }, (_, i) => `${String(i).padStart(2, "0")}h`),
          datasets: [{ data: [12,8,5,3,2,2,4,9,18,27,34,41,38,44,52,48,61,73,88,96,81,64,42,26], borderColor: "#8b5cf6", backgroundColor: "rgba(139,92,246,.16)", fill: true, tension: .35, pointRadius: 0, borderWidth: 2 }] },
        options: { ...base, scales: { y: { beginAtZero: true, grid: { color: grid }, ticks: tick, border: { display: false } }, x: { grid: { display: false }, ticks: { ...tick, maxTicksLimit: 8 }, border: { color: "#23233a" } } } }
      });
    }
    if (this._apiEl && this._apiEl !== this._apiDrawn) {
      this._apiDrawn = this._apiEl;
      new Chart(this._apiEl, {
        type: "doughnut",
        data: { labels: Object.values(REG).map(b => b.display), datasets: [{ data: [412, 318, 96, 288, 502, 226], backgroundColor: Object.values(REG).map(b => b.color), borderWidth: 0, cutout: "62%" }] },
        options: { ...base, plugins: { legend: { display: true, position: "right", labels: { color: "#9aa4b8", boxWidth: 10, font: { size: 11 } } } } }
      });
    }
    if (this._convEl && this._convEl !== this._convDrawn) {
      this._convDrawn = this._convEl;
      new Chart(this._convEl, {
        type: "bar",
        data: { labels: ["Sheo", "M'aiq", "Alfred", "Johnny", "Sugar", "Malena"], datasets: [{ data: [1284, 902, 214, 761, 1533, 488], backgroundColor: Object.values(REG).map(b => b.color), borderRadius: 5, barThickness: 26 }] },
        options: { ...base, scales: { y: { beginAtZero: true, grid: { color: grid }, ticks: tick, border: { display: false } }, x: { grid: { display: false }, ticks: tick, border: { color: "#23233a" } } } }
      });
    }
  }

  navItems(group) {
    return NAV.filter(n => n.group === group).map(n => {
      const on = this.state.view === n.key;
      return { label: n.label, icon: n.icon,
        go: () => this.setState({ view: n.key }),
        bg: on ? "rgba(139,92,246,.14)" : "transparent",
        color: on ? "#c4b5fd" : "#8f99ad",
        ring: on ? "inset 0 0 0 1px rgba(139,92,246,.35)" : "none",
        hasCount: !!n.count, count: n.count,
        countBg: n.key === "errors" ? "rgba(239,68,68,.18)" : "rgba(245,158,11,.18)",
        countColor: n.key === "errors" ? "#f87171" : "#fbbf24" };
    });
  }

  pill(on) { return { bg: on ? "#8b5cf6" : "transparent", color: on ? "#fff" : "#8f99ad" }; }

  renderVals() {
    const s = this.state, v = s.view, d = ERRORS[s.err];
    const nav = NAV.find(n => n.key === v) || {};
    const panel = TWITCH_PANELS[s.twitchTab];
    return {
      clock: s.clock,
      pageTitle: nav.title || "", pageSub: nav.sub || "",
      navSup: this.navItems("sup"), navCfg: this.navItems("cfg"),
      railW: s.rail ? "232px" : "64px", wide: s.rail,
      railIcon: s.rail ? "fa-solid fa-angles-left" : "fa-solid fa-angles-right",
      toggleRail: () => this.setState({ rail: !s.rail }),
      isOverview: v === "overview", isLogs: v === "logs", isErrors: v === "errors",
      isApi: v === "api-keys", isConversations: v === "conversations",
      isReports: v === "reports", isAudit: v === "audit-logs", isConfig: v === "bot-config",
      goErrors: () => this.setState({ view: "errors", err: 0 }),
      goLogs: () => this.setState({ view: "logs" }),
      showLogin: () => this.setState({ login: true }),
      hideLogin: () => this.setState({ login: false }),
      loginOpen: s.login,
      activityRef: el => { this._actEl = el; },
      apiRef: el => { this._apiEl = el; },
      convRef: el => { this._convEl = el; },
      reportSample: REPORT,

      kpis: [
        { label: "Bots actifs", value: "4", unit: "/ 6", icon: "fa-solid fa-robot", tone: "#fbbf24", pct: "67%", hint: "Alfred et Malena sont arrêtés" },
        { label: "Erreurs 24 h", value: "3", unit: "non résolues", icon: "fa-solid fa-triangle-exclamation", tone: "#f87171", pct: "35%", hint: "dont 1 critique sur Johnny" },
        { label: "Succès API", value: "98.6", unit: "%", icon: "fa-solid fa-bolt", tone: "#34d399", pct: "98.6%", hint: "1 842 appels · 1 clé en cooldown" },
        { label: "Utilisateurs 7 j", value: "27", unit: "uniques", icon: "fa-solid fa-users", tone: "#c4b5fd", pct: "54%", hint: "+6 vs semaine précédente" }
      ],
      apiKpis: [
        { label: "Appels 24 h", value: "1 842", tone: "#f2f4f8", hint: "pic de 214 appels à 19 h" },
        { label: "Taux de succès", value: "98.6 %", tone: "#34d399", hint: "26 échecs, tous des 429" },
        { label: "Clés utilisables", value: "9 / 18", tone: "#fbbf24", hint: "1 cooldown, 2 plafonnées, 1 désactivée, 2 vides" },
        { label: "Latence médiane", value: "1.28 s", tone: "#c4b5fd", hint: "gemini-2.0-flash" }
      ],

      bots: STATE.map((b, i) => {
        const r = REG[b.id], st = STATUS[b.status];
        const dim = b.status === "stopped";
        return { display: r.display, name: r.name, glyph: r.glyph, color: r.color,
          avatarBg: `${r.color}${dim ? "14" : "24"}`, avatarColor: dim ? "#7c8699" : r.color,
          nameColor: dim ? "#a9b2c1" : "#f2f4f8",
          dot: st.dot, dotGlow: st.glow, badgeBg: st.bg, badgeColor: st.color, statusLabel: st.label,
          cardBorder: b.status === "stopped" ? "#3a2028" : (b.status === "degraded" ? "#40361c" : "#23233a"),
          rowBg: i % 2 ? "#12121f" : "#141426",
          meta: b.status === "stopped" ? "hors ligne · dernier arrêt 21:30"
              : `${b.uptime} · CPU ${b.cpu} · RAM ${b.ram} · ${b.msgs} msg`,
          uptimeCell: b.uptime || "—", cpuCell: b.cpu || "—", ramCell: b.ram || "—", msgCell: String(b.msgs),
          actions: b.status === "stopped"
            ? [{ label: "Démarrer", icon: "fa-solid fa-play", bg: "rgba(16,185,129,.15)", color: "#34d399", border: "#1e4d3c" },
               { label: "Voir les logs", icon: "fa-solid fa-terminal", bg: "transparent", color: "#8f99ad", border: "#23233a" }]
            : [{ label: "Redémarrer", icon: "fa-solid fa-rotate-right", bg: "transparent", color: "#c3cbd9", border: "#23233a" },
               { label: "Arrêter", icon: "fa-solid fa-stop", bg: "transparent", color: "#fca5a5", border: "#4a2230" },
               { label: "Voir les logs", icon: "fa-solid fa-terminal", bg: "transparent", color: "#8f99ad", border: "#23233a" }]
        };
      }),

      alerts: [
        { message: "Johnny : RateLimitError 429, round-robin saturé", meta: "09:10:44 · 14 occurrences", color: "#f87171", icon: "fa-solid fa-circle-exclamation", tint: "rgba(239,68,68,.13)" },
        { message: "Malena : process terminé (exit 1)", meta: "09:04:22 · redémarrage requis", color: "#f87171", icon: "fa-solid fa-power-off", tint: "rgba(239,68,68,.13)" },
        { message: "Clé AIza…c03d passée en cooldown", meta: "09:11:58 · retour estimé dans 28 min", color: "#fbbf24", icon: "fa-solid fa-hourglass-half", tint: "rgba(245,158,11,.13)" },
        { message: "Sheogorath : heartbeat gateway reset, reconnecté", meta: "09:07:02 · résolu automatiquement", color: "#7dd3fc", icon: "fa-solid fa-arrow-rotate-left", tint: "rgba(56,189,248,.12)" }
      ],

      levelChips: LEVELS.map(l => ({ label: l, go: () => this.setState({ level: l }), ...this.pill(s.level === l) })),
      levelLabel: s.level, logCount: LOGS.length,
      logLines: LOGS.map(l => {
        const warn = l.level === "WARNING", info = l.level === "INFO";
        return { ...l,
          botColor: (REG[l.bot] || {}).textColor || (REG[l.bot] || {}).color || "#7c8699",
          levelColor: info ? "#60a5fa" : (warn ? "#fbbf24" : "#f87171"),
          levelBg: info ? "rgba(59,130,246,.14)" : (warn ? "rgba(245,158,11,.14)" : "rgba(239,68,68,.14)") };
      }),

      errors: ERRORS.map((e, i) => ({ bot: e.bot, type: e.type, severity: e.severity, time: e.time,
        select: () => this.setState({ err: i }),
        bg: i === s.err ? "rgba(139,92,246,.12)" : "#161628",
        borderColor: i === s.err ? "#5b3fa8" : "#23233a",
        sevColor: SEV[e.severity].color, sevBg: SEV[e.severity].bg })),
      detail: { ...d, sevColor: SEV[d.severity].color, sevBg: SEV[d.severity].bg },

      keyGroups: ["johnny", "sugar", "sheogorath", "maiq", "alfred", "malena"].map(id => {
        const r = REG[id], mine = KEYS.filter(k => k.bot === id);
        const bad = mine.filter(k => ["COOLDOWN", "PLAFONNÉE", "DÉSACTIVÉE"].includes(k.status)).length;
        const ok = mine.filter(k => k.status === "ACTIVE").length;
        const providers = [...new Set(mine.map(k => k.provider))];
        return {
          id, name: r.name, glyph: r.glyph, avatarBg: `${r.color}24`, avatarColor: r.color,
          summary: `${ok}/${mine.length} clés utilisables · ${providers.length} fournisseurs`,
          headBorder: bad ? "#40361c" : "#23233a",
          flagColor: bad ? "#fbbf24" : "#6f7889",
          flag: bad ? `${bad} à surveiller` : "nominal",
          keys: mine.map(k => {
            const t = KEY_TONE[k.status];
            return { ...k, badgeColor: t.color, badgeBg: t.bg,
              errColor: k.lastError === "aucune erreur" ? "#6f7889" : t.color };
          })
        };
      }),

      auditRows: AUDIT.map((a, i) => ({ ...a, bot: a.bot || "—",
        botColor: a.bot ? REG[a.bot].color : "#6f7889",
        zebra: i % 2 ? "#12121f" : "#141426",
        actionBg: a.action.startsWith("BOT") ? "rgba(139,92,246,.14)" : "rgba(59,130,246,.12)",
        actionColor: a.action.startsWith("BOT") ? "#c4b5fd" : "#93c5fd" })),

      topUsers: TOP_USERS.map((u, i) => ({ ...u, rank: i + 1, botColor: REG[u.bot].color })),

      timeframes: TIMEFRAMES.map(t => ({ label: t, go: () => this.setState({ tf: t }), ...this.pill(s.tf === t) })),

      onDiscord: s.platform === "discord", onTwitch: s.platform === "twitch",
      setDiscord: () => this.setState({ platform: "discord" }),
      setTwitch: () => this.setState({ platform: "twitch" }),
      tabDiscord: this.pill(s.platform === "discord"), tabTwitch: this.pill(s.platform === "twitch"),
      features: FEATURES.map(f => ({ ...f, opacity: f.locked ? .5 : 1 })),
      twitchTabs: TWITCH_TABS.map(t => ({ label: t.label, go: () => this.setState({ twitchTab: t.key }), ...this.pill(s.twitchTab === t.key) })),
      twitchPanel: { ...panel,
        badgeBg: panel.ok ? "rgba(16,185,129,.15)" : "rgba(239,68,68,.15)",
        badgeColor: panel.ok ? "#34d399" : "#f87171" },
      subs: SUBS.map(x => ({ ...x,
        badgeBg: x.ok ? "rgba(16,185,129,.15)" : "rgba(148,163,184,.12)",
        badgeColor: x.ok ? "#34d399" : "#94a3b8" }))
    };
  }
}

