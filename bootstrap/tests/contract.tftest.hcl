mock_provider "oci" {}

variables {
  tenancy_ocid      = "ocid1.tenancy.oc1..fixture"
  region            = "us-ashburn-1"
  state_bucket_name = "fixture-state"
  state_namespace   = "fixture-namespace"
  pipeline_user_emails = { apply = "apply@example.com", plan = "plan@example.com" }
  pipeline_public_keys = {
    apply = "-----BEGIN PUBLIC KEY-----\nfixture\n-----END PUBLIC KEY-----"
    plan  = "-----BEGIN PUBLIC KEY-----\nfixture\n-----END PUBLIC KEY-----"
  }
}

run "root_boundary" {
  command = plan
  assert {
    condition     = output.root_contract.root == "bootstrap" && output.root_contract.state_key == "bootstrap/terraform.tfstate"
    error_message = "Root must own its independent state key."
  }
  assert {
    condition     = oci_objectstorage_bucket.state.versioning == "Enabled" && oci_objectstorage_bucket.state.access_type == "NoPublicAccess"
    error_message = "State must be versioned and private."
  }
  assert {
    condition     = oci_identity_user.pipeline["apply"].compartment_id == var.tenancy_ocid && oci_identity_user.pipeline["plan"].compartment_id == var.tenancy_ocid
    error_message = "OCI users are tenancy-scoped; Bootstrap owns both."
  }
  assert {
    condition     = oci_identity_api_key.pipeline["apply"].key_value == var.pipeline_public_keys.apply
    error_message = "Only public PEMs may enter Terraform."
  }
}

run "private_keys_rejected" {
  command = plan
  variables {
    pipeline_public_keys = {
      apply = "-----BEGIN PRIVATE KEY-----\nfixture\n-----END PRIVATE KEY-----"
      plan  = "-----BEGIN PUBLIC KEY-----\nfixture\n-----END PUBLIC KEY-----"
    }
  }
  expect_failures = [var.pipeline_public_keys]
}

run "name_exclusions" {
  command = plan
  assert {
    condition     = strcontains(oci_identity_policy.pipeline["apply"].statements[0], "target.compartment.name != 'bootstrap'") && strcontains(oci_identity_policy.pipeline["apply"].statements[0], "target.group.name != 'terraform-plan'") && strcontains(oci_identity_policy.pipeline["apply"].statements[0], "target.policy.name != 'terraform-apply'")
    error_message = "Apply must exclude Bootstrap and both pipeline groups and policies."
  }
  assert {
    condition     = length(oci_identity_policy.pipeline["plan"].statements) == 1 && endswith(oci_identity_policy.pipeline["plan"].statements[0], "to read all-resources in tenancy")
    error_message = "Plan reads the tenancy and state without writes."
  }
  assert {
    condition     = alltrue([for s in slice(oci_identity_policy.pipeline["apply"].statements, 1, 3) : strcontains(s, "target.bucket.name = 'fixture-state'")])
    error_message = "Bootstrap bucket access must be restricted to the state bucket."
  }
}

run "deny_fallback" {
  command = plan
  variables {
    iam_exclusion_mode = "deny"
  }
  assert {
    condition     = length([for s in oci_identity_policy.pipeline["apply"].statements : s if startswith(s, "Deny ")]) == 4
    error_message = "Fallback must deny changes to both groups and both policies."
  }
}

run "ordinary_iam_operations_keep_access" {
  command = plan
  assert {
    condition     = !strcontains(oci_identity_policy.pipeline["apply"].statements[0], "GROUP_CREATE") && !strcontains(oci_identity_policy.pipeline["apply"].statements[0], "POLICY_CREATE") && !strcontains(oci_identity_policy.pipeline["apply"].statements[0], "USER_UPDATE")
    error_message = "Do not require IAM target names on creation or unrelated user mutations."
  }
}

run "pipeline_users_have_distinct_primary_emails" {
  command = plan
  variables {
    pipeline_user_emails = {
      apply = "apply@example.com"
      plan  = "plan@example.com"
    }
  }
  assert {
    condition = oci_identity_user.pipeline["apply"].email == "apply@example.com" && oci_identity_user.pipeline["plan"].email == "plan@example.com"
    error_message = "Each pipeline user must receive its distinct primary email for identity-domain creation."
  }
  assert {
    condition = output.bootstrap_inputs.pipeline_user_emails.apply == "apply@example.com" && output.bootstrap_inputs.pipeline_user_emails.plan == "plan@example.com"
    error_message = "Later CI plans need the same primary emails from migrated state inputs."
  }
}

run "duplicate_primary_emails_rejected" {
  command = plan
  variables {
    pipeline_user_emails = { apply = "same@example.com", plan = "SAME@example.com" }
  }
  expect_failures = [var.pipeline_user_emails]
}
