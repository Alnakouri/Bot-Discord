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
        });
    });
}

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
                        ? `<button class="btn btn-outline" onclick="botAction('${bot.id}', 'restart')"><i class="fa-solid fa-rotate-right"></i></button>
                           <button class="btn btn-danger" onclick="botAction('${bot.id}', 'stop')"><i class="fa-solid fa-stop"></i></button>`
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
    const bots = ["sheogorath", "maiq", "alfred", "zaji", "johnny", "malena"];
    let successCount = 0;
    
    // UI update to prevent spamming
    const btnId = action === 'start' ? 'btn-start-all-bots' : 'btn-stop-all-bots';
    const btn = document.getElementById(btnId);
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
    "sheogorath": { color: "#d946ef" },
    "maiq": { color: "#f97316" },
    "alfred": { color: "#475569" },
    "johnny": { color: "#22c55e" },
    "zaji": { color: "#0ea5e9" },
    "malena": { color: "#f43f5e" }
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
                    <td><span class="tpm-val">${k.tpm_current}</span> / 1M</td>
                    <td>${k.rpm_current} / 4K</td>
                    <td>${k.quota_remaining.toLocaleString()} tokens</td>
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
