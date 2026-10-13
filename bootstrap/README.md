# Owner Bootstrap runbook

Run this **after merge** from the repository root:

```bash
./scripts/bootstrap-wizard.sh
```

The owner runs the wizard and every apply. The agent verifies configuration, mocked plans and static script contracts only. CI never applies Bootstrap. #24 stays open until the owner supplies real authorization and setup evidence. The Break-glass identity, human owner and Default identity-domain sign-on/MFA policies stay unmanaged. Enable owner MFA manually and verify Break-glass access before provisioning.

Install Terraform from `.terraform-version`, OCI CLI, OpenSSL, GitHub CLI, and Python 3. Authenticate `gh` with permission to set repository variables and Environment secrets. GitHub protection/Environment features must be available for this repository's visibility and plan. Work from a trusted local checkout without shell tracing or terminal recording. The wizard disables tracing and Terraform debug logging before handling keys.

## Confirmed value inventory

The owner confirmed this ordered inventory before stages were authored, including the later addition of distinct pipeline primary emails. All local procedure files are under ignored `.bootstrap/`, with a private directory and mode-0600 configuration/key files. Public identifiers are stored as GitHub secrets where workflows require them. Private PEM contents never go into dotenv, tfvars, backend configuration, Terraform outputs, plans or state.

| Stage | Source → destination | Classification |
| --- | --- | --- |
| 1. Tenancy/repository | OCI Tenancy details: `TENANCY_OCID`, `HOME_REGION`; GitHub: `GITHUB_REPOSITORY`, `OWNER_LOGIN` → `.bootstrap/wizard.env`; tenancy and region also → public tfvars | Public identifiers |
| 2. Owner session/MFA | `oci session authenticate`: profile/config path → wizard env; session token and session private key → OCI CLI files only | Credentials secret; profile/path public |
| 3. Local pipeline keys | OpenSSL → `.bootstrap/keys/{apply,plan}.pem` and `.public.pem`; fingerprints → wizard env | Private PEM secret; public PEM/fingerprint public |
| 4. Public inputs | Owner-chosen bucket name, owner-session namespace lookup, and two distinct owner-controlled primary emails (`APPLY_USER_EMAIL`, `PLAN_USER_EMAIL`) → wizard env and `.bootstrap/root/owner.auto.tfvars.json`; emails also appear in state/plans and `bootstrap_inputs` for CI | Non-credential values |
| 5. Manual apply | Terraform `setup` output: compartment/user IDs, bucket/namespace, group/policy IDs → `.bootstrap/setup.json`; compartment/user IDs also → wizard env | Public |
| 6. Authorization | Owner real permission probes → owner evidence/checklist; verified `IAM_EXCLUSION_MODE` → wizard env/public tfvars | Public evidence; never record credentials |
| 7. Migration | Bucket/namespace → `.bootstrap/backend.hcl`; key is fixed in each Root's backend | Public; state sensitive |
| 8. No-change plan | Successful remote plan and state HEAD → confirmation before deleting local state/backup | No new captured values |
| 9. Protection/Environments | Workflow check names and owner login → manually configured GitHub settings | Public settings |
| 10. CI credentials | Pipeline identity identifiers/region and local private PEM → five `OCI_*` secrets in each Environment; bucket/namespace → `TF_STATE_BUCKET`, `TF_STATE_NAMESPACE` repository variables | PEM secret; other values public |
| 11. First PR plan | GitHub PR/run URLs → `FIRST_PLAN_PR_URL`, `FIRST_PLAN_RUN_URL` in wizard env and owner evidence | Public |
| 12. Rotation | Owner key-installation dates → wizard env and `OCI_APPLY_ROTATED_ON`, `OCI_PLAN_ROTATED_ON` repository variables | Public UTC dates |

The local pipeline CLI configuration is generated from public identifiers and **private-key paths**, never private PEM contents. No session token is copied into wizard persistence. Fingerprints are derived locally from the public PEM. The wizard opens documentation/Console URLs before requesting values. It confirms applies, migration, state deletion and secret installation separately.

## Local apply, migration and later changes

First setup copies Bootstrap's `.tf` files and committed provider lock to `.bootstrap/root`, leaving out `backend.tf`. It writes public inputs only, initializes local state, shows a plan, and asks the owner to approve an interactive apply. Users, groups and policies are tenancy-scoped in OCI; Bootstrap owns them although the physical compartment holds only state. The state bucket is private, versioned, `prevent_destroy`, Oracle encrypted, and untagged. No extra locking resource is created. Check inherited tag defaults with the owner before applying: Bootstrap must stay untagged.

