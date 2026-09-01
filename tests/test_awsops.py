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
                assert (
                    a == "sts:GetCallerIdentity"
                    or a.startswith("cloudfront:Create")
                    or a.startswith("acm:")
                ), f"étoile interdite pour {a} (Sid {st['Sid']})"


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
    for c in ["new", "add", "import", "remove", "list", "album", "headers", "preview",
              "init", "config", "push", "pull", "domain", "destroy", "doctor", "iam-policy"]:
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


def test_pull_reports_and_rebuilds(monkeypatch, tmp_path):
    from unittest.mock import MagicMock
    from pathlib import Path
    from bookphoto import config as cfg

    monkeypatch.chdir(tmp_path)
    cf = MagicMock()
    cf.describe_stacks.return_value = {"Stacks": [{"Outputs": [
        {"OutputKey": "BucketName", "OutputValue": "bookphoto-x-123"},
        {"OutputKey": "DistributionId", "OutputValue": "DIST"},
        {"OutputKey": "DomainName", "OutputValue": "d.cloudfront.net"},
        {"OutputKey": "KeyValueStoreArn", "OutputValue": "arn:kvs"},
    ]}]}
    s3 = MagicMock()
    pag = MagicMock()
    pag.paginate.return_value = [{"Contents": [{"Key": "site.yaml"}, {"Key": "a/album.yaml"}]}]
    s3.get_paginator.return_value = pag
    s3.download_file.side_effect = lambda b, k, p: Path(p).write_text("x", encoding="utf-8")
    kv = MagicMock()
    kv.get_key.return_value = {"Value": awsops.basic_auth_value("invite", "secret")}
    clients = {"cloudformation": cf, "s3": s3, "cloudfront-keyvaluestore": kv}
    sess = MagicMock()
    sess.client.side_effect = lambda name, region_name=None: clients[name]
    monkeypatch.setattr(awsops, "_session", lambda profile=None: sess)

    msgs: list[str] = []
    n = awsops.pull("X", region="eu-west-1", progress=msgs.append)

    assert n == 2
    assert any("Telechargement de 2" in m for m in msgs)
    assert (tmp_path / "site.yaml").exists() and (tmp_path / "a" / "album.yaml").exists()
    conf = cfg.load_config()
    assert conf.bucket == "bookphoto-x-123"
    assert conf.url == "https://d.cloudfront.net"
    assert conf.password == "secret"


def test_pull_not_found_message(monkeypatch, tmp_path):
    from unittest.mock import MagicMock
    import pytest

    monkeypatch.chdir(tmp_path)
    cf = MagicMock()
    cf.describe_stacks.side_effect = RuntimeError("stack absente")
    sess = MagicMock()
    sess.client.side_effect = lambda name, region_name=None: cf
    monkeypatch.setattr(awsops, "_session", lambda profile=None: sess)

    with pytest.raises(RuntimeError, match="introuvable"):
        awsops.pull("Inexistante", region="eu-west-1")


def test_iam_policy_has_destroy_permissions():
    """destroy supprime BucketPolicy + Bucket + Distribution : les droits doivent y etre."""
    actions = {a for st in awsops.iam_policy()["Statement"] for a in st["Action"]}
    for needed in ("s3:DeleteBucketPolicy", "s3:DeleteBucket",
                   "cloudfront:DeleteDistribution", "cloudfront:GetDistributionConfig"):
        assert needed in actions, needed


def test_iam_policy_has_acm_permissions():
    """gallery domain : ACM (us-east-1) pour le certificat du domaine perso."""
    actions = {a for st in awsops.iam_policy()["Statement"] for a in st["Action"]}
    for needed in ("acm:RequestCertificate", "acm:DescribeCertificate",
                   "acm:ListCertificates", "acm:DeleteCertificate"):
        assert needed in actions, needed


def test_template_has_domain_support():
    tpl = awsops.load_template()
    for token in ("DomainName", "AcmCertificateArn", "ViewerCertificate",
                  "CloudFrontDefaultCertificate", "sni-only"):
        assert token in tpl, token


def test_is_apex():
    assert awsops.is_apex("example.com") is True
    assert awsops.is_apex("photos.example.com") is False


def test_set_domain_reuses_cert_and_updates_stack(monkeypatch, tmp_path):
    from unittest.mock import MagicMock
    from bookphoto import config as cfg

    monkeypatch.chdir(tmp_path)
    domain = "photos.example.com"
    arn = "arn:aws:acm:us-east-1:1:certificate/abc"

    acm = MagicMock()
    pag = MagicMock()
    pag.paginate.return_value = [{"CertificateSummaryList": [
        {"DomainName": domain, "CertificateArn": arn}]}]
    acm.get_paginator.return_value = pag
    acm.describe_certificate.return_value = {"Certificate": {"Status": "ISSUED"}}

    cf = MagicMock()
    cf.describe_stack_events.return_value = {"StackEvents": []}
    cf.describe_stacks.return_value = {"Stacks": [{
        "StackStatus": "UPDATE_COMPLETE",
        "Outputs": [{"OutputKey": "DomainName", "OutputValue": "d.cloudfront.net"}],
    }]}

    clients = {"acm": acm, "cloudformation": cf}
    sess = MagicMock()
    sess.client.side_effect = lambda name, region_name=None: clients[name]
    monkeypatch.setattr(awsops, "_session", lambda profile=None: sess)

    conf = cfg.AppConfig(region="eu-west-1", bucket="b", distribution_id="D", stack="bookphoto-x")
    msgs: list[str] = []
    awsops.set_domain(conf, domain, progress=msgs.append)

    # certificat reutilise (pas de request_certificate), stack mise a jour avec les bons params
    acm.request_certificate.assert_not_called()
    kwargs = cf.update_stack.call_args.kwargs
    pmap = {p["ParameterKey"]: p for p in kwargs["Parameters"]}
    assert pmap["DomainName"]["ParameterValue"] == domain
    assert pmap["AcmCertificateArn"]["ParameterValue"] == arn
    assert pmap["BucketName"]["UsePreviousValue"] is True
    saved = cfg.load_config()
    assert saved.domain == domain and saved.certificate_arn == arn


def test_set_domain_rejects_apex(monkeypatch, tmp_path):
    import pytest
    from bookphoto import config as cfg

    monkeypatch.chdir(tmp_path)
    conf = cfg.AppConfig(region="eu-west-1", bucket="b", distribution_id="D", stack="bookphoto-x")
    with pytest.raises(RuntimeError, match="apex"):
        awsops.set_domain(conf, "example.com")
