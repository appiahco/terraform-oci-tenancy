# Native `oci` state backend in practice

Research for #3. Sources were checked on 2026-10-12.

## Sources

- **[TF-OCI]**: Terraform docs, [Backend type: oci](https://developer.hashicorp.com/terraform/language/backend/oci) (v1.16.x docs)
- **[OCI-STATE]**: Oracle docs, [Using Object Storage for State Files](https://docs.oracle.com/en-us/iaas/Content/dev/terraform/object-storage-state.htm)
- **[TF-INIT]**: Terraform docs, [`terraform init`](https://developer.hashicorp.com/terraform/cli/commands/init)
- **[TOFU]**: OpenTofu docs, [Backend configuration](https://opentofu.org/docs/language/settings/backends/configuration/)

## Findings

### Minimum tool version
- **Terraform 1.12.0 or later** is required. Oracle says to "Upgrade to Terraform version v1.12.0 or greater to use the OCI native backend" [OCI-STATE].
- Oracle recommends the native backend and marks the S3-compatible method as deprecated [OCI-STATE].
- **OpenTofu has no `oci` backend.** Its built-in backends are azurerm, consul, cos, gcs, http, kubernetes, local, oss, pg, remote and s3, and the docs say the listed ones are the only backends [TOFU]. Choosing the native backend therefore commits the repo to Terraform 1.12 or later. On OpenTofu, the only option would be the deprecated S3-compatible endpoint.

### State locking
- Locking is built in and needs no extra table or service. The backend uses Object Storage's conditional `If-None-Match: *` write [TF-OCI].
- The lock is a `<key>.lock` object stored next to the state in the same bucket [TF-OCI].

### Bucket prerequisites
- **Required arguments:** `bucket` and `namespace`. Both must be set in the backend block or with `-backend-config`; environment variables can't supply them [TF-OCI].
- **Versioning:** recommended, not required. The docs say it is "highly recommended" so that state can be recovered [TF-OCI]. We should enable it on the bootstrap bucket.
- **Encryption:** Object Storage encrypts objects by default with Oracle-managed keys. Neither source treats this as a backend option. The backend can also encrypt with a Vault master key (`kms_key_id`) or with SSE-C (`sse_customer_key`, `sse_customer_key_sha256`, `sse_customer_algorithm`, AES256 only) [TF-OCI]. Both are optional.
- **IAM:** the principal needs OBJECT_INSPECT, OBJECT_CREATE, OBJECT_DELETE and OBJECT_READ on the bucket, or the fine-grained equivalents (GetObject, PutObject, DeleteObject, HeadObject and the multipart operations) [TF-OCI]. OBJECT_DELETE is needed so the backend can remove the lock object.
- Other options: `key` (default `terraform.tfstate`) and `workspace_key_prefix` (default `tf-state-env`) [TF-OCI].

### API-key auth from GitHub Actions
- Supported `auth` values: APIKey, InstancePrincipal, ResourcePrincipal, InstancePrincipalWithCerts, SecurityToken and OKEWorkloadIdentity [TF-OCI]. A GitHub-hosted runner can't use instance or resource principals, so it uses **APIKey**.
- APIKey auth uses `tenancy_ocid`, `user_ocid`, `fingerprint`, `private_key_path` and `region`. Alternatively, `config_file_profile` reads them from `~/.oci/config` [TF-OCI].
- Any optional attribute can come from an environment variable. An `OCI_`-prefixed variable (for example `OCI_region`) takes priority over the bare name, and the provider reads the same variables, so one set of secrets covers both backend and provider [TF-OCI].
- The docs recommend environment variables over hardcoded values or `-backend-config`, because those values can be saved in `.terraform/` and in plan files [TF-OCI].
- **Implication for CI (inference):** store the tenancy, user, fingerprint and region as GitHub secrets exported as `OCI_*` variables. Write the private key to a temp file and point `OCI_private_key_path` at it. Put only `bucket`, `namespace` and `key` in the backend block.

### Migrating the bootstrap root's local state into its own bucket
Neither source documents this chicken-and-egg case. Oracle mentions only that `init` offers to upload an existing local `terraform.tfstate` [OCI-STATE]. The standard flow built from [TF-INIT] is:

1. Apply the bootstrap root with no backend block, which uses local state. This creates the bucket (with versioning) and the CI user, group and policy.
2. Add `backend "oci" { bucket = ..., namespace = ..., key = ... }`.
3. Run `terraform init -migrate-state`. This copies the existing state to the new backend and asks for confirmation. `-force-copy` skips the prompt [TF-INIT].
4. Check with `terraform plan`, which should show no changes, then delete the local `terraform.tfstate*` files. They contain secrets and should never be committed.

After migration, the bootstrap root manages the bucket that holds its own state. Add `prevent_destroy` on the bucket so that an accidental destroy can't remove its own state.

## Open points
- The Terraform docs don't state a minimum version on the backend page itself. The 1.12.0 figure comes from Oracle [OCI-STATE].
- Oracle's page shows a `terraform_remote_state` example with `backend = "oci"` that uses S3-style arguments. Treat it as unreliable and follow [TF-OCI].
