# Bot des vidéos de présentation (launchpads, projets memecoin)

Dans Telegram, on lui donne le **nom** d'un launchpad ou d'un projet, une **phrase d'accroche** (le thème), jusqu'à
**3 points clés**, le **logo** (photo de profil), une **couleur**, un **style** et un **format** ; il renvoie en
30 secondes environ une **courte vidéo de présentation** (10 à 23 s), avec une musique faite pour elle.

Il ne trade rien, ne lit aucune blockchain, ne détient aucune clé. Il n'invente rien : la vidéo ne montre que ce
qu'on lui a écrit. Il est rangé hors du dépôt Git de Pump Radar, comme `pnl-card-bot`.

Les styles viennent d'une recherche sur X (19 octobre 2026) : voir `RECHERCHE-X.md`.

## Démarrer

1. **Créer son bot Telegram** : dans Telegram, écrire à **@BotFather**, envoyer `/newbot`, choisir un nom et un
   identifiant (qui finit par `bot`). BotFather donne un **token**.
2. Ouvrir le fichier **`.env`** de ce dossier et coller le token après `TELEGRAM_BOT_TOKEN=`.
   Ce fichier ne se partage jamais. Il faut **un bot à lui** : ne pas mettre le token d'un autre bot.
3. Double-clic sur **`start.bat`**. La fenêtre affiche le journal ; `Ctrl+C` l'arrête.
4. Dans Telegram, ouvrir le bot et envoyer `/start`.

- Le propriétaire (`TELEGRAM_OWNER_ID` dans `.env` ; vide : celui de `pnl-card-bot/.env` ou de
  `calls-trader-bot/.env`) reçoit le message de démarrage, a `/stats`, et n'est pas limité en vidéos.
- **Par défaut, seul le propriétaire peut s'en servir** (`[access] public = false` dans `config.toml`). Pour l'ouvrir
  à tout le monde : `public = true`, puis relancer.
- `start.bat --check` vérifie tout sans rien envoyer. `start.bat --demo` fabrique une vidéo d'exemple de chaque style
  dans `data\videos` (`start.bat --demo --format portrait` : en 9:16), sans Telegram.
- Le bot ne marche que pendant que la fenêtre est ouverte sur ce PC.

## S'en servir (dans Telegram)

`/new`, puis répondre aux 10 questions (les facultatives ont un bouton **Skip**) :

| # | Question | Exemple | |
|---|---|---|---|
| 1 | Nom | `Froggy Pad` | obligatoire, 28 caractères |
| 2 | Ticker | `$FROG` ou `frog` | facultatif |
| 3 | Accroche (le thème) | `Launch a coin for *anyone* on Solana` | obligatoire, 90 caractères. Un mot **entre étoiles** (ou mis en gras dans Telegram) est mis en avant |
| 4 | Points clés | un par ligne, 3 au plus | facultatif, 48 caractères chacun |
| 5 | Logo | une photo ou un fichier image | facultatif ; sans logo : la première lettre du nom dans un rond |
| 6 | Couleur | un bouton, ou un code `#5CC46E` | « From the logo » prend la couleur dominante du logo |
| 7 | Style | ⚫ Product, 💥 Kinetic, 🎞 Luxe, 🪙 Coins | |
| 8 | Statut | Live now / Coming soon / Neither | |
| 9 | Lien montré à la fin | `froggypad.fun`, `@froggypad`, un CA | facultatif, 44 caractères |
| 10 | Format | 16:9 (X), 1:1, 9:16 (TikTok) | |

Ensuite le bot montre un **résumé** : **Make the video**, **Edit** (changer une réponse), son on/off, **Cancel**.
Sous chaque vidéo : **Other style** et **Other format** la refont tout de suite avec ce seul changement.

**Son.** Par défaut, une musique fabriquée par le bot pour le style (aucun morceau téléchargé, donc pas de droits
d'auteur). On peut envoyer **son propre son** : un fichier audio ou une vidéo, avec en légende l'endroit où il
commence (`1:20`). Attention : un morceau connu peut être protégé par le droit d'auteur, c'est à celui qui l'envoie
de vérifier. « No sound » donne une vidéo muette (pour ajouter un son tendance dans TikTok).

Le projet de chacun est gardé (un redémarrage du bot ne fait rien perdre). `/cancel` l'oublie.

## Les quatre styles

| Style | Inspiré de (sur X) | Ce qu'on voit | Durée |
|---|---|---|---|
| ⚫ **Product** | Creator.fun, Make, Borly, Arena | fond noir et grille de points ; le logo s'allume avec une lueur de la couleur, un cercle se trace, le nom s'écrit avec un curseur ; l'accroche mot à mot ; les points clés « 01 / 02 / 03 » avec un trait qui avance ; le ticker en grand avec LIVE NOW / COMING SOON ; carte de fin (logo, nom, accroche, lien) | 15-19 s |
| 💥 **Kinetic** | Shielded Shell | mots géants qui changent à chaque temps (128 BPM), en alternant noir / aplat de couleur / mot en couleur ; le logo en points qui se rassemblent ; grands numéros au trait ; fin avec le lien tapé dans une fenêtre de terminal | 12-16 s |
| 🎞 **Luxe** | ZAT | teaser lent : le logo frappé dans un métal de la couleur, un reflet le traverse, des poussières ; cartons de texte blanc à empattements ; le nom en capitales espacées devant des lumières floues ; bandes noires du cinéma, grain de film | 17-23 s |
| 🪙 **Coins** | Smart Pocket | fond clair ; des pièces frappées du logo tombent en tournant ; une grande pièce monte et s'arrête de face ; nom, ticker, points en étiquettes ; fin : les pièces jaillissent, COMING SOON en grand | 10-13 s |

Fabrication mesurée le 19 octobre 2026 sur ce PC, en 16:9 : Product 33 s, Kinetic 14 s, Luxe 35 s, Coins 10 s.
Fichiers de 2 à 16 Mo.

## Ce qui n'a PAS été vérifié

- **Aucun essai avec un vrai Telegram** : il n'y a pas encore de token. Les 37 tests utilisent un faux Telegram.
- La musique n'a pas été **écoutée** (je ne peux pas entendre) : seulement mesurée.
- Les vidéos ont été regardées image par image, pas en mouvement à vitesse réelle.
- Un logo très clair sur fond blanc, ou très sombre, peut mal ressortir dans certains styles (le métal du style Luxe
  surtout) : à regarder avec de vrais logos.
- Les emojis tapés sont retirés des textes (les polices de la vidéo ne savent pas les dessiner).

## Fichiers

```
run.py                   point d'entrée (--check, --demo)
launchbot/bot.py         la conversation : questions, résumé, boutons, file d'attente, limites
launchbot/project.py     les champs d'un projet, le nettoyage de ce qui est tapé, les couleurs
launchbot/messages.py    les textes Telegram (anglais) et leurs boutons
launchbot/maker.py       lance la fabrication dans un programme à part, une vidéo à la fois
launchbot/video/         le dessin : base.py (commun), product.py, kinetic.py, luxe.py, coins.py,
                         music.py (la musique), render.py (enchaîne les images, ffmpeg)
launchbot/telegram.py, config.py, state.py, log.py
samples/                 le projet d'exemple (demo.json) et son faux logo
tests/                   unittest, faux Telegram : venv\Scripts\python.exe -m unittest discover -s tests -t .
data/                    (créé au lancement) state.json, logos, sons, vidéos, journal
```
