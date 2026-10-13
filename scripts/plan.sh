#!/usr/bin/env bash
set -euo pipefail
root=$1
mode=$2
case "$root" in bootstrap|foundation|workloads) ;; *) echo 'Unknown Root' >&2; exit 1;; esac
if [[ "$mode" != plan ]]; then
  echo 'Apply mode is reserved for #25; no apply implementation exists.' >&2
  exit 1
fi
for key in OCI_TENANCY_OCID OCI_USER_OCID OCI_FINGERPRINT OCI_PRIVATE_KEY OCI_REGION TF_STATE_BUCKET TF_STATE_NAMESPACE; do
  if [[ -z "${!key:-}" ]]; then echo "Missing $key" >&2; exit 1; fi
done
# Terraform 1.16's native OCI backend reads OCI_<lowercase attribute>.
# Keep uppercase names for the provider and expose matching backend aliases.
export OCI_tenancy_ocid="$OCI_TENANCY_OCID"
export OCI_user_ocid="$OCI_USER_OCID"
export OCI_fingerprint="$OCI_FINGERPRINT"
export OCI_private_key="$OCI_PRIVATE_KEY"
export OCI_region="$OCI_REGION"
export TF_IN_AUTOMATION=true
terraform -chdir="$root" init -input=false -lockfile=readonly \
  -backend-config="bucket=$TF_STATE_BUCKET" -backend-config="namespace=$TF_STATE_NAMESPACE"
terraform -chdir="$root" plan -input=false -no-color -lock=false -out=plan.tfplan > "$root/plan.txt" 2>&1 || {
  cat "$root/plan.txt"
  exit 1
}
cat "$root/plan.txt"
terraform -chdir="$root" show -json plan.tfplan > "$root/plan.json"
