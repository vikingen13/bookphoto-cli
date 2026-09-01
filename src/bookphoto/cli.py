"""CLI de bookphoto (``gallery``). Un site = le dossier courant.

Commandes : init, config, new, album, add, remove, list, push, pull, doctor, iam-policy.
Toutes agissent sur le repertoire courant.
"""

from __future__ import annotations

import re
import shutil
from datetime import date
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from . import albums as al
from . import config as cfg
from .derivatives import generate_derivatives

app = typer.Typer(
    help="bookphoto - galerie photo privee serverless (S3 + CloudFront). Un site = un dossier.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()

AUTH_USER = "invite"  # utilisateur Basic Auth (fixe)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"bookphoto {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True,
        help="Affiche la version et quitte.",
    ),
) -> None:
    """Galerie photo privee. Les commandes agissent sur le dossier courant."""


def _require_site() -> None:
    if not cfg.site_exists():
        console.print("[red]Aucun site ici.[/red] Lance [bold]gallery init[/bold].")
        raise typer.Exit(1)


def _clean_path(s: str) -> str:
    """Nettoie un chemin saisi au clavier : espaces, guillemets englobants, et
    backslash d'echappement inseres par le glisser-depose macOS (``\\ `` -> espace)."""
    s = (s or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        s = s[1:-1]
    s = re.sub(r"\\(.)", r"\1", s)  # deséchappe "\ ", "\(", "\&", ... du drag-drop
    return s.strip()


def _import_image(path_str: str) -> str | None:
    """Copie une image dans assets/ et renvoie son chemin relatif (ex. assets/cover.jpg)."""
    path_str = _clean_path(path_str)
    if not path_str:
        return None
    src = Path(path_str).expanduser()
    if not src.exists():
        console.print(f"[yellow]Image introuvable, ignoree : {src}[/yellow]")
        return None
    assets = Path.cwd() / "assets"
    assets.mkdir(exist_ok=True)
    shutil.copy2(src, assets / src.name)
    return f"assets/{src.name}"


# --------------------------------------------------------------------------- #
# init / config : identite du site
# --------------------------------------------------------------------------- #
@app.command()
def init(
    region: Optional[str] = typer.Option(None, "--region", help="Region AWS (defaut: celle du profil)."),
    profile: Optional[str] = typer.Option(None, "--profile", help="Profil AWS (~/.aws)."),
) -> None:
    """Creer le site ici, saisir ses infos, provisionner l'infra AWS et le mettre en ligne."""
    from . import awsops

    if cfg.site_exists():
        console.print(f"[yellow]Un site existe deja ici[/yellow] : {Path.cwd()}")
        raise typer.Exit(1)

    region = region or awsops.default_region(profile)
    if not region:
        console.print("[red]Region inconnue : precise --region ou configure une region dans ton profil AWS.[/red]")
        raise typer.Exit(1)

    name = typer.prompt("Nom du site", default=cfg.DEFAULT_SITE_NAME)
    tagline = typer.prompt("Slogan", default="")
    cover = typer.prompt("Image de cover (chemin)", default="")
    avatar = typer.prompt("Avatar (chemin)", default="")
    password = typer.prompt(f"Mot de passe (utilisateur « {AUTH_USER} »)", hide_input=True)
    copyright_ = typer.prompt("Copyright", default=f"© {date.today().year} {name}")

    cfg.save_site(cfg.SiteConfig(
        name=name, tagline=tagline,
        cover=_import_image(cover), avatar=_import_image(avatar), copyright=copyright_,
    ))
    (Path.cwd() / "assets").mkdir(exist_ok=True)
    (Path.cwd() / ".gitignore").write_text(".bookphoto.json\nindex.html\ndata.json\n", encoding="utf-8")
    conf = cfg.load_config()
    conf.region, conf.profile, conf.password = region, profile, password
    cfg.save_config(conf)
    console.print(f"[green]Site cree[/green] : {Path.cwd()}")

    console.print("[dim]Provisionnement AWS (CloudFormation)... suivi en direct :[/dim]")
    awsops.provision_and_publish(
        region=region, profile=profile,
        progress=lambda m: console.print(f"  [dim]{m}[/dim]"),
    )
    conf = cfg.load_config()
    if conf.url:
        console.print(f"[green]En ligne[/green] : [bold]{conf.url}[/bold]  (utilisateur « {AUTH_USER} »)")


@app.command()
def config(
    name: Optional[str] = typer.Option(None, "--name"),
    tagline: Optional[str] = typer.Option(None, "--tagline"),
    cover: Optional[str] = typer.Option(None, "--cover", help="Chemin d'une image (copiee dans assets/)."),
    avatar: Optional[str] = typer.Option(None, "--avatar", help="Chemin d'une image (copiee dans assets/)."),
    copyright: Optional[str] = typer.Option(None, "--copyright"),
    password: Optional[str] = typer.Option(None, "--password"),
) -> None:
    """Afficher / modifier les infos du site (interactif si aucune option)."""
    _require_site()
    site = cfg.load_site()
    conf = cfg.load_config()

    if all(f is None for f in (name, tagline, cover, avatar, copyright, password)):
        site.name = typer.prompt("Nom du site", default=site.name)
        site.tagline = typer.prompt("Slogan", default=site.tagline or "")
        c = typer.prompt("Image de cover (chemin, vide=garder)", default="")
        if c:
            site.cover = _import_image(c)
        a = typer.prompt("Avatar (chemin, vide=garder)", default="")
        if a:
            site.avatar = _import_image(a)
        site.copyright = typer.prompt("Copyright", default=site.copyright or "")
        p = typer.prompt(f"Mot de passe (« {AUTH_USER} », vide=garder)", default="", hide_input=True)
        if p:
            conf.password = p
    else:
        if name is not None:
            site.name = name
        if tagline is not None:
            site.tagline = tagline
        if copyright is not None:
            site.copyright = copyright
        if cover:
            site.cover = _import_image(cover)
        if avatar:
            site.avatar = _import_image(avatar)
        if password is not None:
            conf.password = password

    cfg.save_site(site)
    cfg.save_config(conf)
    console.print("[green]Infos du site mises a jour.[/green]")
    console.print("[dim]'gallery push' pour mettre a jour en ligne.[/dim]")


# --------------------------------------------------------------------------- #
# albums
# --------------------------------------------------------------------------- #
@app.command()
def new(
    title: str = typer.Argument(..., help="Titre de l'album."),
    slug: Optional[str] = typer.Option(None, "--slug", help="Identifiant court (defaut: derive)."),
) -> None:
    """Creer un album (demande la description)."""
    _require_site()
    try:
        created = al.new_album(title, slug)
    except FileExistsError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    description = typer.prompt("Description", default="")
    if description:
        data = al.load_album(created)
        data["description"] = description
        al.write_album(created, data)
    console.print(f"[green]Album cree[/green] : [bold]{created}[/bold]")
    console.print(f"Ajoute des photos : gallery add {created} <fichiers>")


@app.command()
def album(
    slug: str = typer.Argument(..., help="Slug de l'album."),
    title: Optional[str] = typer.Option(None, "--title"),
    description: Optional[str] = typer.Option(None, "--description"),
    cover: Optional[str] = typer.Option(None, "--cover", help="Couverture : nom de fichier OU index (1-based) d'une photo de l'album."),
    show_header: Optional[bool] = typer.Option(None, "--header/--no-header", help="Afficher le bandeau cover dans le header de l'album (defaut: oui)."),
) -> None:
    """Afficher / modifier un album (interactif si aucune option)."""
    _require_site()
    if not al.album_exists(slug):
        console.print(f"[red]Album introuvable : '{slug}'.[/red]")
        raise typer.Exit(1)
    data = al.load_album(slug)

    def _set_cover(raw: str | None) -> None:
        try:
            data["cover"] = al.resolve_cover(slug, raw)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(1)

    if title is None and description is None and cover is None and show_header is None:
        data["title"] = typer.prompt("Titre", default=data.get("title") or slug)
        data["description"] = typer.prompt("Description", default=data.get("description") or "")
        files = [e.get("file") for e in (data.get("photos") or [])]
        if files:
            console.print("[dim]Photos de l'album :[/dim]")
            for i, f in enumerate(files, 1):
                console.print(f"  [dim]{i}.[/dim] {f}")
        raw = typer.prompt("Couverture (nom de fichier ou index, vide=1re photo)",
                           default=data.get("cover") or "")
        _set_cover(raw)
        data["header"] = typer.confirm("Afficher la cover dans le header de l'album ?",
                                       default=data.get("header", True))
    else:
        if title is not None:
            data["title"] = title
        if description is not None:
            data["description"] = description
        if cover is not None:
            _set_cover(cover)
        if show_header is not None:
            data["header"] = show_header
    al.write_album(slug, data)
    console.print(f"[green]Album '{slug}' mis a jour.[/green]")
    if data.get("cover"):
        console.print(f"[dim]Couverture : {data['cover']}[/dim]")
    console.print(f"[dim]Header cover : {'oui' if data.get('header', True) else 'non'}[/dim]")


@app.command()
def add(
    album: str = typer.Argument(..., help="Slug de l'album cible."),
    photos: list[Path] = typer.Argument(..., help="Fichiers photos a ajouter."),
) -> None:
    """Ajouter des photos (copie + date EXIF + redimensionnement immediat)."""
    _require_site()
    photos = [p.expanduser() for p in photos]
    try:
        result = al.add_photos(album, photos)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    console.print(
        f"[green]{len(result.added)} photo(s) ajoutee(s)[/green], "
        f"{result.dated} datee(s) via EXIF, {len(result.skipped)} ignoree(s)."
    )
    if not result.added:
        console.print(
            "[yellow]Rien ajoute.[/yellow] Verifie le chemin/glob : les fichiers existent ? "
            "sont-ils des images ? (astuce : Tab pour completer, ou glisse-depose les fichiers)"
        )
        if result.skipped:
            console.print(f"[dim]Ignores : {', '.join(result.skipped[:8])}[/dim]")
        return
    deriv = generate_derivatives(al.album_dir(album))
    console.print(f"[green]{len(deriv.generated)} image(s) redimensionnee(s)[/green] (miniatures + affichage).")


@app.command("import")
def import_folder(
    folder: Path = typer.Argument(..., help="Dossier contenant un sous-dossier par album."),
    keep_names: bool = typer.Option(False, "--keep-names", "-y",
                                    help="Ne pas demander : utiliser les noms de dossiers."),
) -> None:
    """Importer en masse : chaque sous-dossier de <folder> devient un album.

    Le nom est demande pour chaque album (defaut = nom du dossier ; Entree = garder).
    Le slug est derive du nom. Sous-dossiers vides ignores ; images a la racine ignorees.
    """
    _require_site()
    folder = folder.expanduser()
    if not folder.is_dir():
        console.print(f"[red]Dossier introuvable : {folder}[/red]")
        raise typer.Exit(1)
    subdirs = sorted(d for d in folder.iterdir() if d.is_dir())
    if not subdirs:
        console.print(f"[yellow]Aucun sous-dossier dans {folder}.[/yellow]")
        raise typer.Exit(1)

    used = set(al.list_local_albums())
    created = 0
    total = 0
    for d in subdirs:
        imgs = [p for p in d.rglob("*") if p.is_file() and p.suffix.lower() in al.PHOTO_EXTS]
        if not imgs:
            console.print(f"[yellow]Ignore (aucune image)[/yellow] : {d.name}")
            continue
        default_name = d.name.strip()
        name = default_name if keep_names else typer.prompt(
            f"Nom de l'album pour « {d.name} » ({len(imgs)} photos)", default=default_name)
        slug = al.slugify(name)
        if slug in used:
            if keep_names:
                base, n = slug, 2
                while f"{base}-{n}" in used:
                    n += 1
                slug = f"{base}-{n}"
                console.print(f"[yellow]Slug '{base}' deja pris -> '{slug}'.[/yellow]")
            else:
                while slug in used:
                    console.print(f"[yellow]Slug '{slug}' deja pris, choisis un autre nom.[/yellow]")
                    name = typer.prompt(f"Nom de l'album pour « {d.name} »", default=default_name)
                    slug = al.slugify(name)
        al.new_album(name, slug=slug)
        res = al.add_photos(slug, [d])
        deriv = generate_derivatives(al.album_dir(slug))
        used.add(slug)
        created += 1
        total += len(res.added)
        console.print(f"[green]OK[/green] {name} [dim]({slug})[/dim] : "
                      f"{len(res.added)} photo(s), {len(deriv.generated)} derivee(s).")
    console.print(f"[green]Import termine[/green] : {created} album(s), {total} photo(s). "
                  "[dim]'gallery push' pour publier.[/dim]")


@app.command()
def remove(
    album: str = typer.Argument(..., help="Slug de l'album."),
    photos: Optional[list[str]] = typer.Argument(None, help="Fichiers a supprimer (vide = tout l'album)."),
) -> None:
    """Supprimer des photos, ou l'album entier si aucun fichier n'est donne."""
    _require_site()
    try:
        if not photos:
            al.remove_album(album)
            console.print(f"[green]Album supprime[/green] : {album}")
        else:
            removed = al.remove_photos(album, photos)
            console.print(f"[green]{len(removed)} photo(s) supprimee(s)[/green] de {album}.")
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    console.print("[dim]'gallery push' pour repercuter en ligne.[/dim]")


@app.command("list")
def list_albums() -> None:
    """Lister les albums du site."""
    _require_site()
    slugs = al.list_local_albums()
    if not slugs:
        console.print('[dim]Aucun album. Cree-en un : gallery new "Titre"[/dim]')
        return
    table = Table(title="Albums")
    table.add_column("Slug", style="bold")
    table.add_column("Titre")
    table.add_column("Photos", justify="right")
    for slug in slugs:
        data = al.load_album(slug)
        table.add_row(slug, str(data.get("title") or ""), str(len(data.get("photos") or [])))
    console.print(table)


@app.command()
def preview(
    port: int = typer.Option(8000, "--port", help="Port du serveur local."),
) -> None:
    """Previsualiser la galerie en local (genere la SPA + sert en HTTP + ouvre le navigateur)."""
    import functools
    import http.server
    import socketserver
    import webbrowser

    from .generator import write_site

    _require_site()
    res = write_site()
    console.print(f"[green]Genere[/green] : {res.albums} album(s), {res.photos} photo(s).")
    for w in res.warnings:
        console.print(f"[yellow]! {w}[/yellow]")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(Path.cwd()))
    try:
        httpd = socketserver.TCPServer(("127.0.0.1", port), handler)
    except OSError:
        console.print(f"[red]Port {port} occupe.[/red] Reessaie avec --port <autre>.")
        raise typer.Exit(1)
    url = f"http://127.0.0.1:{port}/"
    console.print(f"[bold]{url}[/bold]  (Ctrl-C pour arreter)")
    webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        console.print("\nArret du serveur.")
    finally:
        httpd.server_close()


