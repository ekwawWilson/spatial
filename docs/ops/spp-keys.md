# Organisation keys for .spp files

*System administrators and whoever runs the servers.*

A `.spp` file is encrypted. Each file has its own random key, and that key is locked with the **organisation key**. A server can open a file only if it holds the organisation key the file was locked with.

- The key lives in the server's secrets (`SPP_ORG_KEYS` in `.env`). It is never sent to a browser or the field app.
- **Without the key, .spp files can't be opened by anyone.** Keep a copy somewhere safe and separate from the server (for example, printed and sealed in the Assembly's safe, or in a password manager).
- Anyone who has both the key and a file can read that file. Treat the key like the keys to the records office.

## The setting
```
SPP_ORG_KEYS=key_id:base64key,older_id:base64key
```
- The **first** key is the active one: new files are locked with it.
- The other keys are kept only so older files still open.
- A key id is a name you choose (letters, digits, `.`, `_`, `-`). It is written in each file, in the clear, so a server can say which key a file needs. Don't put anything secret in it.

## Making the first key
On the server, in the project folder:
```
docker compose exec backend python manage.py spp_key generate --id assembly-2026
```
This prints one `key_id:base64key` entry. Put it in `.env` as `SPP_ORG_KEYS=...`, then restart:
```
docker compose up -d backend worker
```
To have the command write the entry into an env file itself (it becomes the first key, existing keys are kept, and the file's permissions are set to owner-only):
```
python manage.py spp_key generate --id assembly-2026 --write-env /path/to/.env
```
Inside the container the project's `.env` isn't mounted, so with Docker use the first form and edit `.env` on the host.

`make env` adds a throwaway development key when `SPP_ORG_KEYS` is empty. Don't use that key for real work.

## Checking which keys a server has
```
docker compose exec backend python manage.py spp_key list
```
It prints each key's id and a **fingerprint** (never the key). System administrators can see the same list at `GET /api/spp/keys/`. Two servers hold the same key exactly when the id and the fingerprint both match.

## Sharing a key between servers
Servers that must open each other's files need the same key.
1. Copy the `key_id:base64key` entry from the first server's `.env`.
2. Send it over a secure channel: in person, or with an encrypted tool. Not by plain email or chat.
3. Put it in the other server's `SPP_ORG_KEYS` and restart that server's backend and worker. If that server should also write files the first server can open, make it the first entry there too.
4. Compare fingerprints on both servers (`spp_key list`).

If a server should be able to **open** another organisation's files but not write files under that key, add the key after its own first key.

## Changing the key (rotation)
Change the key when someone who knew it leaves, or on a schedule you choose.
1. Generate a new key with a new id.
2. Put it **first** in `SPP_ORG_KEYS` and keep the old entry after it.
3. Restart, and repeat on every server that shares the key.

Old files keep opening because the old key is still listed. New files use the new key. Files are not re-encrypted: to move an old file to the new key, open it and save it again. Remove an old key only when no file locked with it is still needed, because after that those files can't be opened.

## If a key is lost or leaked
- **Lost** (and no copy anywhere): files locked with it can't be recovered. Projects that still exist on a server are unaffected; save them again under a new key.
- **Leaked:** rotate straight away. Files already locked with the leaked key stay readable to whoever has both the key and a copy of the file, so treat those copies as disclosed.

## How the protection works
For those who need to assess it:
- AES-256-GCM. A random 256-bit data key per file encrypts the contents in 1 MiB chunks; the organisation key encrypts ("wraps") the data key.
- Every chunk is authenticated together with the file's header, its position and whether it is the last chunk. Changing, reordering, removing or truncating any part is detected and the file is refused.
- The only readable parts of a file are a fixed signature, the format version, the key id, a random file id and the sizes.
- The code is in `backend/spp/container.py` (format) and `backend/spp/keys.py` (keys).
