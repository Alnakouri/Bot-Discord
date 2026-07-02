const API_BASE = '/api';

// --- AUTHENTIFICATION ---
// Toute réponse 401 (session absente/expirée) ramène à l'écran de login.
const _origFetch = window.fetch.bind(window);
window.fetch = async (...args) => {
    const res = await _origFetch(...args);
    if (res.status === 401) showLogin();
    return res;
};

function showLogin() {
    const ov = document.getElementById('login-overlay');
    if (ov) ov.style.display = 'flex';
}

async function ensureAuthenticated() {
    try {
        const res = await _origFetch(`${API_BASE}/me`);
        const data = await res.json();
        if (data.authenticated) return true;
    } catch (_) { /* serveur injoignable : on montre le login */ }
    showLogin();
    return false;
}

async function logout() {
    try { await _origFetch(`${API_BASE}/logout`, { method: 'POST' }); } catch (_) {}
    location.reload();
}

function initLoginForm() {
    const form = document.getElementById('login-form');
    if (!form) return;
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const pwd = document.getElementById('login-password').value;
        const errEl = document.getElementById('login-error');
        errEl.textContent = '';
        try {
            const res = await _origFetch(`${API_BASE}/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password: pwd }),
            });
            if (res.ok) {
                location.reload();
            } else {
                errEl.textContent = 'Mot de passe invalide.';
            }
        } catch (_) {
            errEl.textContent = 'Serveur injoignable.';
        }
    });
}

// --- INITIALIZATION ---
document.addEventListener('DOMContentLoaded', async () => {
    initLoginForm();
    if (!(await ensureAuthenticated())) return; // login affiché : on stoppe ici

    initNavigation();
    initClock();
    refreshAllData();
    initLogsWebSocket();
    initConfigBotSelect();

    // Bind buttons
    document.getElementById('btn-refresh-logs')?.addEventListener('click', loadLogs);
    document.getElementById('btn-generate-report')?.addEventListener('click', generateReport);

    // Refresh loop every 30s
    setInterval(refreshAllData, 30000);
});

// --- NAVIGATION (SPA) ---
function initNavigation() {
    const links = document.querySelectorAll('.nav-links li');
    const views = document.querySelectorAll('.view');
    
    links.forEach(link => {
        link.addEventListener('click', () => {
            // Update active state
            links.forEach(l => l.classList.remove('active'));
            link.classList.add('active');
            
            // Show target view
            const targetId = link.getAttribute('data-target');
            views.forEach(v => {
                v.classList.remove('active');
                if(v.id === targetId) v.classList.add('active');
            });
            
            // Trigger specific view loads
            if(targetId === 'logs') loadLogs();
            if(targetId === 'errors') loadErrors();
            if(targetId === 'api-keys') loadApiKeysStatus();
            if(targetId === 'bot-config') loadBotConfig();
        });
    });
}

// --- BOT CONFIGURATION PLATFORM TABS & LOADING ---
window.switchPlatform = function(platform) {
    document.querySelectorAll('.tabs-platforms .btn-tab').forEach(btn => {
        btn.classList.toggle('active', btn.getAttribute('data-platform') === platform);
    });
    
    document.querySelectorAll('.platform-view').forEach(view => {
        view.style.display = view.id === `platform-${platform}` ? 'block' : 'none';
    });
    
    loadBotConfig();
};

window.switchTwitchSubtab = function(subtab) {
    document.querySelectorAll('.twitch-subtabs .btn-subtab').forEach(btn => {
        btn.classList.toggle('active', btn.getAttribute('data-subtab') === subtab);
    });
    
    document.querySelectorAll('.twitch-subview-container').forEach(view => {
        view.style.display = view.id === `${subtab}-container` ? 'block' : 'none';
    });
    
    loadBotConfig();
};

window.loadBotConfig = async function() {
    const select = document.getElementById('config-bot-select');
    if (!select) return;
    const botId = select.value;
    
    const activePlatformEl = document.querySelector('.tabs-platforms .btn-tab.active');
    if (!activePlatformEl) return;
    const activePlatform = activePlatformEl.getAttribute('data-platform');
    
    if (activePlatform === 'discord') {
        await loadDiscordConfig(botId);
    } else if (activePlatform === 'twitch') {
        const activeSubtabEl = document.querySelector('.twitch-subtabs .btn-subtab.active');
        const activeSubtab = activeSubtabEl ? activeSubtabEl.getAttribute('data-subtab') : 'twitch-presence';
        await loadTwitchSubtabConfig(botId, activeSubtab);
    }
};

window.onConfigBotSelect = function() {
    loadBotConfig();
};

window.initConfigBotSelect = function() {
    const select = document.getElementById('config-bot-select');
    if (!select) return;
    
    select.innerHTML = '<option value="all">👥 Tous les bots</option>';
    for (const [botId, botData] of Object.entries(BOT_REGISTRY_JS)) {
        const displayName = botData.display || botId;
        select.innerHTML += `<option value="${botId}">${displayName}</option>`;
    }
};

window.loadDiscordConfig = async function(botId) {
    const listContainer = document.getElementById('discord-features-list');
    const bulkContainer = document.getElementById('discord-features-bulk');
    if (!listContainer || !bulkContainer) return;
    
    if (botId === 'all') {
        listContainer.style.display = 'none';
        bulkContainer.style.display = 'block';
        return;
    }
    
    listContainer.style.display = 'grid';
    bulkContainer.style.display = 'none';
    
    try {
        const res = await fetch(`${API_BASE}/features/${botId}`);
        if (res.ok) {
            const cfg = await res.json();
            listContainer.innerHTML = '';
            
            for (const [featureName, value] of Object.entries(cfg)) {
                let displayName = featureName;
                if (featureName === 'decret_enabled') displayName = "Décret activé";
                
                let disabledAttr = '';
                let note = '';
                if (featureName === 'decret_enabled' && botId !== 'sheogorath') {
                    disabledAttr = 'disabled';
                    note = ' <span style="font-size:0.8em; opacity:0.5;">(Uniquement pour Sheogorath)</span>';
                }
                
                listContainer.innerHTML += `
                    <label style="display:flex; align-items:center; gap:10px; cursor:pointer; opacity: ${disabledAttr ? 0.5 : 1}">
                        <input type="checkbox" id="feat-${featureName}-${botId}" ${value ? 'checked' : ''} ${disabledAttr} onchange="window.updateDiscordFeature('${botId}', '${featureName}', this.checked)"> 
                        <b>${displayName}</b>${note}
                    </label>
                `;
            }
            if (listContainer.innerHTML === '') {
                listContainer.innerHTML = '<div class="placeholder-text">Aucune fonctionnalité Discord configurable pour ce bot.</div>';
            }
        }
    } catch (e) {
        console.error("Failed to load Discord features:", e);
    }
};

window.updateDiscordFeature = async function(botId, featureName, value) {
    try {
        await fetch(`${API_BASE}/features/${botId}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ feature: featureName, value: value })
        });
    } catch (e) {
        console.error("Failed to update feature:", e);
    }
};

