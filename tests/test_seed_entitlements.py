from django.db import IntegrityError
from unittest.mock import Mock

from eventyay_business.capabilities import STANDARD_CAPABILITIES
from eventyay_business.services import seed_standard_entitlements_for_version


class DummyEntitlement:
    def __init__(self, tier_version, capability, value, unit, overage_allowed):
        self.tier_version = tier_version
        self.capability = capability
        self.value = value
        self.unit = unit
        self.overage_allowed = overage_allowed


class DummyQuerySet:
    def __init__(self, records):
        self.records = records

    def values_list(self, field, flat=True):
        return [getattr(r, field) for r in self.records]


class DummyManager:
    def __init__(self, created_records):
        self.created_records = created_records

    def filter(self, **kwargs):
        matching = self.created_records
        if "tier_version" in kwargs:
            matching = [r for r in matching if r.tier_version == kwargs["tier_version"]]
        return DummyQuerySet(matching)

    def bulk_create(self, records, ignore_conflicts=False):
        for r in records:
            exists = any(
                existing.tier_version == r.tier_version
                and existing.capability == r.capability
                for existing in self.created_records
            )
            if exists:
                if ignore_conflicts:
                    continue
                raise IntegrityError("Duplicate entry violates unique constraint")
            self.created_records.append(r)


def test_seed_standard_entitlements_for_version():
    created_records = []
    DummyModel = Mock()
    DummyModel.objects = DummyManager(created_records)
    DummyModel.side_effect = DummyEntitlement

    mock_version_1 = Mock(id=1)
    mock_version_2 = Mock(id=2)

    # First call: seeds all 13 capabilities for version 1
    seed_standard_entitlements_for_version(
        mock_version_1, TierEntitlementModel=DummyModel
    )
    v1_records = [r for r in created_records if r.tier_version == mock_version_1]
    assert len(v1_records) == len(STANDARD_CAPABILITIES)
    assert len(v1_records) == 13

    # Verify specific capability values
    seeded = {r.capability: r for r in v1_records}
    assert seeded["organizer.full_admins"].value == "2"
    assert seeded["organizer.full_admins"].unit == "admins"
    assert seeded["email.bulk.monthly"].value == "1000"
    assert seeded["registration.free_allowance_per_event"].value == "100"
    assert seeded["video.youtube"].value == "true"
    assert seeded["api.write"].value == "false"

    # Seed records for a second tier version: each version receives its own 13 entitlements
    seed_standard_entitlements_for_version(
        mock_version_2, TierEntitlementModel=DummyModel
    )
    v2_records = [r for r in created_records if r.tier_version == mock_version_2]
    assert len(v2_records) == 13
    assert len(created_records) == 26

    # Subsequent call on version 1: idempotent, does not re-add existing capabilities
    seed_standard_entitlements_for_version(
        mock_version_1, TierEntitlementModel=DummyModel
    )
    assert len(created_records) == 26


def test_seed_standard_entitlements_concurrency_conflict_tolerance():
    """Verify concurrent calls with simulated race conditions do not raise unique constraint errors."""
    created_records = []
    mock_version = Mock(id=1)

    class ConcurrencySimulatingManager(DummyManager):
        def bulk_create(self, records, ignore_conflicts=False):
            # Simulate a race condition: another thread inserted the first capability in the interim
            first = records[0]
            already_there = any(
                existing.tier_version == first.tier_version
                and existing.capability == first.capability
                for existing in self.created_records
            )
            if not already_there:
                self.created_records.append(first)

            # Now call standard bulk_create with ignore_conflicts
            super().bulk_create(records, ignore_conflicts=ignore_conflicts)

    DummyModel = Mock()
    DummyModel.objects = ConcurrencySimulatingManager(created_records)
    DummyModel.side_effect = DummyEntitlement

    # Without ignore_conflicts, the duplicate would fail; with conflict tolerance it must succeed
    seed_standard_entitlements_for_version(
        mock_version, TierEntitlementModel=DummyModel
    )
    v1_records = [r for r in created_records if r.tier_version == mock_version]
    assert len(v1_records) == 13
