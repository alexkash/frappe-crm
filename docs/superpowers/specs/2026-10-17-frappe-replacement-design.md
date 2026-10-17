# Frappe replacement design

User authorization: replace the codebase with a fork of `frappe/crm`, install it
on the existing VPS and domain, preserve all keys, and eventually remove every
old BottleCRM application/data resource from the destination. The user explicitly
declined a data archive and chose Git preservation. Migration will be from the
live SuiteCRM source in separate work.

Use stable CRM v1.88.0, an independent Compose project and a new MariaDB database.
Retain shared HTTPS infrastructure by moving Caddy TLS state into new named
volumes. Preserve six known environment files and the enumerated long-lived
database/runtime credentials under `/etc/recuite/credentials/bottlecrm`, accessible
only to root. Never publish secrets, old databases, uploads or SQL snapshots.

Preserve final old code, including billing and deployed authentication changes,
in `alexkash/Django-CRM` with tag `bottlecrm-final-20261017`. The new fork is
`alexkash/frappe-crm`. Switch only this worktree to `frappe-main`; leave the old
repository's other worktrees and remotes functional.

Keep the old stack intact until new Frappe initialization, TLS, authentication,
assets, background processes and SMTP authentication pass. SMTP tests send no
messages. No customer records are migrated or created for smoke testing. After
cutover, remove only enumerated old CRM resources, preserving exported keys and
the live SuiteCRM source. New Frappe site configuration/encryption keys must also
be retained securely. No ERPNext, WhatsApp or business feature development is in
scope.
