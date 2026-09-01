from PIL import Image

from bookphoto import albums as al
from bookphoto.derivatives import generate_derivatives


def _album_with_photo(tmp_path, size=(3000, 2000)):
    slug = al.new_album("Album")
    src = tmp_path / "big.jpg"
    Image.new("RGB", size, "green").save(src)
    al.add_photos(slug, [src])
    return al.album_dir(slug)


def test_generate_derivatives_dimensions(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    album_path = _album_with_photo(tmp_path)
    result = generate_derivatives(album_path, thumb_max=400, display_max=2048)

    assert "big.jpg" in result.generated
    thumb = album_path / "thumbs" / "big.jpg"
    display = album_path / "display" / "big.jpg"
    assert thumb.exists() and display.exists()

    with Image.open(thumb) as im:
        assert max(im.size) <= 400
    with Image.open(display) as im:
        assert max(im.size) <= 2048


def test_generate_derivatives_idempotent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    album_path = _album_with_photo(tmp_path)
    first = generate_derivatives(album_path)
    assert "big.jpg" in first.generated

    second = generate_derivatives(album_path)
    assert second.generated == []
    assert "big.jpg" in second.skipped


def test_generate_derivatives_no_photos(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    slug = al.new_album("Vide")
    result = generate_derivatives(al.album_dir(slug))
    assert result.generated == []
    assert result.skipped == []