window.setDiscordFeatureAll = async function(featureName, value) {
    try {
        const res = await fetch(`${API_BASE}/features/all`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ feature: featureName, value: value })
        });
        if (res.ok) {
            alert("Action globale appliquée avec succès !");
            await loadBotConfig();
        } else {
            const d = await res.json();
            alert(`Erreur: ${d.detail || "Sauvegarde impossible"}`);
        }
    } catch (e) {
        alert(`Erreur réseau: ${e}`);
    }
};

window.loadTwitchSubtabConfig = async function(botId, activeSubtab) {
    const presenceStatusPanel = document.getElementById('twitch-bot-status-panel');
    const presenceConfigCard = document.querySelector('#twitch-presence-container .twitch-card');
    const presenceChannelsCard = document.querySelector('#twitch-presence-container div.twitch-card:nth-of-type(2)');
    const presenceAllMsg = document.getElementById('twitch-presence-all-msg');
    
    if (activeSubtab === 'twitch-presence') {
        if (botId === 'all') {
            if (presenceStatusPanel) presenceStatusPanel.style.display = 'none';
            if (presenceConfigCard) presenceConfigCard.style.display = 'none';
            if (presenceChannelsCard) presenceChannelsCard.style.display = 'none';
            if (presenceAllMsg) presenceAllMsg.style.display = 'block';
        } else {
            if (presenceStatusPanel) presenceStatusPanel.style.display = 'flex';
            if (presenceConfigCard) presenceConfigCard.style.display = 'block';
            if (presenceChannelsCard) presenceChannelsCard.style.display = 'block';
            if (presenceAllMsg) presenceAllMsg.style.display = 'none';
            await loadTwitchPresence();
        }
    }
    
    const eventsConfigCard = document.querySelector('#twitch-events-container .twitch-card');
    const eventsAllMsg = document.getElementById('twitch-events-all-msg');
    if (activeSubtab === 'twitch-events') {
        if (botId === 'all') {
            if (eventsConfigCard) eventsConfigCard.style.display = 'none';
            if (eventsAllMsg) eventsAllMsg.style.display = 'block';
        } else {
            if (eventsConfigCard) eventsConfigCard.style.display = 'block';
            if (eventsAllMsg) eventsAllMsg.style.display = 'none';
            await loadTwitchEvents();
        }
    }
    
    const economyConfigCard = document.querySelector('#twitch-economy-container .twitch-card');
    const economyAllMsg = document.getElementById('twitch-economy-all-msg');
    if (activeSubtab === 'twitch-economy') {
        if (botId === 'all') {
            if (economyConfigCard) economyConfigCard.style.display = 'none';
            if (economyAllMsg) economyAllMsg.style.display = 'block';
        } else {
            if (economyConfigCard) economyConfigCard.style.display = 'block';
            if (economyAllMsg) economyAllMsg.style.display = 'none';
            await loadTwitchEconomy();
        }
    }
    
    const listenConfigCard = document.querySelector('#twitch-listen-container .twitch-card');
    const listenAllMsg = document.getElementById('twitch-listen-all-msg');
    if (activeSubtab === 'twitch-listen') {
        if (botId === 'all') {
            if (listenConfigCard) listenConfigCard.style.display = 'none';
            if (listenAllMsg) listenAllMsg.style.display = 'block';
        } else {
            if (listenConfigCard) listenConfigCard.style.display = 'block';
            if (listenAllMsg) listenAllMsg.style.display = 'none';
            await loadTwitchListen();
        }
    }
    
    const announcesConfigCard = document.getElementById('twitch-bot-status-panel');
    const announcesLayout = document.getElementById('twitch-announces-individual-layout');
    if (activeSubtab === 'twitch-announces') {
        if (botId === 'all') {
            if (announcesConfigCard) announcesConfigCard.style.display = 'none';
            if (announcesLayout) announcesLayout.style.display = 'none';
        } else {
            if (announcesConfigCard) announcesConfigCard.style.display = 'flex';
            if (announcesLayout) announcesLayout.style.display = 'grid';
            await loadTwitchConfig();
        }
    }
};

