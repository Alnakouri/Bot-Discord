// Gestion des graphiques (Chart.js)
// Utilisé globalelement via window.refreshCharts appelé depuis app.js

Chart.defaults.color = '#adb5bd';
Chart.defaults.font.family = 'Inter';

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
        // Mock data fetch - in pure prod this matches API schema
        // const res = await fetch(`${API_BASE}/conversations?days=1`);
        // const data = await res.json();
        
        const ctx = document.getElementById('mainActivityChart');
        if(!ctx) return;
        
        if(mainActivityChart) mainActivityChart.destroy();
        
        mainActivityChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00'],
                datasets: [
                    {
                        label: "Interactions",
                        data: [12, 19, 3, 5, 2, 3],
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
                plugins: { legend: { display: false } }
            }
        });
    } catch(e) { console.error("Chart err", e); }
}

async function loadApiUsageChart() {
    try {
        const ctx = document.getElementById('apiUsageChart');
        if(!ctx) return;
        
        if(apiUsageChart) apiUsageChart.destroy();
        
        apiUsageChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Gemini', 'Groq', 'Mistral', 'OpenRouter'],
                datasets: [{
                    data: [300, 50, 100, 40],
                    backgroundColor: ['#3a86ff', '#e74c3c', '#f5a623', '#9b59b6'],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '70%',
                plugins: {
                    legend: { position: 'right' }
                }
            }
        });
    } catch(e) {}
}

async function loadConversationChart() {
    try {
        const ctx = document.getElementById('conversationChart');
        if(!ctx) return;
        
        if(conversationChart) conversationChart.destroy();
        
        conversationChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: ['Sheogorath', "M'aiq", 'Alfred', 'Johnny', "Za'ji", 'Malena'],
                datasets: [{
                    label: 'Messages handling',
                    data: [150, 80, 45, 20, 10, 5],
                    backgroundColor: [
                        '#9b59b6', '#e67e22', '#2c3e50', '#27ae60', '#2980b9', '#e74c3c'
                    ],
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
                plugins: { legend: { display: false } }
            }
        });
    } catch(e) {}
}
