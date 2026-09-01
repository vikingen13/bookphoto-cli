import base64
import json

import typer

from bookphoto import awsops
from bookphoto.cli import app


def test_basic_auth_value_roundtrip():
    v = awsops.basic_auth_value("book", "s3cret")
    assert base64.b64decode(v).decode() == "book:s3cret"


def test_content_type():
    assert awsops.content_type("index.html") == "text/html"
    assert awsops.content_type("rue/display/a.jpg") == "image/jpeg"
    assert awsops.content_type("nope.zzq") == "application/octet-stream"


def test_cache_control():
    assert awsops.cache_control("index.html") == "no-cache"
    assert "immutable" in awsops.cache_control("rue/thumbs/a.jpg")


def test_iam_policy_shape():
    pol = awsops.iam_policy()
    assert pol["Version"] == "2012-10-17"
    actions = {a for st in pol["Statement"] for a in st["Action"]}
    assert "cloudformation:CreateStack" in actions
    assert "cloudfront-keyvaluestore:PutKey" in actions
    assert "s3:PutObject" in actions
    json.dumps(pol)  # doit etre serialisable


def test_iam_policy_no_wildcard_except_create():
    """Regle: Resource '*' uniquement pour actions sans ressource / de creation."""
    pol = awsops.iam_policy()
    for st in pol["Statement"]:
        res = st["Resource"]
        has_star = res == "*" or (isinstance(res, list) and "*" in res)
        if has_star:
            for a in st["Action"]:
                assert a == "sts:GetCallerIdentity" or a.startswith("cloudfront:Create"), \
                    f"étoile interdite pour {a} (Sid {st['Sid']})"


def test_cloudformation_template_present():
    tpl = awsops.load_template()
    for token in [
        "AWS::S3::Bucket",
        "AWS::CloudFront::OriginAccessControl",
        "AWS::CloudFront::KeyValueStore",
        "AWS::CloudFront::Function",
        "AWS::CloudFront::Distribution",
        "cloudfront-js-2.0",
        "viewer-request",
    ]:
        assert token in tpl, token


def test_cli_registers_all_commands():
    click_cmd = typer.main.get_command(app)
    sub = set(click_cmd.commands.keys())
    for c in ["new", "add", "import", "remove", "list", "album", "preview",
              "init", "config", "push", "pull", "destroy", "doctor", "iam-policy"]:
        assert c in sub, c


def test_clean_path():
    from bookphoto.cli import _clean_path
    assert _clean_path("  /a/b\\ c/d.jpg ") == "/a/b c/d.jpg"
    assert _clean_path('"/a b/c.jpg"') == "/a b/c.jpg"
    assert _clean_path("'/x/y.jpg'") == "/x/y.jpg"
    assert _clean_path("/plain/p.jpg") == "/plain/p.jpg"
    assert _clean_path("") == ""


def test_unchanged(tmp_path):
    import hashlib
    from bookphoto.awsops import _unchanged
    p = tmp_path / "f.bin"
    p.write_bytes(b"hello world")
    md5 = hashlib.md5(b"hello world").hexdigest()
    assert _unchanged(p, 11, f'"{md5}"') is True       # identique
    assert _unchanged(p, 11, '"deadbeef"') is False     # empreinte differente
    assert _unchanged(p, 10, f'"{md5}"') is False        # taille differente
    assert _unchanged(p, 11, '"abc123-2"') is True       # multipart, taille ok
    assert _unchanged(p, 12, '"abc123-2"') is False      # multipart, taille differente


def test_auth_value_public_and_basic():
    from bookphoto.awsops import _auth_value, basic_auth_value
    assert _auth_value("invite", "-") == "-"                       # galerie publique
    assert _auth_value("invite", "secret") == basic_auth_value("invite", "secret")
