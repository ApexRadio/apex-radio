# Traductions d'Apex Radio / Translating Apex Radio

🇫🇷 Le français et l'anglais sont écrits dans le code. Chaque autre langue a ici son fichier
`<code>.json` (ex. `de.json` pour l'allemand). Un texte pas encore traduit s'affiche et se dit en anglais.

1. Créer ou mettre à jour le fichier de la langue :
   `python tools/textes.py de --nom Deutsch --virgule` (`--virgule` si la langue écrit 3,6 et pas 3.6)
2. Remplir `"texte"` pour chaque phrase (s'aider de `"fr"` et de `"en"`).
   Les `{0}`, `{1}`… sont des valeurs remplies par l'appli (nombres, noms, morceaux de phrase) :
   les garder, à la place qui sonne juste dans la langue. Pluriel : `{3?Runden:Runde}` donne « Runden » si la
   valeur 3 n'est pas vide (en français, c'est le « s » du pluriel), sinon « Runde ».
3. Remplir `"tournures"` dans la partie `"questions"` : pour chaque question qu'Apex comprend (`"fr"`, aide en `"en"`),
   écrire comment un pilote la pose dans ta langue. Des mots simples, en minuscules, dans l'ordre (d'autres mots
   peuvent s'intercaler) ; `|` sépare plusieurs façons de dire ; `*` = n'importe quel mot ; `{n}` = un nombre.
   Exemple en allemand : `"tournures": ["wie viel sprit|wie viel benzin|tank"]`, `["wo ist p{n}"]`.
   Apex reconnaît la tournure et répond comme à la question française (plusieurs questions d'un coup marchent aussi).
4. Voir l'avancement : `python tools/textes.py --stats`

Le fichier couvre ce que dit l'ingénieur ET ce qu'affichent le tableau de bord et la vue téléphone.
Pour qu'une langue soit vraiment prête pour les joueurs, il faut aussi : une voix Piper dans cette langue
(licence sans restriction commerciale ; en attendant, l'ingénieur parle anglais), et les tournures des
questions vocales (ci-dessus).

🇬🇧 French and English live in the code. Every other language has its own `<code>.json` file here
(e.g. `de.json` for German). Anything not translated yet is shown and spoken in English.

1. Create or update the language file:
   `python tools/textes.py de --nom Deutsch --virgule` (`--virgule` if the language writes 3,6 rather than 3.6)
2. Fill in `"texte"` for each line (use `"fr"` and `"en"` as a guide).
   `{0}`, `{1}`… are values filled in by the app (numbers, names, sentence parts): keep them,
   wherever they sound right in your language. Plurals: `{3?Runden:Runde}` gives "Runden" when value 3 is not
   empty (in French it's the plural "s"), otherwise "Runde".
3. Fill in `"tournures"` in the `"questions"` part: for each question Apex understands (`"fr"`, help in `"en"`),
   write how a driver asks it in your language. Plain lowercase words, in order (other words may sit in between);
   `|` separates alternative wordings; `*` = any word; `{n}` = a number.
   German example: `"tournures": ["wie viel sprit|wie viel benzin|tank"]`, `["wo ist p{n}"]`.
   Apex recognises the wording and answers as for the French question (several questions at once work too).
4. Check progress: `python tools/textes.py --stats`

The file covers what the engineer says AND what the dashboard and phone view show.
For a language to be really ready for players it also needs a Piper voice in that language (licence with no
commercial restriction; until then the engineer speaks English) and the voice-question wordings (above).
