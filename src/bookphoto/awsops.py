"""Operations AWS de bookphoto (code seul — rien ne s'execute a l'import).

Toutes les fonctions qui appellent AWS importent ``boto3`` *paresseusement* et ne sont
declenchees que par les commandes CLI correspondantes. L'infra est decrite dans
``aws/infra.yaml`` (S3 prive + CloudFront + OAC + CloudFront Function Basic Auth + KVS).
"""

from __future__ import annotations

import base64
import hashlib
import mimetypes
import time
from pathlib import Path

from . import config as cfg
from .albums import slugify

TEMPLATE = Path(__file__).parent / "aws" / "infra.yaml"
DEFAULT_STACK = "bookphoto"
DEFAULT_AUTH_USER = "invite"
AUTH_KEY = "auth"

# Politiques de cache : le HTML doit refleter les MAJ, les images sont immuables.
_LONG_CACHE = "public, max-age=31536000, immutable"
_NO_CACHE = "no-cache"


# --------------------------------------------------------------------------- #
# Helpers purs (testables sans AWS)
# --------------------------------------------------------------------------- #
def load_template() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def basic_auth_value(user: str, password: str) -> str:
    """Valeur stockee dans le KVS : base64("user:password") (la partie apres 'Basic ')."""
    return base64.b64encode(f"{user}:{password}".encode()).decode()


def content_type(path: Path | str) -> str:
    ct, _ = mimetypes.guess_type(str(path))
    return ct or "application/octet-stream"


def cache_control(key: str) -> str:
    return _NO_CACHE if key == "index.html" or key.endswith(".html") else _LONG_CACHE


def iam_policy() -> dict:
    """Politique IAM minimale. Regle : pas de ``Resource:"*"`` sauf pour les actions
    sans ressource (``sts:GetCallerIdentity``) ou de creation ou la ressource n'existe
    pas encore (``cloudfront:Create*``). Tout le reste est scope aux ARN ``bookphoto-*``.
    """
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "Identity",
                "Effect": "Allow",
                "Action": ["sts:GetCallerIdentity"],
                "Resource": "*",  # action sans ressource
            },
            {
                "Sid": "CloudFormationStack",
                "Effect": "Allow",
                "Action": [
                    "cloudformation:CreateStack",
                    "cloudformation:UpdateStack",
                    "cloudformation:DeleteStack",
                    "cloudformation:DescribeStacks",
                    "cloudformation:DescribeStackEvents",
                    "cloudformation:GetTemplate",
                ],
                "Resource": "arn:aws:cloudformation:*:*:stack/bookphoto-*/*",
            },
            {
                "Sid": "S3Bucket",
                "Effect": "Allow",
                "Action": [
                    "s3:CreateBucket",
                    "s3:PutBucketPolicy",
                    "s3:PutBucketPublicAccessBlock",
                    "s3:PutBucketOwnershipControls",
                    "s3:PutBucketTagging",
                    "s3:PutEncryptionConfiguration",
                    "s3:GetBucketPolicy",
                    "s3:GetBucketPublicAccessBlock",
                    "s3:ListBucket",
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:DeleteObject",
                    "s3:DeleteBucket",
                ],
                "Resource": [
                    "arn:aws:s3:::bookphoto-*",
                    "arn:aws:s3:::bookphoto-*/*",
                ],
            },
            {
                "Sid": "CloudFrontCreate",
                "Effect": "Allow",
                "Action": [
                    "cloudfront:CreateDistribution",
                    "cloudfront:CreateOriginAccessControl",
                    "cloudfront:CreateFunction",
                    "cloudfront:CreateKeyValueStore",
                ],
                "Resource": "*",  # Create : la ressource n'existe pas encore
            },
            {
                "Sid": "CloudFrontManage",
                "Effect": "Allow",
                "Action": [
                    "cloudfront:GetDistribution",
                    "cloudfront:UpdateDistribution",
                    "cloudfront:DeleteDistribution",
                    "cloudfront:CreateInvalidation",
                    "cloudfront:DescribeFunction",
                    "cloudfront:GetFunction",
                    "cloudfront:UpdateFunction",
                    "cloudfront:PublishFunction",
                    "cloudfront:DeleteFunction",
                    "cloudfront:DescribeKeyValueStore",
                    "cloudfront:DeleteKeyValueStore",
                    "cloudfront:GetOriginAccessControl",
                    "cloudfront:DeleteOriginAccessControl",
                    "cloudfront:ListTagsForResource",
                    "cloudfront:TagResource",
                    "cloudfront:UntagResource",
                ],
                "Resource": [
                    "arn:aws:cloudfront::*:distribution/*",
                    "arn:aws:cloudfront::*:function/*",
                    "arn:aws:cloudfront::*:key-value-store/*",
                    "arn:aws:cloudfront::*:origin-access-control/*",
                ],
            },
            {
                "Sid": "CloudFrontKeyValueStoreData",
                "Effect": "Allow",
                "Action": [
                    "cloudfront-keyvaluestore:DescribeKeyValueStore",
                    "cloudfront-keyvaluestore:PutKey",
                    "cloudfront-keyvaluestore:GetKey",
                    "cloudfront-keyvaluestore:ListKeys",
                ],
                "Resource": "arn:aws:cloudfront::*:key-value-store/*",
            },
        ],
    }


