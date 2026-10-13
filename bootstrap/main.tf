terraform {
  required_version = "= 1.16.4"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "= 9.9.0"
    }
  }
  # Supply bucket and namespace only once Bootstrap has provisioned state storage.
  backend "oci" {
    key = "bootstrap/terraform.tfstate"
  }
}

provider "oci" {
  ignore_defined_tags = ["Oracle-Tags.CreatedBy", "Oracle-Tags.CreatedOn"]
}

# Execution contract only: infrastructure is delivered in subsequent tickets.
output "root_contract" {
  description = "Exclusive ownership boundary; not a dependency on deployed outputs."
  value = {
    root         = "bootstrap"
    state_key    = "bootstrap/terraform.tfstate"
    owned_scopes = ["pipeline identities", "pipeline policies", "state storage"]
  }
}
