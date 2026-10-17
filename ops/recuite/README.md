# Recuite Frappe CRM

Frappe CRM v1.88.0 is installed explicitly from the fork by `Dockerfile`, on a
digest-pinned Framework 15.123.1 / Node 22.23.3 base. The published upstream CRM
v1.88.0 image was inspected and contains no CRM app: its workflow passes an
obsolete build argument that the current builder ignores. Mandatory app/version
and compiled-asset checks prevent repeating that failure. This is a clean
installation at `https://crm.recuite.com/crm`; SuiteCRM migration is separate work.
Production files live in `/opt/frappe-crm`. No customer data or credentials belong
in this repository. The previous code is preserved in
[`alexkash/Django-CRM`, tag `bottlecrm-final-20261017`](https://github.com/alexkash/Django-CRM/tree/bottlecrm-final-20261017).

Run Compose as root, without printing its expanded configuration:

```sh
cd /opt/frappe-crm
docker build -f Dockerfile -t recuite/crm:v1.88.0-20261017 .
docker compose --env-file /etc/recuite/credentials/frappe.env config --quiet
docker compose --env-file /etc/recuite/credentials/frappe.env up -d db redis-cache redis-queue
docker compose --env-file /etc/recuite/credentials/frappe.env run --rm configurator
docker compose --env-file /etc/recuite/credentials/frappe.env --profile setup run --rm create-site
docker compose --env-file /etc/recuite/credentials/frappe.env up -d backend websocket queue-short queue-long scheduler frontend
```

For this one-time clean installation, run `initialize_site.py` inside the backend
from `/home/frappe/frappe-bench/sites`, using `../env/bin/python`. Pass a JSON
object with `smtp_password` through stdin from the protected credential store;
never put the password in command arguments or logs. The script requires paused
email/scheduler and empty CRM tables. It runs Framework setup with Ukraine,
Europe/Kyiv and UAH defaults, excluding the CRM task that creates demo records.
It then validates the retained Cloudflare SMTP account without sending mail.
The `set-config -p` CLI in this Framework release parses Python literals: use
`True` and `False`, not lowercase JSON booleans.

The public proxy has its own profile so it cannot take ports 80/443 before
cutover. Before its first start, transfer the existing Caddy TLS data into
`recuite_caddy_data`, verify the copy and create `recuite_caddy_config`. Then stop
the old proxy and start the new one:

```sh
docker compose --env-file /etc/recuite/credentials/frappe.env --profile public up -d proxy
```

Verify public HTTPS, authenticated access, static assets, websocket handshake,
worker/scheduler health, zero customer records and SMTP authentication. Saving
an Email Account validates SMTP without sending mail. Keep outgoing mail muted
until initialization checks pass; then enable the scheduler and outgoing mail.
Use `bench --site crm.recuite.com set-config -p pause_scheduler False`,
`bench --site crm.recuite.com set-config -p mute_emails False` and
`bench --site crm.recuite.com enable-scheduler` for that final step.

Current and previous credentials are retained under `/etc/recuite/credentials`.
The BottleCRM credentials subdirectory contains six original environment files
and `runtime-and-database-keys.json`, with a non-secret manifest. It is not a
database archive. Frappe credentials include its independent database/admin
passwords and the site encryption key. Do not copy old Django signing keys into
Frappe. Do not revoke external credentials as part of cleanup.
Three previous environment configurations were also retained under
`bottlecrm/previous-config-keys`, including previous integration keys.

After the new site passes, the authorized cleanup removes `/opt/crm`, old app and
migration containers, PostgreSQL/Redis/snapshot volumes, old networks, old
`crm-backend:*` and `crm-frontend:*` images and obsolete backup jobs. Preserve
only the exported credentials and the transferred shared TLS state. Do not run
global `docker system prune --volumes` or touch the live SuiteCRM source server.

For future changes, use `git push frappe HEAD:main`; `origin` still identifies
the previous Django repository because this directory is an existing worktree.
Other worktrees retain their Django branches. Fetch upstream Frappe changes
through `frappe-upstream`; review and test before updating the pinned image.
The fork's image workflow uses this same Dockerfile and its own source ref.
