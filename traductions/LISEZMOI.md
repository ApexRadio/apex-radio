# Traductions d'Apex Radio / Translating Apex Radio

🇫🇷 Le français et l'anglais sont écrits dans le code. Chaque autre langue a ici son fichier
`<code>.json` (ex. `de.json` pour l'allemand). Un texte pas encore traduit s'affiche et se dit en anglais.

1. Créer ou mettre à jour le fichier de la langue :
   `python tools/textes.py de --nom Deutsch --virgule` (`--virgule` si la langue écrit 3,6 et pas 3.6)
2. Remplir `"texte"` pour chaque phrase (s'aider de `"fr"` et de `"en"`).
   Les `{0}`, `{1}`… sont des valeurs remplies par l'appli (nombres, noms, morceaux de phrase) :
   les garder, à la place qui sonne juste dans la langue.
3. Voir l'avancement : `python tools/textes.py --stats`

Le fichier couvre ce que dit l'ingénieur ET ce qu'affichent le tableau de bord et la vue téléphone.
Pour qu'une langue soit vraiment prête pour les joueurs, il faut aussi : une voix Piper dans cette langue
(licence sans restriction commerciale ; en attendant, l'ingénieur parle anglais), et les tournures des
questions vocales dans `questions.py`.

🇬🇧 French and English live in the code. Every other language has its own `<code>.json` file here
(e.g. `de.json` for German). Anything not translated yet is shown and spoken in English.

1. Create or update the language file:
   `python tools/textes.py de --nom Deutsch --virgule` (`--virgule` if the language writes 3,6 rather than 3.6)
2. Fill in `"texte"` for each line (use `"fr"` and `"en"` as a guide).
   `{0}`, `{1}`… are values filled in by the app (numbers, names, sentence parts): keep them,
   wherever they sound right in your language.
3. Check progress: `python tools/textes.py --stats`

The file covers what the engineer says AND what the dashboard and phone view show.
For a language to be really ready for players it also needs a Piper voice in that language (licence with no
commercial restriction; until then the engineer speaks English) and the voice-question phrasings in `questions.py`.
