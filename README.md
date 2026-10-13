# OCI Tenancy execution contracts

Three independently initialized Roots reserve exclusive ownership:

| Root | State key | Ownership | Execution |
| --- | --- | --- | --- |
| Bootstrap | `bootstrap/terraform.tfstate` | Pipeline identities, policies, state storage | Plan in PRs; apply manually after merge |
| Foundation | `foundation/terraform.tfstate` | Compartments, tenancy IAM, networking, security baseline | Plan in PRs |
| Workloads | `workloads/terraform.tfstate` | Compute, databases, clusters, workload identities | Plan in PRs |

These minimal Roots contain no infrastructure resources. The Break-glass identity and Default identity domain sign-on/MFA policies stay unmanaged. Provider exclusions ignore `Oracle-Tags.CreatedBy` and `Oracle-Tags.CreatedOn` in every Root.

## Credential-free validation

Install the exact version from `.terraform-version`. For each Root, use `terraform -chdir=ROOT init -backend=false -input=false -lockfile=readonly`, then `validate` and `test`. Tests use a mocked OCI provider and plan only. Provider locks include Linux amd64 and macOS arm64 checksums. Static jobs run for every PR, including forks and documentation-only changes, so the check names `terraform fmt`, `terraform validate`, and `tflint` remain stable required-check candidates. Checkov and Trivy are advisory. Repository protection is configured separately.

```sh
python3 -m pip install -r tests/requirements.txt
python3 -m unittest discover -s tests -v
node --test tests/plan-comment.test.mjs
python3 scripts/ci.py static fmt
python3 scripts/ci.py static validate
# Install TFLint, then:
tflint --init
python3 scripts/ci.py static tflint
```

Workflow fixtures execute the workflow's detection and preflight commands, evaluate the boolean plan guards, and inject fake Terraform/TFLint executables for credential and failure paths. They never call OCI, initialize a live backend, or apply. Terraform's mocked Root tests and the comment tests assert focused contracts/plan JSON, without whole-plan snapshots. CI validates the complete workflow syntax separately through GitHub Actions.

## PR plan contract

`_terraform.yml` accepts `root` (`bootstrap`, `foundation`, `workloads`) and `mode` (`plan`, `apply`). This implementation accepts plan execution; apply is reserved and fails before invoking Terraform. There is no CI apply command.

The caller maps only the Plan user's `OCI_PLAN_TENANCY_OCID`, `OCI_PLAN_USER_OCID`, `OCI_PLAN_FINGERPRINT`, `OCI_PLAN_PRIVATE_KEY` (PEM content), and `OCI_PLAN_REGION` secrets into the reusable workflow's `OCI_*` credentials. No secrets are inherited. Missing or partial credentials cause the actual plan job to skip successfully while static checks still run. Fork PRs never invoke the reusable workflow. Environment provisioning and identity setup belong to #24; this ticket creates no GitHub Environments or repository settings. Future callers may supply the Plan Environment's credentials explicitly under the same contract.

When credentials exist, the state bucket and namespace come from repository variables `TF_STATE_BUCKET` and `TF_STATE_NAMESPACE`. The Root backend supplies its own key; only bucket and namespace are passed with `-backend-config`. The plan entry point exports matching `OCI_<lowercase attribute>` aliases because Terraform 1.16’s native OCI backend reads those names. No backend credentials are stored in HCL. `backend.hcl.example` documents the three non-secret properties. Plans use `-lock=false` and cancel older runs for the same Root and PR. Each Root has a sticky comment with change and replacement counts, warnings, collapsed escaped text, and a run-log link above 60,000 characters. Always Free advisory content is reserved for its own ticket.

## First initialization

State storage and Plan user credentials do not exist yet; backend examples are placeholders. Bootstrap provisioning, local-to-OCI state migration, and the human runbook are #24 work. Do not initialize against a live backend until that work is complete.

Foundation and Workloads initialization must not assume deployed Foundation outputs exist before the first Foundation apply. These minimal Roots declare no remote-state dependency. When Workloads begins consuming Foundation outputs, introduce that dependency only after Foundation has produced them, or gate it explicitly for first use. Never invent subnet, NSG, or compartment IDs to satisfy initialization.
