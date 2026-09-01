"""Generation des derives d'images (miniatures + versions d'affichage) via Pillow.

- Autorotation selon l'orientation EXIF (ImageOps.exif_transpose).
- Redimensionnement en preservant le ratio (thumbnail).
- Idempotent : un derive n'est regenere que si l'original est plus recent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageOps

THUMB_MAX = 400  # cote max des miniatures (grille)
DISPLAY_MAX = 2048  # cote max des versions d'affichage (lightbox)
JPEG_QUALITY = 85


@dataclass
class DerivativeResult:
    generated: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _needs_update(src: Path, dst: Path) -> bool:
    return (not dst.exists()) or (src.stat().st_mtime > dst.stat().st_mtime)


def _render(src: Path, dst: Path, max_side: int, quality: int) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)  # respecte l'orientation EXIF
        im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        im.convert("RGB").save(dst, format="JPEG", quality=quality, optimize=True)


def generate_derivatives(
    album_path: Path | str,
    thumb_max: int = THUMB_MAX,
    display_max: int = DISPLAY_MAX,
    quality: int = JPEG_QUALITY,
) -> DerivativeResult:
    """Genere thumbs/ et display/ pour chaque photo de l'album. Idempotent."""
    album_path = Path(album_path)
    photos_dir = album_path / "photos"
    thumbs_dir = album_path / "thumbs"
    display_dir = album_path / "display"

    result = DerivativeResult()
    if not photos_dir.exists():
        return result

    for src in sorted(photos_dir.iterdir()):
        if not src.is_file():
            continue
        thumb = thumbs_dir / f"{src.stem}.jpg"
        display = display_dir / f"{src.stem}.jpg"

        did_work = False
        if _needs_update(src, thumb):
            _render(src, thumb, thumb_max, quality)
            did_work = True
        if _needs_update(src, display):
            _render(src, display, display_max, quality)
            did_work = True

        (result.generated if did_work else result.skipped).append(src.name)

    return result
