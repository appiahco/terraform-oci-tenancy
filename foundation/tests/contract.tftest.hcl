mock_provider "oci" {
  mock_data "oci_cloud_guard_security_policies" {
    defaults = {
      security_policy_collection = [{ items = jsondecode(file("tests/security-policies.json")) }]
    }
  }
}

override_resource {
  target          = oci_identity_compartment.environments["platform"]
  override_during = plan
  values          = { id = "fixture-platform" }
}
override_resource {
  target          = oci_identity_compartment.environments["production"]
  override_during = plan
  values          = { id = "fixture-production" }
}
override_resource {
  target          = oci_identity_compartment.environments["staging"]
  override_during = plan
  values          = { id = "fixture-staging" }
}
override_resource {
  target          = oci_identity_compartment.edge["production"]
  override_during = plan
  values          = { id = "fixture-production-edge" }
}
override_resource {
  target          = oci_identity_compartment.edge["staging"]
  override_during = plan
  values          = { id = "fixture-staging-edge" }
}
override_resource {
  target          = oci_cloud_guard_security_recipe.production
  override_during = plan
  values          = { id = "fixture-recipe" }
}
override_resource {
  target          = oci_cloud_guard_security_zone.production
  override_during = plan
  values          = { id = "fixture-zone" }
}

variables {
  tenancy_ocid = "ocid1.tenancy.oc1..fixture"
}

run "governed_foundation" {
  command = plan
  assert {
    condition     = output.root_contract.root == "foundation" && output.root_contract.state_key == "foundation/terraform.tfstate"
    error_message = "Root must own its independent state key."
  }
  assert {
    condition     = toset(keys(oci_identity_compartment.environments)) == toset(["platform", "production", "staging"]) && toset(keys(oci_identity_compartment.edge)) == toset(["production", "staging"])
    error_message = "Foundation owns exactly three environments and two Edge compartments."
  }
  assert {
    condition     = alltrue([for c in oci_identity_compartment.environments : c.compartment_id == var.tenancy_ocid])
    error_message = "Environment compartments belong at the Tenancy root."
  }
  assert {
    condition     = alltrue([for k, c in oci_identity_compartment.environments : c.defined_tags == tomap({ "appiahco.environment" = k, "appiahco.managed-by" = "terraform" })])
    error_message = "CI resources require explicit environment and managed-by tags."
  }
  assert {
    condition     = alltrue([for d in oci_identity_tag_default.environment : !d.is_required])
    error_message = "Defaults must permit explicit overrides and are inherited by Edge."
  }
  assert {
    condition     = toset(oci_identity_tag.environment.validator[0].values) == toset(["platform", "production", "staging"])
    error_message = "Environment taxonomy is an enum."
  }

  assert {
    condition     = alltrue([for k, c in oci_identity_compartment.edge : c.compartment_id == oci_identity_compartment.environments[k].id && c.defined_tags["appiahco.environment"] == k])
    error_message = "Edge must be inside and tagged for its environment."
  }
  assert {
    condition     = oci_cloud_guard_security_zone.production.compartment_id == "fixture-production" && oci_cloud_guard_security_zone.production.security_zone_recipe_id == "fixture-recipe" && oci_cloud_guard_security_recipe.production.compartment_id == "fixture-production"
    error_message = "Production alone owns the zone and its custom recipe in the same plan."
  }
  assert {
    condition     = terraform_data.production_edge_exclusion.input.zone_id == "fixture-zone" && terraform_data.production_edge_exclusion.input.edge_id == "fixture-production-edge"
    error_message = "Production Edge is excluded from Production's zone, never Staging."
  }
  assert {
    condition     = output.environment_compartment_ids == { platform = "fixture-platform", production = "fixture-production", staging = "fixture-staging" } && output.edge_compartment_ids == { production = "fixture-production-edge", staging = "fixture-staging-edge" }
    error_message = "Workloads receives authoritative environment and Edge identifiers."
  }
  assert {
    condition     = contains(local.production_policy_names, "deny public_subnets") && length(local.production_policy_names) == 39 && length(oci_cloud_guard_security_recipe.production.security_policies) == 39
    error_message = "Explicit custom recipe retains deny_public_subnets and resolves each reviewed policy."
  }
}
