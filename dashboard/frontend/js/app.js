const API_BASE = '/api';

function escapeHtml(s) {
    return String(s ?? '').replace(/[&<>"']/g, c =>
        ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

window.toast = function(message, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        document.body.appendChild(container);
    }
    
    const t = document.createElement('div');
    t.className = `toast toast-${type} glass`;
    
    let icon = 'fa-circle-info';
    if (type === 'success') icon = 'fa-circle-check';
    if (type === 'error') icon = 'fa-circle-exclamation';
    
    t.innerHTML = `<i class="fa-solid ${icon}"></i> <span>${escapeHtml(message)}</span>`;
    container.appendChild(t);
    
    setTimeout(() => t.classList.add('show'), 10);
    
    setTimeout(() => {
        t.classList.remove('show');
        setTimeout(() => t.remove(), 300);
    }, 4000);
};

window.toastAction = function(message, actionLabel, onAction, type = 'success') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        document.body.appendChild(container);
    }
    
    const t = document.createElement('div');
    t.className = `toast toast-${type} glass`;
    
    let icon = 'fa-circle-info';
    if (type === 'success') icon = 'fa-circle-check';
    if (type === 'error') icon = 'fa-circle-exclamation';
    
    const content = document.createElement('span');
    content.innerHTML = `<i class="fa-solid ${icon}" style="margin-right: 8px;"></i>${escapeHtml(message)}`;
    t.appendChild(content);
    
    const btn = document.createElement('button');
    btn.className = 'btn btn-primary btn-sm';
    btn.textContent = actionLabel;
    btn.style.marginLeft = 'auto';
    btn.addEventListener('click', () => {
        onAction();
        t.classList.remove('show');
        setTimeout(() => t.remove(), 300);
    });
    t.appendChild(btn);
    
    container.appendChild(t);
    
    setTimeout(() => t.classList.add('show'), 10);
    
    setTimeout(() => {
        t.classList.remove('show');
        setTimeout(() => t.remove(), 300);
    }, 10000);
};

window.confirmDialog = function(message) {
    return new Promise((resolve) => {
        const overlay = document.createElement('div');
        overlay.className = 'confirm-overlay';
        
        overlay.innerHTML = `
            <div class="confirm-box">
                <div class="confirm-message">${escapeHtml(message)}</div>
                <div class="confirm-actions">
                    <button class="btn btn-danger" id="confirm-yes">Confirmer</button>
                    <button class="btn" id="confirm-no">Annuler</button>
                </div>
            </div>
        `;
        
        document.body.appendChild(overlay);
        
        setTimeout(() => overlay.classList.add('show'), 10);
        
        const cleanup = (value) => {
            overlay.classList.remove('show');
            setTimeout(() => overlay.remove(), 200);
            document.removeEventListener('keydown', handleKeydown);
            resolve(value);
        };
        
        const handleKeydown = (e) => {
            if (e.key === 'Escape') cleanup(false);
            if (e.key === 'Enter') cleanup(true);
        };
        
        document.addEventListener('keydown', handleKeydown);
        overlay.querySelector('#confirm-yes').onclick = () => cleanup(true);
        overlay.querySelector('#confirm-no').onclick = () => cleanup(false);
    });
};

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
            if(targetId === 'audit-logs') loadAuditLogs();
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
                if (featureName === 'test_mode') displayName = "Mode test (ne publie que sur le serveur privé)";
                
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
    if (value === false && !await confirmDialog("Désactiver cette fonctionnalité sur TOUS les bots ?")) return;
    try {
        const res = await fetch(`${API_BASE}/features/all`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ feature: featureName, value: value })
        });
        if (res.ok) {
            toast("Action globale appliquée avec succès !", 'success');
            await loadBotConfig();
        } else {
            const d = await res.json();
            toast(`Erreur: ${d.detail || "Sauvegarde impossible"}`, 'error');
        }
    } catch (e) {
        toast(`Erreur réseau: ${e}`, 'error');
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
    await updateStatTiles();
    // Les graphes seront rafraîchis via charts.js
    if (typeof window.refreshCharts === 'function') {
        window.refreshCharts();
    }
}

async function updateStatTiles() {
    try {
        const errRes = await fetch('/api/errors/count?hours=24');
        if (errRes.ok) {
            const errCount = await errRes.json();
            const statErrorsEl = document.getElementById('stat-errors');
            if (statErrorsEl) statErrorsEl.textContent = errCount;
        }
    } catch(e) { console.error("Error stat tile fetch error:", e); }

    try {
        const apiRes = await fetch('/api/api-usage?hours=24');
        if (apiRes.ok) {
            const apiData = await apiRes.json();
            const statApiEl = document.getElementById('stat-api-success');
            if (statApiEl) {
                let totalCalls = 0;
                let totalErrors = 0;
                if (apiData && apiData.by_api) {
                    for (const provider of Object.values(apiData.by_api)) {
                        totalCalls += provider.calls || 0;
                        totalErrors += provider.errors || 0;
                    }
                }
                if (totalCalls > 0) {
                    const rate = ((totalCalls - totalErrors) / totalCalls) * 100;
                    statApiEl.textContent = `${rate.toFixed(1)}%`;
                } else {
                    statApiEl.textContent = '—';
                }
            }
        }
    } catch(e) { console.error("API stat tile fetch error:", e); }

    try {
        const convRes = await fetch('/api/conversations?days=7');
        if (convRes.ok) {
            const convData = await convRes.json();
            const statUsersEl = document.getElementById('stat-users');
            if (statUsersEl) {
                statUsersEl.textContent = convData.unique_users ?? 0;
            }
        }
    } catch(e) { console.error("Users stat tile fetch error:", e); }
}