function initClock() {
    const clockEl = document.getElementById('clock');
    if(!clockEl) return;
    setInterval(() => {
        const now = new Date();
        clockEl.textContent = now.toLocaleString('fr-FR');
    }, 1000);
}

// --- DATA FETCHING ---
async function refreshAllData() {
    await fetchBotsStatus();
    // Les graphes seront rafraîchis via charts.js
    if (typeof window.refreshCharts === 'function') {
        window.refreshCharts();
    }
}

async function fetchBotsStatus() {
    try {
        const res = await fetch(`${API_BASE}/bots`);
        if(!res.ok) throw new Error("Failed to fetch bots");
        const bots = await res.json();
        renderBotsGrid(bots);
        
        const activeCount = bots.filter(b => b.status === 'running').length;
        document.getElementById('stat-active-bots').textContent = `${activeCount} / ${bots.length}`;
    } catch(e) {
        console.error("Bots fetch error:", e);
    }
}

// --- RENDERING ---
function formatUptime(seconds) {
    if(!seconds) return "0s";
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return `${h}h ${m}m`;
}

function renderBotsGrid(bots) {
    const container = document.getElementById('bots-container');
    if(!container) return;
    container.innerHTML = '';
    
    bots.forEach(bot => {
        const isRunning = bot.status === 'running';
        const badgeClass = isRunning ? 'running' : 'stopped';
        const cardHtml = `
            <div class="bot-card glass" style="--color: ${bot.color || '#fff'};">
                <div class="bot-header">
                    <span class="bot-name">${bot.display}</span>
                    <span class="badge ${badgeClass}">${bot.status}</span>
                </div>
                <div class="bot-uptime">
                    ${isRunning ? `⏱️ Uptime: ${formatUptime(bot.uptime)}` : 'Hors ligne'}
                </div>
                <div class="bot-actions">
                    ${isRunning 
                        ? `<button class="btn btn-outline" onclick="botAction('${bot.id}', 'restart')"><i class="fa-solid fa-rotate-right"></i> Redémarrer</button>
                           <button class="btn btn-danger" onclick="botAction('${bot.id}', 'stop')"><i class="fa-solid fa-stop"></i> Arrêter</button>`
                        : `<button class="btn btn-success" onclick="botAction('${bot.id}', 'start')"><i class="fa-solid fa-play"></i> Démarrer</button>`
                    }
                </div>
            </div>
        `;
        container.insertAdjacentHTML('beforeend', cardHtml);
    });
}

// --- BOT ACTIONS ---
window.botAction = async function(botId, action) {
    try {
        const res = await fetch(`${API_BASE}/bots/${botId}/${action}`, { method: 'POST' });
        const data = await res.json();
        if(data.success) {
            refreshAllData(); // reload status
        } else {
            alert(`Erreur: ${data.error}`);
        }
    } catch(e) {
        alert(`Erreur réseau: ${e}`);
    }
}

window.actionAllBots = async function(action) {
    const bots = Object.keys(BOT_REGISTRY_JS);
    let successCount = 0;
    
    // UI update to prevent spamming
    const btnMap = {
        start: 'btn-start-all-bots',
        stop: 'btn-stop-all-bots',
        restart: 'btn-restart-all-bots'
    };
    const btn = document.getElementById(btnMap[action]);
    const originalText = btn.innerHTML;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Action en cours...`;
    btn.disabled = true;

    for (const botId of bots) {
        try {
            const res = await fetch(`${API_BASE}/bots/${botId}/${action}`, { method: 'POST' });
            const data = await res.json();
            if(data.success || data.error.includes("déjà en cours") || data.error.includes("non en cours")) {
                successCount++;
            }
        } catch(e) {
            console.error(`Status erreur pour ${botId}:`, e);
        }
    }
    
    // Restore button & refresh
    btn.innerHTML = originalText;
    btn.disabled = false;
    
    refreshAllData();
    alert(`${successCount}/6 bots ont traité l'ordre de '${action}'.`);
}

