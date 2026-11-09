# Code signing policy / Politique de signature du code

## English

Free code signing provided by [SignPath.io](https://about.signpath.io/), certificate by [SignPath Foundation](https://signpath.org/).

The Windows installer of Apex Radio (`ApexRadio-Setup-<version>.exe`) and the launcher it contains are built from this repository by GitHub Actions
(`.github/workflows/installer.yml`). Only binaries built from this repository's source code are signed.

### Team roles
- Committers and reviewers: [lolotuner](https://github.com/ApexRadio) (Laurent, creator and maintainer)
- Approvers: [lolotuner](https://github.com/ApexRadio)

Every release must be approved manually before it is signed. Accounts with access use multi-factor authentication.

### Privacy policy
This program will not transfer any information to other networked systems unless specifically requested by the user or the person installing or operating it.

To work, Apex Radio connects only to:
- **Le Mans Ultimate on the same PC** (`localhost`), to read the game data and set the pit menu;
- **github.com / api.github.com**, to check whether a new version is available (nothing is downloaded or installed automatically);
- **huggingface.co**, once, to download the voice and speech recognition models chosen by the user.

The optional phone view is served on the user's local network only. Voice recognition runs entirely on the user's PC: no audio or personal data is sent anywhere.

## Français

Signature de code gratuite fournie par [SignPath.io](https://about.signpath.io/), certificat de la [SignPath Foundation](https://signpath.org/).

L'installateur Windows d'Apex Radio et son lanceur sont construits à partir de ce dépôt par GitHub Actions. Seuls les fichiers construits à partir du code de ce dépôt sont signés.

### Rôles
- Contributeurs et relecteurs : [lolotuner](https://github.com/ApexRadio) (Laurent, créateur et mainteneur)
- Approbateurs : [lolotuner](https://github.com/ApexRadio)

Chaque version doit être approuvée à la main avant d'être signée. Les comptes ayant accès utilisent la double authentification.

### Confidentialité
Ce programme ne transmet aucune information à d'autres systèmes en réseau, sauf demande explicite de l'utilisateur ou de la personne qui l'installe ou l'utilise.

Pour fonctionner, Apex Radio se connecte seulement à :
- **Le Mans Ultimate sur le même PC** (`localhost`), pour lire les données du jeu et régler le menu des stands ;
- **github.com / api.github.com**, pour savoir si une nouvelle version existe (rien n'est téléchargé ni installé tout seul) ;
- **huggingface.co**, une seule fois, pour télécharger la voix et le modèle de reconnaissance vocale choisis.

La vue téléphone, facultative, n'est accessible que sur le réseau local. La reconnaissance vocale tourne entièrement sur le PC : aucun son ni aucune donnée personnelle n'est envoyé.
