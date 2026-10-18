# Company document continuation — 2026-10-18

Status: PR #1 is preparing the production billing release. The local-only
restriction below records the earlier QA handoff and is superseded by the user
authorization to merge and deploy. Follow `ua-billing-rollout-20261018.md`; the PR
records the final source, image and deployment receipt. Historical invoice
archive and migration imports remain with the migration coordinator.

The following verification and window-release observations are historical.

## Scope and integration

Company document rows offer invoice creation from active contracts and act
creation from submitted invoices. Draft invoices open for continued editing.
The existing date/item confirmation and server creation APIs remain authoritative;
opening an action link never issues or creates a financial document by itself.

Desk forms show permission-filtered related documents and a return link to the
company's corresponding Documents tab. Contract creation stays visible when the
default bank selection makes a saved form dirty; attempting creation asks the
user to save first. Draft invoices explain that issuance precedes act creation.

Desktop/mobile tabs wait for asynchronous billing capabilities. Source identity
and refresh guards discard delayed responses after document navigation, including
the source-bound creation dialog. Related labels are escaped and IDs encoded.

Base branch commit: `060ea31fdd66666f6e2c6d5460d8a832b1c1ded4`.
Integrate the scoped continuation commit into the migration coordinator's branch;
do not replace its full CRM/addon tree with this checkout. Preserve communication
guards and historical-archive changes, especially concurrent additions to
`api.py` and `OrganizationDocuments.vue`. Rebuild the CRM frontend after integration.
No schema migration or dependency change is required by this continuation patch.

## Verification

- Frontend: 308/308 tests; includes nine continuation regression cases.
- Billing: 85/85 complete app tests; final API module 5/5 after the reader-role
  capability assertion was strengthened. No backend runtime change followed.
- Vue production build, scoped ESLint, Ruff and JS syntax checks passed.
- One independent reviewer found two Important issues: cold capability loading
  could reset the requested tab; a delayed context response could mix documents.
  Both were reproduced RED and fixed GREEN, followed by the complete frontend suite.
- Chrome desktop and 390×844: company → contract action → invoice draft → native
  issuance/PDF → act draft → company Documents. Cold return preserved the selected
  document kind. Browser loaded final entry `index-B_-uSEvV.js`.
- Private final probe: one QA invoice, one QA act, invoice PDF bytes match stored
  SHA; Email Queue 0 and Communication 0; mail muted and scheduler paused.
- Console: expected Socket.IO errors because the private stack has no realtime
  service, plus unrelated Chrome-extension errors. No document-flow error observed.

Known minor: the explicit company return link opens page 1 of the current document
kind. Browser Back retains the originating query/pagination. Live realtime updates
and production delivery/deployment were not tested here.

## Runtime and window release

Private project: `recuite-billing-flow-20261018`.
Site/database: `billing-flow.localhost` / `billing_flow_20261018`.
Evidence/config/logs/retained synthetic volumes:
`/opt/frappe-crm/billing-flow/20261018/` on VPS `crm`.

All five private services (job, web, DB and both Redis services) are stopped.
Fresh release observation: MemAvailable 2155 MiB, above the 2048MiB start guard.
The local SSH tunnel and agent-created QA tab are closed. No further VPS jobs
will be started by this billing-flow task. No production services/config/data or
other sessions' test projects were stopped or changed.

There is **no separate immutable billing-flow image**. QA used this guard candidate
plus read-only addon and compiled frontend overlays:
`sha256:2aa599e379c1504f573c85dd77519fa72c9db24075bd7ff6acbda866488104b2`.
This is not a deployable image containing the continuation patch; the migration
coordinator must build and verify the final combined image.

Local source hashes match the privately tested addon:

- `api.py`: `e489de98810d8e58132fc06aed8be92c06bf2e527a3cd96377891997d4ed4a3f`
- `public/js/billing.js`: `1a7b1af27b364abd89934cefa1f35cc94a8789d8235de0c0a67b257294d9a332`

Unrelated dirty `AGENTS.md`/the earlier billing plan are excluded from this runtime
commit. The user-requested removal of the obsolete coordination gate remains in
the local AGENTS files alongside their pre-existing project-boundary edits.

## Follow-up: partial periods

Ponytail review found that an empty date suggestion also occurs after a document
covers only part of a calendar period. The form now permits manual dates instead
of treating that response as proof of full coverage. Existing server overlap,
quantity and issuance checks are unchanged.

Three new regression cases were observed RED then GREEN: manual invoice and act
creation for January 16–31 with an empty suggestion, and denial when no invoice
quantity remains. They check the explicit creation payload and destination too.
Final local frontend 311/311; scoped ESLint, JS syntax and whitespace checks pass.
No VPS services, production data or migration/archive files were touched for this
follow-up. Combine this follow-up commit with the coordinator's imported flow
commit before final acceptance; no separate flow image has been built here.

## PR integration and bot review

PR1 uses a clean `main`-based branch (`alexkash/billing-flow-release`) with the
already installed billing baseline and this flow; migration/archive work is
excluded. Codex review reproduced stale contract/product/bank selection responses
and JSON-encoded grouped PDF requests. Source-bound guards now cover both invoice
and act source loaders, product rows and bank choices; grouped PDF routing parses
the RPC object before deciding between saved billing archives and native printing.
Eight asynchronous selection/control cases and one real-runtime grouped-PDF test
were added. The local PDF routing probe was observed RED then GREEN.

CodeRabbit's ten comments covered the CI/l10n findings. User-facing messages use
Frappe translation functions and whitelisted print arguments have compatible type
annotations. Standalone synthetic QA programs run under `main()`; audited actor,
commit, native-guest delegation and v15 File-subclass exceptions use specific
Semgrep rule IDs with explanations. No scan paths/rules were disabled.
Local frontend319/319, scoped lints/format/syntax and the complete addon/QA Frappe
Semgrep ruleset pass. Updated GitHub/runtime acceptance and rollout are pending.

The second Codex review found an optional empty act cadence could survive invoice
issuance and block future acts. Issuance now rejects unsupported/empty cadences
while incomplete drafts remain editable; DocType JSON is unchanged. The new real
Frappe regression was observed FAIL without the guard and PASS with the exact
updated validator, including draft status and no allocated invoice number.