// --- LOGS (WebSocket + REST) ---
let ws;
function initLogsWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const botFilter = document.getElementById('log-bot-filter')?.value || '';
    const wsUrl = `${protocol}//${window.location.host}${API_BASE}/logs/stream${botFilter ? `?bot=${botFilter}` : ''}`;
    
    if (ws) {
        ws.onclose = null; // Prevent reconnect loop during manual re-init
        ws.close();
    }
    
    ws = new WebSocket(wsUrl);
    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if(data.type === 'heartbeat') return;
            appendLogLine(data);
        } catch(e) {
            console.error("WS Parse Error:", e);
        }
    };
    
    ws.onopen = () => {
        const term = document.getElementById('logs-terminal');
        if(term) term.insertAdjacentHTML('beforeend', '<div class="log-line log-info" style="color:var(--success); border-top:1px solid rgba(255,255,255,0.1); padding-top:10px;">--- FLUX LIVE CONNECTÉ ---</div>');
    };

    ws.onclose = () => {
        setTimeout(initLogsWebSocket, 5000); 
    };
}

async function loadLogs() {
    const bot = document.getElementById('log-bot-filter').value;
    const level = document.getElementById('log-level-filter').value;
    const term = document.getElementById('logs-terminal');
    
    try {
        term.innerHTML = '<div class="loader">Chargement...</div>';
        const res = await fetch(`${API_BASE}/logs?bot=${bot}&level=${level}`);
        const result = await res.json();
        
        term.innerHTML = '';
        if(result.data && result.data.length > 0) {
            result.data.reverse().forEach(log => appendLogLine(log));
        } else {
            term.innerHTML = '<div class="log-line">Aucun log trouvé.</div>';
        }
    } catch(e) {
        term.innerHTML = `<div class="log-line log-error">Erreur de chargement: ${e}</div>`;
    }
}

function appendLogLine(log) {
    const term = document.getElementById('logs-terminal');
    if(!term) return;
    
    const time = log.timestamp ? log.timestamp.split('T')[1].substring(0,8) : '00:00:00';
    let levelClass = 'log-info';
    if(log.level === 'WARNING') levelClass = 'log-warning';
    if(log.level === 'ERROR' || log.level === 'CRITICAL') levelClass = 'log-error';
    
    const botColor = BOT_REGISTRY_JS[log.bot]?.color || 'var(--text-secondary)';
    
    const lineStr = `
        <div class="log-line">
            <span class="log-time">[${time}]</span>
            <span class="log-bot" style="color: ${botColor}; font-weight: 600;">[${log.bot || 'SYSTEM'}]</span>
            <span class="${levelClass}">[${log.level}]</span> 
            ${log.message}
        </div>
    `;
    term.insertAdjacentHTML('beforeend', lineStr);
    
    // Limit log history to 500 lines to preserve performance
    while(term.children.length > 500) {
        term.removeChild(term.firstChild);
    }
    
    term.scrollTop = term.scrollHeight;
}

const BOT_REGISTRY_JS = {
    "sheogorath": { name: "sheogorath", display: "🧀 Sheogorath", color: "#d946ef" },
    "maiq": { name: "maiq", display: "🐱 M'aiq le Menteur", color: "#f97316" },
    "alfred": { name: "alfred", display: "☕ Alfred Pennyworth", color: "#475569" },
    "johnny": { name: "johnny", display: "🔫 Johnny Silverbot", color: "#22c55e" },
    "onizuka": { name: "onizuka", display: "🏍️ Eikichi Onizuka", color: "#0ea5e9" },
    "malena": { name: "malena", display: "💃 Malena la Gitana", color: "#f43f5e" }
};

// --- ERRORS ---
async function loadErrors() {
    const container = document.getElementById('error-list-container');
    if(!container) return;
    
    try {
        const res = await fetch(`${API_BASE}/errors`);
        const errors = await res.json();
        
        container.innerHTML = '';
        if(errors.length === 0) {
            container.innerHTML = '<li class="placeholder-text">Aucune erreur récente.</li>';
            return;
        }
        
        errors.forEach(err => {
            const timeStr = err.timestamp.split('T').join(' ').substring(0, 16);
            const li = document.createElement('li');
            li.className = 'error-item';
            li.innerHTML = `
                <div style="display:flex; justify-content:space-between;">
                    <strong>[${err.bot_name}] ${err.error_type}</strong>
                    <span class="badge ${err.severity === 'CRITICAL' ? 'stopped' : ''}">${err.severity}</span>
                </div>
                <div style="font-size:0.85rem; color:#888; margin-top:5px;">${timeStr}</div>
            `;
            li.onclick = () => showErrorDetail(err.id);
            container.appendChild(li);
        });
    } catch(e) {
        container.innerHTML = "Erreur de chargement.";
    }
}

