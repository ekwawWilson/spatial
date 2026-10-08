# Installing on a DigitalOcean droplet

*Whoever sets up the Assembly's hosting.* About an hour, most of it waiting for the first build.

One script, `scripts/server-setup.sh`, turns a new Ubuntu droplet into a running site with HTTPS, a firewall, automatic security updates and nightly backups. The general guide, [installing the platform on a server](deployment.md), explains the parts; this page is the short route on DigitalOcean.

## 1. Create the droplet
In the DigitalOcean control panel, **Create → Droplets**:

| Choice | Pick |
|---|---|
| Region | **London (LON1)** or **Frankfurt (FRA1)**: DigitalOcean has no African region, and these are the closest to Ghana. |
| Image | **Ubuntu 24.04 (LTS) x64** |
| Size | **Basic, Regular: 4 vCPUs, 8 GB memory, 160 GB disk** (about US$48 a month; check the current price). Smaller sizes run, but builds are slow and imagery fills 2 GB-memory machines. |
| Authentication | **SSH key** (add yours). Not a password. |
| Backups | **On** (weekly, about 20% extra). A second safety net besides the platform's own nightly backup. |
| Monitoring | **On** (free): CPU, memory and disk graphs, and alerts. |

Note the droplet's **IP address** when it's ready.

## 2. Point the site's address at it
At whoever manages the Assembly's domain, add a DNS **A record**: the site's name, for example `planning.<assembly>.gov.gh`, with the droplet's IP address. It can take from a few minutes to a few hours to take effect; `ping planning.<assembly>.gov.gh` shows the droplet's IP when it has.

No domain yet? Leave the address out in step 3. The script then uses the droplet's IP through sslip.io (for example `203-0-113-5.sslip.io`), which gets a real HTTPS certificate. That's fine for trying the platform out; move to the real address before the Assembly relies on it ([changing the address](#changing-the-address)).

## 3. Run the install
Connect to the droplet (`ssh root@<droplet IP>`, or **Console** in the control panel) and run, with the real address:

```bash
curl -fsSL https://raw.githubusercontent.com/ekwawWilson/spatial/main/scripts/server-setup.sh | bash -s -- planning.<assembly>.gov.gh
```

It:
1. adds 4 GB of swap, installs Docker, and turns on automatic security updates;
2. turns on the firewall: only SSH (22), HTTP (80) and HTTPS (443) are open;
3. puts the platform in `/opt/spatial` and makes `/opt/spatial/.env` with random secrets;
4. builds and starts everything, with Caddy in front getting the HTTPS certificate from Let's Encrypt (the first build takes 10-20 minutes);
5. sets a backup for 02:30 every night into `/opt/spatial/backups`, keeping 14 days;
6. checks the site answers over HTTPS.

## 4. First steps
The script ends with these; do them straight away.

1. **Copy `/opt/spatial/.env` off the server** to somewhere safe (a password manager, or an encrypted drive kept by the Assembly). It holds the database passwords and the key for `.spp` project files. If the droplet is lost and this file with it, `.spp` files can't be opened by anyone. From your own computer:
   ```bash
   scp root@<droplet IP>:/opt/spatial/.env spatial-production.env
   ```
2. **Create the first system administrator**:
   ```bash
   cd /opt/spatial && docker compose exec backend python manage.py createsuperuser
   ```
3. **Open the site**, sign in, and add the region, the district and its district administrator (user guide, System administration).
4. **The field app**: the server address is `https://planning.<assembly>.gov.gh`.

## Updating
Run the same command again, on the droplet:
```bash
curl -fsSL https://raw.githubusercontent.com/ekwawWilson/spatial/main/scripts/server-setup.sh | bash
```
It backs up first, then fetches the newest code, rebuilds and restarts. `.env` is never replaced. Install only versions whose automatic tests passed ([CI/CD](deployment.md#automatic-testing-and-safe-updates-cicd)).

## Day to day
On the droplet, in `/opt/spatial`, a plain `docker compose` works with the production set-up:

| To | Run |
|---|---|
| See what's running | `docker compose ps` |
| Read the logs | `docker compose logs --tail=100 backend` (or `worker`, `web`, `caddy`) |
| Back up now | `scripts/backup.sh /opt/spatial/backups` |
| Check last night's backup | `tail /var/log/spatial-backup.log` |
| Restart | `docker compose restart` |
| Check the installation | `scripts/qa-server-setup.sh` (it adds a test administrator, `first.admin@example.test`; delete it afterwards) |

**Backups off the droplet.** The nightly backups sit on the droplet itself, so they don't survive losing it. DigitalOcean's weekly droplet backup covers that partly; for the platform's own backups, copy `/opt/spatial/backups` regularly to DigitalOcean Spaces (for example with `rclone`) or to a machine at the Assembly. [Backup and restore](backup-restore.md) explains restoring.

**Disk.** Drone imagery is large. When the disk passes about 70% (the monitoring graphs show it), resize the droplet or attach a Volume.

## Changing the address
To move from the sslip.io address to the real one (or between real ones): point the new name at the droplet (step 2), then in `/opt/spatial/.env` change the address in `SITE_HOST`, `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS` and `WEB_APP_URL`, and run `docker compose up -d`. Caddy gets the new certificate by itself. Field officers change the server address in the app.

## If something goes wrong
- **The site doesn't answer over HTTPS.** Usually the address doesn't point at the droplet yet: `docker compose logs caddy` shows Let's Encrypt failing. Fix the DNS record; Caddy keeps trying.
- **The build stopped with an out-of-memory error.** Use the size above, or run the command again (the swap is there by then).
- **The server won't start, and the backend log names a setting.** The start-up checks refuse example secrets and missing addresses; fix that line in `.env` ([settings to review](deployment.md#settings-to-review-in-env)).