async function fetchBotsStatus() {
    try {
        const res = await fetch(`${API_BASE}/bots`);
        if(!res.ok) throw new Error("Failed to fetch bots");
        const bots = await res.json();
        renderBotsGrid(bots);
        
        const activeCount = bots.filter(b => b.status === 'running').length;
        document.getElementById('stat-active-bots').textContent = `${activeCount} / ${bots.length}`;
        
        const indicatorEl = document.getElementById('system-status-indicator');
        const textEl = document.getElementById('system-status-text');
        if (indicatorEl && textEl) {
            const hasStoppedBot = bots.some(b => b.status !== 'running');
            if (hasStoppedBot) {
                indicatorEl.className = 'status-indicator warning';
                textEl.textContent = `${activeCount}/${bots.length} bots actifs`;
            } else {
                indicatorEl.className = 'status-indicator online';
                textEl.textContent = 'Système Normal';
            }
        }
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
    
    const registryOrder = Object.keys(BOT_REGISTRY_JS);
    bots.sort((a, b) => {
        const indexA = registryOrder.indexOf(a.id);
        const indexB = registryOrder.indexOf(b.id);
        if (indexA !== -1 && indexB !== -1) return indexA - indexB;
        return a.id.localeCompare(b.id);
    });

    bots.forEach(bot => {
        const cardId = `bot-card-${bot.id}`;
        let card = document.getElementById(cardId);
        const isRunning = bot.status === 'running';
        const badgeClass = isRunning ? 'badge running' : 'badge stopped';
        
        const actionsHtml = isRunning 
            ? `<button class="btn btn-outline" onclick="botAction('${bot.id}', 'restart')"><i class="fa-solid fa-rotate-right"></i> Redémarrer</button>
               <button class="btn btn-danger" onclick="botAction('${bot.id}', 'stop')"><i class="fa-solid fa-stop"></i> Arrêter</button>`
            : `<button class="btn btn-success" onclick="botAction('${bot.id}', 'start')"><i class="fa-solid fa-play"></i> Démarrer</button>`;
        
        const uptimeHtml = isRunning ? `⏱️ Uptime: ${formatUptime(bot.uptime)}` : 'Hors ligne';
        const statsHtml = isRunning ? `⚡ CPU: ${escapeHtml(bot.cpu)} | 💾 RAM: ${escapeHtml(bot.ram)}` : '';

        if (card) {
            const badge = card.querySelector('.badge');
            if (badge) {
                if (badge.textContent !== bot.status) {
                    badge.textContent = bot.status;
                }
                if (badge.className !== badgeClass) {
                    badge.className = badgeClass;
                }
            }
            
            const uptime = card.querySelector('.bot-uptime');
            if (uptime && uptime.innerHTML !== uptimeHtml) {
                uptime.innerHTML = uptimeHtml;
            }
            
            const stats = card.querySelector('.bot-stats');
            if (stats) {
                if (stats.innerHTML !== statsHtml) {
                    stats.innerHTML = statsHtml;
                }
            } else if (isRunning) {
                const statsDiv = document.createElement('div');
                statsDiv.className = 'bot-stats';
                statsDiv.style.fontSize = '0.85rem';
                statsDiv.style.opacity = '0.8';
                statsDiv.style.marginTop = '4px';
                statsDiv.innerHTML = statsHtml;
                uptime.after(statsDiv);
            }
            
            if (!isRunning && stats) {
                stats.remove();
            }
            
            const actions = card.querySelector('.bot-actions');
            if (actions && actions.innerHTML !== actionsHtml) {
                actions.innerHTML = actionsHtml;
            }
        } else {
            const cardHtml = `
                <div class="bot-card glass" id="${cardId}" style="--color: ${bot.color || '#fff'};">
                    <div class="bot-header">
                        <span class="bot-name">${escapeHtml(bot.display)}</span>
                        <span class="${badgeClass}">${escapeHtml(bot.status)}</span>
                    </div>
                    <div class="bot-uptime">
                        ${uptimeHtml}
                    </div>
                    ${isRunning ? `<div class="bot-stats" style="font-size: 0.85rem; opacity: 0.8; margin-top: 4px;">${statsHtml}</div>` : ''}
                    <div class="bot-actions">
                        ${actionsHtml}
                    </div>
                </div>
            `;
            container.insertAdjacentHTML('beforeend', cardHtml);
        }
    });
    
    const currentBotIds = bots.map(b => `bot-card-${b.id}`);
    Array.from(container.children).forEach(child => {
        if (!currentBotIds.includes(child.id)) {
            child.remove();
        }
    });
}

// --- BOT ACTIONS ---
window.botAction = async function(botId, action) {
    if (action === 'stop' && !await confirmDialog(`Arrêter le bot « ${botId} » ?`)) return;
    try {
        const res = await fetch(`${API_BASE}/bots/${botId}/${action}`, { method: 'POST' });
        const data = await res.json();
        if(data.success) {
            refreshAllData(); // reload status
        } else {
            toast(`Erreur: ${data.error}`, 'error');
        }
    } catch(e) {
        toast(`Erreur réseau: ${e}`, 'error');
    }
}

window.actionAllBots = async function(action) {
    if (action === 'stop' && !await confirmDialog("Arrêter TOUS les bots ? Ils seront déconnectés de Discord et Twitch.")) return;
    if (action === 'restart' && !await confirmDialog("Redémarrer TOUS les bots ? Coupure brève sur Discord et Twitch.")) return;
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
            if(data.success || (data.error || '').includes("déjà en cours") || (data.error || '').includes("non en cours")) {
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
    toast(`${successCount}/6 bots ont traité l'ordre de '${action}'.`, 'info');
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
            <span class="log-bot" style="color: ${botColor}; font-weight: 600;">[${escapeHtml(log.bot || 'SYSTEM')}]</span>
            <span class="${levelClass}">[${escapeHtml(log.level)}]</span> 
            ${escapeHtml(log.message)}
        </div>
    `;
    term.insertAdjacentHTML('beforeend', lineStr);
    
    // Limit log history to 500 lines to preserve performance
    while(term.children.length > 500) {
        term.removeChild(term.firstChild);
    }
    
    term.scrollTop = term.scrollHeight;
}



// --- ERRORS ---
async function loadErrors() {
    const container = document.getElementById('error-list-container');
    if(!container) return;
    
    try {
        const showResolved = document.getElementById('show-resolved-errors')?.checked ?? false;
        const res = await fetch(`${API_BASE}/errors?resolved=${showResolved}`);
        const errors = await res.json();
        
        container.innerHTML = '';
        if(errors.length === 0) {
            container.innerHTML = `<li class="placeholder-text">Aucune erreur ${showResolved ? 'résolue' : 'récente'}.</li>`;
            return;
        }
        
        errors.forEach(err => {
            const timeStr = err.timestamp.split('T').join(' ').substring(0, 16);
            const li = document.createElement('li');
            li.className = 'error-item';
            li.innerHTML = `
                <div style="display:flex; justify-content:space-between;">
                    <strong>[${escapeHtml(err.bot_name)}] ${escapeHtml(err.error_type)}</strong>
                    <span class="badge ${err.severity === 'CRITICAL' ? 'stopped' : ''}">${escapeHtml(err.severity)}</span>
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
            <div class="badge ${data.severity === 'CRITICAL' ? 'stopped' : ''}">${escapeHtml(data.severity)}</div>
            
            <div class="diagnostic-box">
                <h4>🧠 Diagnostic Automatique (Sert de Base GenAI)</h4>
                <p><strong>Catégorie :</strong> ${escapeHtml(data.category)}</p>
                <p>Cause Probable : ${escapeHtml(data.auto_diagnosis)}</p>
                <p>Correction Suggérée : ${escapeHtml(data.suggested_fix)}</p>
            </div>
            <button class="btn btn-outline" onclick="resolveError(${id})"><i class="fa-solid fa-check"></i> Marquer comme résolu</button>
        `;
    } catch(e) {
        pane.innerHTML = "Erreur lors de l'analyse.";
    }
}

window.resolveError = async function(id) {
    try {
        const res = await fetch(`${API_BASE}/errors/${id}/resolve`, {method: 'POST'});
        const data = await res.json();
        if (res.ok && data.success) {
            if (typeof window.toast === 'function') {
                window.toast("Erreur marquée comme résolue", "success");
            } else {
                toast("Erreur marquée comme résolue", 'success');
            }
            loadErrors();
            const pane = document.getElementById('error-detail-pane');
            if (pane) pane.innerHTML = '<li class="placeholder-text" style="list-style: none;">Sélectionnez une erreur pour afficher les détails.</li>';
        } else {
            throw new Error(data.detail || "Échec");
        }
    } catch(e) {
        if (typeof window.toast === 'function') {
            window.toast("Erreur : " + e.message, "error");
        } else {
            toast("Erreur : " + e.message, 'error');
        }
    }
}

// --- API KEYS ---
async function loadApiKeysStatus() {
    const body = document.getElementById('keys-status-body');
    const grid = document.getElementById('keys-health-grid');
    if(!body) return;
    
    try {
        const res = await fetch(`${API_BASE}/api-usage/keys`);
        const keys = await res.json();
        
        if (grid) {
            grid.innerHTML = '';
            if (!keys || keys.length === 0) {
                grid.innerHTML = '<span class="placeholder-text" style="font-size:0.9rem;">Aucune clé configurée.</span>';
            } else {
                keys.forEach(k => {
                    const statusColor = k.status === 'active' ? 'var(--success)' : (k.status === 'cooldown' ? 'var(--warning)' : 'var(--danger)');
                    const dot = document.createElement('div');
                    dot.style.width = '14px';
                    dot.style.height = '14px';
                    dot.style.borderRadius = '50%';
                    dot.style.backgroundColor = statusColor;
                    dot.style.cursor = 'pointer';
                    if (k.status === 'active') {
                        dot.style.boxShadow = '0 0 8px var(--success)';
                    } else if (k.status === 'cooldown') {
                        dot.style.boxShadow = '0 0 8px var(--warning)';
                    } else {
                        dot.style.boxShadow = '0 0 8px var(--danger)';
                    }
                    dot.title = `Clé: ${k.api_key_display} | Statut: ${k.status.toUpperCase()} | Appels: ${k.total_calls} | Erreurs: ${k.error_count}`;
                    grid.appendChild(dot);
                });
            }
        }
        
        body.innerHTML = '';
        if(!keys || keys.length === 0) {
            body.innerHTML = '<tr><td colspan="6" class="placeholder-text">Aucune clé traquée.</td></tr>';
            return;
        }
        
        keys.forEach(k => {
            const statusClass = k.status === 'active' ? 'success' : (k.status === 'cooldown' ? 'warning' : 'stopped');
            const row = `
                <tr>
                    <td><code class="glass-code">${escapeHtml(k.api_key_display)}</code></td>
                    <td><span class="badge ${statusClass}">${escapeHtml(k.status.toUpperCase())}</span></td>
                    <td>${k.error_count}</td>
                    <td>${k.total_calls}</td>
                    <td>${escapeHtml((k.last_used || '—').split('T')[0])}</td>
                    <td class="log-error" title="${escapeHtml(k.last_error || '')}">${escapeHtml(k.last_error || '—')}</td>
                </tr>
            `;
            body.insertAdjacentHTML('beforeend', row);
        });
    } catch(e) {
        body.innerHTML = '<tr><td colspan="6" class="log-error">Erreur de chargement.</td></tr>';
        if (grid) grid.innerHTML = '<span class="log-error">Erreur.</span>';
    }
}

window.loadAuditLogs = async function() {
    const body = document.getElementById('audit-logs-body');
    if (!body) return;
    
    body.innerHTML = '<tr><td colspan="5" class="loader">Chargement...</td></tr>';
    
    try {
        const res = await fetch(`${API_BASE}/audit-logs?limit=100`);
        if (!res.ok) throw new Error("Erreur de chargement");
        const logs = await res.json();
        
        body.innerHTML = '';
        if (logs.length === 0) {
            body.innerHTML = '<tr><td colspan="5" class="placeholder-text">Aucun log d\'audit enregistré pour le moment.</td></tr>';
            return;
        }
        
        logs.forEach(log => {
            const timeStr = log.timestamp.split('T').join(' ').substring(0, 19);
            const row = `
                <tr>
                    <td style="white-space: nowrap;">${escapeHtml(timeStr)}</td>
                    <td><span class="badge warning">${escapeHtml(log.user)}</span></td>
                    <td style="font-weight: 600; color: #a78bfa;">${escapeHtml(log.action)}</td>
                    <td>${log.bot_name ? `<span class="badge info">${escapeHtml(log.bot_name)}</span>` : '—'}</td>
                    <td>${escapeHtml(log.details || '—')}</td>
                </tr>
            `;
            body.insertAdjacentHTML('beforeend', row);
        });
    } catch(e) {
        body.innerHTML = '<tr><td colspan="5" class="log-error">Erreur lors de la récupération des logs d\'audit.</td></tr>';
    }
};

// --- REPORTS ---
let lastGeneratedFilename = null;

async function generateReport() {
    const btn = document.getElementById('btn-generate-report');
    if (!btn) return;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Génération...';
    btn.disabled = true;
    
    const scope = document.getElementById('report-scope').value;
    const hours = document.getElementById('report-timeframe').value;
    
    try {
        const res = await fetch(`${API_BASE}/reports/generate?format=md&scope=${scope}&hours=${hours}`, {method: 'POST'});
        const data = await res.json();
        
        lastGeneratedFilename = data.filename;
        
        const previewText = document.getElementById('report-preview-text');
        const resultPanel = document.getElementById('report-result-panel');
        
        if (previewText && resultPanel) {
            previewText.value = data.content;
            resultPanel.style.display = 'flex';
        }
        
        toast("Rapport généré avec succès !", 'success');
    } catch(e) {
        toast("Erreur lors de la génération.", 'error');
    } finally {
        btn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Générer le Rapport .MD';
        btn.disabled = false;
    }
}

window.copyReportToClipboard = function() {
    const previewText = document.getElementById('report-preview-text');
    if (!previewText || !previewText.value) return;
    
    previewText.select();
    navigator.clipboard.writeText(previewText.value)
        .then(() => {
            toast("Copié dans le presse-papier !", 'success');
        })
        .catch(() => {
            toast("Échec de la copie.", 'error');
        });
};

window.downloadGeneratedReport = function() {
    if (!lastGeneratedFilename) {
        toast("Aucun rapport généré.", 'error');
        return;
    }
    window.location.href = `${API_BASE}/reports/download/${lastGeneratedFilename}`;
};

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
        johnny: "🔫 Johnny Silverhand",
        sugar: "Sugar Bot",
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
                            <span style="font-weight: 600; color: #a78bfa; font-size: 1.05em;"><i class="fa-brands fa-twitch"></i> ${escapeHtml(sub.twitch_login)}</span>
                            <span style="font-size: 0.85em; background: rgba(59, 130, 246, 0.2); color: #60a5fa; padding: 2px 6px; border-radius: 4px; font-family: monospace;">Salon: ${escapeHtml(sub.discord_channel_id)}</span>
                        </div>
                        ${sub.custom_message ? `<div style="font-size: 0.85em; opacity: 0.85; border-left: 2px solid var(--accent); padding-left: 8px; margin-top: 4px; font-style: italic;">"${escapeHtml(sub.custom_message)}"</div>` : `<div style="font-size: 0.8em; opacity: 0.5; font-style: italic;">Message embed standard auto</div>`}
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
        toast("L'intervalle de polling doit être d'au moins 60 secondes.", 'error');
        return;
    }
    
    try {
        const res = await fetch(`${API_BASE}/twitch/${botId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled, poll_interval_seconds: interval })
        });
        
        if (res.ok) {
            toastAction("Enregistré — sera appliqué au redémarrage du bot.",
                        "Redémarrer maintenant", () => botAction(botId, 'restart'));
            await loadTwitchConfig();
        } else {
            const data = await res.json();
            toast(`Erreur: ${data.detail || "Impossible de sauvegarder la configuration"}`, 'error');
        }
    } catch (e) {
        toast(`Erreur réseau: ${e}`, 'error');
    }
}

