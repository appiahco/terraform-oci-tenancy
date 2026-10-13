locals {
  pipeline_names = { apply = "terraform-apply", plan = "terraform-plan" }
  # Target names are absent on creation. Membership changes require GROUP_UPDATE.
  group_names_excluded  = join(", ", [for name in values(local.pipeline_names) : "target.group.name != '${name}'"])
  policy_names_excluded = join(", ", [for name in values(local.pipeline_names) : "target.policy.name != '${name}'"])
  group_exclusion       = "any {all {request.permission != 'GROUP_UPDATE', request.permission != 'GROUP_DELETE'}, all {${local.group_names_excluded}}}"
  policy_exclusion      = "any {all {request.permission != 'POLICY_UPDATE', request.permission != 'POLICY_DELETE'}, all {${local.policy_names_excluded}}}"
  apply_condition       = var.iam_exclusion_mode == "deny" ? "target.compartment.name != 'bootstrap'" : "all {target.compartment.name != 'bootstrap', ${local.group_exclusion}, ${local.policy_exclusion}}"
}

resource "oci_identity_compartment" "bootstrap" {
  compartment_id = var.tenancy_ocid
  name           = "bootstrap"
  description    = "Manual Bootstrap: protected Terraform state storage."
  enable_delete  = false
  defined_tags   = {}
  freeform_tags  = {}
}

resource "oci_objectstorage_bucket" "state" {
  compartment_id = oci_identity_compartment.bootstrap.id
  namespace      = var.state_namespace
  name           = var.state_bucket_name
  access_type    = "NoPublicAccess"
  versioning     = "Enabled"
  storage_tier   = "Standard"
  # No kms_key_id: Oracle-managed encryption. No additional locking service.
  defined_tags  = {}
  freeform_tags = {}
  lifecycle {
    prevent_destroy = true
  }
}

resource "oci_identity_user" "pipeline" {
  for_each       = local.pipeline_names
  compartment_id = var.tenancy_ocid
  name           = each.value
  description    = "Terraform ${each.key} user; Bootstrap owned."
  defined_tags   = {}
  freeform_tags  = {}
}
resource "oci_identity_group" "pipeline" {
  for_each       = local.pipeline_names
  compartment_id = var.tenancy_ocid
  name           = each.value
  description    = "Terraform ${each.key} user only."
  defined_tags   = {}
  freeform_tags  = {}
}
resource "oci_identity_user_group_membership" "pipeline" {
  for_each = local.pipeline_names
  user_id  = oci_identity_user.pipeline[each.key].id
  group_id = oci_identity_group.pipeline[each.key].id
}
resource "oci_identity_api_key" "pipeline" {
  for_each  = local.pipeline_names
  user_id   = oci_identity_user.pipeline[each.key].id
  key_value = var.pipeline_public_keys[each.key]
}

# Root attachment is necessary for tenancy-wide PR reads and main/Drift access.
resource "oci_identity_policy" "pipeline" {
  for_each       = local.pipeline_names
  compartment_id = var.tenancy_ocid
  name           = each.value
  description    = "Bootstrap-owned ${each.key} permissions."
  defined_tags   = {}
  freeform_tags  = {}
  statements = each.key == "plan" ? [
    "Allow group ${oci_identity_group.pipeline[each.key].name} to read all-resources in tenancy"
    ] : concat([
      "Allow group ${oci_identity_group.pipeline[each.key].name} to manage all-resources in tenancy where ${local.apply_condition}",
      "Allow group ${oci_identity_group.pipeline[each.key].name} to read buckets in compartment bootstrap where target.bucket.name = '${var.state_bucket_name}'",
      "Allow group ${oci_identity_group.pipeline[each.key].name} to manage objects in compartment bootstrap where target.bucket.name = '${var.state_bucket_name}'"
      ], var.iam_exclusion_mode == "deny" ? flatten([for name in values(local.pipeline_names) : [
        "Deny group ${oci_identity_group.pipeline[each.key].name} to use groups in tenancy where target.group.name = '${name}'",
        "Deny group ${oci_identity_group.pipeline[each.key].name} to manage policies in tenancy where target.policy.name = '${name}'"
  ]]) : [])
}

output "setup" {
  description = "Public setup values only; never includes private keys."
  value = {
    compartment_ocid = oci_identity_compartment.bootstrap.id
    bucket           = oci_objectstorage_bucket.state.name
    namespace        = var.state_namespace
    users            = { for role, user in oci_identity_user.pipeline : role => user.id }
    groups           = { for role, group in oci_identity_group.pipeline : role => group.id }
    policies         = { for role, policy in oci_identity_policy.pipeline : role => policy.id }
    fingerprints     = { for role, key in oci_identity_api_key.pipeline : role => key.fingerprint }
  }
}

output "bootstrap_inputs" {
  description = "Public inputs for subsequent Bootstrap plans; CI reads these from migrated state."
  value = {
    tenancy_ocid         = var.tenancy_ocid
    region               = var.region
    state_bucket_name    = var.state_bucket_name
    state_namespace      = var.state_namespace
    pipeline_public_keys = var.pipeline_public_keys
    iam_exclusion_mode   = var.iam_exclusion_mode
  }
}
