# Apex Radio — notes pour Claude

Ingénieur de course vocal pour **Le Mans Ultimate** (LMU), gratuit et open source (GPL v3).
Créateur : Laurent (pseudo lolotuner), francophone : **réponds-lui en français, simplement, étape par étape**
(il n'est pas développeur ; une action à la fois quand il doit cliquer quelque part).

## Le projet
- Python. Lecture de LMU par la mémoire partagée (`vendor/pyLMUSharedMemory`) et l'API REST de LMU (`localhost:6397`,
  ex. `POST /rest/garage/PitMenu/loadPitMenu` pour régler le menu des stands, `GET /rest/garage/summary` pour le setup chargé).
- Voix Piper au choix (`voice.py`, `VOICES`) : FR Jessica/Pierre (upmc), Siwis ; EN LJ, Kristin, John, Northern.
  Seulement des licences sans restriction commerciale (pas Ryan/HFC : NC ; pas Tom : AGPL). Reconnaissance faster-whisper,
  tableau de bord HTTP sur le port 8765 (`ui/index.html`, vue téléphone `ui/tel.html` sur `/tel`).
- Bilingue : `i18n.py` (`L("fr", "en")`), langue dans `config.json`.
- Fenêtre : `desktop.py` (pywebview/WebView2, logo via WM_SETICON, icône près de l'horloge avec pystray,
  secours : Edge en mode `--app`). Un seul Apex à la fois (port exclusif, `already_running()`).
- Données utilisateur : `paths.py` → `Documents\Apex Radio` (records, débriefs, config, carburant, cartes, historique setups) ;
  voix/modèles/journal → `%LOCALAPPDATA%\Apex Radio`. Mode portable si `portable.txt` existe.
- Atelier setup (`setups.py`) : **ne modifie jamais les setups de l'utilisateur**, écrit seulement
  `APEX <circuit> Qualif.svm` / `APEX <circuit> Course.svm` dans le dossier du circuit.
- Menu des stands, réparations (LMU) : « Ne pas réparer », « Réparer la carrosserie », « Tout réparer ».
  Apex choisit « Tout réparer » si la mécanique est touchée (suspension, roue), sinon la carrosserie.
- Mises à jour : `updates.py` interroge `api.github.com/repos/ApexRadio/apex-radio/releases/latest`
  et affiche un bandeau (rien ne s'installe tout seul).

## Publier une version
1. Changer `VERSION`, ajouter la version en haut de `CHANGELOG.md` et sous la ligne « Télécharge » de
   `installer/release-notes.md` (FR + EN, courtes). Retirer de release-notes l'entrée de la version précédente.
2. Commit sur `main`, puis lancer le workflow **Installateur Windows** (`.github/workflows/installer.yml`, workflow_dispatch) :
   Python embarqué 3.12, pip, test d'import, test de la fenêtre WebView2, lanceur C# `launcher/ApexRadio.cs`,
   Inno Setup (`installer/ApexRadio.iss`), puis release `v<VERSION>` avec `ApexRadio-Setup-<VERSION>.exe`.
3. Une branche autre que `main` publie une pré-version `v<VERSION>-test` (ignorée par le bandeau) : utile pour faire tester avant.
4. Sur `main`, une **nouvelle** version est annoncée toute seule dans #annonces-news (Discord) avec les notes de release-notes.md
   (`.github/scripts/discord_announce.py`, secret GitHub `DISCORD_WEBHOOK` créé par Laurent ; sans secret, rien n'est posté).
5. Une **nouvelle** version de test (branche) est annoncée dans #accès-anticipé (catégorie 🏆 PATREON, rôles Pit Wall + Écurie),
   secret `DISCORD_WEBHOOK_EARLY`. Paliers Patreon : Paddock 3 €, Pit Wall 6 € (accès anticipé), Écurie 12 € (accès anticipé,
   #suggestions et #retours réservés, traités en priorité).

## Poste de développement
- Laurent garde une copie de travail dans ses Documents (dossier `IngenieurCourse`) en plus de l'appli installée ;
  les deux partagent `Documents\Apex Radio`. Quand le code change, mettre aussi à jour la copie de travail (il le confirmera).
- Les détails de son PC et de son matériel ne vont pas dans ce dépôt public : les lui demander si besoin.

## Communauté et promotion
- GitHub : https://github.com/ApexRadio/apex-radio (ancien nom laurent22230, redirigé).
- Discord : https://discord.gg/ZHg4qXd26g (lien permanent, créé le 07/11/2026 ; l'ancien wpqNBpMaa expire le 02/12/2026)
- Patreon : https://www.patreon.com/lolotuner
- Ko-fi (dons ponctuels, PayPal relié) : https://ko-fi.com/apexradio — aussi dans le README, `.github/FUNDING.yml` (bouton Sponsor) et ⚙️ Réglages de l'appli.
- Annonce Discord avec image sans navigateur : workflow `annonce.yml` (workflow_dispatch, message + image du dépôt, webhook #annonces-news ou #accès-anticipé).
- OverTake.gg : fiche « Apex Radio - Voice Race Engineer » (LMU Misc), validée le 07/11/2026 : publier une « mise à jour » à chaque version.
- Reddit : publications retirées par les filtres anti-spam (compte récent). Attendre, participer, puis une seule publication à la fois.
- Toujours demander à Laurent de valider un texte avant de le publier à son nom.

## Idées / à faire
- Vidéo de démo (Reel/Short) : question essence → réponse, spotter, « box box » + menu des stands réglé.
- Option de repli si la mise à jour échoue ; signature de code un jour (message SmartScreen).
