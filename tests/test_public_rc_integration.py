"""Release integration invariants shared by PR and delivery workflows."""
from pathlib import Path


def test_legacy_workflows_cannot_publish_stable_without_candidate_gate():
    for name in ('repository-structure.yml', 'fixture-hotfix.yml'):
        text = (Path('.github/workflows') / name).read_text()
        assert '--publish' not in text, name
        assert 'contents: write' not in text, name


def test_pr_checkout_and_quality_evidence_use_the_candidate_head():
    text = Path('.github/workflows/ci.yml').read_text()
    assert 'CANDIDATE_SHA: ${{ github.event.pull_request.head.sha || github.sha }}' in text
    assert text.count('ref: ${{ env.CANDIDATE_SHA }}') == text.count('uses: actions/checkout@')
    assert '--sha "$CANDIDATE_SHA"' in text


def test_delivered_ci_runs_both_real_bat_launchers():
    text = Path('.github/workflows/ci.yml').read_text()
    assert '--launcher --wizard-browser' in text
    assert '--mock-launcher' in text
