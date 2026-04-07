# Read-Only IAM Mapping for Multi-Cloud Billing and Storage Intelligence

Date: 2026-02-17

## Provider Role Mapping

| Provider | Role Name | Permissions | Purpose |
|---|---|---|---|
| AWS | `costintel-readonly-integration-role` | `ce:GetCostAndUsage`, `ce:GetDimensionValues`, `s3:ListBucket`, `s3:GetObject`, `pricing:GetProducts` | Read billing usage, inventory metadata, and pricing catalog for cost derivation and optimization. |
| GCP | `costintel-readonly@<project>.iam.gserviceaccount.com` | `roles/billing.viewer`, `roles/storage.objectViewer`, `roles/bigquery.dataViewer` | Read billing export datasets, object metadata, and usage tables from BigQuery exports. |
| Azure | `costintel-mi-readonly` (Managed Identity) | `Cost Management Reader`, `Storage Blob Data Reader` | Read subscription cost data and blob metadata for recommendations and dashboards. |

## Why Read-Only Is Sufficient
- Cost optimization does not require write privileges to billing systems.
- Classification and recommendation engines operate on metadata snapshots, not mutable cloud resources.
- Migration approval workflow can be separated from integration roles; execution roles can be gated and temporary.

## Security Justification for Enterprise Reviews
- Least privilege reduces blast radius during key compromise.
- Role scope is constrained to billing export and storage metadata read paths.
- No `Put*`, `Delete*`, or mutation permissions in baseline integration roles.
- Credential rotation is supported without policy expansion.
- All integration actions can be traced to role principal + request id.