# --------------------------------------------------------------------------- #
# AWS : push / pull
# --------------------------------------------------------------------------- #
@app.command()
def push() -> None:
    """Mettre a jour le site en ligne (genere + miroir S3 + mot de passe + invalidation)."""
    from . import awsops

    _require_site()
    conf = cfg.load_config()
    if not conf.is_provisioned:
        console.print("[red]Site non provisionne. Lance 'gallery init'.[/red]")
        raise typer.Exit(1)
    try:
        res = awsops.push(conf, user=AUTH_USER,
                          progress=lambda m: console.print(f"  [dim]{m}[/dim]"))
    except Exception as exc:  # noqa: BLE001 - on veut un message propre
        console.print(f"[red]Echec du push : {exc}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Publie[/green] : {res['uploaded']} envoye(s), "
                  f"{res.get('skipped', 0)} inchange(s), {res['deleted']} supprime(s).")
    if conf.url:
        console.print(f"URL : [bold]{conf.url}[/bold]  (utilisateur « {AUTH_USER} »)")


@app.command()
def pull(
    name: str = typer.Argument(..., help='Nom de la galerie a cloner (ex. "Ma galerie").'),
    region: Optional[str] = typer.Option(None, "--region", help="Region AWS (defaut: profil)."),
    profile: Optional[str] = typer.Option(None, "--profile", help="Profil AWS (~/.aws)."),
) -> None:
    """Cloner une galerie depuis AWS dans le dossier courant.

    Source de verite : la stack CloudFormation bookphoto-<slug du nom de la galerie>.
    Le nom du dossier local n'a pas d'importance.
    """
    from . import awsops

    n = awsops.pull(name, region=region, profile=profile, user=AUTH_USER)
    console.print(f"[green]{n} fichier(s) clone(s)[/green] dans {Path.cwd()}.")
    console.print("[dim]Le site est pret : edite puis 'gallery push'.[/dim]")


