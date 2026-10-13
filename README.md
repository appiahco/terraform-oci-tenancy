# OCI Tenancy execution contracts

Three independently initialized Roots reserve exclusive ownership:

| Root | State key | Ownership | Execution |
| --- | --- | --- | --- |
| Bootstrap | `bootstrap/terraform.tfstate` | Pipeline identities, policies, state storage | Plan in PRs; apply manually after merge |
| Foundation | `foundation/terraform.tfstate` | Compartments, tenancy IAM, networking, security baseline | Plan in PRs; reviewed apply on main |
| Workloads | `workloads/terraform.tfstate` | Compute, databases, clusters, workload identities | Plan in PRs; apply on main after Foundation succeeds |

Bootstrap provisions state storage and pipeline access through the [owner runbook](bootstrap/README.md) and `./scripts/bootstrap-wizard.sh`. Foundation declares governed compartments, tags and the Production Security Zone. Workloads retains its execution contract until workload resources are introduced. The Break-glass identity and Default identity domain sign-on/MFA policies stay unmanaged. Provider exclusions ignore `Oracle-Tags.CreatedBy` and `Oracle-Tags.CreatedOn` in every Root.

## Credential-free validation

Install the exact version from `.terraform-version`. For each Root, use `terraform -chdir=ROOT init -backend=false -input=false -lockfile=readonly`, then `validate` and `test`. Tests use a mocked OCI provider and plan only. Provider locks include Linux amd64 and macOS arm64 checksums. Static jobs run for every PR, including forks and documentation-only changes, so the check names `terraform fmt`, `terraform validate`, and `tflint` remain stable required-check candidates. Checkov and Trivy are advisory. Repository protection is configured separately.

```sh
python3 -m pip install -r tests/requirements.txt
python3 -m unittest discover -s tests -v
node --test tests/*.test.mjs
python3 scripts/ci.py static fmt
python3 scripts/ci.py static validate
# Install TFLint, then:
tflint --init
python3 scripts/ci.py static tflint
```

Workflow fixtures execute the workflow's detection and preflight commands, evaluate the boolean plan guards, and inject fake Terraform/TFLint executables for credential and failure paths. They use fake Terraform and OCI executables and never initialize a live backend or write to the tenancy. Terraform's mocked Root tests and the comment tests assert focused contracts/plan JSON, without whole-plan snapshots. CI validates the complete workflow syntax separately through GitHub Actions.

## PR plan contract

`_terraform.yml` accepts `root` (`bootstrap`, `foundation`, `workloads`) and `mode` (`plan`, `apply`). PRs use the Plan user for unlocked previews. A main push uses the Apply user to re-plan with locking and apply that exact saved plan in the same job. Foundation selects the reviewed `apply-foundation` Environment; Workloads proceeds only after Foundation succeeds. Bootstrap cannot be applied by CI.

The reusable workflow binds its preflight and plan jobs to the `plan` Environment, whose `OCI_TENANCY_OCID`, `OCI_USER_OCID`, `OCI_FINGERPRINT`, `OCI_PRIVATE_KEY` (PEM content), and `OCI_REGION` secrets supply the Plan identity. No secrets are inherited from the caller. Fork PRs never invoke the reusable workflow and receive no credentials; static checks still run for them.

### Unconfigured versus configured setup

CI treats setup as **complete** once either repository variable `TF_STATE_BUCKET` or `TF_STATE_NAMESPACE` is non-empty (the owner wizard installs them only after the Plan and Apply credentials), or once all five `OCI_*` secrets are present. The `credentials` preflight (`scripts/ci.py credentials`) then decides:

| State | Condition | Result |
| --- | --- | --- |
| Initial setup | Both state variables are empty and at least one `OCI_*` secret is missing | Preflight passes with `available=false`; the live plan is skipped and the job summary says no live plan ran and infrastructure is **not verified**. |
| Setup complete | Either marker above holds and all five `OCI_*` secrets and both state variables are non-empty | `available=true`; the plan runs. |
| Setup complete, input missing or empty | Either marker above holds but any of the seven inputs is missing, empty or whitespace | The preflight **fails** with one `::error` annotation and a job summary naming the inputs. Only names are printed, never values. |

A green run with a skipped live plan therefore only occurs during initial setup, for a fork PR, or when no Root is affected, and the job summary says which. Fork and no-Root runs state that no live plan ran and infrastructure is not verified. To return to initial setup deliberately, delete both state variables and at least one secret. The owner provisions GitHub settings and credentials after merge using the Bootstrap runbook. Apply jobs use the same contract and always fail on missing inputs, including initial setup. Drift remains separate work in #31.

When credentials exist, the state bucket and namespace come from repository variables `TF_STATE_BUCKET` and `TF_STATE_NAMESPACE`. The Root backend supplies its own key; only bucket and namespace are passed with `-backend-config`. The plan entry point exports matching `OCI_<lowercase attribute>` aliases because Terraform 1.16’s native OCI backend reads those names. No backend credentials are stored in HCL. `backend.hcl.example` documents the three non-secret properties. Plans use `-lock=false` and cancel older runs for the same Root and PR. Each Root has a sticky comment with change and replacement counts, warnings, collapsed escaped text, and a run-log link above 60,000 characters. Always Free advisory content is reserved for its own ticket.

## First initialization

Backend examples are placeholders until owner provisioning is complete. Follow [Bootstrap setup](bootstrap/README.md) for owner provisioning, local-to-OCI migration and permission evidence. Do not initialize against a live backend until that work is complete.

Foundation and Workloads initialization must not assume deployed Foundation outputs exist before the first Foundation apply. Both Roots currently declare no remote-state dependency. When Workloads begins consuming Foundation outputs, introduce that dependency only after Foundation has produced them, or gate it explicitly for first use. Never invent subnet, NSG, or compartment IDs to satisfy initialization.

Foundation governance and the reviewed merge path are documented in [foundation/README.md](foundation/README.md).