async function showErrorDetail(id) {
    const pane = document.getElementById('error-detail-pane');
    try {
        pane.innerHTML = '<div class="loader">Analyse en cours...</div>';
        const res = await fetch(`${API_BASE}/errors/analyze?error_id=${id}`, {method: 'POST'});
        const data = await res.json();
        
        pane.innerHTML = `
            <h2>Analyse Diagnostique</h2>
            <div class="badge ${data.severity === 'CRITICAL' ? 'stopped' : ''}">${data.severity}</div>
            
            <div class="diagnostic-box">
                <h4>🧠 Diagnostic Automatique (Sert de Base GenAI)</h4>
                <p><strong>Catégorie :</strong> ${data.category}</p>
                <p><strong>Cause Probable :</strong> ${data.auto_diagnosis}</p>
                <p><strong>Correction Suggérée :</strong> ${data.suggested_fix}</p>
            </div>
            <button class="btn btn-outline" onclick="alert('Résolu!')"><i class="fa-solid fa-check"></i> Marquer comme résolu</button>
        `;
    } catch(e) {
        pane.innerHTML = "Erreur lors de l'analyse.";
    }
}

// --- API KEYS ---
async function loadApiKeysStatus() {
    const body = document.getElementById('keys-status-body');
    if(!body) return;
    
    try {
        const res = await fetch(`${API_BASE}/api-usage/keys`);
        const keys = await res.json();
        
        body.innerHTML = '';
        if(!keys || keys.length === 0) {
            body.innerHTML = '<tr><td colspan="6" class="placeholder-text">Aucune clé traquée.</td></tr>';
            return;
        }
        
        keys.forEach(k => {
            const statusClass = k.status === 'active' ? 'success' : (k.status === 'cooldown' ? 'warning' : 'stopped');
            const row = `
                <tr>
                    <td><code class="glass-code">${k.api_key_display}</code></td>
                    <td><span class="badge ${statusClass}">${k.status.toUpperCase()}</span></td>
                    <td>${k.error_count}</td>
                    <td>${k.total_calls}</td>
                    <td>${(k.last_used || '—').split('T')[0]}</td>
                    <td class="log-error">${k.last_error || '—'}</td>
                </tr>
            `;
            body.insertAdjacentHTML('beforeend', row);
        });
    } catch(e) {
        body.innerHTML = '<tr><td colspan="6" class="log-error">Erreur de chargement.</td></tr>';
    }
}

// --- REPORTS ---
async function generateReport() {
    const btn = document.getElementById('btn-generate-report');
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Génération...';
    btn.disabled = true;
    
    const scope = document.getElementById('report-scope').value;
    const hours = document.getElementById('report-timeframe').value;
    
    try {
        const res = await fetch(`${API_BASE}/reports/generate?format=md&scope=${scope}&hours=${hours}`, {method: 'POST'});
        const data = await res.json();
        alert(`Rapport généré avec succès :\n${data.filename}\nEmplacement: ${data.path}`);
    } catch(e) {
        alert("Erreur lors de la génération.");
    } finally {
        btn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Générer le Rapport .MD';
        btn.disabled = false;
    }
}

// --- TWITCH MANAGEMENT ---
let twitchConfig = {};

async function loadTwitchConfig() {
    try {
        const res = await fetch(`${API_BASE}/twitch`);
        if (!res.ok) throw new Error("Impossible de charger la config Twitch");
        twitchConfig = await res.json();
        renderTwitchBotView();
    } catch (e) {
        console.error("Twitch config error:", e);
    }
}

window.onTwitchBotSelect = function() {
    renderTwitchBotView();
}

function renderTwitchBotView() {
    const botId = document.getElementById('config-bot-select').value;
    const botConfig = twitchConfig[botId];
    
    if (!botConfig) return;
    
    // Set status title
    const botDisplayNames = {
        sheogorath: "🧀 Sheogorath",
        maiq: "🐱 M'aiq le Menteur",
        alfred: "☕ Alfred Pennyworth",
        johnny: "🔫 Johnny Silverbot",
        onizuka: "🏍️ Eikichi Onizuka",
        malena: "💃 Malena la Gitana"
    };
    document.getElementById('twitch-bot-status-title').textContent = `Configuration Twitch de ${botDisplayNames[botId] || botId}`;
    
    // Set form values
    document.getElementById('twitch-bot-enabled').checked = botConfig.enabled;
    document.getElementById('twitch-bot-interval').value = botConfig.poll_interval_seconds;
    
    // Set subscriptions
    const emptyEl = document.getElementById('twitch-subs-empty');
    const listEl = document.getElementById('twitch-subs-list');
    
    listEl.innerHTML = '';
    
    const subs = botConfig.subscriptions || [];
    if (subs.length === 0) {
        emptyEl.style.display = 'block';
        listEl.style.display = 'none';
    } else {
        emptyEl.style.display = 'none';
        listEl.style.display = 'flex';
        
        subs.forEach((sub, index) => {
            const card = `
                <div class="twitch-sub-card glass" style="padding: 1rem; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05); display: flex; justify-content: space-between; align-items: center; background: rgba(255,255,255,0.01);">
                    <div style="flex-grow: 1; margin-right: 15px;">
                        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 6px;">
                            <span style="font-weight: 600; color: #a78bfa; font-size: 1.05em;"><i class="fa-brands fa-twitch"></i> ${sub.twitch_login}</span>
                            <span style="font-size: 0.85em; background: rgba(59, 130, 246, 0.2); color: #60a5fa; padding: 2px 6px; border-radius: 4px; font-family: monospace;">Salon: ${sub.discord_channel_id}</span>
                        </div>
                        ${sub.custom_message ? `<div style="font-size: 0.85em; opacity: 0.85; border-left: 2px solid var(--accent); padding-left: 8px; margin-top: 4px; font-style: italic;">"${sub.custom_message}"</div>` : `<div style="font-size: 0.8em; opacity: 0.5; font-style: italic;">Message embed standard auto</div>`}
                    </div>
                    <button class="btn btn-danger" onclick="deleteTwitchSubscription(${index})" style="padding: 6px 12px; font-size: 0.9em; flex-shrink: 0;">
                        <i class="fa-solid fa-trash"></i> Supprimer
                    </button>
                </div>
            `;
            listEl.insertAdjacentHTML('beforeend', card);
        });
    }
}

