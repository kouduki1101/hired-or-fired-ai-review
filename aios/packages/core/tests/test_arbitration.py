from aios_core.policy.arbitration import ProposalKind, arbitrate_proposal
from aios_core.types import HealthStatus


class TestRehatchRequest:
    def test_chaotic_freezes_rehatch(self) -> None:
        """¶0230: 群が過分散(カオス)状態の間はRehatch申請を否認。"""
        d = arbitrate_proposal(ProposalKind.REHATCH_REQUEST, HealthStatus.CHAOTIC)
        assert not d.approved
        assert d.rule == "chaotic_freeze"

    def test_stable_and_fixed_grant(self) -> None:
        assert arbitrate_proposal(ProposalKind.REHATCH_REQUEST, HealthStatus.STABLE).approved
        d = arbitrate_proposal(ProposalKind.REHATCH_REQUEST, HealthStatus.FIXED)
        assert d.approved and d.rule == "diversity_recovery"

    def test_unknown_holds(self) -> None:
        assert not arbitrate_proposal(ProposalKind.REHATCH_REQUEST, HealthStatus.UNKNOWN).approved

    def test_locked_slot_rejected(self) -> None:
        d = arbitrate_proposal(
            ProposalKind.REHATCH_REQUEST, HealthStatus.STABLE, slot_rehatch_locked=True
        )
        assert not d.approved and d.rule == "slot_locked"


class TestRoleChange:
    def test_only_stable_grants(self) -> None:
        assert arbitrate_proposal(ProposalKind.ROLE_CHANGE, HealthStatus.STABLE).approved
        for h in (HealthStatus.FIXED, HealthStatus.CHAOTIC, HealthStatus.UNKNOWN):
            assert not arbitrate_proposal(ProposalKind.ROLE_CHANGE, h).approved