The wizard authenticates a short-lived owner session in **`~/.oci/config`**. The pinned Terraform backend/provider load SecurityToken profiles from that path; a custom CLI config path is unsupported in this procedure. It exports `OCI_AUTH`, `OCI_CONFIG_FILE_PROFILE`, `OCI_REGION` for the provider and matching lowercase `OCI_auth`, `OCI_config_file_profile`, `OCI_region` for the backend. No credentials, auth type or profile are passed through `-backend-config`. Refresh an expired session by re-running authentication before planning/applying; never replace it with a standing personal key.

After permission verification, the wizard copies the checked-in `backend.tf` into the local working Root and runs:

```bash
terraform -chdir=.bootstrap/root init -migrate-state -lockfile=readonly -backend-config="$PWD/.bootstrap/backend.hcl"
terraform -chdir=.bootstrap/root plan -input=false -detailed-exitcode
```

Only exit **0** allows deletion of local `terraform.tfstate` and `terraform.tfstate.backup`; exit 2 means changes, exit 1 means failure. The wizard also checks the remote state object exists. Never use `-force-copy`, delete local state before verification, remove `.terraform` backend metadata mid-migration, or reset a partially migrated working directory. Re-running the wizard preserves its working state/backend and key pairs. An interrupted migration resumes with `init -migrate-state` and its native confirmation.

Later Bootstrap changes use the same protected working Root, owner session, remote backend and reviewed manual plan/apply. Re-running copies the latest resource configuration without removing the active backend. Foundation and Workloads have separate `foundation/terraform.tfstate` and `workloads/terraform.tfstate` keys, and must initialize without requiring Foundation outputs before its first apply. Bootstrap's `bootstrap_inputs` output contains public inputs; PR plans read it after backend initialization. A first PR plan cannot succeed before owner provisioning/migration.

## Real permission evidence

Mocks verify Terraform contracts, **not OCI authorization**. Do this after merge and before migration/CI credentials are installed. Wait for IAM propagation. Use only generated pipeline users with no extra group memberships, administrative roles, or unrelated policies. Keep evidence in #24: timestamp, acting identity, command/operation, target, expected/actual result and OCI request ID. Redact credentials and object bodies. Use a separate scratch compartment/resource for positive write checks and negative Plan writes; the owner owns cleanup.

The wizard writes `.bootstrap/pipeline.config` with `apply` and `plan` profiles referencing the local PEM files. For example:

```bash
oci os bucket get --config-file .bootstrap/pipeline.config --profile apply --auth api_key --namespace-name "$STATE_NAMESPACE" --name "$STATE_BUCKET"
oci os object head --config-file .bootstrap/pipeline.config --profile plan --auth api_key --namespace-name "$STATE_NAMESPACE" --bucket-name "$STATE_BUCKET" --name bootstrap/terraform.tfstate
```

Before migration the state object does not exist: use an owner-created harmless probe object instead. Variables in these examples refer to the public values shown in `.bootstrap/wizard.env`; enter them in your shell without copying any private PEM. For object writes, use a uniquely named harmless probe file/object, verify Apply can upload/read/delete it in the state bucket, and verify Plan cannot upload/delete it. Never use actual state or lock objects for negative write probes.

For each of `terraform-apply` and `terraform-plan`, retrieve the group/policy IDs from `.bootstrap/setup.json`. With the Apply profile, attempt **no-op updates**:

```bash
oci iam group update --config-file .bootstrap/pipeline.config --profile apply --auth api_key --group-id "$GROUP_OCID" --description "$EXISTING_DESCRIPTION"
oci iam policy update --config-file .bootstrap/pipeline.config --profile apply --auth api_key --policy-id "$POLICY_OCID" --description "$EXISTING_DESCRIPTION"
```

Use the existing descriptions from an owner read. Both groups and both policies must reject updates. A successful no-op is an exclusion failure, even if nothing changed. Also test denied changes to pipeline group membership with an owner-reviewed harmless request; a duplicate-membership error alone does **not** prove denial. Never remove the Apply user's active membership as a test. Separately prove Apply can manage an ordinary scratch group/policy; otherwise a broken permission condition could appear to protect the pipeline merely because it denies all IAM writes.