window.addTwitchSubscription = async function() {
    const botId = document.getElementById('config-bot-select').value;
    const twitchLogin = document.getElementById('twitch-add-login').value.trim();
    const channelId = document.getElementById('twitch-add-channel').value.trim();
    const customMessage = document.getElementById('twitch-add-message').value.trim() || null;
    
    if (!twitchLogin || !channelId) {
        toast("La chaîne Twitch et l'ID du salon Discord sont requis.", 'error');
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
            toast("Abonnement Twitch ajouté avec succès !", 'success');
            await loadTwitchConfig();
        } else {
            const data = await res.json();
            toast(`Erreur: ${data.detail || "Impossible d'ajouter l'abonnement"}`, 'error');
        }
    } catch (e) {
        toast(`Erreur réseau: ${e}`, 'error');
    }
}

window.setTwitchEnabledAll = async function(enabled) {
    if (!await confirmDialog(enabled ? "Activer la surveillance Twitch pour TOUS les bots ?"
                                     : "Désactiver la surveillance Twitch pour TOUS les bots ?")) return;
    try {
        const res = await fetch(`${API_BASE}/twitch/all`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled })
        });
        if (res.ok) {
            toast(enabled ? "Surveillance activée pour tous les bots."
                          : "Surveillance désactivée pour tous les bots.", 'success');
            await loadTwitchConfig();
        } else {
            const d = await res.json(); toast(`Erreur: ${d.detail || ''}`, 'error');
        }
    } catch (e) { toast(`Erreur réseau: ${e}`, 'error'); }
}