window.saveTwitchBotSettings = async function() {
    const botId = document.getElementById('config-bot-select').value;
    const enabled = document.getElementById('twitch-bot-enabled').checked;
    const interval = parseInt(document.getElementById('twitch-bot-interval').value);
    
    if (isNaN(interval) || interval < 60) {
        alert("L'intervalle de polling doit être d'au moins 60 secondes.");
        return;
    }
    
    try {
        const res = await fetch(`${API_BASE}/twitch/${botId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled, poll_interval_seconds: interval })
        });
        
        if (res.ok) {
            alert("Paramètres enregistrés avec succès !");
            await loadTwitchConfig();
        } else {
            const data = await res.json();
            alert(`Erreur: ${data.detail || "Impossible de sauvegarder la configuration"}`);
        }
    } catch (e) {
        alert(`Erreur réseau: ${e}`);
    }
}

window.addTwitchSubscription = async function() {
    const botId = document.getElementById('config-bot-select').value;
    const twitchLogin = document.getElementById('twitch-add-login').value.trim();
    const channelId = document.getElementById('twitch-add-channel').value.trim();
    const customMessage = document.getElementById('twitch-add-message').value.trim() || null;
    
    if (!twitchLogin || !channelId) {
        alert("La chaîne Twitch et l'ID du salon Discord sont requis.");
        return;
    }
    
    try {
        const res = await fetch(`${API_BASE}/twitch/${botId}/subscriptions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                twitch_login: twitchLogin,
                discord_channel_id: channelId,
                custom_message: customMessage
            })
        });
        
        if (res.ok) {
            document.getElementById('twitch-add-login').value = '';
            document.getElementById('twitch-add-channel').value = '';
            document.getElementById('twitch-add-message').value = '';
            alert("Abonnement Twitch ajouté avec succès !");
            await loadTwitchConfig();
        } else {
            const data = await res.json();
            alert(`Erreur: ${data.detail || "Impossible d'ajouter l'abonnement"}`);
        }
    } catch (e) {
        alert(`Erreur réseau: ${e}`);
    }
}

window.setTwitchEnabledAll = async function(enabled) {
    if (!confirm(enabled ? "Activer la surveillance Twitch pour TOUS les bots ?"
                         : "Désactiver la surveillance Twitch pour TOUS les bots ?")) return;
    try {
        const res = await fetch(`${API_BASE}/twitch/all`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled })
        });
        if (res.ok) {
            alert(enabled ? "Surveillance activée pour tous les bots."
                          : "Surveillance désactivée pour tous les bots.");
            await loadTwitchConfig();
        } else {
            const d = await res.json(); alert(`Erreur: ${d.detail || ''}`);
        }
    } catch (e) { alert(`Erreur réseau: ${e}`); }
}

window.addTwitchSubscriptionAll = async function() {
    const login = document.getElementById('twitch-all-login').value.trim();
    const channel = document.getElementById('twitch-all-channel').value.trim();
    const msg = document.getElementById('twitch-all-message').value.trim() || null;
    if (!login || !channel) { alert("La chaîne Twitch et le salon Discord sont requis."); return; }
    try {
        const res = await fetch(`${API_BASE}/twitch/all/subscriptions`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ twitch_login: login, discord_channel_id: channel, custom_message: msg })
        });
        const d = await res.json();
        if (res.ok) {
            document.getElementById('twitch-all-login').value = '';
            document.getElementById('twitch-all-channel').value = '';
            document.getElementById('twitch-all-message').value = '';
            alert(`Ajouté à ${d.added.length} bot(s).` + (d.skipped.length ? ` Déjà présent sur ${d.skipped.length}.` : ''));
            await loadTwitchConfig();
        } else {
            alert(`Erreur: ${d.detail || "Impossible d'ajouter l'abonnement"}`);
        }
    } catch (e) { alert(`Erreur réseau: ${e}`); }
}

