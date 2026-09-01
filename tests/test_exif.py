from datetime import date

from PIL import Image

from bookphoto.exif import extract_date_taken, parse_exif_datetime


def test_parse_exif_datetime():
    assert parse_exif_datetime("2026:06:14 10:30:00") == date(2026, 6, 14)
    assert parse_exif_datetime("2026-06-14") == date(2026, 6, 14)
    assert parse_exif_datetime("") is None
    assert parse_exif_datetime(None) is None
    assert parse_exif_datetime("pas une date") is None


def test_extract_no_exif(tmp_path):
    p = tmp_path / "sans_exif.jpg"
    Image.new("RGB", (10, 10)).save(p)
    assert extract_date_taken(p) is None


def test_extract_with_datetime(tmp_path):
    p = tmp_path / "avec_date.jpg"
    im = Image.new("RGB", (10, 10))
    exif = im.getexif()
    exif[306] = "2026:06:14 10:30:00"  # DateTime (IFD de base)
    im.save(p, exif=exif)
    assert extract_date_taken(p) == date(2026, 6, 14)


def test_extract_on_missing_file(tmp_path):
    assert extract_date_taken(tmp_path / "nexiste_pas.jpg") is None
