# Security review

**Date:** 2026-10-06. **Scope:** access control (roles and districts), the file-upload surface, sign-in, secrets, and the production configuration.

**What this is:** a review by the developer against the code and its automated tests. **It is not an independent penetration test.** Before the platform holds a district's real ownership data, have someone independent test it; this document tells them where to look.

## Result
No high or critical findings are open. Two medium findings and three low ones are accepted with reasons, below.

## Access control
| Checked | How it is enforced | Evidence |
|---|---|---|
| One district can't read or change another's data | PostgreSQL row-level security on every tenant table; the running application connects as a role that can't bypass it | A cross-district test in every app's test suite, each also checking the table directly, not only the API |
| Roles get exactly their permissions | One matrix (`core/permissions.py`); every endpoint names the permission it needs | `test_permissions.py` checks every role against every permission; each endpoint has a forbidden-role test |
| The matrix in the docs is the real one | — | A test fails if `docs/dev/permissions.md` differs from the code |
| Personal data is limited by role | Restricted fields are removed from every output for roles without `data.sensitive` | `projects/tests/test_privacy.py` covers details, lists, tiles, history, the field package, sync and labels |
| The audit log can't be altered | Written only by a database trigger; the application role has read-only access | `test_audit.py` |
| Field officers can add data but not edit office data freely | Their only write path is sync, which validates like any edit and queues conflicts | `sync/tests/test_sync.py` |

## Uploads
| Risk | Control | Evidence |
|---|---|---|
| Zip bomb | Limits on unpacked size, member count and compression ratio before unpacking | `test_zip_bomb_is_refused` |
| Path traversal in archives and file names | Archive member paths are checked; stored names are reduced to their last component | `test_path_traversal_zip_is_refused`, `test_attachment_files_stay_under_media` |
| Oversized uploads | 500 MB per file (25 MB per photo); nginx refuses more than 600 MB | size tests per endpoint |
| A script uploaded as a "photo" and shown in a browser | Photos must start with JPEG or PNG bytes and match the checksum the device declared; responses carry `nosniff` | `test_only_photos_are_accepted_as_photos` |
| Checklist documents of any type | Always sent as downloads (`Content-Disposition: attachment`), never shown inline | `test_attachments` |
| Malformed GIS files crashing the parser | Parsed in a background job, not the web process; failures are reported on the job | import tests |
| The server fetching an attacker's URL (offline basemap builder) | Only http(s); private, loopback and link-local addresses are refused | `test_tile_addresses_inside_the_servers_network_are_refused` |
| Tampered `.spp` files | Authenticated encryption: any changed byte is refused before anything is read | `test_a_file_with_one_changed_byte_is_rejected` |
| Flooding with uploads | 120 uploads an hour per user | `test_uploads_have_their_own_tighter_limit` |

## Sign-in and sessions
| Checked | Control |
|---|---|
| Password guessing | Account locks for 15 minutes after 5 wrong passwords; 10 sign-in attempts a minute per address |
| Token theft | Access tokens last 15 minutes; refresh tokens rotate and the old one is blacklisted |
| Weak passwords | Django's validators (length, common passwords, similarity to the email) |
| Sign-in on a lost phone | The field app asks for the password every time it starts; the stored check is a salted, slow hash in the phone's secure storage |

## Secrets and configuration
| Checked | Control |
|---|---|
| Running production with example secrets | The server refuses to start (`core/checks.py`) |
| API keys for map providers | Encrypted at rest; never returned by the API |
| `.spp` organisation key | Only in the server's environment; never sent to any client |
| Debug pages | Off in production; the production start-up test checks no debug page is served |
| HTTPS | Expected in front of the platform; `HTTPS_ONLY` and HSTS are settings |
| Clickjacking, MIME sniffing | `X-Frame-Options: DENY`, `nosniff` |

## Findings accepted for now
| # | Severity | Finding | Why it is accepted | What would close it |
|---|---|---|---|---|
| 1 | Medium | Reading data is not logged. The audit log records changes, not who viewed an owner's name. | Restricted fields limit who can view. Read logging is a significant addition. | An access log for restricted values. |
| 2 | Medium | Keys for Google and Bing basemaps reach the browser, because the map tiles are requested from there. | It is how those services work. | Restrict each key to the site's address in the provider's console (documented in the basemaps guide). |
| 3 | Low | Free-text notes and photos from the field are not covered by restricted fields. | They are not structured fields. | Guidance to field officers (in the data-protection guide); a per-layer switch later. |
| 4 | Low | No two-factor sign-in. | Lockout and rate limits are in place. | Add TOTP for administrators. |
| 5 | Low | Rate limits are per user and per address, not per district. One heavy user can't starve others at the application level, but there is no server-level protection against a large flood. | That belongs in front of the application. | A firewall or the hosting provider's protection. |

## Not reviewed
- The server's operating system, firewall and Docker host.
- Third-party libraries beyond keeping to current versions.
- The Android app on a compromised (rooted) phone.