def _boto3():
    import boto3  # import paresseux : pas requis pour l'usage local/tests

    return boto3


def _session(profile: str | None = None):
    """Session boto3 utilisant le profil ~/.aws si fourni, sinon la chaine par defaut."""
    boto3 = _boto3()
    return boto3.Session(profile_name=profile) if profile else boto3.Session()


# --------------------------------------------------------------------------- #
# init : deploiement CloudFormation
# --------------------------------------------------------------------------- #
def _stack_exists(cf, stack_name: str) -> bool:
    try:
        cf.describe_stacks(StackName=stack_name)
        return True
    except cf.exceptions.ClientError:
        return False


def _stack_outputs(cf, stack_name: str) -> dict:
    stacks = cf.describe_stacks(StackName=stack_name)["Stacks"]
    outs = stacks[0].get("Outputs", [])
    return {o["OutputKey"]: o["OutputValue"] for o in outs}


_TERMINAL_STATES = {
    "CREATE_COMPLETE", "UPDATE_COMPLETE", "ROLLBACK_COMPLETE",
    "CREATE_FAILED", "ROLLBACK_FAILED", "DELETE_COMPLETE", "DELETE_FAILED",
    "UPDATE_ROLLBACK_COMPLETE", "UPDATE_ROLLBACK_FAILED",
}


def _wait_stack(cf, stack_name: str, seen: set[str], progress=None) -> str:
    """Attend la fin de la stack en signalant chaque nouvel evenement via ``progress``."""
    while True:
        try:
            status = cf.describe_stacks(StackName=stack_name)["Stacks"][0]["StackStatus"]
        except cf.exceptions.ClientError:
            # Stack disparue : rollback + suppression apres un echec de creation (OnFailure=DELETE).
            if progress:
                progress("Stack supprimee suite a un echec de creation (voir la cause ci-dessus)")
            return "ROLLBACK_COMPLETE"
        try:
            events = cf.describe_stack_events(StackName=stack_name)["StackEvents"]
        except cf.exceptions.ClientError:
            events = []
        for ev in reversed(events):  # du plus ancien au plus recent
            if ev["EventId"] in seen:
                continue
            seen.add(ev["EventId"])
            if progress:
                reason = ev.get("ResourceStatusReason") or ""
                line = f"{ev.get('ResourceStatus', '')} · {ev.get('LogicalResourceId', '')}"
                progress(f"{line} — {reason}" if reason else line)
        if status in _TERMINAL_STATES:
            return status
        time.sleep(5)