window.deleteTwitchSubscription = async function(index) {
    const botId = document.getElementById('config-bot-select').value;
    if (!confirm("Voulez-vous vraiment supprimer cet abonnement ?")) return;
    
    try {
        const res = await fetch(`${API_BASE}/twitch/${botId}/subscriptions/${index}`, {
            method: 'DELETE'
        });
        
        if (res.ok) {
            await loadTwitchConfig();
        } else {
            const data = await res.json();
            alert(`Erreur: ${data.detail || "Impossible de supprimer l'abonnement"}`);
        }
    } catch (e) {
        alert(`Erreur réseau: ${e}`);
    }
}

// --- PRESENCE & CONNEXION ---
window.onPresenceBotSelect = function() {
    loadTwitchPresence();
}

async function loadTwitchPresence() {
    const botId = document.getElementById('config-bot-select').value;
    try {
        const configRes = await fetch(`${API_BASE}/twitch`);
        const configData = await configRes.json();
        const botConfig = configData[botId] || {};
        const targetChannel = (botConfig.subscriptions || []).map(s => s.twitch_login).join(', ') || 'Aucune';
        document.getElementById('presence-target-channel').textContent = targetChannel;
        
        const res = await fetch(`${API_BASE}/twitch/chat/${botId}`);
        if (!res.ok) throw new Error("Impossible de charger la config présence Twitch");
        const chatCfg = await res.json();
        
        document.getElementById('presence-status-badge').textContent = botConfig.enabled ? "Active" : "Inactive";
        document.getElementById('presence-status-badge').className = botConfig.enabled ? "badge badge-success" : "badge badge-secondary";
        
        document.getElementById('presence-chat-events').checked = chatCfg.events !== false;
        document.getElementById('presence-chat-interjections').checked = chatCfg.interjections !== false;
        document.getElementById('presence-chat-greetings').checked = chatCfg.greetings !== false;
        document.getElementById('presence-chat-memory').checked = chatCfg.viewer_memory !== false;

        // Charger les chaînes de chat
        const channelsRes = await fetch(`${API_BASE}/twitch/channels/${botId}`);
        if (channelsRes.ok) {
            const channelsData = await channelsRes.json();
            document.getElementById('presence-chat-channels').value = (channelsData.chat_channels || []).join(', ');
        } else {
            document.getElementById('presence-chat-channels').value = '';
        }
    } catch (e) {
        console.error("Twitch presence config error:", e);
    }
}

window.savePresenceSettings = async function() {
    const botId = document.getElementById('config-bot-select').value;
    const events = document.getElementById('presence-chat-events').checked;
    const interjections = document.getElementById('presence-chat-interjections').checked;
    const greetings = document.getElementById('presence-chat-greetings').checked;
    const viewer_memory = document.getElementById('presence-chat-memory').checked;
    
    try {
        const res = await fetch(`${API_BASE}/twitch/chat/${botId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ events, interjections, greetings, viewer_memory })
        });
        if (res.ok) {
            alert("Configuration de présence enregistrée avec succès !");
            await loadTwitchPresence();
        } else {
            const data = await res.json();
            alert(`Erreur: ${data.detail || "Sauvegarde impossible"}`);
        }
    } catch (e) {
        alert(`Erreur réseau: ${e}`);
    }
}

window.saveChatChannels = async function() {
    const botId = document.getElementById('config-bot-select').value;
    const rawChannels = document.getElementById('presence-chat-channels').value;
    const channels = rawChannels.split(/[,\n]/).map(c => c.trim()).filter(c => c.length > 0);
    
    try {
        const res = await fetch(`${API_BASE}/twitch/channels/${botId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ chat_channels: channels })
        });
        if (res.ok) {
            const data = await res.json();
            alert("Chaînes de chat enregistrées avec succès !");
            document.getElementById('presence-chat-channels').value = (data.chat_channels || []).join(', ');
        } else {
            const data = await res.json();
            alert(`Erreur: ${data.detail || "Sauvegarde impossible"}`);
        }
    } catch (e) {
        alert(`Erreur réseau: ${e}`);
    }
}

// --- EVENTS & REWARDS ---
let currentRewardMap = {};
window.onEventsBotSelect = function() {
    loadTwitchEvents();
}

async function loadTwitchEvents() {
    const botId = document.getElementById('config-bot-select').value;
    try {
        const res = await fetch(`${API_BASE}/twitch/rewards/${botId}`);
        if (!res.ok) throw new Error("Impossible de charger le mappage de récompenses");
        currentRewardMap = await res.json();
        renderRewardsTable();
    } catch (e) {
        console.error("Twitch events config error:", e);
    }
}

