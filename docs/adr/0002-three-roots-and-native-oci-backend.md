# Three roots with state in the native OCI backend

Configuration is split into `bootstrap` (hand-applied once), `foundation` and `workloads`, each with its own state, so a workload change can never touch IAM. State lives in Object Storage via Terraform's native `oci` backend rather than HCP Terraform, keeping everything inside the tenancy; CI authenticates with a dedicated CI user's API key (stored as a GitHub Environment secret, rotated every 90 days) rather than OIDC federation.
