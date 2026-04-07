resource "google_service_account" "costintel_readonly" {
  account_id   = var.gcp_service_account_id
  display_name = "CostIntel Read-Only Integration"
  description  = "Read-only service account for billing + storage intelligence"
}

# Billing export read-only.
resource "google_project_iam_member" "billing_viewer" {
  project = var.gcp_project_id
  role    = "roles/billing.viewer"
  member  = "serviceAccount:${google_service_account.costintel_readonly.email}"
}

# Object metadata read-only for inventory and storage telemetry.
resource "google_project_iam_member" "storage_object_viewer" {
  project = var.gcp_project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.costintel_readonly.email}"
}

# BigQuery export read-only for billing datasets.
resource "google_project_iam_member" "bigquery_data_viewer" {
  project = var.gcp_project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.costintel_readonly.email}"
}