window.addTwitchSubscriptionAll = async function() {
    const login = document.getElementById('twitch-all-login').value.trim();
    const channel = document.getElementById('twitch-all-channel').value.trim();
    const msg = document.getElementById('twitch-all-message').value.trim() || null;
    if (!login || !channel) { toast("La chaîne Twitch et le salon Discord sont requis.", 'error'); return; }
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
            toast(`Ajouté à ${d.added.length} bot(s, 'success').` + (d.skipped.length ? ` Déjà présent sur ${d.skipped.length}.` : ''));
            await loadTwitchConfig();
        } else {
            toast(`Erreur: ${d.detail || "Impossible d'ajouter l'abonnement"}`, 'error');
        }
    } catch (e) { toast(`Erreur réseau: ${e}`, 'error'); }
}

window.deleteTwitchSubscription = async function(index) {
    const botId = document.getElementById('config-bot-select').value;
    if (!await confirmDialog("Voulez-vous vraiment supprimer cet abonnement ?")) return;
    
    try {
        const res = await fetch(`${API_BASE}/twitch/${botId}/subscriptions/${index}`, {
            method: 'DELETE'
        });
        
        if (res.ok) {
            await loadTwitchConfig();
        } else {
            const data = await res.json();
            toast(`Erreur: ${data.detail || "Impossible de supprimer l'abonnement"}`, 'error');
        }
    } catch (e) {
        toast(`Erreur réseau: ${e}`, 'error');
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
        document.getElementById('presence-chat-game-qa').checked = chatCfg.game_qa === true;
        document.getElementById('presence-chat-eventsub').checked = chatCfg.eventsub === true;

        // Charger les chaînes de chat
        const channelsRes = await fetch(`${API_BASE}/twitch/channels/${botId}`);
        if (channelsRes.ok) {
            const channelsData = await channelsRes.json();
            document.getElementById('presence-chat-channels').value = (channelsData.chat_channels || []).join(', ');
        } else {
            document.getElementById('presence-chat-channels').value = '';
        }

        // Charger les co-hosts
        const cohostRes = await fetch(`${API_BASE}/twitch/cohost/${botId}`);
        if (cohostRes.ok) {
            const cohostData = await cohostRes.json();
            document.getElementById('presence-cohost-channels').value = (cohostData.cohost_channels || []).join(', ');
        } else {
            document.getElementById('presence-cohost-channels').value = '';
        }

        // Charger les link commands
        const linksRes = await fetch(`${API_BASE}/twitch/links/${botId}`);
        if (linksRes.ok) {
            const linksData = await linksRes.json();
            renderLinksTable(linksData.link_commands || []);
        } else {
            renderLinksTable([]);
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
    const game_qa = document.getElementById('presence-chat-game-qa').checked;
    const eventsub = document.getElementById('presence-chat-eventsub').checked;

    try {
        const res = await fetch(`${API_BASE}/twitch/chat/${botId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ events, interjections, greetings, viewer_memory, game_qa, eventsub })
        });
        if (res.ok) {
            toastAction("Enregistré — sera appliqué au redémarrage du bot.",
                        "Redémarrer maintenant", () => botAction(botId, 'restart'));
            await loadTwitchPresence();
        } else {
            const data = await res.json();
            toast(`Erreur: ${data.detail || "Sauvegarde impossible"}`, 'error');
        }
    } catch (e) {
        toast(`Erreur réseau: ${e}`, 'error');
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
            toastAction("Enregistré — sera appliqué au redémarrage du bot.",
                        "Redémarrer maintenant", () => botAction(botId, 'restart'));
            document.getElementById('presence-chat-channels').value = (data.chat_channels || []).join(', ');
        } else {
            const data = await res.json();
            toast(`Erreur: ${data.detail || "Sauvegarde impossible"}`, 'error');
        }
    } catch (e) {
        toast(`Erreur réseau: ${e}`, 'error');
    }
}

window.saveCohostChannels = async function() {
    const botId = document.getElementById('config-bot-select').value;
    const rawChannels = document.getElementById('presence-cohost-channels').value;
    const channels = rawChannels.split(/[,\n]/).map(c => c.trim()).filter(c => c.length > 0);
    
    try {
        const res = await fetch(`${API_BASE}/twitch/cohost/${botId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cohost_channels: channels })
        });
        if (res.ok) {
            const data = await res.json();
            toastAction("Enregistré — sera appliqué au redémarrage du bot.",
                        "Redémarrer maintenant", () => botAction(botId, 'restart'));
            document.getElementById('presence-cohost-channels').value = (data.cohost_channels || []).join(', ');
        } else {
            const data = await res.json();
            toast(`Erreur: ${data.detail || "Sauvegarde impossible"}`, 'error');
        }
    } catch (e) {
        toast(`Erreur réseau: ${e}`, 'error');
    }
}