def init_infrastructure(
    bucket_name: str,
    region: str,
    stack_name: str = DEFAULT_STACK,
    price_class: str = "PriceClass_100",
    save: bool = True,
    profile: str | None = None,
    progress=None,
    tags: dict | None = None,
) -> dict:
    """Cree/actualise la stack CloudFormation et renvoie ses outputs (execute AWS)."""
    cf = _session(profile).client("cloudformation", region_name=region)
    template = load_template()
    params = [
        {"ParameterKey": "BucketName", "ParameterValue": bucket_name},
        {"ParameterKey": "PriceClass", "ParameterValue": price_class},
    ]
    do_wait = True
    seen: set[str] = set()
    tag_list = [{"Key": k, "Value": v} for k, v in (tags or {}).items()]
    if _stack_exists(cf, stack_name):
        try:
            seen = {e["EventId"] for e in cf.describe_stack_events(StackName=stack_name)["StackEvents"]}
        except cf.exceptions.ClientError:
            pass
        try:
            cf.update_stack(StackName=stack_name, TemplateBody=template, Parameters=params, Tags=tag_list)
        except cf.exceptions.ClientError as exc:
            if "No updates are to be performed" in str(exc):
                do_wait = False
            else:
                raise
    else:
        cf.create_stack(
            StackName=stack_name,
            TemplateBody=template,
            Parameters=params,
            Tags=tag_list,
            OnFailure="DELETE",
        )

    if do_wait:
        status = _wait_stack(cf, stack_name, seen, progress)
        if status not in ("CREATE_COMPLETE", "UPDATE_COMPLETE"):
            raise RuntimeError(
                f"Provisionnement CloudFormation echoue (statut {status}). "
                "Cause affichee ci-dessus (souvent une permission IAM manquante)."
            )

    outputs = _stack_outputs(cf, stack_name)
    if save:
        conf = cfg.load_config()
        conf.region = region
        conf.bucket = outputs.get("BucketName")
        conf.distribution_id = outputs.get("DistributionId")
        conf.url = f"https://{outputs.get('DomainName')}"
        if profile:
            conf.profile = profile
        cfg.save_config(conf)
    return outputs


# --------------------------------------------------------------------------- #
# password : mise a jour du KeyValueStore
# --------------------------------------------------------------------------- #
def set_password(kvs_arn: str, password: str, user: str = DEFAULT_AUTH_USER, profile: str | None = None) -> None:
    """Ecrit base64("user:password") sous la cle 'auth' du KeyValueStore (execute AWS)."""
    kv = _session(profile).client("cloudfront-keyvaluestore")
    meta = kv.describe_key_value_store(KvsARN=kvs_arn)
    kv.put_key(
        KvsARN=kvs_arn,
        Key=AUTH_KEY,
        Value=basic_auth_value(user, password),
        IfMatch=meta["ETag"],
    )


# --------------------------------------------------------------------------- #
# provision + push : mise en ligne (miroir S3)
# --------------------------------------------------------------------------- #
_EXCLUDE = {".bookphoto.json", ".gitignore"}


def default_region(profile: str | None = None) -> str | None:
    """Region du profil / de la session boto3 (ou None si non configuree)."""
    return _session(profile).region_name


def account_id(profile: str | None = None) -> str:
    return _session(profile).client("sts").get_caller_identity()["Account"]


def provision_and_publish(region, profile=None, progress=None) -> dict:
    """Provisionne l'infra de ce site (dossier courant) puis le met en ligne (execute AWS).

    Stack et bucket DERIVES du slug du nom de la galerie (site.yaml). ``progress`` est
    appele avec une ligne texte a chaque evenement CloudFormation.
    """
    slug = slugify(cfg.load_site().name)
    stack = f"bookphoto-{slug}"
    bucket = f"bookphoto-{slug}-{account_id(profile)}"
    tags = {"Project": "bookphoto", "Gallery": slug, "ManagedBy": "bookphoto"}
    outputs = init_infrastructure(bucket, region, stack_name=stack, profile=profile,
                                  progress=progress, tags=tags)
    conf = cfg.load_config()
    conf.stack = stack
    conf.kvs_arn = outputs.get("KeyValueStoreArn")
    cfg.save_config(conf)
    push(cfg.load_config())
    return outputs


def _unchanged(path: Path, s3_size: int, s3_etag: str) -> bool:
    """Vrai si le fichier local est deja en ligne a l'identique (taille + empreinte)."""
    if path.stat().st_size != s3_size:
        return False
    etag = s3_etag.strip('"')
    if "-" in etag:  # upload multipart : pas de MD5 simple -> taille identique suffit (photos)
        return True
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest() == etag


