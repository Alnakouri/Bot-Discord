# PLAN — Décret v2 : la D.A. « manuscrit enluminé »

> **Destinataire : Antigravity.** Plan d'exécution.
> **Base de référence : commit `4af9c1a`** + les correctifs non commités du décret
> (`_ajuster_corps`, `_HALO_CREME`, `tests/test_decret_rendu.py` refait) et du chantier
> mistral. **Ne pas refaire ces correctifs**, ils sont dans l'arbre et testés.
> **Une maquette existe** : `proto_v2_medieval.png` (scratchpad). Elle prouve que la
> structure tient avec les assets actuels, et elle montre les pièges. Le code du
> prototype est dans `proto_decret_v2.py` — à reprendre, pas à réinventer.

---

## 1. Ce qui est demandé

Référence fournie par l'utilisateur le 2026-08-30. Sept éléments, du haut vers le bas :

1. **sur-titre** en petites capitales espacées, discret, au-dessus du titre ;
2. **titre sur 2 lignes**, violet profond, lettrage gothique, ombre douce ;
3. **filet fin coupé par un losange violet** ;
4. **lettrine** violette en tête du corps, sur la hauteur de 2 lignes ;
5. **corps justifié** — pas centré comme aujourd'hui — interligne généreux ;
6. la **mention `@Pseudo`** mise en valeur (violet, soulignée) ;
7. des **runes** en ornement de marge.

---

## 2. Ce qui marche déjà, prouvé par la maquette

Les points **1, 2, 3, 4, 5, 6** sont rendus avec les **assets déjà dans le dépôt**.
Reprendre les helpers du prototype :

- `petites_capitales(draw, img, texte, font, y, couleur, ecart)` — PIL n'a pas
  d'interlettrage : on pose les caractères **un par un**.
- `justifie(draw, ligne, font, largeur, derniere)` — même raison, `draw.text` ne sait pas
  étirer les blancs, il faut placer chaque mot. ⚠️ **La dernière ligne d'un paragraphe
  reste au fer à gauche**, sinon elle s'étale en peigne sur toute la largeur.
- La lettrine impose un **retrait sur les 2 premières lignes seulement** : le calcul de
  césure doit donc se faire ligne par ligne avec une largeur variable, pas en un seul
  `_wrap_by_width` sur tout le paragraphe.

---

## 3. Les quatre défauts de la maquette — à corriger, pas à reproduire

**3.1 — Les runes sortent en carrés « tofu ». AUCUNE police ne les a.**
Vérifié dans la `cmap` de six polices (DejaVu, MedievalSharp, Arial, Times, Segoe UI,
Segoe UI Symbol) : **0/4 runes présentes**, partout.

⚠️ Piège de mesure : `ImageFont.getmask("ᚠ").size` rend une boîte **non vide** —
c'est celle du glyphe `.notdef`, le carré vide. Un premier test s'y est laissé prendre
et a conclu « couverture OK ». **Pour savoir si un caractère existe, lire la `cmap`
(`fontTools.ttLib.TTFont(...).getBestCmap()`), jamais la taille du masque.**

→ **Décision : ne pas dessiner de runes.** `parchment.png` en **porte déjà** dans sa
bordure violette. En rajouter serait redondant, et éviterait d'embarquer une police de
plus. L'élément 7 est donc obtenu par le fond, pas par le code.

**3.2 — Le sur-titre se pose dans la brume violette** et devient illisible. Le titre est
à `y=92`, or la brume descend jusqu'à ~130 px. Le descendre sous `y=150`, et le faire
passer par le même halo crème que le reste (dans la maquette il est dessiné avant le
halo, donc il n'en bénéficie pas).

**3.3 — Le corps justifié touche la brume des bords.** `MARGE = 150` suffit pour du texte
centré (qui n'atteint jamais la largeur pleine) mais **pas pour du justifié**, qui va
au bord par définition. Passer à **`MARGE = 185`**.

**3.4 — Le losange n'est pas un losange.** `draw.regular_polygon(..., 4, rotation=0)`
donne un petit carré. Il faut `rotation=45`, et un rayon d'au moins 12 px.

**3.5 — La maquette déborde en bas** (« soupe. » à ras du cadre) : elle ne rappelle pas
`_ajuster_corps`. Le code final **doit** passer par lui — c'est le correctif du jour, et
le test `test_le_corps_tient_toujours_dans_la_zone_disponible` le verrouille. La zone
disponible est plus petite qu'avant (sur-titre + filet + 2 paragraphes) : vérifier que
`_CORPS_MAX = 44` reste atteignable, sinon le baisser à 38.

---

## 4. La seule décision qui reste : la police du titre

La référence utilise un vrai **blackletter** (type UnifrakturCook / Pirata One).
`MedievalSharp` est médiévalisant mais **n'est pas un blackletter** — c'est la seule
différence visible entre la maquette et la référence.

Aucune police gothique n'existe sur la machine (`msgothic.ttc` est du gothique japonais,
sans rapport). Il faudrait donc **ajouter un fichier de police au dépôt**, comme
`MedievalSharp.ttf` l'a été — licence OFL, et à mentionner dans
`Sheogorath/assets/OFL.txt`.

> **⚠️ À faire trancher par l'utilisateur avant d'écrire la moindre ligne.** Télécharger
> un binaire dans son dépôt n'est pas une décision d'agent. Deux options :
>
> - **(A)** ajouter une police blackletter OFL → rendu fidèle à la référence ;
> - **(B)** garder `MedievalSharp` → aucun asset, rendu de la maquette ci-jointe.
>
> Tout le reste du plan est identique dans les deux cas : seul le fichier chargé pour le
> titre et la lettrine change.

Le **fond** diffère aussi de la référence (planches claires + cadre lilas contre
parchemin + brume violette). Ce n'est pas générable en code : si l'utilisateur veut ce
fond-là, il doit fournir l'image. Sinon on garde `parchment.png`, qui a l'avantage de
déjà porter les runes (cf. 3.1).

---

## 5. Tests à ajouter dans `tests/test_decret_rendu.py`

**Chacun validé par mutation** : casser la ligne visée, vérifier que le test rougit,
remettre. Un test qui passe avant ET après le changement ne verrouille rien — c'est
déjà arrivé deux fois sur ce fichier.

1. `test_la_derniere_ligne_d_un_paragraphe_n_est_pas_justifiee` — appeler `justifie(...)`
   avec `derniere=True` et vérifier que les mots sont espacés d'un blanc simple, pas
   étirés jusqu'au bord (piège 2 de la section 2).
2. `test_une_ligne_justifiee_atteint_la_largeur_demandee` — l'inverse, `derniere=False`.
3. `test_la_lettrine_ne_mord_que_sur_les_deux_premieres_lignes` — la 3ᵉ ligne doit partir
   de la marge, pas du retrait.
4. `test_le_texte_ne_touche_jamais_la_brume_des_bords` — aucun pixel d'encre à moins de
   `MARGE` du bord (mesurable : recadrer les bandes latérales et vérifier qu'aucun pixel
   n'est aussi sombre que `_ENCRE_SEPIA`).
5. `test_aucun_caractere_ne_sort_en_tofu` — **le garde-fou du piège 3.1**. Pour chaque
   caractère du sur-titre, du titre et du corps, vérifier via la `cmap` de la police
   utilisée qu'il existe vraiment. À écrire avec `fontTools` (déjà installé).
   Ce test aurait attrapé les runes du premier coup.
6. `test_la_mention_est_mise_en_valeur` — un `@Pseudo` dans le texte ressort en violet et
   souligné, et le reste de la ligne non.
