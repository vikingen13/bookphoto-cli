# Référence des commandes

Toutes les commandes agissent sur le **dossier courant** (le site). Aucune ne prend de
chemin de site en argument : `cd` dans le bon dossier d'abord. L'utilisateur Basic Auth
est fixe : **`invite`**. Un mot de passe `-` rend la galerie **publique**.

```bash
gallery --version
gallery --help
```

---

## `init`

```bash
gallery init [--region <region>] [--profile <profil>]
```

Crée le site dans le dossier courant, **provisionne l'infra AWS** (CloudFormation) et
**publie**. Interactif — demande : nom, slogan, image de cover (chemin), avatar (chemin),
**mot de passe** (`invite` ; `-` = publique), copyright.

- `--region` : région AWS. Par défaut, celle du profil/environnement. Erreur si aucune.
- `--profile` : profil `~/.aws`. Seul le **nom** est mémorisé (jamais les secrets).
- Écrit `site.yaml`, `assets/`, un `.gitignore` (`.bookphoto.json`, `index.html`, `data.json`),
  puis `.bookphoto.json` (région, profil, mot de passe) et enfin les sorties de la stack.
- Échoue si un site existe déjà ici.

Stack : `bookphoto-<slug(nom)>` · bucket : `bookphoto-<slug(nom)>-<accountId>`.

---

## `config`

```bash
gallery config                       # interactif
gallery config --name "…" --tagline "…" --copyright "…"
gallery config --cover chemin.jpg    # '-' pour retirer
gallery config --avatar chemin.jpg   # '-' pour retirer
gallery config --password "secret"   # '-' = galerie publique
```

Affiche / modifie le branding (`site.yaml`) et le mot de passe (`.bookphoto.json`). Sans
option : mode interactif (Entrée conserve la valeur actuelle). Les images passées à
`--cover`/`--avatar` sont copiées dans `assets/`. Applique en ligne avec `gallery push`.

---

## `new`

```bash
gallery new "<titre>" [--slug <slug>]
```

Crée un album (dossier `<slug>/` + `photos/` + `album.yaml`) et demande la description.
Le slug est dérivé du titre s'il n'est pas fourni.

---

## `add`

```bash
gallery add <album> <fichiers…>
```

Copie les photos dans `<album>/photos/`, lit la **date EXIF**, met à jour `album.yaml`
(dédup par nom de fichier), puis génère les **dérivés** : miniatures `thumbs/` (≤ 400 px)
et affichage `display/` (≤ 2048 px), avec autorotation EXIF. Un dossier passé en argument
est développé récursivement en images.

---

## `import`

```bash
gallery import <dossier> [--keep-names|-y]
```

Import en masse : **chaque sous-dossier** de `<dossier>` devient un album (nom demandé,
défaut = nom du dossier ; slug dérivé). Génère les dérivés au passage. Sous-dossiers
vides ignorés ; images à la racine ignorées. `--keep-names` : pas de question, utilise les
noms de dossiers (gère les collisions de slug en suffixant `-2`, `-3`…).

---

## `album`

```bash
gallery album <slug>                         # interactif
gallery album <slug> --title "…" --description "…"
gallery album <slug> --cover <nom|index>     # ex. photo.jpg OU 3 (3e photo)
gallery album <slug> --header / --no-header  # bandeau cover dans l'en-tête de l'album
```

Modifie un album. La couverture s'indique par **nom de fichier** ou **index 1-based**
d'une photo de l'album (jamais un chemin). `--header/--no-header` contrôle l'affichage du
bandeau cover en tête d'album (défaut : affiché).

---

## `headers`

```bash
gallery headers            # affiche l'état
gallery headers on         # force le bandeau partout
gallery headers off        # masque le bandeau partout
gallery headers auto       # chaque album décide (réglage par album)
```

Override **global** du bandeau cover, stocké dans `site.yaml` (`header_override`). Non
destructif : `auto` restaure les choix par album.

---

## `remove`

```bash
gallery remove <album>              # supprime l'album entier
gallery remove <album> <fichiers…>  # supprime des photos (original + dérivés + entrée)
```

---

## `list`

```bash
gallery list
```

Tableau des albums (slug, titre, nombre de photos).

---

## `preview`

```bash
gallery preview [--port 8000]
```

Génère la SPA (`index.html` + `data.json`) et sert le dossier en local
(`http://127.0.0.1:<port>`), ouvre le navigateur. `Ctrl-C` pour arrêter. N'appelle pas AWS.

---

## `push`

```bash
gallery push
```

Publie en ligne : génère la SPA, **synchronise le dossier vers S3 de façon incrémentale**
(n'envoie que les fichiers nouveaux/modifiés — comparaison taille + ETag —, supprime les
obsolètes), écrit le mot de passe dans le KeyValueStore, puis **invalide** le cache
CloudFront. `.bookphoto.json` et `.gitignore` ne sont jamais envoyés. Nécessite un site
provisionné (`init`).

---

## `pull`

```bash
gallery pull "<nom de la galerie>" [--region <region>] [--profile <profil>]
```

Clone une galerie existante depuis AWS **dans le dossier courant**. La source de vérité
est la stack `bookphoto-<slug(nom)>` : le **nom de la galerie** compte, pas le nom du
dossier local. Reconstruit `.bookphoto.json` depuis les sorties de la stack et restaure le
mot de passe depuis le KeyValueStore.

---

## `destroy`

```bash
gallery destroy [--yes|-y]
```

**Irréversible.** Vide le bucket S3 puis supprime la stack CloudFormation (donc toute
l'infra AWS de ce site). Le contenu **local** (photos, albums) est conservé. Demande
confirmation sauf `--yes`.

---

## `doctor`

```bash
gallery doctor
```

Diagnostics en **lecture seule** : identifiants AWS, infra provisionnée, bucket privé,
distribution déployée.

---

## `iam-policy`

```bash
gallery iam-policy
```

Affiche (JSON) la politique IAM minimale requise. Voir [architecture.md](architecture.md).