def push(conf: cfg.AppConfig, user: str = DEFAULT_AUTH_USER, progress=None) -> dict:
    """Genere le site puis le synchronise sur S3 (execute AWS).

    INCREMENTAL : n'envoie que les fichiers nouveaux ou modifies (compare taille + ETag
    a l'inventaire du bucket), supprime les obsoletes, met le mot de passe dans le KVS,
    invalide CloudFront. ``progress`` recoit une ligne texte a chaque etape.
    """
    from .generator import write_site

    def _say(m):
        if progress:
            progress(m)

    root = Path.cwd()
    _say("Generation du site (index.html + data.json)...")
    write_site()
    sess = _session(conf.profile)
    s3 = sess.client("s3", region_name=conf.region)

    _say("Inventaire du bucket...")
    inventory: dict[str, tuple[int, str]] = {}
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=conf.bucket):
        for o in page.get("Contents", []):
            inventory[o["Key"]] = (o["Size"], o["ETag"])

    files = [
        p for p in sorted(root.rglob("*"))
        if p.is_file()
        and p.relative_to(root).parts[0] not in _EXCLUDE
        and p.relative_to(root).name not in _EXCLUDE
    ]
    total = len(files)
    _say(f"Synchronisation de {total} fichier(s) vers S3 (bucket {conf.bucket})...")
    local: set[str] = set()
    uploaded = 0
    skipped = 0
    for p in files:
        rel = p.relative_to(root)
        key = str(rel).replace("\\", "/")
        local.add(key)
        cur = inventory.get(key)
        if cur and _unchanged(p, cur[0], cur[1]):
            skipped += 1
            continue
        s3.upload_file(
            str(p), conf.bucket, key,
            ExtraArgs={"ContentType": content_type(p), "CacheControl": cache_control(key)},
        )
        uploaded += 1
        if uploaded == 1 or uploaded % 20 == 0:
            _say(f"  envoye {uploaded}...")
    _say(f"{uploaded} envoye(s), {skipped} inchange(s) ignore(s).")

    stale = [k for k in inventory if k not in local]
    if stale:
        _say(f"Suppression de {len(stale)} fichier(s) obsolete(s)...")
    for i in range(0, len(stale), 1000):
        s3.delete_objects(
            Bucket=conf.bucket, Delete={"Objects": [{"Key": k} for k in stale[i : i + 1000]]}
        )

    if conf.password and conf.kvs_arn:
        _say("Mise a jour du mot de passe (KeyValueStore)...")
        set_password(conf.kvs_arn, conf.password, user=user, profile=conf.profile)

    _say("Invalidation du cache CloudFront...")
    sess.client("cloudfront").create_invalidation(
        DistributionId=conf.distribution_id,
        InvalidationBatch={
            "Paths": {"Quantity": 1, "Items": ["/*"]},
            "CallerReference": str(time.time()),
        },
    )
    _say("Termine.")
    return {"uploaded": uploaded, "skipped": skipped, "deleted": len(stale)}


# --------------------------------------------------------------------------- #
# pull : cloner le site depuis S3
# --------------------------------------------------------------------------- #
def pull(name: str, region: str | None = None, profile: str | None = None,
         user: str = DEFAULT_AUTH_USER) -> int:
    """Clone la galerie ``name`` depuis AWS dans le DOSSIER COURANT.

    Source de verite : la stack ``bookphoto-<slug(nom de la galerie)>``. Le nom du
    dossier local n'a aucune importance. Reconstruit ``.bookphoto.json`` depuis les
    outputs de la stack et restaure le mot de passe depuis le KVS.
    """
    dest = Path.cwd()
    region = region or default_region(profile)
    stack = f"bookphoto-{slugify(name)}"
    sess = _session(profile)
    outputs = _stack_outputs(sess.client("cloudformation", region_name=region), stack)
    bucket = outputs["BucketName"]

    s3 = sess.client("s3", region_name=region)
    n = 0
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            target = dest / obj["Key"]
            target.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(bucket, obj["Key"], str(target))
            n += 1

    conf = cfg.AppConfig(
        region=region, bucket=bucket, profile=profile, stack=stack,
        distribution_id=outputs.get("DistributionId"),
        url=f"https://{outputs.get('DomainName')}",
        kvs_arn=outputs.get("KeyValueStoreArn"),
    )
    if conf.kvs_arn:
        try:
            value = sess.client("cloudfront-keyvaluestore").get_key(
                KvsARN=conf.kvs_arn, Key=AUTH_KEY
            )["Value"]
            decoded = base64.b64decode(value).decode()
            conf.password = decoded.split(":", 1)[1] if ":" in decoded else None
        except Exception:  # noqa: BLE001 - le clone ne doit pas casser si le KVS est illisible
            pass

    cfg.save_config(conf, dest)
    return n


