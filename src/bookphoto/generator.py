"""Generation des artefacts du site.

Le site est une **SPA** : un shell fixe ``index.html`` (le design) qui charge
``data.json`` au runtime. Ce module produit ces deux fichiers dans le dossier du
site ; ``push`` les envoie ensuite sur S3 avec le reste (images, sources).

``data.json`` = ``{ "config": { site, albums }, "seed": [[file, w, h], ...] }``.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from PIL import Image

from . import albums as al
from . import config as cfg

TEMPLATE = Path(__file__).parent / "templates" / "gallery.html"

_MOIS = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


@dataclass
class BuildResult:
    albums: int = 0
    photos: int = 0
    warnings: list[str] = field(default_factory=list)


def _fr_date(value) -> str:
    """ISO (``2024-06-12``) -> ``12 juin 2024``. Sinon renvoie la valeur telle quelle."""
    if not value:
        return ""
    s = str(value)
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        try:
            dt = datetime.strptime(s[:10], "%Y-%m-%d")
        except ValueError:
            return s
    return f"{dt.day} {_MOIS[dt.month - 1]} {dt.year}"


def _dims(path: Path) -> tuple[int, int]:
    try:
        with Image.open(path) as im:
            return im.width, im.height
    except Exception:  # noqa: BLE001 - une image illisible ne casse pas le build
        return 3, 2


def _jpg(fname: str) -> str:
    """Nom du derive (toujours .jpg)."""
    return Path(fname).stem + ".jpg"


def build_data() -> tuple[dict, BuildResult]:
    """Construit le payload data.json a partir de site.yaml + albums + derives (cwd)."""
    site = cfg.load_site()
    res = BuildResult()
    seed: list[list] = []
    albums_cfg: list[dict] = []

    for slug in al.list_local_albums():
        data = al.load_album(slug)
        adir = al.album_dir(slug)
        photos: list[dict] = []
        for entry in (data.get("photos") or []):
            fname = entry.get("file")
            if not fname:
                continue
            stem = _jpg(fname)
            display = adir / "display" / stem
            if not display.exists():
                res.warnings.append(f"[{slug}] dérivé manquant pour {fname} (relance 'gallery add')")
                continue
            file_rel = f"{slug}/display/{stem}"
            thumb_rel = f"{slug}/thumbs/{stem}" if (adir / "thumbs" / stem).exists() else file_rel
            w, h = _dims(display)
            seed.append([file_rel, w, h])
            photos.append({
                "file": file_rel,
                "thumb": thumb_rel,
                "date": _fr_date(entry.get("date")),
                "caption": entry.get("caption") or "",
            })
        if not photos:
            res.warnings.append(f"[{slug}] album sans photo exploitable — ignoré")
            continue

        cover = photos[0]["file"]
        cover_name = data.get("cover")
        if cover_name:
            want = f"{slug}/display/{_jpg(cover_name)}"
            if any(p["file"] == want for p in photos):
                cover = want
        albums_cfg.append({
            "id": slug,
            "title": data.get("title") or slug,
            "description": data.get("description") or "",
            "cover": cover,
            "header": bool(data.get("header", True)),
            "photos": photos,
        })
        res.albums += 1
        res.photos += len(photos)

    year = datetime.now().year
    config = {
        "site": {
            "name": site.name,
            "tagline": site.tagline or "",
            "avatar": site.avatar or "",
            "cover": site.cover or "",
            "copyright": site.copyright or f"© {year} {site.name}",
        },
        "albums": albums_cfg,
    }
    return {"config": config, "seed": seed}, res


def write_site() -> BuildResult:
    """Ecrit index.html (shell) + data.json dans le dossier courant."""
    root = Path.cwd()
    payload, res = build_data()
    shutil.copyfile(TEMPLATE, root / "index.html")
    (root / "data.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return res
