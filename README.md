# APEX//RADIO

**A free voice race engineer for Le Mans Ultimate** · *Un ingénieur de course vocal gratuit pour Le Mans Ultimate*

🇬🇧 [English](#english) · 🇫🇷 [Français](#français)

---

## English

Apex Radio listens to Le Mans Ultimate in real time and talks to you on the radio, like a real race engineer.
Push a button on your wheel, ask a question, get an answer. Everything runs locally on your PC: no subscription,
no account, no internet needed once installed.

### What it does
- **Strategy**: fuel and energy per lap, range, pit lap, how much fuel to add, tyre change or not.
- **Pit menu**: sets the LMU pit menu for you when you box (fuel, tyres, repairs).
- **Voice questions** (push-to-talk on your wheel or keyboard): fuel, tyres, gaps, position, weather, sectors, records…
- **Spotter** (car left / right), faster class coming, cars stopped on track ahead.
- **Live dashboard**: track map with all cars, gaps, fuel, tyres, weather forecast, live delta to your best lap.
- **Car behaviour analysis**: understeer, oversteer, lock-ups, wheelspin, corner by corner, with setup advice.
- **Setup workshop**: builds one Qualifying and one Race setup file per track from what it measured
  (never touches your own setup files). Starting fuel calculated from your consumption.
- **Records and debriefs**: best lap per track and class, progress chart, a report for every session.
- **Phone view**: open `http://<your-PC-IP>:8765/tel` on your phone (same Wi-Fi).
- **French and English**, voice included (button at the top of the dashboard, or set on first launch from Windows language).

### Install
1. Install Python 3.11+ from python.org (tick **Add python.exe to PATH**).
2. Download and unzip Apex Radio.
3. Double-click **Lancer.bat**. The first launch installs the components (2-5 min) and creates a desktop shortcut.
4. Start LMU and get in your car. The dashboard opens in your browser.
5. Click **CHOOSE THE RADIO BUTTON** and press the wheel button you want for push-to-talk.

`Demo.bat` runs a simulated race to try everything without the game.

### Credits and licences
Apex Radio is free software under the **GNU GPL v3** (see `LICENSE`).
It uses: Piper TTS (GPL-3.0), faster-whisper and Whisper (MIT), pyLMUSharedMemory (MIT), pygame-ce (LGPL-2.1),
and others listed in `THIRD_PARTY_LICENSES.txt`.
Voices: French "Jessica" from the MaryTTS **upmc** recordings (CC BY-SA 4.0); English voice trained on **LJ Speech** (public domain).
Not affiliated with Studio 397, Motorsport Games or the ACO.

---

## Français

Apex Radio lit Le Mans Ultimate en direct et te parle à la radio, comme un vrai ingénieur de course.
Tu appuies sur un bouton du volant, tu poses ta question, il te répond. Tout tourne sur ton PC :
pas d'abonnement, pas de compte, pas besoin d'internet une fois installé.

### Ce qu'il fait
- **Stratégie** : conso essence et énergie, autonomie, tour d'arrêt, quantité à remettre, pneus ou pas.
- **Menu des stands** : il règle le menu de LMU tout seul au moment du box (essence, pneus, réparations).
- **Questions à la voix** (bouton radio sur le volant ou le clavier) : essence, pneus, écarts, position, météo, secteurs, records…
- **Spotter** (voiture à gauche / à droite), catégorie plus rapide qui arrive, voitures arrêtées devant.
- **Tableau de bord en direct** : carte du circuit avec toutes les voitures, écarts, essence, pneus, prévisions météo, delta en direct.
- **Analyse du comportement** : sous-virage, survirage, blocages, patinage, virage par virage, avec conseils de réglage.
- **Atelier setup** : un fichier Qualif et un fichier Course par circuit, construits à partir des mesures
  (il ne touche jamais à tes propres setups). Essence de départ calculée d'après ta conso.
- **Records et débriefs** : meilleur tour par circuit et catégorie, courbe de progression, un rapport par session.
- **Affichage téléphone** : `http://<IP-du-PC>:8765/tel` sur ton téléphone (même Wi-Fi).
- **Français et anglais**, voix comprise (bouton en haut du tableau de bord).

### Installation
1. Installe Python 3.11 ou plus récent depuis python.org (coche **Add python.exe to PATH**).
2. Télécharge et dézippe Apex Radio.
3. Double-clique sur **Lancer.bat**. Le premier lancement installe les composants (2 à 5 min) et crée un raccourci sur le bureau.
4. Lance LMU et monte dans ta voiture. Le tableau de bord s'ouvre dans ton navigateur.
5. Clique sur **CHOISIR LE BOUTON RADIO** et appuie sur le bouton du volant que tu veux utiliser.

`Demo.bat` lance une course simulée pour tout essayer sans le jeu.

### Crédits et licences
Apex Radio est un logiciel libre sous licence **GNU GPL v3** (voir `LICENSE`).
Composants : Piper TTS (GPL-3.0), faster-whisper et Whisper (MIT), pyLMUSharedMemory (MIT), pygame-ce (LGPL-2.1),
et les autres listés dans `THIRD_PARTY_LICENSES.txt`.
Voix : « Jessica » (français), enregistrements MaryTTS **upmc** (CC BY-SA 4.0) ; voix anglaise entraînée sur **LJ Speech** (domaine public).
Sans lien avec Studio 397, Motorsport Games ou l'ACO.
