terraform {
  backend "oci" {
    key = "bootstrap/terraform.tfstate"
  }
}
