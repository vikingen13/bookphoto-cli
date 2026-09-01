# Troubleshooting

Always start with:

```bash
gallery doctor        # AWS credentials, infra provisioned, bucket private, distribution
gallery --version
```

## Credentials / region

- **"Region inconnue"** at `init`: no region in the profile/environment. Pass
  `--region eu-west-1` (or configure your default AWS region).
- **`doctor` → AWS credentials KO**: no valid credentials. Use a profile
  (`--profile my-profile`), env variables, or `aws sso login`.
- bookphoto only stores the profile **name** in `.bookphoto.json`, never the secrets.

## Permissions (AccessDenied)

Provisioning often fails on a **missing IAM permission** (the CloudFormation message says so).
Apply the minimal policy:

```bash
gallery iam-policy > bookphoto-policy.json
```

and attach it to the user/role that runs `gallery` (see [architecture.md](architecture.md)).

## init / CloudFormation

- **"Un site existe déjà ici"**: `init` refuses to overwrite. Use an empty folder, or `pull`
  to clone an existing site.
- **Provisioning failed**: the CloudFormation cause is printed live. If the stack rolled
  back / was deleted (`OnFailure=DELETE`), fix the cause (often IAM) then re-run `init` in an
  empty folder.
- The live output shows every stack event; let it run to `*_COMPLETE`.

## push

- **"Site non provisionné"**: run `gallery init` first (or `pull`).
- **A derivative is missing** (build warning): re-run `gallery add <album> …` to (re)generate
  `thumbs/`/`display/`.
- push is **incremental**: `X uploaded, Y unchanged, Z deleted`. An "unchanged" file is not
  re-uploaded (size + ETag comparison).

## The site shows an old version

`push` already invalidates CloudFront (`/*`). Propagation can take a minute. HTML is served
`no-cache`, images with a long immutable cache. If in doubt, hard-reload to bypass the browser
cache.

## Authentication

- **401 loop**: wrong password, or the KVS isn't updated yet. Re-run `gallery push` (or
  `gallery config --password …`) to rewrite the `auth` key.
- **Make public / private**: `gallery config --password -` (public) or a real password
  (private). The user is always `invite`.
- **Fail-closed**: if the KVS is unreadable, access is denied (401) by design.

## pull

- Clones by **gallery name** (`gallery pull "My gallery"`), not by folder name: the source is
  the stack `bookphoto-<slug(name)>`. Check the spelling of the name.
- Pass `--region`/`--profile` if the gallery isn't in the default region/account.

## Custom domain

- **Certificate stuck in `PENDING_VALIDATION`**: the DNS **validation CNAME** printed by
  `gallery domain` isn't in your zone yet, or hasn't propagated. Add it exactly as shown
  (name + value), then wait — ACM validates automatically. `gallery doctor` shows the cert
  status.
- **"ressemble a un domaine apex"**: you passed a bare domain (`example.com`). Use a
  **subdomain** (`photos.example.com`) — a bare apex can't be a CNAME.
- **Site not reachable on the custom domain**: after the cert is `ISSUED` and the stack
  updated, add the final `photos.example.com CNAME dxxxx.cloudfront.net` to your zone (printed
  by the command). Give CloudFront a minute to redeploy.
- **The cert must be in `us-east-1`** — bookphoto handles that for you; if you create one by
  hand for CloudFront, it must be there.
- **Revert**: `gallery domain --clear` detaches the alias (back to cloudfront.net); remove the
  CNAME from your zone yourself. The ACM cert is kept (reusable) and cleaned up by `destroy`.

## destroy fails (DELETE_FAILED)

- Message `s3:DeleteBucketPolicy ... not authorized` (or another `Delete*` action): the role
  lacks **delete** permissions. Apply the up-to-date policy (`gallery iam-policy`) to the
  user/role, then re-run `gallery destroy`.
- The stack stays in `DELETE_FAILED` until the cause is resolved: once the permissions are
  added, `gallery destroy` **retries** the deletion (an already-emptied bucket is fine). As a
  last resort, delete the failing resource then the stack from the CloudFormation console (or
  `delete-stack --retain-resources <LogicalId>`).

## Cost

For any bill estimate, use the [AWS Pricing Calculator](https://calculator.aws/). To stop a
site's charges: `gallery destroy` (deletes bucket + stack; local content is kept).

## Tests

```bash
uv run pytest
```
