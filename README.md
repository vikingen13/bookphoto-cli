# bookphoto

CLI pour une **galerie photo privée serverless** sur AWS (S3 privé + CloudFront), protégée par un **mot de passe unique** (Basic Auth via CloudFront Function + KeyValueStore). Administration 100 % locale en Python ; design de la galerie produit avec Open Design.

**Un site = un dossier.** Tu `cd` dans un dossier, `gallery init` l'initialise, et tout (branding, albums, config AWS, build) vit **dans ce dossier**. Plusieurs galeries = plusieurs dossiers indépendants — aucun état global.

> État : socle local complet (site, albums+EXIF, dérivés, **générateur de site statique**) + **code** des commandes AWS (`provision`, `password`, `publish`, `pull`, `doctor`, `iam-policy`). Le déploiement AWS n'a pas encore été exécuté.

## Prérequis

- Python **3.12+** (recommandé : 3.14)
- [uv](https://docs.astral.sh/uv/) : `brew install uv`
- Pour les commandes AWS : des identifiants AWS (`~/.aws`) avec les droits de `gallery iam-policy`.

## Installation

```bash
uv sync
uv run gallery --help
# ou, comme outil global :
uv tool install .
gallery --help
```

## Flux de travail

```bash
mkdir mon-book && cd mon-book        # le dossier = le site
gallery init                          # crée site.yaml + assets/ ici
# édite site.yaml (nom, tagline, cover, avatar) et dépose les images dans assets/

gallery new "Rue de nuit"             # crée l'album + album.yaml
gallery add rue-de-nuit ~/photos/*.jpg  # copie les photos, lit la date EXIF
gallery gen rue-de-nuit               # miniatures (thumbs/) + affichage (display/)
gallery list                          # liste les albums
gallery build                         # génère le site statique dans ./build

# --- AWS (le jour de la mise en ligne) ---
gallery provision --bucket mon-book-unique-123 --region eu-west-3 --profile bookphoto
gallery password                      # mot de passe unique (Basic Auth)
gallery publish                       # build + upload S3 + invalidation CloudFront
gallery doctor                        # diagnostics
gallery pull ./backup                 # récupère le site publié
gallery iam-policy                    # policy IAM minimale requise
```

### Identifiants AWS (pas besoin de l'AWS CLI)

bookphoto parle à AWS via **boto3** (livré avec l'outil). Fournis tes identifiants au choix :

- **Profil** `~/.aws/credentials` (recommandé — écrit une fois, mémorisé par `--profile` dans `.bookphoto.json` du site) :
  ```ini
  [bookphoto]
  aws_access_key_id = AKIA...
  aws_secret_access_key = ...
  region = eu-west-3
  ```
- ou variables d'env (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`), ou un profil SSO (`aws sso login`).

Les secrets restent dans `~/.aws` — **jamais** dans le projet. bookphoto ne mémorise que le **nom** du profil.

## Organisation d'un site (le dossier)

```
mon-book/
  site.yaml        # branding : name, tagline, cover (hero), avatar, copyright
  .bookphoto.json  # config machine (region, bucket, distribution, url, profil) — écrite par `provision`
  assets/          # images de branding (cover.jpg, avatar.jpg)
  <slug>/
    album.yaml     # title, description, cover, photos:[{file, date, caption}]
    photos/        # originaux copiés
    thumbs/        # miniatures (grille)
    display/       # versions d'affichage (lightbox, covers)
  build/           # site généré (uploadé par `publish`)
```

## Architecture AWS

- **S3 privé** (public access bloqué, chiffré) — servi **uniquement** via CloudFront (**Origin Access Control**, SigV4).
- **CloudFront** (HTTPS `*.cloudfront.net`, PriceClass_100, cache optimisé).
- **Basic Auth** : une **CloudFront Function** (`cloudfront-js-2.0`, `viewer-request`) compare l'en-tête `Authorization` à `base64("user:password")` lu dans un **KeyValueStore**. Changer le mot de passe = mettre à jour le KVS (`gallery password`), sans redéployer.
- Décrit dans `src/bookphoto/aws/infra.yaml` (CloudFormation).

## Tests

```bash
uv run pytest
```
