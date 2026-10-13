variable "tenancy_ocid" {
  description = "Tenancy OCID; IAM users, groups and policies attach at the tenancy root."
  type        = string
}
variable "region" {
  description = "Tenancy home region and state bucket region."
  type        = string
}
variable "state_namespace" {
  description = "Object Storage namespace."
  type        = string
}
variable "state_bucket_name" {
  description = "Unique private state bucket name; also used in policy conditions."
  type        = string
  validation {
    condition     = can(regex("^[A-Za-z0-9_-]+$", var.state_bucket_name))
    error_message = "Use letters, digits, underscores and hyphens only."
  }
}
variable "pipeline_public_keys" {
  description = "Locally generated public PEMs only; private keys must never enter Terraform."
  type        = object({ apply = string, plan = string })
  validation {
    condition = alltrue([for key in values(var.pipeline_public_keys) :
      startswith(trimspace(key), "-----BEGIN PUBLIC KEY-----") &&
      endswith(trimspace(key), "-----END PUBLIC KEY-----") && !strcontains(key, "PRIVATE KEY")
    ])
    error_message = "Provide public PEM keys only."
  }
}
variable "iam_exclusion_mode" {
  description = "Owner verifies name_conditions first; choose deny after enabling OCI IAM Deny if exclusions fail."
  type        = string
  default     = "name_conditions"
  validation {
    condition     = contains(["name_conditions", "deny"], var.iam_exclusion_mode)
    error_message = "Choose name_conditions or deny."
  }
}

variable "pipeline_user_emails" {
  description = "Distinct primary email addresses controlled by the owner; required by identity-domain-backed tenancies."
  type        = object({ apply = string, plan = string })
  validation {
    condition = alltrue([for email in values(var.pipeline_user_emails) :
      can(regex("^[^@[:space:]]+@[^@[:space:]]+\\.[^@[:space:]]+$", email))
    ]) && lower(var.pipeline_user_emails.apply) != lower(var.pipeline_user_emails.plan)
    error_message = "Provide two distinct, valid primary email addresses, one per pipeline user."
  }
}
