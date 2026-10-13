# Tenancy source-of-truth spec

This repository is the enforced single source of truth for the `appiahco` Oracle Cloud **Tenancy** (home region us-ashburn-1). This spec is the hand-off for building it: every decision below is settled, and nothing is left to decide before implementation starts. Vocabulary is defined in [`GLOSSARY.md`](../GLOSSARY.md); the reasoning behind the larger choices lives in [`docs/adr/`](adr/).

The tenancy is greenfield (verified 2026-10-12): it holds only Oracle defaults, the Default identity domain and the owner `karthik@appiah.company`. Nothing is imported.

## 1. Operating model

- Changes reach the tenancy only through this repository. Pull requests plan; merging to `main` applies ([ADR 0001](adr/0001-enforced-source-of-truth-with-auto-revert.md)).
- A daily drift check reverts drift automatically, but only when the revert is an in-place update (see §6.6).
- The owner is the **Break-glass identity**: an administrator left unmanaged by this repository so that no apply can lock them out. The Default identity domain's sign-on and MFA policies are also unmanaged. The owner enables MFA by hand.
- The tenancy is pay-as-you-go. Going beyond Always Free produces warnings and never blocks a change (§8).

## 2. Tooling

- **Terraform ≥ 1.12**, not OpenTofu. The `oracle/oci` provider works under both, but only Terraform has the native `oci` backend.
- Pin the exact version in `.terraform-version`, which `setup-terraform` reads. Commit `.terraform.lock.hcl` in each root. Renovate raises version bumps.
- Static gates: `terraform fmt -check`, `terraform validate` and `tflint` with the OCI ruleset are required status checks on `main`. Checkov and Trivy run as advisory checks only.

## 3. Repository layout

```
bootstrap/        # root, applied by hand; README.md is the bootstrap runbook
foundation/       # root, applied by CI
workloads/        # root, applied by CI
modules/          # shared modules; a change here triggers every root
.github/workflows/
  _terraform.yml  # reusable: inputs root, mode (plan|apply)
  pr.yml
  apply.yml
  drift.yml
.terraform-version
```

The Always Free allowlist data file (§8) is checked in next to the workflows.

## 4. Roots and state

There are three **Roots**, each with its own state, so a workload change can never touch IAM ([ADR 0002](adr/0002-three-roots-and-native-oci-backend.md)). No resource is owned by more than one root.

| Root | Holds | Applied by |
| --- | --- | --- |
| `bootstrap` | `bootstrap` compartment, state bucket, apply user and plan user, their groups, policies and API keys | Owner, by hand |
| `foundation` | compartments, tenancy-wide IAM, tagging, budgets, networking, security baseline, Security Zone | CI, behind an Environment reviewer |
| `workloads` | compute, databases, clusters and their dynamic groups and policies | CI |

**State backend:** the native `oci` backend, using one versioned Object Storage bucket in the `bootstrap` compartment with `prevent_destroy`, Oracle-managed encryption and one state key per root.

- Locking is built in. It uses conditional writes and a `.lock` object. No extra service is needed.
- The backend block contains only `bucket`, `namespace` and `key`. Credentials come from `OCI_*` environment variables and are never passed through `-backend-config`, because values passed that way persist in `.terraform` and in plan files.
- `workloads` reads `foundation` outputs (subnet and NSG IDs, compartment IDs) through `terraform_remote_state` on the `oci` backend.

## 5. Identities and access

### 5.1 Pipeline users (in `bootstrap`)

| | **Apply user** | **Plan user** |
| --- | --- | --- |
| Used for | applying on `main`, and the whole drift job | every PR plan |
| Policy | `manage all-resources in tenancy where target.compartment.name != 'bootstrap'`, plus read buckets and manage objects on the state bucket only | `read all-resources in tenancy` (this covers reading state) |
| Excluded from its policy | its own group and policy, and the plan user's group and policy | — |
| Key's GitHub Environment | `apply-foundation`, `apply-workloads` (deployable from `main` only; `apply-foundation` has a required reviewer) | `plan` (no reviewer) |

- There is one apply user for the whole tenancy, across all roots and environments. Protection comes from PR review and the `foundation` Environment reviewer.
- Key pairs are generated locally with `openssl`. Only the public key is a Terraform input, so private keys never enter state.
- Keys are rotated by hand every 90 days. Each user has its own scheduled reminder issue. Rotation reuses the bootstrap runbook's key and `gh secret set` steps.
- **Build-time check:** confirm that OCI honours the name conditions excluding the pipeline's own groups and policies for IAM resources. If it does not, express the exclusions as OCI deny policies.

