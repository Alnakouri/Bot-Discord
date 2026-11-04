// Produit site/dashboard/ : le vrai front du dashboard, branché sur le faux backend de
// dashboard/demo.js. Le front est copié tel quel ; seul index.html est retouché.
// Usage : node demo-alfred/generer_dashboard.mjs   (à relancer après toute retouche du front)
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ICI = path.dirname(fileURLToPath(import.meta.url));
const FRONT = path.join(ICI, '..', 'dashboard', 'frontend');
const DONNEES = path.join(ICI, '..', 'data');
const CIBLE = path.join(ICI, 'site', 'dashboard');

const die = (message) => { console.error(`❌ ${message}`); process.exit(1); };
const lire = (p) => fs.readFileSync(p, 'utf8');

fs.rmSync(CIBLE, { recursive: true, force: true });
for (const dossier of ['css', 'js', 'vendor']) {
    fs.cpSync(path.join(FRONT, dossier), path.join(CIBLE, 'static', dossier), { recursive: true });
}
for (const f of ['demo.js', 'demo.css']) fs.copyFileSync(path.join(ICI, 'dashboard', f), path.join(CIBLE, 'static', f));

let page = lire(path.join(FRONT, 'index.html'));
const remplacer = (ancien, nouveau) => {
    const n = typeof ancien === 'string' ? page.split(ancien).length - 1 : (page.match(new RegExp(ancien, 'g')) || []).length;
    if (n !== 1) die(`index.html : passage à remplacer trouvé ${n} fois (${ancien}).`);
    page = page.replace(ancien, nouveau);
};
remplacer('<title>Ecosystem Dashboard | 6 Bots Discord</title>', '<title>Dashboard des bots · démo</title>');
remplacer('<link rel="stylesheet" href="static/css/dashboard.css">',
    '<link rel="stylesheet" href="static/css/dashboard.css">\n    <link rel="stylesheet" href="static/demo.css">');
remplacer('<script src="static/js/charts.js"></script>',
    '<script src="static/demo.js"></script>\n    <script src="static/js/charts.js"></script>');
remplacer(/<button id="btn-logout"[\s\S]*?<\/button>/,
    '<a class="demo-retour" href="../"><i class="fa-solid fa-arrow-left"></i> Parler à Alfred</a>');
remplacer('<main class="content">', `<main class="content">
        <div class="demo-bandeau">
            <span><i class="fa-solid fa-flask"></i> <b>Démo, données fictives.</b> Les boutons agissent sur une copie en mémoire : aucun vrai bot n'est touché.</span>
            <a href="https://github.com/Alnakouri/Bot-Discord/tree/main/dashboard">Voir le code</a>
        </div>`);
fs.writeFileSync(path.join(CIBLE, 'index.html'), page);

// --- Contrôle : rien de réel ne doit partir ---------------------------------------------

const fuites = [];
const publics = ['index.html', 'js/app.js', 'js/charts.js'].map((f) => lire(path.join(FRONT, f)).toLowerCase()).join('\n');
const ecrits = ['index.html', 'static/demo.js', 'static/demo.css'].map((f) => [f, lire(path.join(CIBLE, f))]);
const tous = [];
const parcourir = (d) => fs.readdirSync(d, { withFileTypes: true }).forEach((e) => {
    const p = path.join(d, e.name);
    if (e.isDirectory()) parcourir(p); else if (/\.(js|css|html)$/.test(e.name)) tous.push([path.relative(CIBLE, p), lire(p)]);
});
parcourir(CIBLE);
for (const [f, texte] of tous) {
    for (const [id] of texte.matchAll(/(?<!\d)\d{17,20}(?!\d)/g)) {
        if (!publics.includes(id)) fuites.push(`${f} : identifiant Discord possible (${id})`);
    }
    if (/gsk_|AIza|xox[abp]-|oauth:|sk-[A-Za-z0-9]{16}/.test(texte)) fuites.push(`${f} : motif de clé d'API`);
}

// Tout nom, salon ou serveur des fichiers réels du bot, sauf ce que le front public contient déjà.
const SOURCES = /^(twitch_config|bot_guilds.*|twitch_viewers_.*|.*_cred_twitch|sheo_faveurs.*|identites_locales|.*_memory)\.json$/;
// Mots présents dans les fichiers réels, mais qui viennent ici du code (new Response).
const MOTS_DU_CODE = new Set(['response']);
const candidats = new Set();
const recolter = (v) => {
    if (typeof v === 'string' || typeof v === 'number') {
        const s = String(v).trim().toLowerCase();
        if (s.length >= 5 && !publics.includes(s) && !MOTS_DU_CODE.has(s)) candidats.add(s);
    } else if (v && typeof v === 'object') {
        for (const [k, x] of Object.entries(v)) { recolter(k); recolter(x); }
    }
};
const reels = fs.existsSync(DONNEES) ? fs.readdirSync(DONNEES).filter((f) => SOURCES.test(f)) : [];
for (const f of reels) {
    try { recolter(JSON.parse(lire(path.join(DONNEES, f)))); } catch { /* fichier illisible : ignoré */ }
}
for (const [f, texte] of ecrits) {
    const bas = texte.toLowerCase();
    for (const c of candidats) if (bas.includes(c)) fuites.push(`${f} : valeur réelle « ${c} »`);
}

if (fuites.length) {
    // Rien de déployable ne doit rester après un refus.
    fs.rmSync(CIBLE, { recursive: true, force: true });
    die(`Fuite possible :\n  ${fuites.join('\n  ')}`);
}
console.log(`✅ site/dashboard prêt : ${tous.length} fichiers contrôlés`
    + (reels.length ? `, ${candidats.size} valeurs réelles absentes (${reels.length} fichiers de data/).` : ' (data/ absent : contrôle des valeurs réelles sauté).'));
