# APEX//RADIO

**A free voice race engineer for sim racing** · *Un ingénieur de course vocal gratuit pour le sim racing*  
Le Mans Ultimate and Assetto Corsa EVO, more sims on the way. · *Le Mans Ultimate et Assetto Corsa EVO, d'autres simulateurs arrivent.*

[![Téléchargements / Downloads](https://img.shields.io/github/downloads/ApexRadio/apex-radio/total?label=t%C3%A9l%C3%A9chargements%20%2F%20downloads&color=00b8d4)](https://github.com/ApexRadio/apex-radio/releases) [![Version](https://img.shields.io/github/v/release/ApexRadio/apex-radio?label=version&color=00b8d4)](https://github.com/ApexRadio/apex-radio/releases/latest)

🇬🇧 [English](#english) · 🇫🇷 [Français](#français)

**⬇️ [Download / Télécharger](https://github.com/ApexRadio/apex-radio/releases/latest)** · 💬 [Discord](https://discord.gg/ZHg4qXd26g) · ❤️ [Patreon](https://www.patreon.com/lolotuner) · ☕ [Ko-fi](https://ko-fi.com/apexradio)

![Apex Radio dashboard](docs/dashboard-en.png)

---

## English

Apex Radio reads Le Mans Ultimate (and Assetto Corsa EVO) in real time and talks to you on the radio, like a real race engineer.
Push a button on your wheel, ask a question, get an answer. Voice and speech recognition run on your PC: no subscription,
no account. Internet is only needed the first time (to download the voice) and to check for updates.

### Supported games

| Game | Status |
|---|---|
| Le Mans Ultimate | ✅ Supported (all features) |
| Assetto Corsa EVO | ✅ Supported (no pit menu or setup workshop yet) |
| iRacing | 🧪 In testing |
| Automobilista 2 | 📋 Planned |

Want another sim? Tell us on [Discord](https://discord.gg/ZHg4qXd26g).

### What it does
- **Strategy**: fuel and energy per lap, range, pit lap, how much fuel to add, tyre change or not.
- **Pit menu** (LMU): sets the pit menu about a lap before your stop (fuel or virtual energy, tyres, repairs), or only when you ask. Voice orders work too ("wet tyres at the next stop").
- **Voice questions** (push-to-talk on your wheel or keyboard): fuel, tyres, gaps, position, weather, sectors, records…
- **Spotter** (car left / right), faster class coming, cars stopped on track ahead.
- **Live dashboard**: track map with all cars, gaps, fuel, tyres, weather forecast, live delta to your best lap.
- **Car behaviour analysis**: understeer, oversteer, lock-ups, wheelspin, corner by corner, with setup advice.
- **Setup workshop** (LMU): builds one Qualifying and one Race setup file per track from what it measured
  (never touches your own setup files). Starting fuel calculated from your consumption.
- **Reference lap**: keeps your best clean lap per car and track and tells you where you lose time, corner by corner (not while you're battling).
- **Stint planner** for team endurance: drivers, stints in tanks or in time, driver change called at the right stop.
- **Records and debriefs**: best lap per track and class, progress chart, a report for every session.
- **Phone view**: scan the QR code (📱 button) with your phone, on the same Wi-Fi.
- **Assetto Corsa EVO**: strategy, gaps and full race order, spotter, track cuts to give back, penalties, tyre temperatures. Pit menu and setup workshop are LMU only for now.
- **French and English**, voice included (button at the top of the dashboard, or set on first launch from Windows language), with several voices to choose from (female and male).

### Install
1. Download **[ApexRadio-Setup.exe](https://github.com/ApexRadio/apex-radio/releases/latest)** and run it (Python and everything is included).
   If Windows says "Windows protected your PC": **More info** → **Run anyway** (the app isn't signed yet).
   It's not a virus warning: Windows just doesn't know unsigned apps yet. The installer is built automatically by GitHub from this public code.

   ![Installing past the blue Windows message](docs/installation-guide.png)
2. Launch **Apex Radio** from the desktop icon (its window opens), then start LMU or AC EVO and get in your car: the dashboard fills in by itself.
3. Click **CHOOSE THE RADIO BUTTON** and press the wheel button you want for push-to-talk.

The **Apex Radio (demo)** shortcut in the Start menu runs a simulated race to try everything without the game.
Developers: you can also run from source with `Lancer.bat` (needs Python 3.11+).

### Credits and licences
Apex Radio is free software under the **GNU GPL v3** (see `LICENSE`).
It uses: Piper TTS (GPL-3.0), faster-whisper and Whisper (MIT), pyLMUSharedMemory (MIT), pygame-ce (LGPL-2.1),
and others listed in `THIRD_PARTY_LICENSES.txt`.
Voices (pick one in the dashboard): French "Jessica" and "Pierre" (MaryTTS **upmc**, CC BY-SA 4.0), "Siwis" (SIWIS, CC BY 4.0);
English "LJ" (**LJ Speech**, public domain), "Kristin" and "John" (LibriVox, public domain), "Northern" (OpenSLR 83, CC BY-SA 4.0).
Not affiliated with Studio 397, Motorsport Games or the ACO.

### Community and support
Questions, bugs, ideas: join the [Discord](https://discord.gg/ZHg4qXd26g). The app is free and will stay free;
if it helps you find a few tenths, you can support its development on [Patreon](https://www.patreon.com/lolotuner) or with a coffee on [Ko-fi](https://ko-fi.com/apexradio).

---

## Français

Apex Radio lit Le Mans Ultimate (et Assetto Corsa EVO) en direct et te parle à la radio, comme un vrai ingénieur de course.
Tu appuies sur un bouton du volant, tu poses ta question, il te répond. La voix et la reconnaissance vocale tournent sur ton PC :
pas d'abonnement, pas de compte. Internet sert seulement la première fois (téléchargement de la voix) et pour vérifier les mises à jour.

### Jeux supportés

| Jeu | État |
|---|---|
| Le Mans Ultimate | ✅ Supporté (toutes les fonctions) |
| Assetto Corsa EVO | ✅ Supporté (sans menu des stands ni atelier setup pour l'instant) |
| iRacing | 🧪 En test |
| Automobilista 2 | 📋 Prévu |

Tu veux un autre simulateur ? Dis-le sur [Discord](https://discord.gg/ZHg4qXd26g).

### Ce qu'il fait
- **Stratégie** : conso essence et énergie, autonomie, tour d'arrêt, quantité à remettre, pneus ou pas.
- **Menu des stands** (LMU) : il règle le menu environ un tour avant ton arrêt (essence ou énergie virtuelle, pneus, réparations), ou seulement quand tu le demandes. Marche aussi à la voix (« pneus pluie au prochain arrêt »).
- **Questions à la voix** (bouton radio sur le volant ou le clavier) : essence, pneus, écarts, position, météo, secteurs, records…
- **Spotter** (voiture à gauche / à droite), catégorie plus rapide qui arrive, voitures arrêtées devant.
- **Tableau de bord en direct** : carte du circuit avec toutes les voitures, écarts, essence, pneus, prévisions météo, delta en direct.
- **Analyse du comportement** : sous-virage, survirage, blocages, patinage, virage par virage, avec conseils de réglage.
- **Atelier setup** (LMU) : un fichier Qualif et un fichier Course par circuit, construits à partir des mesures
  (il ne touche jamais à tes propres setups). Essence de départ calculée d'après ta conso.
- **Tour de référence** : il garde ton meilleur tour propre par voiture et circuit et te dit où tu perds du temps, virage par virage (pas pendant une bagarre).
- **Planning des relais** pour l'endurance en équipe : pilotes, relais en pleins ou en durée, changement de pilote annoncé au bon arrêt.
- **Records et débriefs** : meilleur tour par circuit et catégorie, courbe de progression, un rapport par session.
- **Affichage téléphone** : scanne le QR code (bouton 📱) avec ton téléphone, sur le même Wi-Fi.
- **Assetto Corsa EVO** : stratégie, écarts et classement complet, spotter, coupes de piste à rendre, pénalités, température des pneus. Menu des stands et atelier setup : LMU seulement pour l'instant.
- **Français et anglais**, voix comprise (bouton en haut du tableau de bord), avec plusieurs voix au choix (femme et homme).

### Installation
1. Télécharge **[ApexRadio-Setup.exe](https://github.com/ApexRadio/apex-radio/releases/latest)** et lance-le (Python et tout le reste sont inclus).
   Si Windows affiche « Windows a protégé votre ordinateur » : **Informations complémentaires** → **Exécuter quand même** (l'appli n'est pas encore signée).
   Ce n'est pas une alerte virus : Windows ne connaît simplement pas encore les applis non signées. L'installateur est fabriqué automatiquement par GitHub à partir de ce code public.

   ![Installer malgré le message bleu de Windows](docs/installation-guide.png)
2. Ouvre **Apex Radio** avec l'icône du bureau (sa fenêtre s'ouvre), puis lance LMU ou AC EVO et monte dans ta voiture : le tableau de bord se remplit tout seul.
3. Clique sur **CHOISIR LE BOUTON RADIO** et appuie sur le bouton du volant que tu veux utiliser.

Le raccourci **Apex Radio (demo)** du menu Démarrer lance une course simulée pour tout essayer sans le jeu.
Pour les développeurs : on peut aussi lancer depuis le code avec `Lancer.bat` (Python 3.11+ requis).

### Crédits et licences
Apex Radio est un logiciel libre sous licence **GNU GPL v3** (voir `LICENSE`).
Composants : Piper TTS (GPL-3.0), faster-whisper et Whisper (MIT), pyLMUSharedMemory (MIT), pygame-ce (LGPL-2.1),
et les autres listés dans `THIRD_PARTY_LICENSES.txt`.
Voix (au choix dans le tableau de bord) : « Jessica » et « Pierre » (MaryTTS **upmc**, CC BY-SA 4.0), « Siwis » (SIWIS, CC BY 4.0) ;
en anglais « LJ » (**LJ Speech**, domaine public), « Kristin » et « John » (LibriVox, domaine public), « Northern » (OpenSLR 83, CC BY-SA 4.0).
Sans lien avec Studio 397, Motorsport Games ou l'ACO.

### Communauté et soutien
Questions, bugs, idées : rejoins le [Discord](https://discord.gg/ZHg4qXd26g). L'appli est gratuite et le restera ;
si elle t'aide à gagner quelques dixièmes, tu peux soutenir son développement sur [Patreon](https://www.patreon.com/lolotuner) ou m'offrir un café sur [Ko-fi](https://ko-fi.com/apexradio).
