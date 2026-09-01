"""Albums locaux (Modele A : les photos sont copiees dans l'album).

Un album = un sous-dossier du **repertoire courant** (le site) :

    <slug>/
        album.yaml     # metadonnees (commentaires preserves)
        photos/        # originaux copies
        thumbs/        # miniatures (cf. derivatives.py)
        display/       # versions d'affichage web
"""

from __future__ import annotations

import re
import shutil
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from ruamel.yaml import YAML

from .exif import extract_date_taken

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".gif", ".heic", ".heif"}


def _yaml() -> YAML:
    y = YAML()  # round-trip : preserve commentaires et mise en forme
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-") or "album"


def album_dir(slug: str) -> Path:
    return Path.cwd() / slug


def album_yaml_path(slug: str) -> Path:
    return album_dir(slug) / "album.yaml"


def album_exists(slug: str) -> bool:
    return album_yaml_path(slug).exists()


def new_album(title: str, slug: str | None = None) -> str:
    """Cree un album (dossier + photos/ + album.yaml). Retourne le slug."""
    slug = slug or slugify(title)
    if album_exists(slug):
        raise FileExistsError(f"L'album '{slug}' existe deja.")
    (album_dir(slug) / "photos").mkdir(parents=True, exist_ok=True)
    write_album(slug, {"title": title, "description": "", "cover": None, "header": True, "photos": []})
    return slug


def load_album(slug: str):
    path = album_yaml_path(slug)
    if not path.exists():
        raise FileNotFoundError(f"Album introuvable : '{slug}'.")
    with path.open("r", encoding="utf-8") as f:
        return _yaml().load(f)


def write_album(slug: str, data) -> Path:
    path = album_yaml_path(slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        _yaml().dump(data, f)
    return path


@dataclass
class AddResult:
    added: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    dated: int = 0


def _expand_sources(sources):
    """Developpe les dossiers en fichiers images (recursif). Les fichiers passent tels quels."""
    files = []
    for s in sources:
        s = Path(s)
        if s.is_dir():
            files.extend(sorted(p for p in s.rglob("*") if p.is_file() and p.suffix.lower() in PHOTO_EXTS))
        else:
            files.append(s)
    return files


def add_photos(slug: str, sources) -> AddResult:
    """Copie des photos dans l'album, lit la date EXIF, met a jour album.yaml (dedup par nom).

    Chaque source peut etre un fichier ou un dossier (toutes ses images sont prises).
    """
    if not album_exists(slug):
        raise FileNotFoundError(f"Album introuvable : '{slug}'.")
    data = load_album(slug)
    if data.get("photos") is None:
        data["photos"] = []
    photos = data["photos"]
    existing = {entry.get("file") for entry in photos}

    dest_dir = album_dir(slug) / "photos"
    dest_dir.mkdir(parents=True, exist_ok=True)

    result = AddResult()
    for src in _expand_sources(sources):
        src = Path(src)
        if src.suffix.lower() not in PHOTO_EXTS or not src.is_file():
            result.skipped.append(src.name)
            continue
        if src.name in existing:
            result.skipped.append(src.name)
            continue
        dest = dest_dir / src.name
        shutil.copy2(src, dest)
        taken = extract_date_taken(dest)
        photos.append({"file": src.name, "date": taken.isoformat() if taken else None, "caption": ""})
        existing.add(src.name)
        result.added.append(src.name)
        if taken:
            result.dated += 1

    write_album(slug, data)
    return result


def list_local_albums() -> list[str]:
    """Liste les slugs des albums du repertoire courant."""
    return [p.name for p in sorted(Path.cwd().iterdir()) if p.is_dir() and (p / "album.yaml").exists()]


def remove_album(slug: str) -> None:
    d = album_dir(slug)
    if not d.exists():
        raise FileNotFoundError(f"Album introuvable : '{slug}'.")
    shutil.rmtree(d)


def remove_photos(slug: str, names) -> list[str]:
    """Supprime des photos : entree album.yaml + original + derives. Retourne les supprimees."""
    if not album_exists(slug):
        raise FileNotFoundError(f"Album introuvable : '{slug}'.")
    data = load_album(slug)
    wanted = set(names)
    adir = album_dir(slug)
    removed: list[str] = []
    kept = []
    for entry in (data.get("photos") or []):
        f = entry.get("file")
        if f in wanted:
            stem = Path(f).stem + ".jpg"
            for sub, fn in (("photos", f), ("thumbs", stem), ("display", stem)):
                fp = adir / sub / fn
                if fp.exists():
                    fp.unlink()
            removed.append(f)
        else:
            kept.append(entry)
    data["photos"] = kept
    write_album(slug, data)
    return removed


def resolve_cover(slug: str, value: str | None) -> str | None:
    """Resout une couverture d'album depuis un nom de fichier OU un index (1-based).

    - vide -> None (=> 1re photo au rendu) ;
    - chemin interdit : on ne garde que le nom de fichier ;
    - doit correspondre a une photo de l'album, sinon ValueError.
    """
    value = (value or "").strip()
    if not value:
        return None
    files = [e.get("file") for e in (load_album(slug).get("photos") or [])]
    if not files:
        raise ValueError(f"L'album '{slug}' n'a aucune photo : impossible de definir une couverture.")
    if value.isdigit():
        idx = int(value)
        if not (1 <= idx <= len(files)):
            raise ValueError(f"Index {idx} hors limites (1..{len(files)}).")
        return files[idx - 1]
    name = Path(value).name  # jamais de chemin : la cover est forcement une image de l'album
    if name in files:
        return name
    stem = Path(name).stem.lower()
    for f in files:
        if Path(f).stem.lower() == stem:
            return f
    raise ValueError(
        f"'{value}' n'est pas une photo de '{slug}'. Photos : {', '.join(files)}"
    )
