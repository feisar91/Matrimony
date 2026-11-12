# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Matrimony is a self-hosted wedding website: guest pages, Save the Date / RSVP, a time-locked photo
challenge and gallery, all configured from an admin panel. Flask + PostgreSQL, Jinja2 templates,
vanilla JS/CSS, no build step.

## Commands

```bash
pip install -r requirements.txt
cp .env.example .env                     # SECRET_KEY + DB_* (or DATABASE_URL)
python setup_database.py                 # create PG user/db/tables (prompts for postgres superuser pw)
python setup_database.py --tables-only   # tables only (what the Docker entrypoint runs)

FLASK_DEBUG=1 python app.py              # dev server on 127.0.0.1:5000 (HOST/PORT env to override)
gunicorn -w 4 -b 0.0.0.0:8000 app:app    # production, as in docker/entrypoint.sh

docker compose -f docker/docker-compose.yml up -d   # pulls ghcr.io/feisar91/matrimony; see file to build locally
docker build -f docker/Dockerfile -t matrimony .
```

There is **no test suite and no linter config**. To verify changes without Postgres:
- `DATABASE_URL=sqlite:////tmp/x.db` works with Flask's test client (`app.test_client()`).
  Use a fresh app context per request: holding one context open shares `g`, so Flask-Login's
  cached `current_user` leaks between test clients.
- The pinned deps target the production image (`python:3.11-slim`). If the host Python is much
  newer, run checks in that image:
  `docker run --rm -v "$PWD:/src:ro" python:3.11-slim sh -c 'cp -r /src /app && pip install -q -r /app/requirements.txt && ...'`
- Dependency audit: `pip-audit -r requirements.txt` (inside that image).

CI (`.github/workflows/docker-publish.yml`) only builds and pushes the Docker image to GHCR on push
to `main` (tag `latest`) and on `v*` tags. Render deploys via `render.yaml`.

## Architecture

**Everything lives in `app.py`** (one module, no blueprints): models, helpers, and all routes.
Importing it has side effects: it connects to the DB (10 retries × 3 s), runs `db.create_all()`,
applies ad-hoc column migrations, and loads mail settings. `setup_database.py` imports `app` for
the same reason.

**Configuration is in the database, not files.** `WeddingConfig` is a single-row table read via
`get_wedding_config()` (first row). Couple names, dates, venues, theme colours, layout, feature
toggles, site password and SMTP settings are all edited at `/admin/wedding`. Env vars cover only
infra: `SECRET_KEY`, `DATABASE_URL` or `DB_*`, `DEFAULT_TIMEZONE`, `SETUP_TOKEN`, `PORT`.

**Schema migrations are manual (no Alembic).** `db.create_all()` creates missing tables only.
New `WeddingConfig` columns must also be added to the `alter_statements` dict in
`ensure_wedding_config_columns()`, or existing installs break. Other tables have no migration
path.

**Request gating, in order:**
1. `before_request` redirects everything to `/admin/setup` until an admin exists.
2. The setup wizard: step 1 creates the admin (optionally gated by `SETUP_TOKEN`) and logs them
   in; step 2 creates `WeddingConfig` and requires that login.
3. Admin routes use `@admin_required` (Flask-Login, `AdminUser`).
4. Guest pages use `@require_site_password` (the session flag `site_authenticated`, enforced only
   when `site_password_protected` is on).
5. Guest RSVP confirmation needs no login: `/rsvp/confirm/<unique_code>`. Codes are distributed
   as per-guest QR codes from the admin panel.

**Time handling:** `wedding_datetime` and the photo-challenge unlock date are stored as naive
datetimes in the wedding's local time. Compare them against `now_local()`, which converts using
`WeddingConfig.timezone`, never against `datetime.now()`.

**Templates and theming:** guest pages extend `templates/base.html`; the admin panel extends
`templates/admin/base.html`. The context processor `inject_template_globals()` supplies the theme
colours (rendered as CSS custom properties in `base.html`), `site_layout` (applied as
`<body class="layout-…">`, styled in `static/css/style.css`) and feature toggles to every
template.

**Uploads** go under `static/uploads/{photos,favicon,hero}/` and are served as static files. In
Docker that directory is a named volume. Photo metadata lives in `PhotoSubmission`; files are
named `{guest}_{timestamp}_{original}`.

**Email:** `build_wedding_email_template()` builds the HTML for guest emails.
`apply_mail_config()` copies SMTP settings from `WeddingConfig` into `app.config` at startup and
on settings save. That copy is per gunicorn worker, so other workers keep stale settings until
restart. Sending is skipped when no SMTP server is configured.

## Security conventions (from past fixes; keep them)

- Never interpolate data into inline JS handlers as `'{{ x }}'`; HTML escaping doesn't protect
  that context. Use `{{ x|tojson }}` inside a **single-quoted** attribute: `onclick='f({{ x|tojson }})'`.
- Redirect targets taken from user input must go through `is_safe_redirect_target()`.
- Values interpolated into email HTML must be escaped (`html_escape`); colours go through
  `_safe_color()`.
- Guest-supplied fields (guest names, challenge text, RSVP names, emails) reach the admin pages,
  so treat every admin template as rendering untrusted data.

## Known issues

`docs/FUTURE_WORK.md` tracks open security items and bugs. Notable ones: there are no CSRF
tokens yet, and the legacy `/rsvp/admin*` routes are broken because they reference an undefined
`config`.
