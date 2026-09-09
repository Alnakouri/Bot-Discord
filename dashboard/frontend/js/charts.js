// Gestion des graphiques (Chart.js)
// Utilisé globalement via window.refreshCharts appelé depuis app.js

Chart.defaults.color = '#adb5bd';
Chart.defaults.font.family = 'Inter';

// BOT_REGISTRY_JS est declare en tete de app.js (charge apres ce fichier) ;
// il n'est lu ici que depuis des fonctions appelees une fois la page chargee.

let mainActivityChart = null;
let apiUsageChart = null;
let conversationChart = null;

window.refreshCharts = async function() {
    await loadActivityChart();
    await loadApiUsageChart();
    await loadConversationChart();
};

async function loadActivityChart() {
    try {
        const res = await fetch(`/api/conversations/activity?hours=24`);
        const data = await res.json();
        
        const ctx = document.getElementById('mainActivityChart');
        if(!ctx) return;
        
        if(mainActivityChart) mainActivityChart.destroy();
        
        let labels = [];
        let counts = [];
        
        if (data && data.buckets) {
            labels = data.buckets.map(b => {
                const tIndex = b.hour.indexOf('T');
                if (tIndex !== -1) {
                    return b.hour.substring(tIndex + 1, tIndex + 6);
                }
                return b.hour;
            });
            counts = data.buckets.map(b => b.count);
        }
        
        mainActivityChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: "Interactions",
                        data: counts,
                        borderColor: '#6b4cda',
                        backgroundColor: 'rgba(107, 76, 218, 0.2)',
                        tension: 0.4,
                        fill: true
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { 
                    legend: { display: false },
                    title: {
                        display: counts.length === 0 || counts.reduce((a, b) => a + b, 0) === 0,
                        text: "Aucune donnée",
                        position: "bottom"
                    }
                }
            }
        });
    } catch(e) { console.error("Chart err", e); }
}

async function loadApiUsageChart() {
    try {
        const res = await fetch(`/api/api-usage?hours=24`);
        const data = await res.json();
        
        const ctx = document.getElementById('apiUsageChart');
        if(!ctx) return;
        
        if(apiUsageChart) apiUsageChart.destroy();
        
        let labels = [];
        let counts = [];
        
        if (data && data.by_api) {
            labels = Object.keys(data.by_api);
            counts = Object.values(data.by_api).map(val => val.calls);
        }
        
        const defaultColors = ['#3a86ff', '#e74c3c', '#f5a623', '#9b59b6'];
        const colors = labels.map((_, idx) => defaultColors[idx % defaultColors.length]);
        
        apiUsageChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: counts,
                    backgroundColor: colors,
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '70%',
                plugins: {
                    legend: { position: 'right' },
                    title: {
                        display: counts.length === 0 || counts.reduce((a, b) => a + b, 0) === 0,
                        text: "Aucune donnée",
                        position: "bottom"
                    }
                }
            }
        });
    } catch(e) { console.error("Chart err", e); }
}

async function loadConversationChart() {
    try {
        const res = await fetch(`/api/conversations?days=7`);
        const data = await res.json();
        
        const ctx = document.getElementById('conversationChart');
        if(!ctx) return;
        
        if(conversationChart) conversationChart.destroy();
        
        let labels = [];
        let counts = [];
        let colors = [];
        
        const bots = Object.keys(BOT_REGISTRY_JS);
        
        for (const botId of bots) {
            const botMeta = BOT_REGISTRY_JS[botId];
            labels.push(botMeta.display);
            colors.push(botMeta.color);
            
            let count = 0;
            if (data && data.by_bot) {
                const matchingKey = Object.keys(data.by_bot).find(k => 
                    k.toLowerCase() === botId.toLowerCase() || 
                    k.toLowerCase() === botMeta.name.toLowerCase() ||
                    k.toLowerCase() === botMeta.display.toLowerCase()
                );
                if (matchingKey) {
                    count = data.by_bot[matchingKey].messages;
                }
            }
            counts.push(count);
        }
        
        conversationChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Messages handling',
                    data: counts,
                    backgroundColor: colors,
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' } },
                    x: { grid: { display: false } }
                },
                plugins: { 
                    legend: { display: false },
                    title: {
                        display: counts.length === 0 || counts.reduce((a, b) => a + b, 0) === 0,
                        text: "Aucune donnée",
                        position: "bottom"
                    }
                }
            }
        });
    } catch(e) { console.error("Chart err", e); }
}
