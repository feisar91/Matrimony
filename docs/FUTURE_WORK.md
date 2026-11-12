# Future Work

Known issues and planned improvements, mostly from the November 2026 dependency and
security review. The high-severity findings from that review (gallery XSS, setup-wizard
admin takeover) and the quick hardening items are already fixed.

## Security

### CSRF tokens on all forms
No form or `fetch` call carries a CSRF token. `SESSION_COOKIE_SAMESITE='Lax'` blocks the
common cross-site POST case, but full protection needs Flask-WTF `CSRFProtect`, a
`{{ csrf_token() }}` hidden input in every POST form (admin templates, site login, Save the
Date, RSVP confirm, setup wizard) and a real `X-CSRFToken` header on JS `fetch` calls
(`templates/admin/gallery.html` currently sends an empty one).

### Rate limiting
Nothing limits `/admin/login`, `/site-login` (brute force), `/save` (unauthenticated; each
submission emails the couple) or `/api/upload-photo` (60 MB per request, so disk can fill).
Flask-Limiter fits, but gunicorn runs 4 workers, so limits need shared storage (Postgres or
Redis) to be accurate.

### Run the container as a non-root user
The image runs as root. Switching to an unprivileged user needs a migration step: existing
`matrimony-uploads` volumes are root-owned, so the app would lose write access to
`static/uploads/` (for example, a one-off `chown` in the entrypoint before dropping
privileges).

### `Secure` flag on the session cookie
Not set, because the plain-HTTP localhost Docker setup would break. It needs to know when it
is behind HTTPS (Render, reverse proxies): `ProxyFix` plus an opt-in env var, or detection
of the forwarded scheme.

### Smaller hardening items
- **SMTP password** is stored in plaintext in `wedding_config.mail_smtp_password`.
- **Favicon upload accepts SVG**, which can carry script served from the site's own origin
  (only admins can upload it).
- **Photo uploads are validated by extension only.** `nosniff` now limits the impact;
  checking the content with Pillow (`Image.open(...).verify()`) would close it. Two uploads
  with the same guest name and file name in the same second overwrite each other.
- **Setup wizard race:** two simultaneous step-1 POSTs on a brand-new install could both
  create an admin. The window is tiny; a Postgres advisory lock would close it.
- **No Content-Security-Policy.** It needs inline scripts and handlers moved out of the
  templates first.

## Bugs and cleanup

### Legacy `/rsvp/admin*` routes are broken
`rsvp_admin_login` and `rsvp_admin_bulk_email` in `app.py` reference an undefined `config`
(left over from the old YAML-config version), so the login always returns 500 and these
pages can't be reached. Bulk email to guests exists only here. Decide whether to move it
into the `/admin/rsvp` panel or delete the routes, along with `templates/rsvp_admin*.html`
and the unused `templates/rsvp_qr_codes.html`.

### Mail settings are per gunicorn worker
`apply_mail_config()` copies SMTP settings into `app.config` at startup and when settings
are saved. Only the worker that handled the save is updated, so the other 3 send with stale
settings until restart. Read the config from the database when sending instead.

### SQLAlchemy legacy API
Code uses `Model.query.get()`, which is deprecated in SQLAlchemy 2.x. Switch to
`db.session.get(Model, id)`.

## Dependencies
- **Pin transitive dependencies.** SQLAlchemy, Jinja2, Pillow and itsdangerous are
  unpinned and float to the latest version at build time. Use a lock file or constraints.
- **Update Flask-Mail and qrcode.** Flask-Mail 0.9.1 hasn't been updated since 2014; 0.10.0
  is current. qrcode 7.4.2 → 8.x. Neither has known CVEs.
- **Pin CI and image versions.** GitHub Actions are pinned by tag, not commit SHA, and the
  `python:3.11-slim` base image isn't pinned to a digest.
- **Trivy flags `setuptools` 70.3.0** (CVE-2025-47273) in the built image, although only
  84.x and the `ensurepip` bundled 79.0.1 are present. Likely a false positive from vendored
  metadata; it's build tooling only.
