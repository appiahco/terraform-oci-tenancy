locals {
  # Reviewed allowlist: resolve names to OCIDs, never adopt the catalogue wholesale.
  production_policy_names = jsondecode(file("${path.module}/security-policy-names.json"))
  policy_ids_by_name = {
    for policy in data.oci_cloud_guard_security_policies.available.security_policy_collection[0].items :
    policy.display_name => policy.id
  }
}

data "oci_cloud_guard_security_policies" "available" {
  compartment_id = var.tenancy_ocid
}

resource "oci_cloud_guard_security_recipe" "production" {
  compartment_id    = oci_identity_compartment.environments["production"].id
  display_name      = "appiahco-production"
  description       = "Reviewed explicit policies; gateways and Vault keys excluded."
  defined_tags      = local.environment_tags["production"]
  security_policies = [for name in local.production_policy_names : local.policy_ids_by_name[name]]
}

resource "oci_cloud_guard_security_zone" "production" {
  compartment_id          = oci_identity_compartment.environments["production"].id
  display_name            = "appiahco-production"
  description             = "Production protection; its Edge compartment is excluded."
  security_zone_recipe_id = oci_cloud_guard_security_recipe.production.id
  defined_tags            = local.environment_tags["production"]
}

# OCI provider 9.9.0 has no remove-compartment resource. Keep the API operation in
# the authoritative Foundation plan, after both the zone and Edge exist. A failed
# exclusion fails Foundation, preventing Workloads. No provisioner runs on plan.
resource "terraform_data" "production_edge_exclusion" {
  triggers_replace = [
    oci_cloud_guard_security_zone.production.id,
    oci_identity_compartment.edge["production"].id,
    filesha256("${path.module}/../scripts/security-zone-edge.py"),
  ]
  input = {
    zone_id = oci_cloud_guard_security_zone.production.id
    edge_id = oci_identity_compartment.edge["production"].id
  }
  provisioner "local-exec" {
    command = "python3 ../scripts/security-zone-edge.py"
    environment = {
      SECURITY_ZONE_ID    = self.input.zone_id
      EDGE_COMPARTMENT_ID = self.input.edge_id
    }
  }
}

output "production_security_zone" {
  description = "Production zone and explicit recipe; available after Edge exclusion succeeds."
  value = {
    zone_id                  = oci_cloud_guard_security_zone.production.id
    recipe_id                = oci_cloud_guard_security_recipe.production.id
    policy_names             = local.production_policy_names
    excluded_compartment_ids = [oci_identity_compartment.edge["production"].id]
  }
  depends_on = [terraform_data.production_edge_exclusion]
}
