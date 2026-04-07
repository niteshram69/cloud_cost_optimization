output "aws_readonly_role_arn" {
  value       = aws_iam_role.costintel_readonly.arn
  description = "AWS role ARN to be configured in cross-account integration."
}

output "gcp_readonly_service_account_email" {
  value       = google_service_account.costintel_readonly.email
  description = "GCP service account email for read-only integration."
}

output "azure_readonly_identity_principal_id" {
  value       = azurerm_user_assigned_identity.costintel_readonly.principal_id
  description = "Azure managed identity principal id for role assignment reviews."
}