Verify Apply cannot update the Bootstrap bucket, create another bucket there, or manage other Bootstrap resources. A no-op bucket update with `--versioning Enabled --force` is a non-destructive negative probe. Verify bucket-read/object-management grants match only the state bucket; test a scratch second bucket with an owner-created harmless object. Verify ordinary resources outside Bootstrap remain manageable. Verify Plan can read ordinary tenancy resources and state, and cannot change either. Record actual authorization errors (not syntax errors, duplicate conflicts or missing-resource failures) with positive controls.

The normal policy guards name exclusions by permission so APIs without `target.group.name` or `target.policy.name` are not accidentally denied. Group membership changes require `GROUP_UPDATE`; creation and unrelated user operations are not gated on absent target names. The concrete behavior still requires the owner's real probes. IAM grants are additive: unrelated grants can defeat exclusions. Review the broad tenancy grant and all identity memberships with the owner.

If OCI does not honor these name exclusions, **stop**. Follow [OCI Deny Policies](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/denypolicies.htm): Policies → Actions → Policy settings → Enable IAM Deny Policy. Enabling is permanent; the owner must deliberately confirm it and preserve the seeded default deny policy. Set `iam_exclusion_mode` to `deny` in `.bootstrap/root/owner.auto.tfvars.json`, manually review/plan/apply, and repeat every positive/negative probe. The fallback denies group `use` and policy `manage` for both pipeline names. Select the verified mode when the wizard resumes; its working public tfvars take precedence over the older wizard record. Do not proceed if fallback probes fail.

## GitHub settings and secrets

The wizard opens settings pages and waits for owner confirmation; it does not automate settings changes. Following [GitHub protected branch instructions](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/managing-a-branch-protection-rule), add a classic protection rule for `main` under Settings → Branches. Enable required status checks and **Require branches to be up to date before merging**. Select exactly `terraform fmt`, `terraform validate`, `tflint` as the three required static gates. These names must have appeared in a recent PR run to be selectable.

Under Settings → Environments, create:

| Environment | Identity | Reviewers | Deployment restriction |
| --- | --- | --- | --- |
| `plan` | Plan | None | Permit in-repository PR branches |
| `apply-foundation` | Apply | Owner required | Selected branches and tags: branch `main` only; no tag policies |
| `apply-workloads` | Apply | None | Selected branches and tags: branch `main` only; no tag policies |

See [GitHub Environment setup](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments). For Foundation, permit the owner to approve their own deployment when they are the sole owner; this is a deployment review, not a PR approval. Settings take effect only when installed by the owner. Applying/drift workflows are subsequent tickets; this change reserves their Environments and credentials without adding CI applies.

The wizard uses the unmodified template's `set_secret` helper through a procedure-local `gh` adapter that adds `--repo` and `--env`. Each Environment receives **exactly** `OCI_TENANCY_OCID`, `OCI_USER_OCID`, `OCI_FINGERPRINT`, `OCI_PRIVATE_KEY`, `OCI_REGION`. The `plan` workflow references these names at Environment-bound job level; it no longer passes repository `OCI_PLAN_*` secrets. Forks remain static-only. The two apply Environments receive the same Apply identity/key. The template's `set_var` helper writes `TF_STATE_BUCKET`, `TF_STATE_NAMESPACE`, and the two rotation-date variables to the chosen repository. Missing `gh` access fails setup; resolve it before proceeding.

Private PEM contents travel through stdin to `gh secret set`, never through command arguments or output. Don't paste multiline private keys into dotenv or Terraform. The generated local private PEM files are their only local persistence. The owner verifies secret names in GitHub and confirms a first affected-Root PR plan is green after migration. Installing `TF_STATE_BUCKET`/`TF_STATE_NAMESPACE` last is what switches CI from skipping to requiring the live plan: after that, any missing or empty credential fails the run (see the README's *Unconfigured versus configured setup*). Install the five secrets in the `plan` Environment before the variables.

## Key rotation

Daily `key-rotation.yml` runs on main at 14:00 UTC. It creates a distinct reminder issue for each user 90 days after that user's `OCI_APPLY_ROTATED_ON` or `OCI_PLAN_ROTATED_ON` UTC date. Missing baselines produce no reminder; installing both dates is part of setup. Existing issues, including closed issues with the same identity/date, prevent duplicate reminders. Advance a date only after a real successful rotation; merely closing an issue does not rotate a key.

