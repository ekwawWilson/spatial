# Installing the platform on a server

*Whoever runs the Assembly's server or cloud hosting.*

The platform runs as a set of Docker containers: the database (PostgreSQL with PostGIS), a cache (Redis), the application (backend and background worker) and the web app behind nginx.

## What the server needs
- Ubuntu 22.04 or 24.04 (or another Linux that runs Docker), 4 CPU cores, 8 GB of memory, 100 GB of disk to start. Imagery and photos are what fill the disk.
- Docker Engine with the Compose plugin, version 2.24 or newer.
- A domain name pointing at the server, and a TLS certificate. The platform's own nginx speaks plain HTTP on one port; put HTTPS in front of it with the server's nginx, Caddy, or the cloud provider's load balancer, and have it send the `X-Forwarded-Proto` header.

## First install
```bash
git clone https://github.com/ekwawWilson/spatial.git && cd spatial

# 1. Settings and secrets, with every secret generated at random.
scripts/make-production-env.sh planning.example.gov.gh > .env
chmod 600 .env

# 2. Build and start.
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build --wait

# 3. The first system administrator.
docker compose exec backend python manage.py createsuperuser
```
Then open the site, sign in, and create the region, the district and its first district administrator (see the user guide, System administration).

**Copy `.env` somewhere safe and separate from the server straight away.** It holds the database passwords and the organisation key for `.spp` project files. Without that key, `.spp` files can't be opened by anyone ([organisation keys](spp-keys.md)).

### Settings to review in `.env`
| Setting | Meaning |
|---|---|
| `WEB_PORT` | The port the web app listens on (80 by default in production). |
| `HTTPS_ONLY` | Set to `true` once HTTPS is working: redirects to HTTPS and marks cookies secure. |
| `HSTS_SECONDS` | How long browsers should insist on HTTPS. Start with `3600`; raise to `31536000` when you're sure. |
| `EMAIL_BACKEND` and mail settings | Needed for password-reset emails. The default only prints them to the log. |
| `THROTTLE_*` | Rate limits. The defaults suit an Assembly; raise `THROTTLE_USER` if many people share one account (they shouldn't). |
| `GUNICORN_WORKERS` | Application processes. About 2 x CPU cores + 1. |

The server refuses to start with the example secrets, a development `.spp` key, or `DJANGO_ALLOWED_HOSTS` unset: `manage.py check` explains which.

## Updating
```bash
scripts/backup.sh                     # always first
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build --wait
```
Database changes are applied automatically when the stack starts.

## Automatic testing and safe updates (CI/CD)
Every change pushed to the repository is tested by GitHub Actions before it should be installed: backend tests, web tests, browser tests, a two-server `.spp` test, a load test, a backup-and-restore test, and a start-up test of this production configuration. Install only commits whose run is green. The update above can be run by hand, or from a scheduled job on the server once you trust the pipeline.

## The field app
Build the Android app with `apps/mobile/build-apk.sh` and give field officers the APK, or publish it ([distributing the field app](field-app-distribution.md)). In the app, the **server address** is the site's address.

## Checking an installation
`WEB_PORT=<port> scripts/qa-phase-13-production.sh` runs the same checks the pipeline does: deployment checks, the web app and API through nginx, security headers, sign-in, and rate limiting. It creates demo accounts, so run it on a test installation, not the live one.
