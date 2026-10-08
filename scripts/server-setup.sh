#!/usr/bin/env bash
# Installs the platform on a new Ubuntu server (a DigitalOcean droplet, or any
# Ubuntu 22.04/24.04 machine), behind HTTPS, with nightly backups. Run as root:
#
#   curl -fsSL https://raw.githubusercontent.com/ekwawWilson/spatial/main/scripts/server-setup.sh | bash -s -- planning.example.gov.gh
#
# The address must already point at the server (a DNS "A" record), so the
# HTTPS certificate can be issued. Without an address, the server's own
# address is used through sslip.io (e.g. 203-0-113-5.sslip.io): fine for
# trying it out, not for the Assembly's real site.
#
# Running it again updates the installation: a backup first, then the newest
# code, rebuilt and restarted. .env is never replaced.
#
# Settings (environment): REPO, BRANCH (default main), DIR (default
# /opt/spatial), SKIP_SYSTEM=true to leave the machine itself alone (swap,
# packages, Docker, firewall, cron), as the CI test does.
set -euo pipefail

# Everything is in one function, called on the last line: when the script is
# piped into bash (curl ... | bash), bash has then read all of it before any
# command runs, so a command that reads its input (docker compose does) can't
# swallow the rest of the script.
main() {

  REPO="${REPO:-https://github.com/ekwawWilson/spatial.git}"
  BRANCH="${BRANCH:-main}"
  DIR="${DIR:-/opt/spatial}"
  SKIP_SYSTEM="${SKIP_SYSTEM:-false}"
  SITE="${1:-}"

  step() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
  fail() { echo "FAILED: $1" >&2; exit 1; }

  if [ "$SKIP_SYSTEM" != true ]; then
    [ "$(id -u)" = 0 ] || fail "run this as root (sudo)"

    step "The machine: swap, packages, Docker, firewall"
    # Building the images needs more memory than small droplets have.
    if ! swapon --show | grep -q .; then
      fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
      grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
      echo "  4 GB swap added"
    fi
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq git curl openssl ufw unattended-upgrades >/dev/null
    # Security updates for the operating system install themselves.
    dpkg-reconfigure -f noninteractive unattended-upgrades
    command -v docker >/dev/null || curl -fsSL https://get.docker.com | sh
    # Docker publishes only Caddy's ports (80, 443); SSH stays open.
    ufw allow OpenSSH >/dev/null
    ufw allow 80/tcp >/dev/null
    ufw allow 443/tcp >/dev/null
    ufw allow 443/udp >/dev/null
    ufw --force enable >/dev/null
    echo "  firewall: SSH, HTTP and HTTPS only"
  fi

  step "The site's address"
  public_ip() {
    # DigitalOcean's metadata service first, then a public lookup.
    curl -fsS --max-time 3 http://169.254.169.254/metadata/v1/interfaces/public/0/ipv4/address 2>/dev/null \
      || curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null \
      || hostname -I | awk '{print $1}'
  }
  if [ -f "$DIR/.env" ]; then
    CURRENT=$(grep '^SITE_HOST=' "$DIR/.env" | cut -d= -f2- || true)
    if [ -n "$SITE" ] && [ -n "$CURRENT" ] && [ "$SITE" != "$CURRENT" ]; then
      fail "this server is set up for $CURRENT. To change the address, see 'Changing the address' in docs/ops/digitalocean.md"
    fi
    SITE="${SITE:-$CURRENT}"
  fi
  if [ -z "$SITE" ]; then
    IP=$(public_ip)
    SITE="${IP//./-}.sslip.io"
    echo "  no address given: using $SITE (for trying out only)"
  fi
  if [ "$SITE" != localhost ]; then
    IP="${IP:-$(public_ip)}"
    POINTS_AT=$(getent ahostsv4 "$SITE" | awk 'NR==1{print $1}' || true)
    if [ "$POINTS_AT" != "$IP" ]; then
      echo "  WARNING: $SITE points at '${POINTS_AT:-nothing}', not this server ($IP)."
      echo "  The HTTPS certificate can't be issued until it does; Caddy keeps trying."
    fi
  fi
  echo "  https://$SITE"

  step "The code"
  UPDATE=false
  if [ -f "$DIR/.env" ]; then
    UPDATE=true
  elif [ ! -d "$DIR/.git" ]; then
    git clone --branch "$BRANCH" "$REPO" "$DIR"
  fi
  cd "$DIR"
  if [ "$UPDATE" = true ]; then
    if [ -n "$(docker compose ps -q backend 2>/dev/null)" ]; then
      echo "  backing up before the update"
      scripts/backup.sh "$DIR/backups"
    fi
    git fetch -q origin "$BRANCH"
    git checkout -q "$BRANCH"
    git merge -q --ff-only "origin/$BRANCH"
  fi
  echo "  $(git log --oneline -1)"

  step "Settings (.env)"
  if [ "$UPDATE" = false ]; then
    umask 077
    WEB_PORT=80 scripts/make-production-env.sh "$SITE" > .env
    WORKERS=$(( $(nproc) * 2 + 1 )); [ "$WORKERS" -le 9 ] || WORKERS=9
    sed -i \
      -e "s|^HTTPS_ONLY=.*|HTTPS_ONLY=true|" \
      -e "s|^HSTS_SECONDS=.*|HSTS_SECONDS=3600|" \
      -e "s|^GUNICORN_WORKERS=.*|GUNICORN_WORKERS=$WORKERS|" \
      .env
    echo "  new .env with random secrets"
  fi
  # Older installs may lack these two; add them once.
  grep -q '^SITE_HOST=' .env || printf '\n# The site, served over HTTPS by Caddy (docker-compose.https.yml).\nSITE_HOST=%s\n' "$SITE" >> .env
  grep -q '^COMPOSE_FILE=' .env || printf '# So a plain `docker compose` uses the production files.\nCOMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml:docker-compose.https.yml\n' >> .env
  chmod 600 .env

  step "Build and start (the first build takes 10-20 minutes)"
  docker compose up -d --build --wait --remove-orphans
  docker image prune -f >/dev/null

  if [ "$SKIP_SYSTEM" != true ]; then
    step "Nightly backups"
    cat > /etc/cron.d/spatial-backup <<EOF
# The platform's database and files, every night at 02:30; 14 days are kept.
30 2 * * * root cd $DIR && KEEP_DAYS=14 scripts/backup.sh $DIR/backups >> /var/log/spatial-backup.log 2>&1
EOF
    echo "  02:30 every night into $DIR/backups (copy them off the server too)"
  fi

  step "Check"
  INSECURE=""; [ "$SITE" = localhost ] && INSECURE="-k"
  for _ in $(seq 1 30); do
    if curl -fsS $INSECURE "https://$SITE/api/health/" >/dev/null 2>&1; then
      echo "  https://$SITE answers"
      break
    fi
    sleep 5
  done
  curl -fsS $INSECURE "https://$SITE/api/health/" >/dev/null 2>&1 \
    || echo "  WARNING: https://$SITE doesn't answer yet. If the address was only just pointed here, wait a few minutes; otherwise see 'docker compose logs caddy'."

  if [ "$UPDATE" = true ]; then
    printf '\n\033[1mUpdated.\033[0m\n'
  else
    cat <<EOF

$(printf '\033[1mInstalled.\033[0m')

Next:
  1. Copy $DIR/.env somewhere safe, off this server, now. It holds the
     database passwords and the key for .spp project files.
  2. Create the first system administrator:
       cd $DIR && docker compose exec backend python manage.py createsuperuser
  3. Open https://$SITE, sign in, and add the region, the district and its
     district administrator.
  4. In the field app, the server address is https://$SITE
EOF
  fi
}

main "$@"
