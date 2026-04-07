resource "azurerm_user_assigned_identity" "costintel_readonly" {
  name                = var.azure_identity_name
  resource_group_name = var.azure_resource_group_name
  location            = var.azure_location
}

# Subscription-level cost data read-only.
resource "azurerm_role_assignment" "cost_management_reader" {
  scope                = var.azure_cost_scope
  role_definition_name = "Cost Management Reader"
  principal_id         = azurerm_user_assigned_identity.costintel_readonly.principal_id
}

# Storage metadata read-only for blob inventory and usage telemetry.
resource "azurerm_role_assignment" "storage_blob_data_reader" {
  scope                = var.azure_storage_scope
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = azurerm_user_assigned_identity.costintel_readonly.principal_id
}
