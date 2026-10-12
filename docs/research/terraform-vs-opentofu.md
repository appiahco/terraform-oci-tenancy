# Terraform or OpenTofu with the OCI provider

Research for #2. Checked on 2026-10-12. Latest releases then: Terraform v1.16.5, OpenTofu v1.13.1.

## Question

Is the `oracle/oci` provider fully supported under OpenTofu? That covers registry availability, known incompatibilities, and the native `oci` backend. Given the answer, and the trade-offs on licensing and state encryption, should this repo use Terraform or OpenTofu?

## Findings

### 1. Provider: available on the OpenTofu registry and current

- The OpenTofu registry lists `oracle/oci` and tracks upstream releases. The latest is v9.9.0, published 2026-10-06. `hashicorp/oci` and `opentofu/oci` are aliases that resolve to it. Source: <https://api.opentofu.org/registry/docs/providers/oracle/oci/index.json>
- OpenTofu uses the same provider plugin protocol, so it runs the same Oracle-built binary.

### 2. Provider: no OpenTofu-specific incompatibilities found

- No issue in `oracle/terraform-provider-oci` has "opentofu" in its title. Query: `gh search issues --repo oracle/terraform-provider-oci "opentofu in:title"` returned nothing.
- A full-text search for "opentofu" in that repo only finds ordinary resource bugs that mention OpenTofu in passing. None of them is about OpenTofu compatibility, for example #2615, #2258 and #2460. Source: <https://github.com/oracle/terraform-provider-oci/issues?q=opentofu>
- No issue in `opentofu/opentofu` reports a problem with the Oracle provider. Every "OCI" hit there is about OCI *container registries* (Open Container Initiative), a different OCI, for example #1672 and #2540.
- The provider README makes no claim of OpenTofu support. Oracle does not officially support OpenTofu, but nothing documented is broken. Source: <https://github.com/oracle/terraform-provider-oci/blob/master/README.md>

### 3. Backend: the real incompatibility

- **Terraform** has a native `oci` backend that stores state in OCI Object Storage. It was added in Terraform 1.12.0: "Added Terraform backend implementation for OCI Object Storage" (hashicorp/terraform#34465). Its code lives at `internal/backend/remote-state/oci`. Sources: <https://github.com/hashicorp/terraform/blob/v1.12.0/CHANGELOG.md>, <https://github.com/hashicorp/terraform/tree/main/internal/backend/remote-state>
- **OpenTofu has no `oci` backend.** Its `internal/backend/remote-state` contains only azure, consul, cos, gcs, http, inmem, kubernetes, oss, pg and s3, and its backend docs match that list. Sources: <https://github.com/opentofu/opentofu/tree/main/internal/backend/remote-state>, <https://github.com/opentofu/opentofu/tree/main/website/docs/language/settings/backends>
- I found no open OpenTofu issue that requests an Oracle Object Storage backend. The closest is the general "Backends as plugins" issue (opentofu/opentofu#382).
- With OpenTofu, the workaround is the `s3` backend pointed at OCI Object Storage's Amazon S3 Compatibility API. This needs customer secret keys (HMAC credentials), and the setup uses S3-compatibility flags such as `skip_region_validation`, `use_path_style` and `skip_s3_checksum`. Locking: the `s3` backend's native lockfile (`use_lockfile`) needs conditional writes. I did **not** verify whether OCI's S3 compatibility layer supports them, so treat locking as a risk to test. Sources: <https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/s3compatibleapi.htm>, <https://opentofu.org/docs/language/settings/backends/s3/>

### 4. Trade-offs

| | Terraform | OpenTofu |
|---|---|---|
| License | BUSL 1.1 (source-available) | MPL 2.0 (open source, Linux Foundation) |
| `oracle/oci` provider | Officially targeted by Oracle | Same binary from its own registry; nothing found broken |
| Native OCI state backend | Yes, `oci` (1.12+), authenticated with OCI API keys or instance principals | No. Uses `s3` over the S3 Compatibility API with HMAC keys; locking unverified |
| Client-side state encryption | No (relies on bucket encryption at rest) | Yes, built in since 1.7 (`encryption` block, PBKDF2, AWS/GCP KMS, OpenBao) |

Sources: <https://github.com/hashicorp/terraform/blob/main/LICENSE>, <https://github.com/opentofu/opentofu/blob/main/LICENSE>, <https://opentofu.org/docs/language/state/encryption/>

## Conclusion

The belief that the OCI **provider** is incompatible with OpenTofu is **not supported** by primary sources. The provider is published on the OpenTofu registry, it stays current, and no compatibility bugs are filed against it. The real gap is the **backend**: only Terraform has the native `oci` backend.

Recommendation: use **Terraform**. A tenancy repo depends heavily on state safety. Terraform's native `oci` backend uses ordinary OCI auth and keeps state in Object Storage without HMAC keys or an S3 shim with unverified locking. Pick OpenTofu only if the MPL license or client-side state encryption outweighs that, and accept the `s3`-compatibility backend after testing its locking.
