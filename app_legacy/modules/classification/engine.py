"""Rule-based classification engine with extensibility for ML models."""

import re
from typing import Any

from app.core.constants import ClassificationCategory


class ClassificationRule:
    """Individual classification rule with matching logic."""
    
    def __init__(
        self,
        name: str,
        category: ClassificationCategory,
        confidence: float,
        condition: callable,
        explanation: str,
    ):
        self.name = name
        self.category = category
        self.confidence = confidence
        self.condition = condition
        self.explanation = explanation
    
    def matches(self, metadata: dict) -> bool:
        """Check if metadata matches this rule's condition."""
        try:
            return self.condition(metadata)
        except Exception:
            return False


class ClassificationEngine:
    """
    Rule-based classification engine for cloud resources.
    
    Classifies resources by:
    - Sensitivity (high/medium/low)
    - Relevance (critical/important/optional)
    - Cost category (compute/storage/network/license)
    - Action recommendation (archive/retain/optimize)
    """
    
    VERSION = "1.0.0"
    
    def __init__(self):
        self.rules: list[ClassificationRule] = self._build_rules()
    
    def _build_rules(self) -> list[ClassificationRule]:
        """Build the rule set for classification."""
        return [
            # === SENSITIVE DATA RULES ===
            ClassificationRule(
                name="production_database",
                category=ClassificationCategory.SENSITIVE,
                confidence=0.95,
                condition=lambda m: (
                    m.get('entity_type') == 'database' and
                    self._has_tag(m, 'environment', ['prod', 'production'])
                ),
                explanation="Production database - contains live application data",
            ),
            ClassificationRule(
                name="user_data_storage",
                category=ClassificationCategory.SENSITIVE,
                confidence=0.90,
                condition=lambda m: (
                    m.get('entity_type') == 'storage_bucket' and
                    any(keyword in str(m.get('tags', {})).lower() 
                        for keyword in ['user', 'customer', 'pii', 'personal'])
                ),
                explanation="Storage containing user or customer data",
            ),
            
            # === ARCHIVE CANDIDATE RULES ===
            ClassificationRule(
                name="old_unused_storage",
                category=ClassificationCategory.ARCHIVE,
                confidence=0.85,
                condition=lambda m: (
                    m.get('entity_type') == 'storage_bucket' and
                    self._get_attribute(m, 'object_count', 0) > 0 and
                    self._days_since_update(m) > 180
                ),
                explanation="Storage bucket not modified in 6+ months - candidate for archival",
            ),
            ClassificationRule(
                name="stopped_instances",
                category=ClassificationCategory.ARCHIVE,
                confidence=0.80,
                condition=lambda m: (
                    m.get('entity_type') == 'compute_instance' and
                    self._get_attribute(m, 'running_hours', 0) == 0
                ),
                explanation="Stopped/stagnant compute instance - candidate for deletion or archival",
            ),
            ClassificationRule(
                name="dev_test_resources",
                category=ClassificationCategory.ARCHIVE,
                confidence=0.75,
                condition=lambda m: (
                    self._has_tag(m, 'environment', ['dev', 'test', 'staging']) and
                    self._days_since_update(m) > 90
                ),
                explanation="Development/testing resources inactive for 90+ days",
            ),
            
            # === INTERNAL/INFRASTRUCTURE RULES ===
            ClassificationRule(
                name="infrastructure_compute",
                category=ClassificationCategory.INTERNAL,
                confidence=0.85,
                condition=lambda m: (
                    m.get('entity_type') in ['compute_instance', 'serverless_function'] and
                    self._has_tag(m, 'purpose', ['infra', 'infrastructure', 'platform'])
                ),
                explanation="Infrastructure compute resources (not customer-facing)",
            ),
            ClassificationRule(
                name="logging_monitoring",
                category=ClassificationCategory.INTERNAL,
                confidence=0.80,
                condition=lambda m: (
                    'log' in str(m.get('attributes', {}).get('service_type', '')).lower() or
                    any(keyword in str(m.get('tags', {})).lower() 
                        for keyword in ['log', 'monitor', 'metric'])
                ),
                explanation="Logging, monitoring, or observability resources",
            ),
            ClassificationRule(
                name="network_resources",
                category=ClassificationCategory.INTERNAL,
                confidence=0.80,
                condition=lambda m: (
                    m.get('entity_type') == 'network_resource' or
                    'VPC' in str(m.get('attributes', {}).get('service_type', ''))
                ),
                explanation="Network infrastructure (VPCs, load balancers, etc.)",
            ),
            
            # === PUBLIC/SHARED RESOURCES ===
            ClassificationRule(
                name="static_website_assets",
                category=ClassificationCategory.PUBLIC,
                confidence=0.85,
                condition=lambda m: (
                    m.get('entity_type') == 'storage_bucket' and
                    self._has_tag(m, 'purpose', ['static', 'website', 'cdn', 'public'])
                ),
                explanation="Public static assets or website content",
            ),
            ClassificationRule(
                name="shared_datasets",
                category=ClassificationCategory.PUBLIC,
                confidence=0.70,
                condition=lambda m: (
                    self._has_tag(m, 'access', ['public', 'shared']) and
                    self._has_tag(m, 'data_type', ['dataset', 'analytics'])
                ),
                explanation="Shared/public datasets for analytics",
            ),
            
            # === COST-HEAVY RESOURCES (need review) ===
            ClassificationRule(
                name="high_cost_storage",
                category=ClassificationCategory.INTERNAL,
                confidence=0.75,
                condition=lambda m: (
                    m.get('entity_type') == 'storage_bucket' and
                    float(self._get_attribute(m, 'size_gb', 0)) > 1000
                ),
                explanation="Large storage bucket (>1TB) - review for optimization opportunities",
            ),
            ClassificationRule(
                name="underutilized_compute",
                category=ClassificationCategory.ARCHIVE,
                confidence=0.70,
                condition=lambda m: (
                    m.get('entity_type') == 'compute_instance' and
                    float(self._get_attribute(m, 'running_hours', 0)) < 100
                ),
                explanation="Compute instance running less than 100 hours - consider downsizing",
            ),
        ]
    
    def classify(self, metadata: dict) -> dict:
        """
        Classify a single metadata record.
        
        Returns classification result with category, confidence, and explanation.
        """
        matching_rules = []
        
        for rule in self.rules:
            if rule.matches(metadata):
                matching_rules.append(rule)
        
        if not matching_rules:
            return {
                'category': ClassificationCategory.UNKNOWN.value,
                'confidence': 0.0,
                'method': 'rule_based',
                'model_version': self.VERSION,
                'rules_applied': [],
                'explanation': 'No matching classification rules found',
            }
        
        # Select highest confidence rule
        best_rule = max(matching_rules, key=lambda r: r.confidence)
        
        return {
            'category': best_rule.category.value,
            'confidence': best_rule.confidence,
            'method': 'rule_based',
            'model_version': self.VERSION,
            'rules_applied': [r.name for r in matching_rules],
            'explanation': best_rule.explanation,
        }
    
    def classify_batch(self, metadata_list: list[dict]) -> list[dict]:
        """Classify multiple metadata records."""
        return [self.classify(m) for m in metadata_list]
    
    # === Helper methods for rule conditions ===
    
    @staticmethod
    def _has_tag(metadata: dict, tag_key: str, values: list[str]) -> bool:
        """Check if metadata has a tag with any of the given values."""
        tags = metadata.get('tags', {})
        tag_value = tags.get(tag_key, '').lower()
        return any(v.lower() in tag_value for v in values)
    
    @staticmethod
    def _get_attribute(metadata: dict, key: str, default: Any = None) -> Any:
        """Safely get an attribute from metadata."""
        attrs = metadata.get('attributes', {})
        value = attrs.get(key, default)
        
        # Try to convert numeric strings
        if isinstance(value, str):
            try:
                if '.' in value:
                    return float(value)
                else:
                    return int(value)
            except ValueError:
                pass
        
        return value
    
    @staticmethod
    def _days_since_update(metadata: dict) -> int:
        """Calculate days since resource was last updated."""
        from datetime import datetime, timezone
        
        updated_at = metadata.get('resource_updated_at')
        if not updated_at:
            updated_at = metadata.get('discovered_at')
        
        if not updated_at:
            return 0
        
        try:
            if isinstance(updated_at, str):
                updated_at = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
            
            delta = datetime.now(timezone.utc) - updated_at
            return delta.days
        except Exception:
            return 0
    
    # === Extensibility hooks for ML ===
    
    def register_ml_model(self, model: Any, model_name: str) -> None:
        """
        Register an ML model for hybrid classification.
        
        Args:
            model: ML model with predict() method
            model_name: Identifier for the model
        """
        # Placeholder for future ML integration
        # Would combine rule-based + ML predictions with weighted confidence
        pass
    
    def classify_with_ml(self, metadata: dict, model_name: str | None = None) -> dict:
        """
        Classify using ML model (placeholder for future implementation).
        
        For now, falls back to rule-based classification.
        """
        # TODO: Implement ML classification when models are available
        return self.classify(metadata)
