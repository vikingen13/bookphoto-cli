"""Extraction de la date de prise de vue depuis les metadonnees EXIF."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from PIL import Image

# Tags EXIF pertinents pour la date de prise de vue.
_EXIF_IFD = 0x8769  # sous-IFD Exif
_TAG_DATETIME_ORIGINAL = 36867  # DateTimeOriginal (sous-IFD)
_TAG_DATETIME_DIGITIZED = 36868  # DateTimeDigitized (sous-IFD)
_TAG_DATETIME = 306  # DateTime (IFD de base)

_FORMATS = (
    "%Y:%m:%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y:%m:%d",
    "%Y-%m-%d",
)


def parse_exif_datetime(value: str | None) -> date | None:
    """Convertit une chaine EXIF (ex. '2026:06:14 10:30:00') en date."""
    if not value:
        return None
    value = str(value).strip().strip("\x00")
    if not value:
        return None
    for fmt in _FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def extract_date_taken(path: Path | str) -> date | None:
    """Retourne la date de prise de vue si presente dans l'EXIF, sinon None."""
    try:
        with Image.open(path) as im:
            exif = im.getexif()
    except Exception:
        return None
    if not exif:
        return None

    # 1) sous-IFD Exif : DateTimeOriginal / DateTimeDigitized (le plus fiable)
    try:
        sub = exif.get_ifd(_EXIF_IFD)
    except Exception:
        sub = {}
    for tag in (_TAG_DATETIME_ORIGINAL, _TAG_DATETIME_DIGITIZED):
        parsed = parse_exif_datetime(sub.get(tag))
        if parsed:
            return parsed

    # 2) repli : DateTime de l'IFD de base
    return parse_exif_datetime(exif.get(_TAG_DATETIME))