def destroy(conf: cfg.AppConfig, progress=None) -> None:
    """Vide le bucket puis supprime la stack CloudFormation (execute AWS, IRREVERSIBLE)."""
    sess = _session(conf.profile)

    if conf.bucket:
        s3 = sess.client("s3", region_name=conf.region)
        try:
            keys = [
                {"Key": o["Key"]}
                for page in s3.get_paginator("list_objects_v2").paginate(Bucket=conf.bucket)
                for o in page.get("Contents", [])
            ]
            for i in range(0, len(keys), 1000):
                s3.delete_objects(Bucket=conf.bucket, Delete={"Objects": keys[i : i + 1000]})
            if progress and keys:
                progress(f"bucket vide ({len(keys)} objet(s))")
        except Exception:  # noqa: BLE001 - bucket peut-etre deja absent
            pass

    cf = sess.client("cloudformation", region_name=conf.region)
    stack = conf.stack
    try:
        seen = {e["EventId"] for e in cf.describe_stack_events(StackName=stack)["StackEvents"]}
    except Exception:  # noqa: BLE001
        seen = set()
    cf.delete_stack(StackName=stack)

    while True:
        try:
            status = cf.describe_stacks(StackName=stack)["Stacks"][0]["StackStatus"]
        except cf.exceptions.ClientError:
            if progress:
                progress("DELETE_COMPLETE · stack supprimee")
            break
        try:
            for ev in reversed(cf.describe_stack_events(StackName=stack)["StackEvents"]):
                if ev["EventId"] in seen:
                    continue
                seen.add(ev["EventId"])
                if progress:
                    progress(f"{ev.get('ResourceStatus', '')} · {ev.get('LogicalResourceId', '')}")
        except cf.exceptions.ClientError:
            pass
        if status == "DELETE_FAILED":
            raise RuntimeError(f"Suppression de la stack '{stack}' echouee : {status}")
        time.sleep(5)

    conf.bucket = conf.distribution_id = conf.url = conf.kvs_arn = conf.stack = None
    cfg.save_config(conf)


# --------------------------------------------------------------------------- #
# doctor : diagnostics
# --------------------------------------------------------------------------- #
def doctor(conf: cfg.AppConfig) -> list[tuple[str, bool, str]]:
    """Verifications de sante (execute AWS en lecture seule)."""
    sess = _session(conf.profile)
    checks: list[tuple[str, bool, str]] = []

    try:
        ident = sess.client("sts").get_caller_identity()
        checks.append(("Identifiants AWS", True, ident["Arn"]))
    except Exception as exc:  # noqa: BLE001
        checks.append(("Identifiants AWS", False, str(exc)))
        return checks

    checks.append(
        (
            "Infra provisionnee",
            conf.is_provisioned,
            f"bucket={conf.bucket} distribution={conf.distribution_id}",
        )
    )

    if conf.bucket:
        try:
            s3 = sess.client("s3", region_name=conf.region)
            s3.head_bucket(Bucket=conf.bucket)
            pab = s3.get_public_access_block(Bucket=conf.bucket)[
                "PublicAccessBlockConfiguration"
            ]
            checks.append(("Bucket prive", all(pab.values()), str(pab)))
        except Exception as exc:  # noqa: BLE001
            checks.append(("Bucket", False, str(exc)))

    if conf.distribution_id:
        try:
            dist = sess.client("cloudfront").get_distribution(Id=conf.distribution_id)[
                "Distribution"
            ]
            checks.append(("Distribution deployee", dist["Status"] == "Deployed", dist["Status"]))
        except Exception as exc:  # noqa: BLE001
            checks.append(("Distribution", False, str(exc)))

    return checks
