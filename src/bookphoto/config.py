"""Configuration de bookphoto — **un site = le dossier courant**.

Toutes les fonctions operent sur le repertoire courant : aucun chemin en argument.
Plusieurs sites = plusieurs dossiers ; on fait ``cd`` dans celui qu'on gere.

- ``site.yaml``       : branding (nom, slogan, cover, avatar, copyright).
- ``.bookphoto.json`` : config machine (region, bucket, distribution, url, profil,
  mot de passe, stack, kvs), ecrite par ``gallery init``.
"""

from __future__ import annotations

import io
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ruamel.yaml import YAML

DEFAULT_SITE_NAME = "Ma galerie"
CONFIG_FILENAME = ".bookphoto.json"
SITE_FILENAME = "site.yaml"


def config_path() -> Path:
    return Path.cwd() / CONFIG_FILENAME


def site_file() -> Path:
    return Path.cwd() / SITE_FILENAME


def site_exists() -> bool:
    return site_file().exists()


# --------------------------------------------------------------------------- #
# Config machine (.bookphoto.json)
# --------------------------------------------------------------------------- #
@dataclass
class AppConfig:
    region: str | None = None
    bucket: str | None = None
    distribution_id: str | None = None
    url: str | None = None
    profile: str | None = None
    password: str | None = None
    stack: str | None = None
    kvs_arn: str | None = None
    domain: str | None = None
    certificate_arn: str | None = None

    @property
    def is_provisioned(self) -> bool:
        return bool(self.bucket and self.distribution_id)


def load_config() -> AppConfig:
    path = config_path()
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return AppConfig(
        region=data.get("region"),
        bucket=data.get("bucket"),
        distribution_id=data.get("distribution_id"),
        url=data.get("url"),
        profile=data.get("profile"),
        password=data.get("password"),
        stack=data.get("stack"),
        kvs_arn=data.get("kvs_arn"),
        domain=data.get("domain"),
        certificate_arn=data.get("certificate_arn"),
    )


def save_config(cfg: AppConfig) -> Path:
    path = config_path()
    path.write_text(json.dumps(asdict(cfg), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# Branding (site.yaml)
# --------------------------------------------------------------------------- #
@dataclass
class SiteConfig:
    name: str = DEFAULT_SITE_NAME
    tagline: str | None = None
    cover: str | None = None
    avatar: str | None = None
    copyright: str | None = None
    header_override: bool | None = None  # None=auto (par album), True=on, False=off (override global)


def load_site() -> SiteConfig:
    path = site_file()
    if not path.exists():
        return SiteConfig()
    data = YAML(typ="safe").load(path.read_text(encoding="utf-8")) or {}
    return SiteConfig(
        name=data.get("name") or DEFAULT_SITE_NAME,
        tagline=data.get("tagline"),
        cover=data.get("cover"),
        avatar=data.get("avatar"),
        copyright=data.get("copyright"),
        header_override=data.get("header_override"),
    )


def save_site(site: SiteConfig) -> Path:
    data = {
        "name": site.name,
        "tagline": site.tagline or "",
        "cover": site.cover or "",
        "avatar": site.avatar or "",
        "copyright": site.copyright or "",
    }
    if site.header_override is not None:
        data["header_override"] = site.header_override
    buf = io.StringIO()
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.dump(data, buf)
    path = site_file()
    path.write_text("# Branding du site (gere par 'gallery config')\n" + buf.getvalue(), encoding="utf-8")
    return path
