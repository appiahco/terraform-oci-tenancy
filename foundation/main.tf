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
    key = "foundation/terraform.tfstate"
  }
}

provider "oci" {
  ignore_defined_tags = ["Oracle-Tags.CreatedBy", "Oracle-Tags.CreatedOn"]
}

# Foundation owns governance; networking and the remaining baseline arrive separately.
output "root_contract" {
  description = "Exclusive ownership boundary; not a dependency on deployed outputs."
  value = {
    root         = "foundation"
    state_key    = "foundation/terraform.tfstate"
    owned_scopes = ["compartments", "tenancy IAM", "networking", "security baseline"]
  }
}
