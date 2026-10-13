terraform {
  required_version = "= 1.16.4"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "= 9.9.0"
    }
  }
}

provider "oci" {
  region              = var.region
  ignore_defined_tags = ["Oracle-Tags.CreatedBy", "Oracle-Tags.CreatedOn"]
}

output "root_contract" {
  description = "Exclusive ownership boundary; not a dependency on deployed outputs."
  value = {
    root         = "bootstrap"
    state_key    = "bootstrap/terraform.tfstate"
    owned_scopes = ["pipeline identities", "pipeline policies", "state storage"]
  }
}
