mock_provider "oci" {}

run "root_boundary" {
  command = plan
  assert {
    condition     = output.root_contract.root == "workloads" && output.root_contract.state_key == "workloads/terraform.tfstate"
    error_message = "Root must own its independent state key."
  }
  assert {
    condition     = length(output.root_contract.owned_scopes) == 4
    error_message = "Root ownership boundary must remain explicit."
  }
}
