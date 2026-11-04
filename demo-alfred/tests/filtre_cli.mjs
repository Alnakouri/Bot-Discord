// Lit un tableau JSON de textes sur stdin, rend le meme tableau passe au filtre JS.
import { readFileSync } from 'node:fs';
import { filtreSortie } from '../src/filtre.js';

const textes = JSON.parse(readFileSync(0, 'utf-8'));
process.stdout.write(JSON.stringify(textes.map((t) => filtreSortie(t))));