window.renderLinksTable = function(links) {
    const tbody = document.getElementById('twitch-links-table-body');
    tbody.innerHTML = '';
    if (!links || links.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; opacity:0.5; padding: 15px;">Aucune commande de lien configurée.</td></tr>`;
        return;
    }
    links.forEach(link => {
        addLinkRow(link.cmd, link.url, link.label, link.message, link.aliases);
    });
}

window.addLinkRow = function(cmd = '', url = '', label = '', message = '', aliases = []) {
    const tbody = document.getElementById('twitch-links-table-body');
    if (tbody.children.length === 1 && tbody.children[0].cells.length === 1) {
        tbody.innerHTML = '';
    }
    
    const tr = document.createElement('tr');
    tr.style.borderBottom = '1px solid var(--border-glass)';
    
    const aliasesStr = Array.isArray(aliases) ? aliases.join(', ') : aliases;
    
    tr.innerHTML = `
        <td style="padding: 8px;"><input type="text" class="link-cmd-input form-input" placeholder="Ex: discord" value="${escapeHtml(cmd)}"></td>
        <td style="padding: 8px;"><input type="text" class="link-url-input form-input" placeholder="Ex: https://..." value="${escapeHtml(url)}"></td>
        <td style="padding: 8px;"><input type="text" class="link-label-input form-input" placeholder="Ex: Discord" value="${escapeHtml(label)}"></td>
        <td style="padding: 8px;"><input type="text" class="link-message-input form-input" placeholder="Ex: Rejoins-nous : {url}" value="${escapeHtml(message)}"></td>
        <td style="padding: 8px;"><input type="text" class="link-aliases-input form-input" placeholder="Ex: serveur, community" value="${escapeHtml(aliasesStr)}"></td>
        <td style="padding: 8px; text-align: center;"><button class="btn btn-danger btn-sm" onclick="this.closest('tr').remove(); if(document.getElementById('twitch-links-table-body').children.length === 0) { renderLinksTable([]); }" style="padding: 5px 10px;"><i class="fa-solid fa-trash"></i></button></td>
    `;
    tbody.appendChild(tr);
}

