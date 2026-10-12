# Research: guarding automatic drift revert

Question (#4): how can a scheduled plan reliably classify drift as safe to revert (no destroy/replace) from the plan JSON, and which OCI provider resources produce perpetual diffs that would make a revert loop noisy?

## Conclusion

1. Run `terraform plan -detailed-exitcode -out=tfplan`. Exit `0` = no drift, stop; `1` = error, open issue; `2` = changes, classify.
2. Classify with `terraform show -json tfplan`: auto-apply **only if** every `resource_changes[].change.actions` is `["no-op"]`, `["update"]` or `["read"]`. Any action list containing `"delete"` (covers `["delete"]`, `["delete","create"]`, `["create","delete"]`) or `"create"` → open an issue instead. Example guard:
   ```sh
   terraform show -json tfplan | jq -e '[.resource_changes[]?.change.actions[]] | all(. == "no-op" or . == "update" or . == "read")'
   ```
   Apply the saved `tfplan` (not a fresh plan) so what was classified is what runs.
3. Neutralise OCI perpetual diffs before enabling auto-apply, otherwise every run is exit `2` and the loop applies forever (or, worse, proposes replacements and opens an issue on every run):
   - Set provider-level `ignore_defined_tags = ["Oracle-Tags.CreatedBy", "Oracle-Tags.CreatedOn"]` (or `lifecycle { ignore_changes = [defined_tags["Oracle-Tags.CreatedBy"], ...] }`).
   - Add a "no-op twice" check: after an auto-apply, a re-plan should exit `0`; if the same address changes on consecutive runs, treat it as a perpetual diff and open an issue rather than re-applying.

## Evidence

### Terraform plan JSON (primary: Terraform JSON output format doc)
- Valid `actions` values are exactly `["no-op"]`, `["create"]`, `["read"]`, `["update"]`, `["delete","create"]`, `["create","delete"]`, `["delete"]`; the docs state replaces are encoded this way so callers can "just scan the list for delete" to catch every deletion. Source: https://developer.hashicorp.com/terraform/internals/json-format (change representation).
- `replace_paths` lists the attribute paths that forced replacement: useful for the issue body. Same source.
- `resource_drift` describes changes detected outside Terraform during refresh; it is informational and is not itself the action set. Classify on `resource_changes`, put `resource_drift` in the issue body. Same source.

### Plan flags (primary: `terraform plan` command doc)
- `-detailed-exitcode`: 0 = empty diff, 1 = error, 2 = non-empty diff. https://developer.hashicorp.com/terraform/cli/commands/plan
- `-refresh-only` (>= v0.15.4) only updates state to match remote objects; it does **not** revert drift, so it is a reporting tool, not the revert mechanism. Same source. `-refresh=false` must not be used (it hides external changes).

### OCI provider perpetual diffs (primary: oracle/terraform-provider-oci issues)
- #2418 (open): `oci_identity_domains_dynamic_resource_group` re-updates every apply due to `Oracle-Tags` CreatedBy/CreatedOn tag detection. https://github.com/oracle/terraform-provider-oci/issues/2418
- #1887 (open): Oracle-maintained defined tags trigger **replacement** of load balancer `oci_logging_log` resources on every apply: a guard would correctly block it but open an issue each run. https://github.com/oracle/terraform-provider-oci/issues/1887
- #2559 (open): interaction of provider `ignore_defined_tags = ["Oracle-Tags.CreatedBy","Oracle-Tags.CreatedOn"]` with `oci_identity_policy` destroy behaviour: verify ignore setting per resource type. https://github.com/oracle/terraform-provider-oci/issues/2559
- #2237 (open): `oci_os_management_hub_software_source` constantly requires updating. https://github.com/oracle/terraform-provider-oci/issues/2237

## Open points
- Confirm per-resource that `ignore_defined_tags` actually suppresses the diff (#2418, #2559 suggest it is not universal); fall back to `lifecycle.ignore_changes`.
- Decide whether `create` alone (resource deleted out-of-band) should auto-apply; this note treats it as needing a human.