@app.command()
def destroy(
    yes: bool = typer.Option(False, "--yes", "-y", help="Ne pas demander de confirmation."),
) -> None:
    """Detruire l'infra AWS de ce site (vide le bucket + supprime la stack). IRREVERSIBLE."""
    from . import awsops

    _require_site()
    conf = cfg.load_config()
    if not conf.is_provisioned:
        console.print("[red]Rien a detruire : ce site n'est pas provisionne.[/red]")
        raise typer.Exit(1)
    console.print(
        f"[yellow]Suppression[/yellow] : stack [bold]{conf.stack}[/bold] + bucket "
        f"[bold]{conf.bucket}[/bold] (region {conf.region}). [red]Irreversible.[/red]"
    )
    if not yes and not typer.confirm("Confirmer ?"):
        console.print("Annule.")
        raise typer.Exit(0)
    awsops.destroy(conf, progress=lambda m: console.print(f"  [dim]{m}[/dim]"))
    console.print("[green]Infra supprimee.[/green] (Le contenu local est conserve.)")


@app.command()
def doctor() -> None:
    """Diagnostiquer la configuration et l'infra AWS (lecture seule)."""
    from . import awsops

    for name, ok, detail in awsops.doctor(cfg.load_config()):
        mark = "[green]OK[/green]" if ok else "[red]KO[/red]"
        console.print(f"{mark}  {name} — [dim]{detail}[/dim]")


@app.command("iam-policy")
def iam_policy() -> None:
    """Afficher la politique IAM minimale requise."""
    from . import awsops

    console.print_json(data=awsops.iam_policy())


def main() -> None:
    app()


if __name__ == "__main__":
    main()