window.saveLinkCommands = async function() {
    const botId = document.getElementById('config-bot-select').value;
    const tbody = document.getElementById('twitch-links-table-body');
    const rows = tbody.querySelectorAll('tr');
    const links = [];
    
    for (let row of rows) {
        if (row.cells.length === 1) continue;
        
        const cmd = row.querySelector('.link-cmd-input').value.trim();
        const url = row.querySelector('.link-url-input').value.trim();
        const label = row.querySelector('.link-label-input').value.trim();
        const message = row.querySelector('.link-message-input').value.trim();
        const aliasesRaw = row.querySelector('.link-aliases-input').value;
        const aliases = aliasesRaw.split(',').map(a => a.trim()).filter(a => a.length > 0);
        
        if (!cmd || !url) {
            toast("Erreur: Chaque ligne doit avoir au moins une Commande et une URL.", 'error');
            return;
        }
        
        links.push({ cmd, url, label, message, aliases });
    }
    
    try {
        const res = await fetch(`${API_BASE}/twitch/links/${botId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ link_commands: links })
        });
        if (res.ok) {
            const data = await res.json();
            toastAction("Enregistré — sera appliqué au redémarrage du bot.",
                        "Redémarrer maintenant", () => botAction(botId, 'restart'));
            renderLinksTable(data.link_commands);
        } else {
            const data = await res.json();
            toast(`Erreur: ${data.detail || "Sauvegarde impossible"}`, 'error');
        }
    } catch (e) {
        toast(`Erreur réseau: ${e}`, 'error');
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
                <td style="color:#a78bfa; font-weight:600;"><i class="fa-solid fa-gift"></i> ${escapeHtml(title)}</td>
                <td><code style="background:rgba(255,255,255,0.1); padding:2px 6px; border-radius:4px; font-family:monospace;">!${escapeHtml(action)}</code></td>
                <td>
                    <button class="btn btn-danger" onclick="deleteRewardMapping('${encodeURIComponent(title)}')" style="padding:4px 8px; font-size:0.85em;">
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
        toast("Le titre de la récompense et l'action/commande sont requis.", 'error');
        return;
    }
    
    currentRewardMap[title] = action;
    document.getElementById('add-reward-title').value = '';
    document.getElementById('add-reward-action').value = '';
    renderRewardsTable();
}

window.deleteRewardMapping = function(encodedTitle) {
    const title = decodeURIComponent(encodedTitle);
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
            toastAction("Enregistré — sera appliqué au redémarrage du bot.",
                        "Redémarrer maintenant", () => botAction(botId, 'restart'));
            await loadTwitchEvents();
        } else {
            const data = await res.json();
            toast(`Erreur: ${data.detail || "Sauvegarde impossible"}`, 'error');
        }
    } catch (e) {
        toast(`Erreur réseau: ${e}`, 'error');
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
                        <td style="color:#fff; font-weight:600;"><i class="fa-solid fa-user-ninja"></i> ${escapeHtml(entry.name)}</td>
                        <td style="color:#60a5fa; font-weight:700;">${escapeHtml(String(entry.points))} pts</td>
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
            toastAction("Enregistré — sera appliqué au redémarrage du bot.",
                        "Redémarrer maintenant", () => botAction(botId, 'restart'));
            await loadTwitchListen();
        } else {
            const data = await res.json();
            toast(`Erreur: ${data.detail || "Sauvegarde impossible"}`, 'error');
        }
    } catch (e) {
        toast(`Erreur réseau: ${e}`, 'error');
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MODE TEST — « les bots ne publient que sur le serveur privé »
//
// Les bots relisent data/bot_features.json toutes les 5 s : basculer ici prend
// effet sans redémarrage.
// ═══════════════════════════════════════════════════════════════════════════

window.loadTestMode = async function () {
    const banniere = document.getElementById('testmode-banner');
    if (!banniere) return;
    try {
        const res = await fetch(`${API_BASE}/testmode`);
        if (!res.ok) return;
        const data = await res.json();
        banniere.style.display = 'block';

        const actifGlobal = !!(data.global && data.global.test_mode);
        document.getElementById('testmode-global').checked = actifGlobal;

        // Menu déroulant alimenté par ce que les bots ont réellement remonté.
        const select = document.getElementById('testmode-guild');
        const choisi = data.global && data.global.test_guild_id ? String(data.global.test_guild_id) : '';
        select.innerHTML = '<option value="">— aucun —</option>';
        (data.guilds || []).forEach(g => {
            const opt = document.createElement('option');
            opt.value = g.id;
            opt.textContent = `${g.name} (${g.bots.length} bot${g.bots.length > 1 ? 's' : ''})`;
            if (g.id === choisi) opt.selected = true;
            select.appendChild(opt);
        });
        // Un serveur configuré mais qu'aucun bot n'a remonté doit rester visible,
        // sinon l'enregistrer le remettrait silencieusement à « aucun ».
        if (choisi && !(data.guilds || []).some(g => g.id === choisi)) {
            const opt = document.createElement('option');
            opt.value = choisi;
            opt.textContent = `${choisi} (aucun bot connecté)`;
            opt.selected = true;
            select.appendChild(opt);
        }

        const parBot = Object.entries(data.bots || {}).filter(([, v]) => v).map(([b]) => b);
        const etat = document.getElementById('testmode-state');
        if (actifGlobal) {
            etat.textContent = '🧪 Les 6 bots sont muselés.';
        } else if (parBot.length) {
            etat.textContent = `🧪 Muselés individuellement : ${parBot.join(', ')}.`;
        } else {
            etat.textContent = '🟢 Publication normale.';
        }

        const avert = document.getElementById('testmode-warning');
        if (data.avertissement) {
            avert.textContent = '⚠️ ' + data.avertissement;
            avert.style.display = 'block';
        } else {
            avert.style.display = 'none';
        }

        const aide = document.getElementById('testmode-hint');
        aide.textContent = (data.bots_vus && data.bots_vus.length)
            ? `Serveurs remontés par : ${data.bots_vus.join(', ')}. Le réglage par bot est dans Discord → Fonctionnalités.`
            : "Aucun bot n'a encore remonté ses serveurs — démarre les bots, puis actualise.";
    } catch (e) {
        console.error('Mode test : chargement impossible', e);
    }
};

async function envoyerTestMode(corps, message) {
    try {
        const res = await fetch(`${API_BASE}/testmode`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(corps)
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            toast(`Erreur: ${err.detail || res.status}`, 'error');
        } else if (message) {
            toast(message, 'success');
        }
    } catch (e) {
        toast(`Erreur réseau: ${e}`, 'error');
    }
    await window.loadTestMode();
}

window.setTestModeGlobal = async function (actif) {
    // Activer sans serveur choisi = silence total. On le dit AVANT, pas après.
    if (actif) {
        const select = document.getElementById('testmode-guild');
        if (!select.value) {
            const ok = await confirmDialog(
                "Aucun serveur privé n'est sélectionné : les 6 bots ne publieront NULLE PART " +
                "(ni Discord, ni Twitch, ni messages privés). Activer quand même ?"
            );
            if (!ok) {
                document.getElementById('testmode-global').checked = false;
                return;
            }
        }
    }
    await envoyerTestMode(
        { test_mode: actif },
        actif ? 'Mode test activé' : 'Mode test désactivé — publication normale'
    );
};

window.setTestGuild = async function (guildId) {
    await envoyerTestMode(
        { test_guild_id: guildId || null },
        guildId ? 'Serveur privé enregistré' : 'Serveur privé retiré'
    );
};

document.addEventListener('DOMContentLoaded', () => window.loadTestMode());

// ═══════════════════════════════════════════════════════════════════════════
// REDEMARRAGE DU DASHBOARD LUI-MEME
//
// Contrairement aux bots, l'interface qui envoie l'ordre est celle qui meurt :
// la requête n'aura pas de « fin » normale et le serveur sera injoignable un
// instant. On attend donc son retour avant de recharger, plutôt que d'afficher
// une erreur réseau qui ferait croire à un échec.
// ═══════════════════════════════════════════════════════════════════════════

window.restartDashboard = async function () {
    const ok = await confirmDialog(
        "Redémarrer le dashboard ? L'interface sera injoignable quelques secondes. " +
        "Les 6 bots continuent de tourner, ils ne sont pas touchés."
    );
    if (!ok) return;

    const bouton = document.getElementById('btn-restart-dashboard');
    if (bouton) {
        bouton.disabled = true;
        bouton.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Redémarrage...';
    }

    try {
        const res = await fetch(`${API_BASE}/dashboard/restart`, { method: 'POST' });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            toast(`Redémarrage impossible : ${err.detail || res.status}`, 'error');
            if (bouton) {
                bouton.disabled = false;
                bouton.innerHTML = '<i class="fa-solid fa-gauge-high"></i> Redémarrer le Dashboard';
            }
            return;
        }
    } catch (e) {
        // Le serveur peut mourir avant de finir de répondre : ce n'est pas un échec.
        console.warn('Réponse interrompue (attendu) :', e);
    }

    toast("Redémarrage du dashboard en cours...", 'info');
    await attendreRetourDashboard();
};

async function attendreRetourDashboard() {
    const DEBUT_ATTENTE = 1500;   // laisse le temps au processus de mourir
    const INTERVALLE = 700;
    const LIMITE = 45000;

    await new Promise(r => setTimeout(r, DEBUT_ATTENTE));
    const echeance = Date.now() + LIMITE;

    while (Date.now() < echeance) {
        try {
            const res = await fetch(`${API_BASE}/health`, { cache: 'no-store' });
            if (res.ok) {
                toast("Dashboard redémarré.", 'success');
                setTimeout(() => window.location.reload(), 600);
                return;
            }
        } catch (e) {
            // normal tant qu'il n'est pas revenu
        }
        await new Promise(r => setTimeout(r, INTERVALLE));
    }

    // Ne pas recharger : une page blanche serait plus déroutante que ce message.
    toast("Le dashboard n'est pas revenu. Relance start_dashboard.bat à la main.", 'error');
    const bouton = document.getElementById('btn-restart-dashboard');
    if (bouton) {
        bouton.disabled = false;
        bouton.innerHTML = '<i class="fa-solid fa-gauge-high"></i> Redémarrer le Dashboard';
    }
}