### 5.2 Other IAM

- **Human groups:** none until a second person needs access.
- **Workload identities:** each workload's dynamic group and policy are declared in `workloads` alongside the resource that uses them. The dynamic group matches on that environment's compartment, and the policy is attached to it. `foundation` declares no dynamic groups in advance.
- **Policy placement:** a policy attaches to its environment's compartment by default. Only genuinely tenancy-wide policies sit at the root (pipeline users, Cloud Guard, the `appiahco` tag namespace), and each root exception is justified in a comment.

## 6. CI/CD (GitHub Actions)

### 6.1 Repository settings

- `main` is protected. Branches must be up to date before merging, and the static gates (§2) are required.
- Environments: `plan`, `apply-foundation` (with a required reviewer: the owner) and `apply-workloads`. Each holds that identity's `OCI_*` secrets.

### 6.2 Change detection

A detection job matches path globs for each root (`bootstrap/**`, `foundation/**`, `workloads/**`). Shared paths such as `modules/**` and `.terraform-version` trigger every root. The job outputs a matrix of the affected roots.

### 6.3 Pull requests (`pr.yml`)

- Branches in this repository: fmt, validate and tflint run, then a plan per affected root as the plan user with `-lock=false`. The locked re-plan on `main` is the authoritative one.
- Fork PRs get fmt, validate and tflint only, with no credentials and no plan.
- `bootstrap` is planned but never applied by CI. Its comment says "apply manually after merge".
- Concurrency: one group per root per PR, with `cancel-in-progress: true`.

### 6.4 Plan comment

Each root gets one sticky comment that is updated in place. It contains:

1. A `+N ~N -N` summary line, with replacements called out.
2. A ⚠️ banner when the plan contains any destroy or replace.
3. The plan inside a collapsed `<details>` block, replaced by a link to the full log when it would exceed about 60k characters.
4. An **Always Free advisory** section (§8).

### 6.5 Apply on merge (`apply.yml`)

- CI re-plans on `main` as the apply user and applies that saved plan file in the same job.
- `foundation` applies first and waits for the `apply-foundation` reviewer. `workloads` applies afterwards and is skipped if `foundation` fails or is rejected.
- Concurrency: one group per root, shared with drift, with `cancel-in-progress: false`.

### 6.6 Drift (`drift.yml`)

- Runs daily on cron `0 14 * * *` (14:00 UTC) as the apply user.
- `foundation` and `workloads`: run `plan -detailed-exitcode` and save the plan, then scan `terraform show -json`. The saved plan is applied only when every `resource_changes[].change.actions` is `no-op`, `update` or `read`. Any `create`, `delete` or replace opens an issue instead. A `create` usually means a resource was deleted out of band, and recreating it is a decision for a person to make.
- `foundation` reverts still wait for the Environment reviewer.
- If the same diff reappears on consecutive runs, open an issue rather than reverting it again.
- Prerequisite: every resource ignores the `Oracle-Tags.CreatedBy` and `Oracle-Tags.CreatedOn` defined tags (provider `ignore_defined_tags`), because otherwise they produce perpetual diffs.
- `bootstrap`: plan only. Any diff opens an issue and is never reverted.

## 7. Bootstrap procedure

The runbook lives at `bootstrap/README.md` and takes the tenancy from empty to the first green PR plan. The owner runs it from a laptop with `oci session authenticate`, a short-lived token, so no standing personal API key is needed.

1. Generate the apply user's and plan user's key pairs with `openssl`.
2. Apply `bootstrap` with local state. This creates the `bootstrap` compartment under the root, the versioned `prevent_destroy` state bucket, both users, their groups and policies, and their public API keys.
3. Uncomment the `backend "oci"` block, run `terraform init -migrate-state`, confirm that `plan` shows no changes, then delete the local state files.
4. In GitHub, by hand: protect `main`, create the three Environments and the `apply-foundation` reviewer, and set the `OCI_*` secrets with `gh secret set`.
5. Open a PR. Bootstrap is done when that PR plans green.

Later `bootstrap` changes, such as widening a policy or rotating a key, are applied the same way against remote state.

## 8. Cost: budgets and Always Free warnings

- **Budgets** (in `foundation`; every amount is a variable; alerts email `karthikgappiah+budget@gmail.com` directly):
  - Tenancy root: $10/month, with alerts on actual > $1 (the authoritative "left Always Free" signal), forecast > 100% and actual > 100%.
  - `platform`, `production` and `staging`: $5/month each, with one alert on forecast > 100%.
