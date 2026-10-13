variable "tenancy_ocid" {
  description = "Tenancy root identifier, supplied by CI from the credential contract."
  type        = string
}

locals {
  environments = toset(["platform", "production", "staging"])
  environment_tags = {
    for name in local.environments : name => {
      "appiahco.environment" = name
      "appiahco.managed-by"  = "terraform"
    }
  }
  # Taxonomy resources cannot depend on the tag definitions they create.
  taxonomy_tags = { environment = "platform", managed-by = "terraform" }
}

# Tenancy-wide exception: the namespace and definitions are shared by all Roots.
# No default is attached to the Tenancy root, so Bootstrap stays untagged.
resource "oci_identity_tag_namespace" "appiahco" {
  compartment_id = var.tenancy_ocid
  name           = "appiahco"
  description    = "Shared taxonomy for resources governed by Terraform."
  freeform_tags  = local.taxonomy_tags
}

resource "oci_identity_tag" "environment" {
  tag_namespace_id = oci_identity_tag_namespace.appiahco.id
  name             = "environment"
  description      = "Environment owning the resource."
  freeform_tags    = local.taxonomy_tags
  validator {
    validator_type = "ENUM"
    values         = ["platform", "production", "staging"]
  }
}

resource "oci_identity_tag" "managed_by" {
  tag_namespace_id = oci_identity_tag_namespace.appiahco.id
  name             = "managed-by"
  description      = "Source of management for the resource."
  freeform_tags    = local.taxonomy_tags
}

resource "oci_identity_compartment" "environments" {
  for_each       = local.environments
  compartment_id = var.tenancy_ocid
  name           = each.key
  description    = "${title(each.key)} resources governed by Foundation."
  defined_tags   = local.environment_tags[each.key]
  depends_on     = [oci_identity_tag.environment, oci_identity_tag.managed_by]
}

resource "oci_identity_compartment" "edge" {
  for_each       = toset(["production", "staging"])
  compartment_id = oci_identity_compartment.environments[each.key].id
  name           = "edge"
  description    = "Public-facing resources for ${title(each.key)}."
  defined_tags   = local.environment_tags[each.key]
}

resource "oci_identity_tag_default" "environment" {
  for_each          = local.environments
  compartment_id    = oci_identity_compartment.environments[each.key].id
  tag_definition_id = oci_identity_tag.environment.id
  value             = each.key
  is_required       = false
}

# Edge inherits both defaults from its environment; explicit CI tags remain mandatory.
resource "oci_identity_tag_default" "managed_by" {
  for_each          = local.environments
  compartment_id    = oci_identity_compartment.environments[each.key].id
  tag_definition_id = oci_identity_tag.managed_by.id
  value             = "terraform"
  is_required       = false
}

# Attach future Workload policies to their environment compartments. Foundation
# creates no speculative identities or policies; Bootstrap owns pipeline access.
output "environment_compartment_ids" {
  description = "Authoritative environment compartment identifiers for Workloads."
  value       = { for name, compartment in oci_identity_compartment.environments : name => compartment.id }
}

output "edge_compartment_ids" {
  description = "Edge compartments inheriting their environment's tag defaults."
  value       = { for name, compartment in oci_identity_compartment.edge : name => compartment.id }
}
