from __future__ import annotations

from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.models import MigrationLifecycleState
from backend.app.services.migration_authorization_service import MigrationAuthorizationService


def test_requires_explicit_ack_when_confidence_is_low() -> None:
    assert MigrationAuthorizationService.requires_explicit_ack(
        decision_state="PREDICTED",
        confidence=0.62,
        threshold=0.80,
    )


def test_requires_explicit_ack_when_decision_is_downgraded() -> None:
    assert MigrationAuthorizationService.requires_explicit_ack(
        decision_state="FALLBACK",
        confidence=0.95,
        threshold=0.80,
    )


def test_state_machine_rejects_illegal_transition() -> None:
    with pytest.raises(ValueError):
        MigrationAuthorizationService.validate_transition(
            current_state=MigrationLifecycleState.PLANNED,
            next_state=MigrationLifecycleState.EXECUTING,
        )


def test_state_machine_allows_planned_to_dry_run() -> None:
    MigrationAuthorizationService.validate_transition(
        current_state=MigrationLifecycleState.PLANNED,
        next_state=MigrationLifecycleState.DRY_RUN,
    )


def test_resource_name_candidates_include_prefixed_and_plain_ids() -> None:
    candidates = MigrationAuthorizationService._resource_name_candidates(
        resource_id="azure::cf72cdae-0fa7-494c-b121-ff37e1dc3ec1"
    )

    assert "azure::cf72cdae-0fa7-494c-b121-ff37e1dc3ec1" in candidates
    assert "cf72cdae-0fa7-494c-b121-ff37e1dc3ec1" in candidates


def test_provider_hint_parses_prefixed_resource_id() -> None:
    provider = MigrationAuthorizationService._provider_hint(
        resource_id="gcp::cf72cdae-0fa7-494c-b121-ff37e1dc3ec1"
    )

    assert provider is not None
    assert provider.value == "GCP"
