import json

from PIL import Image

from bookphoto import albums as al
from bookphoto import config as cfg
from bookphoto.derivatives import generate_derivatives
from bookphoto.generator import _fr_date, build_data, write_site


def _jpg(path, size=(120, 80), color="red"):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


def test_fr_date():
    assert _fr_date("2024-06-12") == "12 juin 2024"
    assert _fr_date("2024-06-12T10:30:00") == "12 juin 2024"
    assert _fr_date(None) == ""
    assert _fr_date("deja formate") == "deja formate"


def _prepare(tmp_path):
    cfg.save_site(cfg.SiteConfig(name="Studio Seb", tagline="Portraits",
                                 cover="assets/cover.jpg", avatar="assets/avatar.jpg"))
    slug = al.new_album("Rue de nuit")
    src = tmp_path / "_src"
    src.mkdir()
    al.add_photos(slug, [_jpg(src / "a.jpg", (160, 90)), _jpg(src / "b.jpg", (90, 160))])
    generate_derivatives(al.album_dir(slug))
    return slug


def test_build_data(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    slug = _prepare(tmp_path)
    payload, res = build_data()
    assert res.albums == 1
    assert res.photos == 2
    assert payload["config"]["site"]["name"] == "Studio Seb"
    alb = payload["config"]["albums"][0]
    assert alb["id"] == slug
    assert alb["photos"][0]["thumb"].startswith(f"{slug}/thumbs/")
    assert alb["photos"][0]["file"].startswith(f"{slug}/display/")
    assert alb["cover"].startswith(f"{slug}/display/")
    assert len(payload["seed"]) == 2


def test_write_site(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    slug = _prepare(tmp_path)
    write_site()
    idx = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "fetch('data.json'" in idx
    assert "buildAlbum" not in idx
    assert "let CONFIG = { site: {}, albums: [] };" in idx
    data = json.loads((tmp_path / "data.json").read_text(encoding="utf-8"))
    assert data["config"]["albums"][0]["id"] == slug
    assert data["config"]["site"]["name"] == "Studio Seb"
