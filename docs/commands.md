# Command reference

Every command operates on the **current folder** (the site). None takes a site path as an
argument: `cd` into the right folder first. The Basic Auth user is fixed — **`invite`**. A
password of `-` makes the gallery **public**.

```bash
gallery --version
gallery --help
```

---

## `init`

```bash
gallery init [--region <region>] [--profile <profile>]
```

Creates the site in the current folder, **provisions the AWS infra** (CloudFormation) and
**publishes**. Interactive — asks for: name, tagline, cover image (path), avatar (path),
**password** (`invite`; `-` = public), copyright.

- `--region`: AWS region. Defaults to the profile/environment region. Errors if none.
- `--profile`: `~/.aws` profile. Only the **name** is stored (never your secrets).
- Writes `site.yaml`, `assets/`, a `.gitignore` (`.bookphoto.json`, `index.html`, `data.json`),
  then `.bookphoto.json` (region, profile, password) and finally the stack outputs.
- Fails if a site already exists here.

Stack: `bookphoto-<slug(name)>` · bucket: `bookphoto-<slug(name)>-<accountId>`.

---

## `config`

```bash
gallery config                       # interactive
gallery config --name "…" --tagline "…" --copyright "…"
gallery config --cover path.jpg      # '-' to remove
gallery config --avatar path.jpg     # '-' to remove
gallery config --password "secret"   # '-' = public gallery
```

Views / edits branding (`site.yaml`) and the password (`.bookphoto.json`). With no option:
interactive (Enter keeps the current value). Images passed to `--cover`/`--avatar` are copied
into `assets/`. Apply online with `gallery push`.

---

## `new`

```bash
gallery new "<title>" [--slug <slug>]
```

Creates an album (folder `<slug>/` + `photos/` + `album.yaml`) and asks for the description.
The slug is derived from the title if not provided.

---

## `add`

```bash
gallery add <album> <files…>
```

Copies photos into `<album>/photos/`, reads the **EXIF date**, updates `album.yaml`
(dedup by filename), then generates **derivatives**: thumbnails `thumbs/` (≤ 400 px) and
display `display/` (≤ 2048 px), with EXIF auto-rotation. A folder passed as an argument is
expanded recursively into images.

---

## `import`

```bash
gallery import <folder> [--keep-names|-y]
```

Bulk import: **each subfolder** of `<folder>` becomes an album (name is asked, default = folder
name; slug derived). Generates derivatives along the way. Empty subfolders ignored; images at
the root ignored. `--keep-names`: no prompt, use folder names (handles slug collisions by
suffixing `-2`, `-3`…).

---

## `album`

```bash
gallery album <slug>                         # interactive
gallery album <slug> --title "…" --description "…"
gallery album <slug> --cover <name|index>    # e.g. photo.jpg OR 3 (3rd photo)
gallery album <slug> --header / --no-header  # cover banner in the album header
```

Edits an album. The cover is given by **filename** or **1-based index** of a photo in the
album (never a path). `--header/--no-header` toggles the cover banner at the top of the album
(default: shown).

---

## `headers`

```bash
gallery headers            # show current state
gallery headers on         # force the banner everywhere
gallery headers off        # hide the banner everywhere
gallery headers auto       # each album decides (per-album setting)
```

**Global** override of the album cover banner, stored in `site.yaml` (`header_override`).
Non-destructive: `auto` restores the per-album choices.

---

## `remove`

```bash
gallery remove <album>              # delete the whole album
gallery remove <album> <files…>     # delete photos (original + derivatives + entry)
```

---

## `list`

```bash
gallery list
```

Table of albums (slug, title, photo count).

---

## `preview`

```bash
gallery preview [--port 8000]
```

Builds the SPA (`index.html` + `data.json`) and serves the folder locally
(`http://127.0.0.1:<port>`), opening the browser. `Ctrl-C` to stop. Does not call AWS.

---

## `push`

```bash
gallery push
```

Publishes online: builds the SPA, **mirrors the folder to S3 incrementally** (uploads only new/
changed files — size + ETag comparison —, deletes stale ones), writes the password to the
KeyValueStore, then **invalidates** the CloudFront cache. `.bookphoto.json` and `.gitignore`
are never uploaded. Requires a provisioned site (`init`).

---

## `pull`

```bash
gallery pull "<gallery name>" [--region <region>] [--profile <profile>]
```

Clones an existing gallery from AWS **into the current folder**. The source of truth is the
stack `bookphoto-<slug(name)>`: the **gallery name** matters, not the local folder name.
Rebuilds `.bookphoto.json` from the stack outputs and restores the password from the
KeyValueStore.

---

## `domain`

```bash
gallery domain photos.example.com    # attach a custom subdomain
gallery domain                       # show the current domain / cert
gallery domain --clear               # detach (back to cloudfront.net)
```

Associates a custom **subdomain** with the distribution. Requests (or reuses) a DNS-validated
**ACM certificate in `us-east-1`** (CloudFront requirement), then attaches the alias + cert to
CloudFront. bookphoto **does not manage DNS**: it prints the records to add to your zone — the
**validation CNAME**, then the final `photos.example.com CNAME dxxxx.cloudfront.net`. Apex
domains aren't supported (use a subdomain). `--clear` reverts and keeps the ACM cert (free,
reusable; removed by `destroy`).

---

## `destroy`

```bash
gallery destroy [--yes|-y]
```

**Irreversible.** Empties the S3 bucket then deletes the CloudFormation stack (i.e. all of
this site's AWS infra). The **local** content (photos, albums) is kept. Asks for confirmation
unless `--yes`.

---

## `doctor`

```bash
gallery doctor
```

**Read-only** diagnostics: AWS credentials, infra provisioned, bucket private, distribution
deployed. If a custom domain is set, also checks the ACM certificate (`ISSUED`) and the
CloudFront alias.

---

## `iam-policy`

```bash
gallery iam-policy
```

Prints (JSON) the minimal required IAM policy. See [architecture.md](architecture.md).
