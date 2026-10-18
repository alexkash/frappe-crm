# Ukrainian billing for Frappe CRM

Independent Frappe app `recuite_billing`, installed alongside `crm` on the same
site. Requires Framework 15.123.1+ (v15) and CRM 1.88.0+. It uses CRM Organization
and CRM Product, adds Ukrainian legal requisites without changing their standard
schemas, and registers the Billing module and document workspace.

## Development

Never install or run tests on the production site. Use the dedicated
`ops/recuite/billing-test/compose.yaml` project with new volumes and its private
network. Its services have resource limits and mail/scheduler remain disabled.
Only the frontend binds a port, on `127.0.0.1:18082`.

Create a protected env file outside Git with newly generated
`BILLING_TEST_DB_PASSWORD`, `BILLING_TEST_ADMIN_PASSWORD`, and
`BILLING_TEST_SOURCE_PATH` (absolute source checkout). No production credential
or site volume is used. The CI workflow demonstrates synthetic env generation.
Do not print expanded Compose configuration containing those passwords.

Build `ops/recuite/billing-test/Dockerfile` with this repository as context.
It preserves the pinned Framework backend and prepares the separately pinned
compatible Framework UI source before building CRM assets. The test-only
`Dockerfile.runtime` can overlay source on the already verified local
`recuite/crm:v1.88.0-20261017` image when an operator has checked its image ID;
it does not update that base image or existing deployments.

With the chosen env/config passed to `docker compose`, start `db`,
`redis-cache`, `redis-queue`, then run `bootstrap` once. It refuses an existing
site rather than resetting it. Run subsequent migrations explicitly with
`run --rm -T --entrypoint bench backend --site test_site migrate`.

Billing tests use:

```sh
docker compose --env-file /path/to/test.env -f ops/recuite/billing-test/compose.yaml run --rm -T --entrypoint /home/frappe/frappe-bench/env/bin/python backend /opt/billing-test/run_tests.py
```

The wrapper checks the actual unittest summary: this Framework version can
return exit code zero even when tests fail. Add `--module
recuite_billing.tests.test_install` to select a module. The app's pure unit
tests can also run outside Frappe with
`PYTHONPATH=extensions/recuite_billing python3 -m unittest discover -s
extensions/recuite_billing/recuite_billing/tests -p test_calculations.py -v`;
use `test_periods.py`, `test_amount_in_words.py` or `test_validations.py`
for the other pure modules.

Stop only this Compose project when finished. Keep its volumes and failure
evidence; deleting them is an explicit cleanup decision. Never use global Docker
prune or production/migration resource names for test cleanup.

User workflow: [Українські рахунки та акти](../../docs/feats/ua-billing.md).

The locally compiled runtime overlay expects `ops/recuite/billing-test/.frontend-build/`
containing the output of `yarn --cwd frontend build` (`crm/public/frontend/`).
Use a new tag for each reviewed image and set `BILLING_TEST_IMAGE` for Compose.
This overlay verifies current Python and compiled assets without rebuilding the
large frontend on a small shared VPS. The clean CI Dockerfile installs the locked
frontend dependencies and builds from source. Neither process deploys production.

`qa_acceptance.py` creates only synthetic test documents and exports PDFs into the
private `test_site/private/billing-qa` directory. `qa_restore.py` refuses an existing
restore target, backs up this isolated site's database/public/private files and
verifies hashes, images, contract attachment and roles in `billing_restore_test`.
Run the restore script through the `bootstrap` service (override its command), so
only that disposable process receives the new test database/admin credentials.