function renderRewardsTable() {
    const body = document.getElementById('twitch-rewards-table-body');
    if (!body) return;
    body.innerHTML = '';
    
    const keys = Object.keys(currentRewardMap);
    if (keys.length === 0) {
        body.innerHTML = '<tr><td colspan="3" style="text-align:center;opacity:0.5;">Aucun mappage de récompense défini pour ce bot.</td></tr>';
        return;
    }
    
    keys.forEach(title => {
        const action = currentRewardMap[title];
        const row = `
            <tr>
                <td style="color:#a78bfa; font-weight:600;"><i class="fa-solid fa-gift"></i> ${title}</td>
                <td><code style="background:rgba(255,255,255,0.1); padding:2px 6px; border-radius:4px; font-family:monospace;">!${action}</code></td>
                <td>
                    <button class="btn btn-danger" onclick="deleteRewardMapping('${title.replace(/'/g, "\\'")}')" style="padding:4px 8px; font-size:0.85em;">
                        <i class="fa-solid fa-trash"></i> Retirer
                    </button>
                </td>
            </tr>
        `;
        body.insertAdjacentHTML('beforeend', row);
    });
}

window.addRewardMapping = function() {
    const title = document.getElementById('add-reward-title').value.trim();
    const action = document.getElementById('add-reward-action').value.trim();
    
    if (!title || !action) {
        alert("Le titre de la récompense et l'action/commande sont requis.");
        return;
    }
    
    currentRewardMap[title] = action;
    document.getElementById('add-reward-title').value = '';
    document.getElementById('add-reward-action').value = '';
    renderRewardsTable();
}

window.deleteRewardMapping = function(title) {
    delete currentRewardMap[title];
    renderRewardsTable();
}

window.saveRewardsMapping = async function() {
    const botId = document.getElementById('config-bot-select').value;
    try {
        const res = await fetch(`${API_BASE}/twitch/rewards/${botId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(currentRewardMap)
        });
        if (res.ok) {
            alert("Mappage des récompenses enregistré avec succès !");
            await loadTwitchEvents();
        } else {
            const data = await res.json();
            alert(`Erreur: ${data.detail || "Sauvegarde impossible"}`);
        }
    } catch (e) {
        alert(`Erreur réseau: ${e}`);
    }
}

// --- ECONOMY ---
window.onEconomyBotSelect = function() {
    loadTwitchEconomy();
}

async function loadTwitchEconomy() {
    const botId = document.getElementById('config-bot-select').value;
    try {
        const res = await fetch(`${API_BASE}/twitch/leaderboard/${botId}`);
        if (!res.ok) throw new Error("Impossible de charger le classement économique");
        const top = await res.json();
        
        const emptyEl = document.getElementById('economy-leaderboard-empty');
        const tableEl = document.getElementById('economy-leaderboard-table');
        const bodyEl = document.getElementById('economy-leaderboard-body');
        
        if (!bodyEl) return;
        bodyEl.innerHTML = '';
        if (!top || top.length === 0) {
            emptyEl.style.display = 'block';
            tableEl.style.display = 'none';
        } else {
            emptyEl.style.display = 'none';
            tableEl.style.display = 'table';
            top.forEach((entry, index) => {
                const row = `
                    <tr>
                        <td style="font-weight:700; opacity:0.6;">#${index+1}</td>
                        <td style="color:#fff; font-weight:600;"><i class="fa-solid fa-user-ninja"></i> ${entry.name}</td>
                        <td style="color:#60a5fa; font-weight:700;">${entry.points} pts</td>
                    </tr>
                `;
                bodyEl.insertAdjacentHTML('beforeend', row);
            });
        }
    } catch (e) {
        console.error("Twitch economy leaderboard error:", e);
    }
}

// --- LISTEN (STT) ---
window.onListenBotSelect = function() {
    loadTwitchListen();
}

async function loadTwitchListen() {
    const botId = document.getElementById('config-bot-select').value;
    try {
        const res = await fetch(`${API_BASE}/twitch/listen/${botId}`);
        if (!res.ok) throw new Error("Impossible de charger la config écoute Twitch");
        const listenCfg = await res.json();
        
        document.getElementById('listen-enabled').checked = listenCfg.enabled === true;
        document.getElementById('listen-mode').value = listenCfg.mode || "C";
        document.getElementById('listen-device').value = (listenCfg.device === "cuda") ? "cuda" : "cpu";
        document.getElementById('listen-chunk').value = String(listenCfg.chunk_ms || 160);
        document.getElementById('listen-min-interval').value = listenCfg.min_interval || 45;
    } catch (e) {
        console.error("Twitch listen config error:", e);
    }
}

window.saveListenSettings = async function() {
    const botId = document.getElementById('config-bot-select').value;
    const enabled = document.getElementById('listen-enabled').checked;
    const mode = document.getElementById('listen-mode').value;
    const device = document.getElementById('listen-device').value.trim();
    const chunk_ms = parseInt(document.getElementById('listen-chunk').value);
    const min_interval = parseInt(document.getElementById('listen-min-interval').value);
    
    try {
        const res = await fetch(`${API_BASE}/twitch/listen/${botId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled, mode, device, chunk_ms, min_interval })
        });
        if (res.ok) {
            alert("Configuration d'écoute micro enregistrée avec succès !");
            await loadTwitchListen();
        } else {
            const data = await res.json();
            alert(`Erreur: ${data.detail || "Sauvegarde impossible"}`);
        }
    } catch (e) {
        alert(`Erreur réseau: ${e}`);
    }
}
