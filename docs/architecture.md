# Architecture AWS & sécurité

## Vue d'ensemble

```
Navigateur ──HTTPS──▶ CloudFront ──(viewer-request)──▶ CloudFront Function ──▶ KeyValueStore
                          │                                   │  (clé "auth")
                          │  Origin Access Control (SigV4)     └─ Basic Auth : 401 si KO
                          ▼
                      S3 (privé)
```

Tout est **statique** : aucun serveur, aucune fonction Lambda côté origine. La galerie est
une SPA (`index.html` + `data.json`) plus les images (`thumbs/`, `display/`), stockées dans
un bucket S3 **privé** et distribuées par CloudFront.

Infra décrite dans [`../src/bookphoto/aws/infra.yaml`](../src/bookphoto/aws/infra.yaml)
(CloudFormation). Nommage : stack `bookphoto-<slug(nom)>`, bucket
`bookphoto-<slug(nom)>-<accountId>`. Tags : `Project=bookphoto`, `Gallery=<slug>`,
`ManagedBy=bookphoto`.

## Composants

- **S3 (`AWS::S3::Bucket`)** — privé de bout en bout :
  - `PublicAccessBlockConfiguration` : les 4 blocages activés.
  - `OwnershipControls: BucketOwnerEnforced` (pas d'ACL).
  - `BucketEncryption: AES256` (SSE-S3).
  - Politique de bucket : lecture `s3:GetObject` autorisée **uniquement** au service
    `cloudfront.amazonaws.com`, et **conditionnée** à l'ARN de *cette* distribution
    (`AWS:SourceArn`). Personne d'autre ne lit le bucket.
- **Origin Access Control (OAC)** — CloudFront signe ses requêtes vers S3 en **SigV4**
  (`SigningBehavior: always`). Remplace l'ancien OAI.
- **CloudFront Distribution** :
  - `ViewerProtocolPolicy: redirect-to-https`, `HttpVersion: http2and3`, `Compress: true`.
  - Cache : managed policy **CachingOptimized**.
  - `PriceClass` paramétrable (défaut **PriceClass_100** : edges US/EU, le moins cher).
  - `DefaultRootObject: index.html`.
  - **Erreurs 403 et 404 → `/index.html`** (code 404) : routage SPA + ne divulgue pas la
    liste des objets.
- **KeyValueStore (`AWS::CloudFront::KeyValueStore`)** — stocke la valeur d'auth sous la
  clé **`auth`**.
- **CloudFront Function (`cloudfront-js-2.0`, `viewer-request`)** — le contrôle d'accès :
  lit `auth` dans le KVS et
  - si la valeur est `-` → **galerie publique** (laisse passer) ;
  - sinon compare l'en-tête `Authorization` à `Basic <auth>` → laisse passer si égal ;
  - sinon **401** avec `WWW-Authenticate: Basic realm="Galerie privee"`.

## Modèle d'authentification

- **Utilisateur unique et fixe : `invite`**. Un seul mot de passe partagé.
- La valeur stockée dans le KVS est `base64("invite:<mot de passe>")` (exactement la partie
  qui suit `Basic ` dans l'en-tête HTTP). Marqueur spécial `-` = public.
- **Fail-closed** : si le KVS est illisible ou vide, la Function renvoie 401.
- Changer le mot de passe = un simple `PutKey` sur le KVS (fait par `push`/`config`),
  **sans redéploiement** ni invalidation nécessaires pour l'auth.

### Portée de sécurité (à connaître)

- « Privé » = **contrôle d'accès par mot de passe partagé**, pas de la confidentialité de
  niveau militaire. Le Basic Auth protège l'accès HTTP ; il n'y a pas de comptes
  individuels ni de révocation par personne (un seul secret pour tous).
- Le mot de passe est stocké **en clair** dans `.bookphoto.json` (config machine locale).
  Ce fichier est **git-ignoré** par `init`. Ne le committe pas, ne le partage pas.
- Le transport est chiffré (HTTPS), le bucket n'est **jamais** exposé en direct.

## Politique IAM minimale

`gallery iam-policy` imprime la politique exacte. Principes :

- **Aucun `Resource: "*"`** sauf pour les actions qui n'ont pas de ressource
  (`sts:GetCallerIdentity`) ou de **création** dont la ressource n'existe pas encore
  (`cloudfront:Create*`). Tout le reste est **scopé** aux ARN `bookphoto-*`.
- Blocs : identité STS, CloudFormation (`stack/bookphoto-*`), S3 (`bookphoto-*`),
  CloudFront création, CloudFront gestion (distribution/function/kvs/OAC), et données
  KeyValueStore (`PutKey`/`GetKey`…).

Récupérer et appliquer :

```bash
gallery iam-policy > bookphoto-policy.json
# puis attacher cette policy au user/role qui exécute gallery
```

## Coûts

Pas de compute (tout statique). Les postes de coût sont :

- **Stockage S3** : proportionnel au poids des images (originaux + dérivés).
- **CloudFront** : transfert sortant + nombre de requêtes (selon le trafic).
- **KeyValueStore / Function** : négligeable pour une galerie personnelle.

Les montants dépendent de ton volume et de ton trafic ; pour une estimation chiffrée,
utilise le [AWS Pricing Calculator](https://calculator.aws/). Détruire l'infra d'un site :
`gallery destroy` (voir [commandes.md](commandes.md)).
