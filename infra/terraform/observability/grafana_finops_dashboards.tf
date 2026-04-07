terraform {
  required_providers {
    grafana = {
      source  = "grafana/grafana"
      version = ">= 2.9.0"
    }
  }
}

variable "grafana_folder_uid" {
  type        = string
  description = "Grafana folder UID for FinOps dashboards"
}

resource "grafana_dashboard" "finops_end_user" {
  folder = var.grafana_folder_uid
  config_json = jsonencode({
    title = "FinOps Optimization - End User"
    tags  = ["finops", "optimization", "end-user"]
    schemaVersion = 39
    timezone = "browser"
    panels = [
      {
        id = 1
        type = "stat"
        title = "Estimated Savings (USD)"
        gridPos = { h = 4, w = 6, x = 0, y = 0 }
        targets = [{ expr = "sum(increase(savings_estimated_usd[30d]))" }]
      },
      {
        id = 2
        type = "stat"
        title = "Realized Savings (USD)"
        gridPos = { h = 4, w = 6, x = 6, y = 0 }
        targets = [{ expr = "sum(increase(savings_realized_usd[30d]))" }]
      },
      {
        id = 3
        type = "timeseries"
        title = "Decision States"
        gridPos = { h = 8, w = 12, x = 0, y = 4 }
        targets = [{ expr = "sum by (decision_state) (rate(optimization_decisions_total[5m]))" }]
      },
      {
        id = 4
        type = "timeseries"
        title = "Fallback Actions"
        gridPos = { h = 8, w = 12, x = 12, y = 4 }
        targets = [{ expr = "sum by (fallback_type) (rate(fallback_actions_total[5m]))" }]
      },
      {
        id = 5
        type = "timeseries"
        title = "Pricing Drift Detection"
        gridPos = { h = 8, w = 12, x = 0, y = 12 }
        targets = [{ expr = "sum(rate(pricing_version_drift_detected[5m]))" }]
      },
      {
        id = 6
        type = "timeseries"
        title = "Confidence Decay Factors"
        gridPos = { h = 8, w = 12, x = 12, y = 12 }
        targets = [{ expr = "avg by (factor_name) (confidence_decay_factor)" }]
      }
    ]
  })
}

resource "grafana_dashboard" "finops_admin" {
  folder = var.grafana_folder_uid
  config_json = jsonencode({
    title = "FinOps Optimization - Platform Admin"
    tags  = ["finops", "optimization", "admin"]
    schemaVersion = 39
    timezone = "browser"
    panels = [
      {
        id = 1
        type = "timeseries"
        title = "Optimization Throughput"
        gridPos = { h = 8, w = 12, x = 0, y = 0 }
        targets = [{ expr = "sum(rate(optimization_decisions_total[5m]))" }]
      },
      {
        id = 2
        type = "timeseries"
        title = "Blocked Decisions"
        gridPos = { h = 8, w = 12, x = 12, y = 0 }
        targets = [{ expr = "sum(rate(optimization_blocked_total[5m]))" }]
      },
      {
        id = 3
        type = "timeseries"
        title = "Migration State Transitions"
        gridPos = { h = 8, w = 12, x = 0, y = 8 }
        targets = [{ expr = "sum by (from_state, to_state) (rate(migration_state_transitions_total[5m]))" }]
      },
      {
        id = 4
        type = "timeseries"
        title = "Pricing Drift Events"
        gridPos = { h = 8, w = 12, x = 12, y = 8 }
        targets = [{ expr = "sum(rate(pricing_version_drift_detected[5m]))" }]
      },
      {
        id = 5
        type = "timeseries"
        title = "Savings Estimated vs Realized"
        gridPos = { h = 8, w = 24, x = 0, y = 16 }
        targets = [
          { expr = "sum(rate(savings_estimated_usd[5m]))", legendFormat = "estimated" },
          { expr = "sum(rate(savings_realized_usd[5m]))", legendFormat = "realized" }
        ]
      }
    ]
  })
}
