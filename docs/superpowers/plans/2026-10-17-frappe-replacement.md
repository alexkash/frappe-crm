# Frappe replacement implementation plan

> **For agentic workers:** Use superpowers:executing-plans for inline execution;
> independent agents review configuration and safety without mutating shared state.

**Goal:** Replace BottleCRM with a clean Frappe CRM installation, preserve keys
and Git history, and remove the old destination stack after verification.

**Architecture:** Independent production Compose project using the pinned CRM
v1.88.0 image, MariaDB, separate Redis cache/queue, Frappe background services and
Caddy. Store secrets outside the repository and transfer existing TLS state at
cutover. No SuiteCRM migration in this change.

**Tech stack:** Frappe/CRM, Docker Compose, MariaDB, Redis, Caddy, GitHub.

**Spec:** `docs/superpowers/specs/2026-10-17-frappe-replacement-design.md`.

## Execution ledger

- Old code and the deployed authentication overlay are pushed under tag
  `bottlecrm-final-20261017` (commit `20c6e5798fe51181b0556522f6ec16812135c3fe`).
- All six environment files and enumerated long-lived database/runtime keys
  were exported under `/etc/recuite/credentials/bottlecrm` and read-back verified.
- Upstream frontend verification: 26 files / 294 tests passed.
- Ruling: build the CRM app explicitly on the inspected Framework 15.123.1 /
  Node 22.23.3 foundation. Both published `v1.88.0` and `stable` resolve to the
  same image without `apps/crm`; the builder stopped accepting the workflow's
  obsolete `APPS_JSON_BASE64` argument. The fork's Dockerfile and image workflow
  now install the fork source explicitly and fail if app/assets/version are missing.
- Ruling: retain only current keys and shared TLS state; the user explicitly
  rejected a database/file archive and chose future migration from live SuiteCRM.

## Global constraints

- No old database/file archive; Git is the requested code preservation method.
- Never commit or print credentials. Retain keys under root-only `/etc/recuite/credentials`.
- Do not touch the live SuiteCRM source. Do not migrate or create customer records.
- Preserve other worktrees and the existing domain/HTTPS identity.
- Old resources may be deleted only after the new site's checks pass.

## Review focus

- Old code differs from the local branch: preserve deployed billing/authentication too.
- A new stack must not claim 80/443 before TLS transfer and cutover.
- Keep database/Redis ports private; persistent volumes must survive app restarts.
- Passwords, SMTP tokens and encryption keys must remain usable after old files disappear.
- Cleanup must not delete the new stack, retained credentials, TLS data or SuiteCRM source.

## Tasks

- [x] Commit and push the old changes; preserve the deployed authentication source in the final old tag.
- [x] Create `alexkash/frappe-crm`; switch this worktree to stable upstream CRM.
- [x] Enumerate and export the six environment files plus long-lived DB/runtime keys; compare copies.
- [ ] Validate `ops/recuite/compose.yaml` with a protected generated env file, inspect baked image scripts and review independently.
- [ ] Run upstream `cd frontend && yarn test:run` using its documented sibling Frappe UI dependency.
- [ ] Install the new services under `/opt/frappe-crm`, create `crm.recuite.com`, keep email/scheduler paused during initialization.
- [ ] Verify internal ping/login/assets and empty CRM tables; configure Cloudflare SMTP with SSL465 and validate authentication without mail delivery.
- [ ] Copy and verify Caddy TLS state, switch the proxy, verify authenticated HTTPS and background health; enable normal background/mail operation.
- [ ] Export new Frappe credentials/site encryption config, save non-secret deployment evidence and commit/push operational files to the fork.
- [ ] Remove only old `/opt/crm`, enumerated old containers/volumes/networks/images and obsolete scheduled jobs; verify old resources are absent and Frappe still works.