- **Plan-time advisory:** reads `terraform show -json` against the checked-in allowlist of free resource types and shapes (for example `VM.Standard.A1.Flex` and `VM.Standard.E2.1.Micro`). It totals OCPU, memory and storage across current state plus the plan, and flags anything over the free limits (for example A1 > 4 OCPU / 24 GB, block storage > 200 GB). The result is posted in the plan comment and never fails the job.

## 9. Compartments

Nothing but compartments and tenancy-wide settings lives in the root compartment.

```
root
├── bootstrap        # bootstrap root: state bucket only
├── platform         # shared networking and security
├── production       # Security Zone
│   └── edge         # excluded from the zone: public LB subnet + load balancers
└── staging
    └── edge         # mirrors production/edge, no zone
```

`foundation` owns every compartment except `bootstrap`.

## 10. Tagging

- `foundation` declares one tag namespace, `appiahco`, with two defined tags: `environment` (enum `platform`, `production`, `staging`) and `managed-by` (`terraform`).
- Each environment compartment has a tag default that stamps `environment` with the compartment's name. The `edge` subcompartments inherit their parent's value. Tag defaults are **not** required, so console and provider flows don't break. CI sets both tags explicitly.
- `bootstrap` resources are not tagged, because the namespace does not exist until `foundation` is applied.

## 11. Network

All of this lives in `foundation` ([ADR 0003](adr/0003-separate-vcns-joined-by-a-drg.md)). `workloads` only consumes subnet and NSG IDs.

- **Topology:** a **Platform VCN** in `platform` and one **Environment VCN** each in `production` and `staging`, joined by a **DRG** in `platform`. The DRG route tables let each environment import Platform's routes only, never the other environment's.
- **Region:** us-ashburn-1 only. No remote peering, VPN or FastConnect.
- **CIDR:** supernet `10.0.0.0/16`. Platform uses `10.0.0.0/20`, Production `10.0.16.0/20` and Staging `10.0.32.0/20`. The rest is reserved.
- **Platform VCN:** a DRG attachment plus one private subnet for the OCI Bastion service, which is the only admin path. There is no public SSH anywhere.
- **Environment VCNs:** each has its own NAT, Service and Internet gateways, with no transit through Platform. Regional subnets:
  - public `/24` for load balancers only, in the environment's `edge` compartment
  - private app `/22`
  - private data `/24`
- No instance gets a public IP.
- **Firewalling:** NSGs per resource. Default security lists are empty (deny-all). No IPv6.
- **Flow logs:** on private subnets only, into the `security` log group (within the free 10 GB/month).
- VCNs, the DRG, gateways and Bastion are all free.

## 12. Security baseline

All of this is in `foundation`. Tenancy-level settings live at the root, and every resource it creates lives in `platform` unless stated otherwise.

- **Cloud Guard:** enabled tenancy-wide, with the home region as the reporting region and Oracle-managed detector recipes. Responders are notify-only, with no auto-remediation, so they cannot fight drift revert.
- **Alerting:** an Events rule sends HIGH and CRITICAL Cloud Guard problems to one Notifications topic, which emails `karthikgappiah+budget@gmail.com`.
- **Audit:** retention explicitly set to 365 days.
- **Logging:** one `security` log group, holding VCN flow logs and the state bucket's Object Storage read and write logs.
- **Vault:** none until it has a first consumer.
- **Security Zone** ([ADR 0004](adr/0004-security-zone-with-excluded-edge-compartment.md)): one zone on `production`, created in the same apply as the compartment, with `production/edge` excluded.
  - It uses a custom recipe that lists its policies explicitly and keeps `deny_public_subnets`. Policies Oracle adds later are adopted only through a reviewed PR.
  - It omits the Internet, NAT and Service gateway policies and the DRG and public load-balancer policies, because the network needs them.
  - It also omits the four Vault-key policies (block volume, boot volume, file system and bucket) while there is no Vault.
  - Violations surface through Cloud Guard's alerting.
  - `staging`, `platform` and `bootstrap` have no zone.

## 13. Out of scope

- The `clonecademy` tenancy.
- Deploying applications onto compute or clusters.
- Carrying out this build.
- Future trigger: if a Vault is ever introduced, add the four Vault-key policies back to the production Security Zone recipe and revisit the plan user's `read all-resources` grant.
