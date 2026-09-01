from bookphoto import config as cfg


def test_appconfig_roundtrip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg.save_config(cfg.AppConfig(
        region="eu-west-3", bucket="bookphoto-galerie-abc",
        distribution_id="E123ABC", url="https://d123.cloudfront.net", profile="bookphoto",
    ))
    assert cfg.config_path().exists()
    loaded = cfg.load_config()
    assert loaded.bucket == "bookphoto-galerie-abc"
    assert loaded.region == "eu-west-3"
    assert loaded.distribution_id == "E123ABC"
    assert loaded.profile == "bookphoto"
    assert loaded.is_provisioned is True


def test_appconfig_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    conf = cfg.load_config()
    assert conf.bucket is None
    assert conf.password is None
    assert conf.is_provisioned is False


def test_site_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    site = cfg.load_site()
    assert site.name == cfg.DEFAULT_SITE_NAME
    assert site.cover is None
    assert site.avatar is None


def test_site_parse(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "site.yaml").write_text(
        "name: Studio Seb\ntagline: Portraits\ncover: assets/cover.jpg\navatar: assets/avatar.jpg\n",
        encoding="utf-8",
    )
    site = cfg.load_site()
    assert site.name == "Studio Seb"
    assert site.tagline == "Portraits"
    assert site.cover == "assets/cover.jpg"
    assert site.avatar == "assets/avatar.jpg"


def test_save_and_load_site(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert not cfg.site_exists()
    cfg.save_site(cfg.SiteConfig(name="Studio Seb", cover="assets/c.jpg"))
    assert cfg.site_exists()
    site = cfg.load_site()
    assert site.name == "Studio Seb"
    assert site.cover == "assets/c.jpg"


def test_two_sites_are_independent(tmp_path, monkeypatch):
    a, b = tmp_path / "siteA", tmp_path / "siteB"
    a.mkdir(); b.mkdir()
    monkeypatch.chdir(a); cfg.save_config(cfg.AppConfig(bucket="bucket-a"))
    monkeypatch.chdir(b); cfg.save_config(cfg.AppConfig(bucket="bucket-b"))
    monkeypatch.chdir(a); assert cfg.load_config().bucket == "bucket-a"
    monkeypatch.chdir(b); assert cfg.load_config().bucket == "bucket-b"
