from unittest.mock import Mock

from eventyay_business.capabilities import STANDARD_CAPABILITIES
from eventyay_business.services import seed_standard_entitlements_for_version


def test_seed_standard_entitlements_for_version():
    class DummyEntitlement:
        def __init__(self, tier_version, capability, value, unit, overage_allowed):
            self.tier_version = tier_version
            self.capability = capability
            self.value = value
            self.unit = unit
            self.overage_allowed = overage_allowed

    created_records = []

    class DummyManager:
        def filter(self, **kwargs):
            return self

        def values_list(self, field, flat=True):
            return [r.capability for r in created_records]

        def bulk_create(self, records):
            created_records.extend(records)

    DummyModel = Mock()
    DummyModel.objects = DummyManager()
    DummyModel.side_effect = DummyEntitlement

    mock_version = Mock(id=1)

    # First call: seeds all 13 capabilities
    seed_standard_entitlements_for_version(
        mock_version, TierEntitlementModel=DummyModel
    )
    assert len(created_records) == len(STANDARD_CAPABILITIES)
    assert len(created_records) == 13

    # Verify specific capability values
    seeded = {r.capability: r for r in created_records}
    assert seeded["organizer.full_admins"].value == "2"
    assert seeded["organizer.full_admins"].unit == "admins"
    assert seeded["email.bulk.monthly"].value == "1000"
    assert seeded["registration.free_allowance_per_event"].value == "100"
    assert seeded["video.youtube"].value == "true"
    assert seeded["api.write"].value == "false"

    # Second call: idempotent, does not re-add existing capabilities
    initial_count = len(created_records)
    seed_standard_entitlements_for_version(
        mock_version, TierEntitlementModel=DummyModel
    )
    assert len(created_records) == initial_count
