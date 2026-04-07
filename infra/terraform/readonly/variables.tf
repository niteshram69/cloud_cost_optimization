variable "aws_region" {
  description = "AWS region used for IAM resources."
  type        = string
  default     = "ap-south-1"
}

variable "aws_role_name" {
  description = "Name of the AWS read-only integration role."
  type        = string
  default     = "costintel-readonly-integration-role"
}

variable "aws_trusted_principal_arn" {
  description = "Principal ARN allowed to assume this role (integration control plane)."
  type        = string
}

variable "aws_external_id" {
  description = "Optional external ID for cross-account trust hardening."
  type        = string
  default     = ""
}

variable "aws_inventory_bucket_arns" {
  description = "S3 bucket ARNs that host inventory/log exports for read-only access."
  type        = list(string)
  default     = []
}

variable "gcp_project_id" {
  description = "GCP project where read-only service account will be created."
  type        = string
}

variable "gcp_region" {
  description = "GCP region for provider config."
  type        = string
  default     = "asia-south1"
}

variable "gcp_service_account_id" {
  description = "Service account ID for read-only integration."
  type        = string
  default     = "costintel-readonly"
}

variable "azure_subscription_id" {
  description = "Azure subscription id for role assignments."
  type        = string
}

variable "azure_resource_group_name" {
  description = "Resource group for managed identity creation."
  type        = string
}

variable "azure_location" {
  description = "Azure location for managed identity."
  type        = string
  default     = "centralindia"
}

variable "azure_identity_name" {
  description = "Managed identity name for read-only integration."
  type        = string
  default     = "costintel-mi-readonly"
}

variable "azure_cost_scope" {
  description = "Scope for Cost Management Reader role assignment (usually subscription scope)."
  type        = string
}

variable "azure_storage_scope" {
  description = "Scope for Storage Blob Data Reader role assignment (storage account scope)."
  type        = string
}
