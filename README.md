# bookphoto

CLI pour une **galerie photo privée serverless** sur AWS : **S3 privé + CloudFront**, protégée par un **mot de passe unique** (Basic Auth via CloudFront Function + KeyValueStore). Administration 100 % locale en Python.

**Un site = un dossier.** Tu `cd` dans un dossier, `gallery init` le crée, le déploie sur AWS et le met en ligne — tout (branding, albums, config, build) vit **dans ce dossier**. Plusieurs galeries = plusieurs dossiers indépendants, aucun état global.

- 🔒 Bucket S3 **privé**, servi uniquement par CloudFront (Origin Access Control, SigV4).
- 🔑 **Un seul mot de passe** (utilisateur fixe `invite`) ; `-` = galerie **publique**.
- ⚡ Site **statique** (SPA `index.html` + `data.json`) ; miroir S3 **incrémental**.
- 🖥️ Aucune AWS CLI requise : tout passe par **boto3** (livré avec l'outil).

## Prérequis

- **Python 3.12+**
- [uv](https://docs.astral.sh/uv/) : `brew install uv`
- Des identifiants AWS (`~/.aws`) avec les droits de `gallery iam-policy` (voir [docs/architecture.md](docs/architecture.md)).

## Installation

```bash
uv tool install --editable .   # depuis le dépôt cloné
gallery --version
```

Identifiants AWS (au choix) : profil `~/.aws/credentials` (recommandé), variables d'env (`AWS_ACCESS_KEY_ID`…), ou SSO (`aws sso login`). bookphoto ne mémorise que le **nom** du profil (`--profile`), jamais les secrets.

## Démarrage rapide

```bash
mkdir mon-book && cd mon-book     # le dossier = le site
gallery init                       # infos + déploiement AWS + mise en ligne (interactif)

gallery new "Rue de nuit"          # crée un album (demande la description)
gallery add rue-de-nuit ~/photos/*.jpg   # copie, lit l'EXIF, génère les dérivés
gallery preview                    # aperçu local (http://127.0.0.1:8000)
gallery push                       # met à jour en ligne (miroir S3 + mot de passe + invalidation)
```

`gallery init` te demande : nom, slogan, image de cover, avatar, **mot de passe** (`invite` ; `-` pour une galerie publique), copyright — puis provisionne la stack CloudFormation et publie. Options : `--region`, `--profile`.

## Commandes

| Commande | Rôle |
|---|---|
| `init` | Crée le site ici, **provisionne l'infra AWS** et met en ligne |
| `config` | Voir / modifier le branding et le mot de passe |
| `new "<titre>"` | Créer un album |
| `add <album> <fichiers>` | Ajouter des photos (copie + date EXIF + dérivés) |
| `import <dossier>` | Import en masse : un sous-dossier = un album |
| `album <slug>` | Modifier un album (titre, description, cover, header) |
| `headers on\|off\|auto` | Override global du bandeau cover des albums |
| `remove <album> [fichiers]` | Supprimer des photos (ou l'album entier) |
| `list` | Lister les albums |
| `preview [--port]` | Aperçu local (génère la SPA + serveur HTTP) |
| `push` | Publier : génère + miroir S3 incrémental + mot de passe + invalidation CloudFront |
| `pull "<nom>"` | Cloner une galerie existante depuis AWS (par **nom**) |
| `destroy [--yes]` | Détruire l'infra AWS de ce site (vide le bucket + supprime la stack) |
| `doctor` | Diagnostics (lecture seule) |
| `iam-policy` | Afficher la politique IAM minimale requise |

Référence détaillée : [docs/commandes.md](docs/commandes.md).

## Organisation d'un site (le dossier)

```
mon-book/
  site.yaml        # branding : name, tagline, cover, avatar, copyright, header_override
  .bookphoto.json  # config machine (region, bucket, distribution, url, profil, stack…) — écrite par init
  assets/          # images de branding (cover, avatar)
  <slug>/
    album.yaml     # title, description, cover, header, photos:[{file, date, caption}]
    photos/        # originaux copiés
    thumbs/        # miniatures (≤ 400 px)
    display/       # versions d'affichage (≤ 2048 px)
  index.html       # SPA générée (git-ignorée)
  data.json        # données de la galerie générées (git-ignorées)
```

`gallery init` écrit un `.gitignore` excluant `.bookphoto.json`, `index.html` et `data.json`.

## Architecture AWS (résumé)

S3 **privé** (accès public bloqué, chiffré AES256, `BucketOwnerEnforced`) → **CloudFront** (HTTPS, HTTP/2+3, `PriceClass_100`) via **Origin Access Control**. Une **CloudFront Function** (`viewer-request`) lit la clé `auth` d'un **KeyValueStore** et applique le Basic Auth (`-` = public). Décrit dans [`src/bookphoto/aws/infra.yaml`](src/bookphoto/aws/infra.yaml). Détails et sécurité : [docs/architecture.md](docs/architecture.md).

**Coût** : pas de compute (tout statique) ; les postes sont le stockage S3 et le transfert/requêtes CloudFront. Pour une estimation chiffrée selon ton trafic, utilise le [AWS Pricing Calculator](https://calculator.aws/).

## Tests

```bash
uv run pytest
```

## Licence

MIT — voir [LICENSE](LICENSE).
