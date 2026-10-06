# Backups and restoring

*Whoever runs the server.*

## What a backup holds
`scripts/backup.sh` makes a folder named by date and time with:
- `db.dump`: the whole database, every district;
- `media.tar`: every uploaded file (checklist documents, field photos, imagery);
- `manifest.txt`: when it was taken, sizes, and checksums.

It does **not** hold `.env`. Keep a copy of `.env` yourself, somewhere safe and separate: it has the database passwords and the organisation key for `.spp` files.

## Taking backups
```bash
scripts/backup.sh /srv/spatial-backups
```
Backups older than 14 days are removed (`KEEP_DAYS=30 scripts/backup.sh ...` to keep more).

Run it every night from cron, then copy the folder **off the server** (another machine, or cloud storage). A backup on the same disk doesn't survive that disk failing.
```
30 0 * * *  cd /srv/spatial && scripts/backup.sh /srv/spatial-backups >> /var/log/spatial-backup.log 2>&1
```
The platform keeps working while a backup runs.

## Restoring
Restoring **replaces everything** in the running database and uploaded files with the backup.
```bash
scripts/restore.sh /srv/spatial-backups/20261006-003000 --yes
```
It checks the backup's checksums first and refuses a damaged one, stops the application, restores the database and files, and starts the application again.

On a **new server**: install the platform first ([deployment](deployment.md)) using the **same `.env`** as the old server, then restore.

## Test your backups
A backup that has never been restored is a hope, not a backup. The pipeline proves the mechanism on every change (`scripts/qa-phase-13-restore.sh`: back up, restore into an empty second stack, compare every feature, the audit log and every file). Still, restore one of **your** backups to a test server a few times a year.

## What is not covered
- Changes made after the last backup are lost in a disaster. With nightly backups that is up to a day of work.
- Captures still on field officers' phones and not yet synced are not on the server, so not in any backup.
