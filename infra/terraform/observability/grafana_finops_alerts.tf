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
  description = "Grafana folder UID for FinOps alert rules"
}

resource "grafana_rule_group" "finops_safety_alerts" {
  name             = "finops-safety-alerts"
  folder_uid       = var.grafana_folder_uid
  interval_seconds = 60

  rule {
    name      = "HighBlockedRate"
    condition = "B"

    data {
      ref_id         = "A"
      datasource_uid = "prometheus"
      model = jsonencode({
        expr = "sum(rate(optimization_blocked_total[15m])) / clamp_min(sum(rate(optimization_decisions_total[15m])), 1)"
      })
    }

    data {
      ref_id         = "B"
      datasource_uid = "__expr__"
      model = jsonencode({
        expression = "A > 0.25"
        type       = "math"
      })
    }

    no_data_state  = "NoData"
    exec_err_state = "Alerting"
    for            = "15m"
    annotations = {
      summary = "Blocked optimization rate above 25%"
      runbook = "https://internal.docs/finops/runbooks/high-blocked-rate"
    }
    labels = {
      severity = "warning"
      service  = "finops-optimizer"
    }
  }

  rule {
    name      = "PricingDriftSpike"
    condition = "B"

    data {
      ref_id         = "A"
      datasource_uid = "prometheus"
      model = jsonencode({
        expr = "sum(increase(pricing_version_drift_detected[10m]))"
      })
    }

    data {
      ref_id         = "B"
      datasource_uid = "__expr__"
      model = jsonencode({
        expression = "A >= 10"
        type       = "math"
      })
    }

    no_data_state  = "NoData"
    exec_err_state = "Alerting"
    for            = "10m"
    annotations = {
      summary = "Pricing drift spike detected"
      runbook = "https://internal.docs/finops/runbooks/pricing-drift"
    }
    labels = {
      severity = "critical"
      service  = "finops-optimizer"
    }
  }

  rule {
    name      = "ConfidenceDecayRegression"
    condition = "B"

    data {
      ref_id         = "A"
      datasource_uid = "prometheus"
      model = jsonencode({
        expr = "avg(confidence_decay_factor)"
      })
    }

    data {
      ref_id         = "B"
      datasource_uid = "__expr__"
      model = jsonencode({
        expression = "A < 0.65"
        type       = "math"
      })
    }

    no_data_state  = "NoData"
    exec_err_state = "Alerting"
    for            = "30m"
    annotations = {
      summary = "Average confidence decay factor below 0.65"
      runbook = "https://internal.docs/finops/runbooks/confidence-regression"
    }
    labels = {
      severity = "warning"
      service  = "finops-optimizer"
    }
  }

  rule {
    name      = "FallbackBurst"
    condition = "B"

    data {
      ref_id         = "A"
      datasource_uid = "prometheus"
      model = jsonencode({
        expr = "sum(increase(fallback_actions_total[10m]))"
      })
    }

    data {
      ref_id         = "B"
      datasource_uid = "__expr__"
      model = jsonencode({
        expression = "A > 20"
        type       = "math"
      })
    }

    no_data_state  = "NoData"
    exec_err_state = "Alerting"
    for            = "10m"
    annotations = {
      summary = "Fallback action burst detected"
      runbook = "https://internal.docs/finops/runbooks/fallback-burst"
    }
    labels = {
      severity = "warning"
      service  = "finops-optimizer"
    }
  }
}