1. Authenticate a fresh short-lived owner session; stop concurrent Bootstrap changes. Back up the old key pair in protected local storage.
2. Generate a new pair at a new private local path using `openssl genrsa -out NEW_PRIVATE.pem 2048` and `openssl rsa -in NEW_PRIVATE.pem -pubout -out NEW_PUBLIC.pem`. Use `umask 077`, never display private PEM contents. Derive its fingerprint with `openssl rsa -pubin -in NEW_PUBLIC.pem -outform DER | openssl dgst -md5 -c`.
3. Schedule a short credential-maintenance window: stop pipeline use of that identity until its replacement secret is installed. Update only that role in `.bootstrap/root/owner.auto.tfvars.json` with the new **public** PEM. Owner-plan/apply against remote state. This replaces the old public API key; never put the private PEM into Terraform.
4. Update that identity's Environment `OCI_PRIVATE_KEY` via stdin (`gh secret set OCI_PRIVATE_KEY --repo OWNER/REPO --env ENV < NEW_PRIVATE.pem`) and its `OCI_FINGERPRINT`. Plan updates only `plan`; Apply updates both apply Environments. Verify new credentials with harmless reads and a PR plan. Use the same owner setup permission checklist.
5. Move the matching new local pair to the canonical `.bootstrap/keys/{role}.pem` and `.public.pem` paths, keeping mode 0600. Update the local fingerprint record and regenerate the pipeline CLI profile from the new Terraform outputs. Re-running the wizard performs these public-output/configuration steps and repeats the permission gate; it does not regenerate existing key pairs.
6. Advance only that user's rotation-date repository variable with `gh variable set OCI_PLAN_ROTATED_ON --repo OWNER/REPO --body YYYY-MM-DD` (or `OCI_APPLY_ROTATED_ON`), update the local wizard date, securely remove obsolete private copies according to your storage's deletion procedure, and close its reminder with evidence. No Bootstrap apply is automated.

## Verification and owner completion

Local agent checks: mocked Terraform Root plans, plan-JSON ownership assertions, workflow fixtures, reminder tests, `bash -n`, executable mode and static value/secret tracing. ShellCheck uses `-e SC1087,SC2317,SC2329` for inherited template-library diagnostics (Readline prompt interpolation and unused library helpers reported as SC2317 in ShellCheck 0.9 or SC2329 in newer releases); the library itself stays byte-identical. No interactive wizard execution, live backend initialization or authorization claim is part of agent verification.

Owner checklist (complete after merge):

- [ ] Owner MFA and Break-glass access verified; identity-domain policies remain unmanaged.
- [ ] Reviewed local-state Bootstrap apply complete; resources untagged.
- [ ] Real pipeline authorization evidence recorded, including both group/policy exclusions and ordinary IAM positive controls; deny fallback applied/retested if needed.
- [ ] Native backend migration complete, with separate Root state keys.
- [ ] Remote no-change plan and state existence confirmed before local-state deletion.
- [ ] Main protection and three Environments configured; both apply Environments restricted to main.
- [ ] Correct identity's five OCI secrets installed in each Environment; backend variables installed.
- [ ] First in-repository affected-Root PR plan green; PR/run evidence recorded.
- [ ] Separate 90-day rotation baselines installed and reminder workflow verified.

Do not close #24 based on script existence or mock success.

Checkov exceptions are scoped to the state bucket: `CKV_OCI_9` conflicts with the specified Oracle-managed encryption; `CKV_OCI_7` requests object events, but this native state backend has no event consumer. Private access, versioning and API-key checks remain active.

## Resuming a partially failed user creation

Identity-domain-backed tenancies require a primary email even though the provider schema labels it optional. Supply two distinct owner-controlled addresses in stage 4; each must be unique across tenancy users. Emails are contact data visible in Terraform inputs, outputs, state and plans, not credentials or GitHub secrets.

After a failed apply, preserve `.bootstrap/root`, its state/backups, and the existing local key pairs. Re-run the updated wizard; Enter keeps existing values and stage 4 asks for the new emails. Stage 5 plans against the same partial state, so already-created resources are retained. Review that the plan creates only remaining resources before you approve another apply. Never delete state or start a fresh working directory to retry.
