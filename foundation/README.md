# Foundation governance

Foundation owns Platform, Production, Staging and Production/Edge and Staging/Edge.
Bootstrap continues to own its compartment, state storage and pipeline identities.
Only compartments and tenancy-wide taxonomy live at the Tenancy root. Future
Workload IAM policies attach to their environment compartment; tenancy-wide
exceptions require a comment explaining their scope. No human or speculative
Workload groups are created here. The Break-glass identity and Default identity
domain policies remain unmanaged.

`environment_compartment_ids` and `edge_compartment_ids` are the authoritative
outputs for Workloads. Foundation requires only `tenancy_ocid`, supplied by CI
from `OCI_TENANCY_OCID`; its first deployment reads no Foundation remote state.
Networking, budgets, the remaining Cloud Guard configuration/logging and Drift
are separate issues (#28, #26, #27 and #31). Foundation owns only the tenancy-level
Cloud Guard enablement required by its Security Zone.

## Tags

`appiahco.environment` accepts `platform`, `production` and `staging`;
`appiahco.managed-by` is `terraform`. Both defaults are non-required and attach
only to environment compartments. Edge inherits these defaults. CI resources
carry explicit defined tags. The namespace and tag definitions use matching
freeform tags to avoid depending on the definitions they create; OCI tag defaults
have no tagging fields. Bootstrap receives neither tags nor inherited defaults.
Every Root retains provider exclusions for `Oracle-Tags.CreatedBy` and
`Oracle-Tags.CreatedOn`.

## Security Zone

Production and its custom recipe and zone are created in the same Foundation
apply. Platform, Staging and Bootstrap have no zone. Production/Edge is removed
from Production's inherited zone before Foundation succeeds.

The reviewed policy names are listed explicitly in
[`security-policy-names.json`](security-policy-names.json). Oracle display names
use a space after `deny`; `deny public_subnets` is the API name for the spec's
`deny_public_subnets`. Terraform resolves exactly those names to policy OCIDs.
New Oracle policies cannot enter the recipe without a reviewed PR. Missing or
renamed selected policies fail the plan rather than silently reducing protection.

The recipe retains resource movement/association, public subnet/bucket/database,
backup, approved image and selected network security controls. It omits Internet,
NAT and Service gateway, DRG (including `deny create_drg`), public-load-balancer,
and all four block-volume/boot-volume/file-system/bucket Vault-key policies.
It also omits blanket management/deletion/update prohibitions and VCN security
list creation prohibitions so future resources can be managed by Terraform.
`deny LPG_gateway` remains because the settled networking design uses a DRG.
The current recipe includes `deny free_database_creation`; this applies to
Production's Security Zone only and must be reviewed before a Production database.

If a Vault is introduced, restore all four Vault-key policies through a reviewed
PR and revisit the Plan user's `read all-resources` grant for Vault access.

**Cloud Guard prerequisite:** a Plan-user read on 2026-10-13 found Cloud Guard
disabled. Foundation declares only tenancy-level enablement at the Tenancy root,
with reporting region `us-ashburn-1`, status `ENABLED` and
`self_manage_resources = false`. Production's Security Zone explicitly depends
on that configuration so the same reviewed apply enables Cloud Guard before
creating the zone. This breaks the #25/#27 compartment dependency cycle.
Cloud Guard configuration has no tagging fields in provider 9.9.0.

All remaining #27 work stays separate: Foundation declares no detector recipe
clones, targets, responders or logging for this prerequisite. Oracle automatically
creates the Security Zone's target when the zone is created. The enablement is a
tenancy-wide service setting; removing the configuration resource can disable
Cloud Guard across the Tenancy and must be reviewed with that scope in mind.

Provider 9.9.0 has no child-compartment exclusion resource. The plan therefore
includes `terraform_data.production_edge_exclusion`, a create-time adapter using
OCI CLI 3.94.2. It reads the zone, removes only Production/Edge when inherited,
waits for ACTIVE and reads again to verify exclusion. It uses the job's Apply-user
credentials in temporary mode-0600 files, never state or command arguments. A
failed exclusion fails Foundation and blocks Workloads. Plan-only tests and PR
plans never execute this adapter. Changes to its script or zone/Edge identifiers
replace the marker and recheck the exclusion. The marker itself cannot detect
out-of-band inheritance changes: post-merge OCI reads are required, and #31 must
account for this provider gap before claiming complete Drift coverage.

## Deployment path

```text
PR: static checks → Plan Environment → Plan-user unlocked preview
main push: apply-foundation review → Apply-user locked saved plan → same plan apply
           Foundation success → apply-workloads → locked saved plan → same plan apply
```

Reusable apply mode preserves #35's explicit caller secret mappings and shared
credential validation. Missing/empty inputs fail all applies, including initial
setup; an apply can never report a successful unverified skip. Fork PRs remain
outside every credential job. Main is the only apply ref, Bootstrap is rejected,
and no PR artifact is downloaded or applied. Both plan and apply happen in the
same job; an obsolete state serial causes Terraform to reject the saved plan.

Applies serialize under `terraform-foundation-apply` and
`terraform-workloads-apply`, with `cancel-in-progress: false`. #31 must use these
exact groups for Reverts. GitHub retains at most one pending job in a concurrency
group; a newer pending main deployment can replace an older pending deployment,
but never cancels a running apply. The latest main configuration is authoritative.
The workflow selects existing Environments; repository review/branch settings
are owner-managed and are not changed by this PR.

## Post-merge acceptance evidence

Keep the final #25 criterion unchecked until the owner has reviewed and approved
the deployment and recorded:

1. The successful main Foundation deployment and successful ordered Workloads job.
2. A subsequent no-change Foundation plan (including refreshed zone state).
3. OCI reads of Production's zone and its `inherited-by-compartments`, confirming
   Production/Edge is absent, plus recipe reads confirming the exact selected
   policy IDs. Read Staging, Platform and Bootstrap zone lists to confirm they
   have no zone. These reads demonstrate attachment/configuration; Staging cannot
   demonstrate Production Security Zone enforcement.

Do not attempt a violating write as part of this task. Only merging the PR and
owner approval of `apply-foundation` authorizes tenancy deployment.
