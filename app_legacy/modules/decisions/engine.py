"""Rule engine for generating cost optimization recommendations."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable

from app.core.constants import DecisionAction
from app.modules.classification.models import ClassificationResult
from app.modules.cost.models import CostRecord


@dataclass
class RuleCondition:
    """Condition for evaluating a rule."""
    field: str
    operator: str  # 'gt', 'lt', 'eq', 'contains', 'in'
    value: Any


@dataclass
class DecisionRule:
    """Rule definition for generating recommendations."""
    id: str
    name: str
    description: str
    priority: int
    conditions: list[RuleCondition]
    action: DecisionAction
    recommendation_template: str
    confidence: float
    auto_execute: bool  # Whether this rule can auto-execute


class RuleEngine:
    """
    Rule-based decision engine for cost optimization.
    
    Evaluates cost records against rules to generate recommendations.
    """
    
    def __init__(self):
        self.rules: list[DecisionRule] = self._load_rules()
    
    def _load_rules(self) -> list[DecisionRule]:
        """Load default decision rules."""
        return [
            # === STORAGE OPTIMIZATION RULES ===
            DecisionRule(
                id="storage_old_unused",
                name="Old Unused Storage",
                description="Storage buckets not modified in 12+ months",
                priority=10,
                conditions=[
                    RuleCondition("entity_type", "eq", "storage_bucket"),
                    RuleCondition("days_since_update", "gt", 365),
                    RuleCondition("size_gb", "gt", 1),
                ],
                action=DecisionAction.ARCHIVE,
                recommendation_template="Storage bucket '{resource_id}' has not been modified in {days} days. Consider archiving to Glacier/Coldline storage or deleting if no longer needed. Potential savings: ${savings}/month.",
                confidence=0.85,
                auto_execute=False,
            ),
            DecisionRule(
                id="storage_large_infrequent",
                name="Large Infrequent Access Storage",
                description="Large storage buckets with infrequent access patterns",
                priority=9,
                conditions=[
                    RuleCondition("entity_type", "eq", "storage_bucket"),
                    RuleCondition("size_gb", "gt", 1000),
                    RuleCondition("storage_class", "eq", "STANDARD"),
                ],
                action=DecisionAction.DOWNSIZE,
                recommendation_template="Large storage bucket '{resource_id}' ({size_gb} GB) is in standard tier. Consider moving to Infrequent Access or Archive tier. Potential savings: ${savings}/month.",
                confidence=0.80,
                auto_execute=False,
            ),
            
            # === COMPUTE OPTIMIZATION RULES ===
            DecisionRule(
                id="compute_low_utilization",
                name="Low Utilization Compute",
                description="Compute instances with low CPU/memory utilization",
                priority=10,
                conditions=[
                    RuleCondition("entity_type", "eq", "compute_instance"),
                    RuleCondition("avg_cpu_utilization", "lt", 20),
                    RuleCondition("running_hours", "gt", 720),  # Running full month
                ],
                action=DecisionAction.DOWNSIZE,
                recommendation_template="Compute instance '{resource_id}' has low utilization ({cpu}%). Consider downsizing to a smaller instance type or using burstable/spot instances. Potential savings: ${savings}/month.",
                confidence=0.85,
                auto_execute=False,
            ),
            DecisionRule(
                id="compute_stopped_long_term",
                name="Long-Term Stopped Instances",
                description="Compute instances stopped for more than 30 days",
                priority=8,
                conditions=[
                    RuleCondition("entity_type", "eq", "compute_instance"),
                    RuleCondition("state", "eq", "stopped"),
                    RuleCondition("days_stopped", "gt", 30),
                ],
                action=DecisionAction.DELETE,
                recommendation_template="Instance '{resource_id}' has been stopped for {days} days. Consider creating an AMI and terminating the instance to stop paying for EBS storage. Potential savings: ${savings}/month.",
                confidence=0.75,
                auto_execute=False,
            ),
            DecisionRule(
                id="compute_dev_non_business_hours",
                name="Dev Instances Running Off-Hours",
                description="Development instances running outside business hours",
                priority=7,
                conditions=[
                    RuleCondition("entity_type", "eq", "compute_instance"),
                    RuleCondition("environment", "contains", "dev"),
                    RuleCondition("running_hours", "gt", 168),  # Running 24/7
                ],
                action=DecisionAction.DOWNSIZE,
                recommendation_template="Development instance '{resource_id}' is running 24/7. Consider implementing auto-start/stop for business hours only. Potential savings: ${savings}/month.",
                confidence=0.70,
                auto_execute=False,
            ),
            
            # === DATABASE OPTIMIZATION RULES ===
            DecisionRule(
                id="db_overprovisioned",
                name="Overprovisioned Database",
                description="Databases with low connection count relative to capacity",
                priority=8,
                conditions=[
                    RuleCondition("entity_type", "eq", "database"),
                    RuleCondition("max_connections", "gt", 100),
                    RuleCondition("avg_connections", "lt", 10),
                ],
                action=DecisionAction.DOWNSIZE,
                recommendation_template="Database '{resource_id}' is overprovisioned ({max_conn} max, {avg_conn} avg connections). Consider downsizing to a smaller instance class. Potential savings: ${savings}/month.",
                confidence=0.75,
                auto_execute=False,
            ),
            DecisionRule(
                id="db_unused_read_replica",
                name="Unused Read Replica",
                description="Read replicas with zero or minimal read activity",
                priority=7,
                conditions=[
                    RuleCondition("entity_type", "eq", "database"),
                    RuleCondition("is_read_replica", "eq", True),
                    RuleCondition("read_iops", "lt", 10),
                ],
                action=DecisionAction.DELETE,
                recommendation_template="Read replica '{resource_id}' has minimal read activity. Consider deleting if not needed. Potential savings: ${savings}/month.",
                confidence=0.70,
                auto_execute=False,
            ),
            
            # === COST ANOMALY RULES ===
            DecisionRule(
                id="cost_spike_detection",
                name="Cost Spike Detected",
                description="Unusual cost increase detected",
                priority=10,
                conditions=[
                    RuleCondition("cost_variance_pct", "gt", 50),
                    RuleCondition("current_cost", "gt", 100),
                ],
                action=DecisionAction.REVIEW,
                recommendation_template="Cost spike detected for '{resource_id}'. Costs increased by {variance}% compared to baseline. Review recent changes or usage patterns. Potential overcharge: ${savings}/month.",
                confidence=0.80,
                auto_execute=False,
            ),
            
            # === ARCHIVE CANDIDATE RULES ===
            DecisionRule(
                id="obsolete_resources",
                name="Potentially Obsolete Resources",
                description="Resources not accessed in 6+ months with low cost",
                priority=5,
                conditions=[
                    RuleCondition("days_since_access", "gt", 180),
                    RuleCondition("monthly_cost", "lt", 50),
                ],
                action=DecisionAction.ARCHIVE,
                recommendation_template="Resource '{resource_id}' has not been accessed in {days} days and costs ${cost}/month. Consider archiving or deleting.",
                confidence=0.60,
                auto_execute=False,
            ),
        ]
    
    def evaluate_record(
        self,
        cost_record: CostRecord,
        classification: ClassificationResult | None,
    ) -> list[dict]:
        """
        Evaluate a cost record against all rules.
        
        Returns list of matching decisions.
        """
        decisions = []
        context = self._build_context(cost_record, classification)
        
        for rule in self.rules:
            if self._evaluate_conditions(rule.conditions, context):
                decision = self._generate_decision(rule, context, cost_record)
                decisions.append(decision)
        
        # Sort by priority (highest first)
        decisions.sort(key=lambda d: d['priority'], reverse=True)
        
        return decisions
    
    def _build_context(
        self,
        cost_record: CostRecord,
        classification: ClassificationResult | None,
    ) -> dict:
        """Build evaluation context from cost record and classification."""
        attrs = cost_record.attributes or {}
        tags = cost_record.tags or {} if hasattr(cost_record, 'tags') else {}
        
        context = {
            # Resource identification
            'resource_id': cost_record.resource_id,
            'entity_type': attrs.get('entity_type', 'unknown'),
            'service_type': cost_record.service_type,
            'provider': cost_record.provider,
            'region': cost_record.region,
            
            # Cost metrics
            'monthly_cost': float(cost_record.cost_amount),
            'usage_quantity': float(cost_record.usage_quantity),
            'usage_unit': cost_record.usage_unit,
            
            # Classification
            'classification_category': classification.category if classification else 'unknown',
            'classification_confidence': classification.confidence if classification else 0,
            
            # Attributes from metadata
            'size_gb': float(attrs.get('size_gb', 0)),
            'object_count': attrs.get('object_count', 0),
            'storage_class': attrs.get('storage_class', 'STANDARD'),
            'avg_cpu_utilization': float(attrs.get('avg_cpu_utilization', 0)),
            'running_hours': attrs.get('running_hours', 0),
            'state': attrs.get('state', 'unknown'),
            'days_stopped': attrs.get('days_stopped', 0),
            'max_connections': attrs.get('max_connections', 0),
            'avg_connections': attrs.get('avg_connections', 0),
            'is_read_replica': attrs.get('is_read_replica', False),
            'read_iops': attrs.get('read_iops', 0),
            'days_since_update': attrs.get('days_since_update', 0),
            'days_since_access': attrs.get('days_since_access', 0),
            'environment': self._get_tag_value(tags, 'environment', ''),
        }
        
        return context
    
    def _evaluate_conditions(
        self,
        conditions: list[RuleCondition],
        context: dict,
    ) -> bool:
        """Evaluate all conditions against the context."""
        for condition in conditions:
            if not self._evaluate_condition(condition, context):
                return False
        return True
    
    def _evaluate_condition(
        self,
        condition: RuleCondition,
        context: dict,
    ) -> bool:
        """Evaluate a single condition."""
        actual_value = context.get(condition.field)
        expected_value = condition.value
        
        if actual_value is None:
            return False
        
        if condition.operator == 'eq':
            return actual_value == expected_value
        elif condition.operator == 'gt':
            try:
                return float(actual_value) > float(expected_value)
            except (ValueError, TypeError):
                return False
        elif condition.operator == 'lt':
            try:
                return float(actual_value) < float(expected_value)
            except (ValueError, TypeError):
                return False
        elif condition.operator == 'contains':
            return str(expected_value).lower() in str(actual_value).lower()
        elif condition.operator == 'in':
            return actual_value in expected_value
        
        return False
    
    def _generate_decision(
        self,
        rule: DecisionRule,
        context: dict,
        cost_record: CostRecord,
    ) -> dict:
        """Generate a decision based on a matched rule."""
        # Calculate potential savings (simple estimation)
        monthly_cost = float(context.get('monthly_cost', 0))
        
        # Estimate savings based on action type
        if rule.action in [DecisionAction.DELETE, DecisionAction.ARCHIVE]:
            estimated_savings = monthly_cost
        elif rule.action == DecisionAction.DOWNSIZE:
            estimated_savings = monthly_cost * 0.5  # Assume 50% savings
        else:
            estimated_savings = monthly_cost * 0.2  # Conservative 20%
        
        # Build recommendation message
        recommendation = rule.recommendation_template.format(
            resource_id=context['resource_id'],
            days=context.get('days_since_update', context.get('days_stopped', 0)),
            size_gb=context.get('size_gb', 0),
            cpu=context.get('avg_cpu_utilization', 0),
            variance=context.get('cost_variance_pct', 0),
            savings=f"{estimated_savings:.2f}",
            cost=f"{monthly_cost:.2f}",
            **context
        )
        
        return {
            'rule_id': rule.id,
            'rule_name': rule.name,
            'priority': rule.priority,
            'action': rule.action.value,
            'recommendation': recommendation,
            'confidence': rule.confidence,
            'auto_execute': rule.auto_execute,
            'estimated_savings_monthly': Decimal(str(estimated_savings)),
            'estimated_cost_to_implement': Decimal('0'),  # Most are config changes
            'context': context,
        }
    
    @staticmethod
    def _get_tag_value(tags: dict, key: str, default: Any = None) -> Any:
        """Get a tag value by key (case-insensitive)."""
        key_lower = key.lower()
        for k, v in tags.items():
            if k.lower() == key_lower:
                return v
        return default
