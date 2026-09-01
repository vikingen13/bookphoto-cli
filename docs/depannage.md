# Dépannage

Commence toujours par :

```bash
gallery doctor        # identifiants AWS, infra provisionnée, bucket privé, distribution
gallery --version
```

## Identifiants / région

- **« Region inconnue »** à l'`init` : aucune région dans le profil/environnement. Passe
  `--region eu-west-1` (ou configure ta région AWS par défaut).
- **`doctor` → Identifiants AWS KO** : pas de credentials valides. Utilise un profil
  (`--profile mon-profil`), des variables d'env, ou `aws sso login`.
- bookphoto ne stocke que le **nom** du profil dans `.bookphoto.json`, jamais les secrets.

## Permissions (AccessDenied)

Le provisionnement échoue souvent sur une **permission IAM manquante** (le message
CloudFormation l'indique). Applique la politique minimale :

```bash
gallery iam-policy > bookphoto-policy.json
```

et attache-la au user/role qui exécute `gallery` (voir [architecture.md](architecture.md)).

## init / CloudFormation

- **« Un site existe déjà ici »** : `init` refuse d'écraser. Va dans un dossier vide, ou
  utilise `pull` pour cloner un site existant.
- **Provisionnement en échec** : la cause CloudFormation est affichée en direct. Si la
  stack est retombée en `ROLLBACK`/supprimée (`OnFailure=DELETE`), corrige la cause
  (souvent IAM) puis relance `init` dans un dossier vide.
- Le suivi affiche chaque événement de la stack ; laisse-le aller jusqu'au `*_COMPLETE`.

## push

- **« Site non provisionné »** : lance `gallery init` d'abord (ou `pull`).
- **Un dérivé manque** (avertissement à la génération) : relance `gallery add <album> …`
  pour (re)générer `thumbs/`/`display/`.
- Le push est **incrémental** : `X envoyé, Y inchangé, Z supprimé`. Un fichier « inchangé »
  n'est pas ré-uploadé (comparaison taille + ETag).

## Le site affiche l'ancienne version

`push` invalide déjà CloudFront (`/*`). La propagation peut prendre une minute. Le HTML est
servi `no-cache`, les images en cache long (immuables). En cas de doute, recharge en
vidant le cache navigateur.

## Authentification

- **401 en boucle** : mot de passe erroné, ou KVS pas encore à jour. Refais un `gallery push`
  (ou `gallery config --password …`) pour réécrire la clé `auth`.
- **Rendre public / privé** : `gallery config --password -` (public) ou un vrai mot de
  passe (privé). L'utilisateur est toujours `invite`.
- **Fail-closed** : si le KVS est illisible, l'accès est refusé (401) par sécurité.

## pull

- Clone par **nom de galerie** (`gallery pull "Ma galerie"`), pas par nom de dossier : la
  source est la stack `bookphoto-<slug(nom)>`. Vérifie l'orthographe du nom.
- Précise `--region`/`--profile` si la galerie n'est pas dans la région/compte par défaut.

## destroy échoue (DELETE_FAILED)

- Message `s3:DeleteBucketPolicy ... not authorized` (ou une autre action `Delete*`) : le
  rôle manque de droits de **suppression**. Applique la politique à jour
  (`gallery iam-policy`) au user/role, puis relance `gallery destroy`.
- La stack reste en `DELETE_FAILED` tant que la cause n'est pas levée : une fois les droits
  ajoutés, `gallery destroy` **relance** la suppression (le bucket déjà vidé n'est pas un
  problème). En dernier recours, supprime la ressource fautive puis la stack depuis la
  console CloudFormation (ou `delete-stack --retain-resources <LogicalId>`).

## Coûts

Pour toute estimation de facture, utilise le [AWS Pricing Calculator](https://calculator.aws/).
Pour arrêter les frais d'un site : `gallery destroy` (supprime bucket + stack ; le contenu
local est conservé).

## Tests

```bash
uv run pytest
```
