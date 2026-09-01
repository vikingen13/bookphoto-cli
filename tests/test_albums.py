import pytest
from PIL import Image

from bookphoto import albums as al


def _make_jpg(path, color="red", size=(16, 16)):
    Image.new("RGB", size, color).save(path)
    return path


def test_slugify():
    assert al.slugify("Shooting Julie - juin 2026") == "shooting-julie-juin-2026"
    assert al.slugify("Été à Paris !") == "ete-a-paris"
    assert al.slugify("???") == "album"


def test_new_album(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    slug = al.new_album("Shooting Julie")
    assert slug == "shooting-julie"
    assert al.album_yaml_path(slug).exists()
    assert (tmp_path / slug / "photos").is_dir()
    data = al.load_album(slug)
    assert data["title"] == "Shooting Julie"
    assert data["cover"] is None
    assert list(data["photos"]) == []


def test_new_album_duplicate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    al.new_album("Test")
    with pytest.raises(FileExistsError):
        al.new_album("Test")


def test_add_photos_copies_reads_and_dedups(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    slug = al.new_album("Album")
    src = tmp_path / "src"
    src.mkdir()
    p1 = _make_jpg(src / "a.jpg", "red")
    p2 = _make_jpg(src / "b.jpg", "blue")
    note = src / "notes.txt"
    note.write_text("pas une image", encoding="utf-8")

    result = al.add_photos(slug, [p1, p2, note])
    assert set(result.added) == {"a.jpg", "b.jpg"}
    assert "notes.txt" in result.skipped
    assert (tmp_path / slug / "photos" / "a.jpg").exists()
    assert p1.exists()  # original non deplace

    result2 = al.add_photos(slug, [p1])
    assert result2.added == []
    assert "a.jpg" in result2.skipped
    assert len(al.load_album(slug)["photos"]) == 2


def test_add_photos_preserves_yaml_comments(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    slug = al.new_album("Album")
    yp = al.album_yaml_path(slug)
    yp.write_text("# Mon commentaire perso\n" + yp.read_text(encoding="utf-8"), encoding="utf-8")
    al.add_photos(slug, [_make_jpg(tmp_path / "x.jpg")])
    assert "# Mon commentaire perso" in yp.read_text(encoding="utf-8")


def test_list_local_albums(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert al.list_local_albums() == []
    al.new_album("Un")
    al.new_album("Deux")
    assert al.list_local_albums() == ["deux", "un"]


def test_add_photos_missing_album(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError):
        al.add_photos("inexistant", [])


def test_add_photos_accepts_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    slug = al.new_album("Album")
    folder = tmp_path / "src"
    folder.mkdir()
    _make_jpg(folder / "a.jpg")
    _make_jpg(folder / "b.jpg")
    (folder / "notes.txt").write_text("x", encoding="utf-8")
    result = al.add_photos(slug, [folder])
    assert set(result.added) == {"a.jpg", "b.jpg"}
    assert len(al.load_album(slug)["photos"]) == 2


def test_resolve_cover(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    slug = al.new_album("Album")
    folder = tmp_path / "src"
    folder.mkdir()
    _make_jpg(folder / "a.jpg")
    _make_jpg(folder / "b.jpg")
    al.add_photos(slug, [folder])
    files = [e["file"] for e in al.load_album(slug)["photos"]]
    assert al.resolve_cover(slug, "") is None            # vide -> 1re photo
    assert al.resolve_cover(slug, "2") == files[1]        # index 1-based
    assert al.resolve_cover(slug, "a.jpg") == "a.jpg"     # nom exact
    assert al.resolve_cover(slug, "/x/y/b.jpg") == "b.jpg"  # chemin ignore
    assert al.resolve_cover(slug, "a") == "a.jpg"         # extension ignoree
    with pytest.raises(ValueError):
        al.resolve_cover(slug, "9")                       # index hors limites
    with pytest.raises(ValueError):
        al.resolve_cover(slug, "zzz.jpg")                 # pas dans l'album


def test_remove_photos_and_album(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    slug = al.new_album("Album")
    src = tmp_path / "s"
    src.mkdir()
    al.add_photos(slug, [_make_jpg(src / "a.jpg"), _make_jpg(src / "b.jpg")])
    removed = al.remove_photos(slug, ["a.jpg"])
    assert removed == ["a.jpg"]
    assert not (tmp_path / slug / "photos" / "a.jpg").exists()
    assert (tmp_path / slug / "photos" / "b.jpg").exists()
    assert len(al.load_album(slug)["photos"]) == 1

    al.remove_album(slug)
    assert not (tmp_path / slug).exists()


def test_new_album_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    slug = al.new_album("X")
    d = al.load_album(slug)
    assert d["header"] is True
    assert d["cover"] is None


def test_import_keep_names(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from typer.testing import CliRunner
    from bookphoto import config as cfg
    from bookphoto.cli import app

    cfg.save_site(cfg.SiteConfig(name="S", tagline="", cover=None, avatar=None, copyright=""))
    src = tmp_path / "src"
    (src / "Alpha").mkdir(parents=True)
    (src / "Beta").mkdir(parents=True)
    (src / "Empty").mkdir(parents=True)
    _make_jpg(src / "Alpha" / "1.jpg")
    _make_jpg(src / "Beta" / "1.jpg")

    result = CliRunner().invoke(app, ["import", str(src), "--keep-names"])
    assert result.exit_code == 0, result.output
    slugs = set(al.list_local_albums())
    assert {"alpha", "beta"} <= slugs
    assert "empty" not in slugs
    assert len(al.load_album("alpha")["photos"]) == 1


def test_headers_global(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from typer.testing import CliRunner
    from bookphoto import config as cfg
    from bookphoto.cli import app

    cfg.save_site(cfg.SiteConfig(name="S", tagline="", cover=None, avatar=None, copyright=""))
    al.new_album("A")

    runner = CliRunner()
    assert runner.invoke(app, ["headers", "off"]).exit_code == 0
    assert cfg.load_site().header_override is False
    assert runner.invoke(app, ["headers", "on"]).exit_code == 0
    assert cfg.load_site().header_override is True
    assert runner.invoke(app, ["headers", "auto"]).exit_code == 0
    assert cfg.load_site().header_override is None
    # non destructif : le header de l'album n'est pas touche
    assert al.load_album("A")["header"] is True
    # valeur invalide -> erreur
    assert runner.invoke(app, ["headers", "bidon"]).exit_code == 1
