import pytest
from datetime import timedelta
from decimal import Decimal
from django.utils.timezone import now
from eventyay.base.models import Event, Organizer

from eventyay_business.models import (
    AddonAssignmentScope,
    AddonDefinition,
    AddonPricingMode,
    AddonStatus,
    EventAddon,
    OrganizerAddon,
)


@pytest.mark.django_db
def test_addon_definition_creation_and_typed_values():
    # Boolean Addon
    bool_addon = AddonDefinition.objects.create(
        slug="loungemesh-pack",
        name="Loungemesh 3D Space",
        capability="video.loungemesh",
        entitlement_value="true",
        assignment_scope=AddonAssignmentScope.ORGANIZER,
        pricing_mode=AddonPricingMode.RECURRING,
        price=Decimal("49.00"),
        currency="USD",
    )
    assert bool_addon.get_typed_value() is True
    assert str(bool_addon) == "Loungemesh 3D Space"

    # Integer Addon
    int_addon = AddonDefinition.objects.create(
        slug="jitsi-extra-rooms",
        name="Jitsi 5 Extra Rooms",
        capability="video.jitsi.concurrent_rooms",
        entitlement_value="5",
        quantity=5,
        assignment_scope=AddonAssignmentScope.ORGANIZER,
        pricing_mode=(
            AddonPricingMode.MONTHLY
            if hasattr(AddonPricingMode, "MONTHLY")
            else AddonPricingMode.RECURRING
        ),
        price=Decimal("25.00"),
    )
    assert int_addon.get_typed_value() == 5

    # Decimal Addon
    dec_addon = AddonDefinition.objects.create(
        slug="reduced-platform-fee",
        name="Reduced Fee Addon",
        capability="commerce.platform_fee_percent",
        entitlement_value="1.5",
        price=Decimal("99.00"),
    )
    assert dec_addon.get_typed_value() == Decimal("1.5")


@pytest.mark.django_db
def test_organizer_addon_assignment_lifecycle():
    organizer = Organizer.objects.create(name="Test Org", slug="test-org")
    addon = AddonDefinition.objects.create(
        slug="extra-seats",
        name="Extra Admin Seat",
        capability="organizer.full_admins",
        entitlement_value="1",
        quantity=1,
    )

    # Active assignment
    oa = OrganizerAddon.objects.create(
        organizer=organizer,
        addon=addon,
        quantity=2,
        starts_at=now() - timedelta(days=1),
        ends_at=now() + timedelta(days=30),
        status=AddonStatus.ACTIVE,
    )
    assert oa.is_active is True
    assert str(oa) == f"{addon.name} for {organizer} (active)"

    # Expired by date
    oa.ends_at = now() - timedelta(minutes=1)
    oa.save()
    assert oa.is_active is False

    # Inactive by status
    oa.ends_at = now() + timedelta(days=30)
    oa.status = AddonStatus.CANCELED
    oa.save()
    assert oa.is_active is False

    # Inactive due to future starts_at
    oa.status = AddonStatus.ACTIVE
    oa.starts_at = now() + timedelta(days=5)
    oa.save()
    assert oa.is_active is False


@pytest.mark.django_db
def test_event_addon_assignment_lifecycle():
    organizer = Organizer.objects.create(name="Test Org 2", slug="test-org-2")
    event = Event.objects.create(
        organizer=organizer,
        name="Test Event",
        slug="test-event",
        date_from=now(),
    )
    addon = AddonDefinition.objects.create(
        slug="event-exhibition",
        name="Exhibition Module",
        capability="plugin.exhibition",
        entitlement_value="true",
        assignment_scope=AddonAssignmentScope.EVENT,
    )

    ea = EventAddon.objects.create(
        event=event,
        addon=addon,
        quantity=1,
        starts_at=now() - timedelta(hours=1),
        status=AddonStatus.ACTIVE,
    )
    assert ea.is_active is True
    assert str(ea) == f"{addon.name} for {event} (active)"

    ea.status = AddonStatus.EXPIRED
    ea.save()
    assert ea.is_active is False
