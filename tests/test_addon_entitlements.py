import pytest
from datetime import timedelta
from django.utils.timezone import now
from eventyay.base.entitlements import check_entitlement
from eventyay.base.models import Event, Organizer

from eventyay_business.models import (
    AddonAssignmentScope,
    AddonDefinition,
    AddonStatus,
    EventAddon,
    OrganizerAddon,
    Subscription,
    SubscriptionStatus,
    Tier,
    TierEntitlement,
    TierStatus,
    TierVersion,
)


@pytest.fixture
def test_setup():
    organizer = Organizer.objects.create(name="Addon Org", slug="addon-org")
    tier = Tier.objects.create(
        name="Custom Tier", slug="custom-tier", status=TierStatus.PUBLISHED
    )
    version = TierVersion.objects.create(tier=tier, version=1, published_at=now())

    # Jitsi rooms = 1, Loungemesh = False
    TierEntitlement.objects.create(
        tier_version=version,
        capability="video.jitsi.concurrent_rooms",
        value="1",
    )
    TierEntitlement.objects.create(
        tier_version=version,
        capability="video.loungemesh",
        value="false",
    )

    Subscription.objects.create(
        organizer=organizer,
        tier_version=version,
        status=SubscriptionStatus.ACTIVE,
        starts_at=now() - timedelta(days=1),
    )
    return organizer


@pytest.mark.django_db
def test_boolean_addon_enhancement(test_setup):
    organizer = test_setup

    # Initially false on tier
    decision = check_entitlement(organizer, "video.loungemesh")
    assert decision.allowed is False

    # Add Loungemesh addon
    addon = AddonDefinition.objects.create(
        slug="loungemesh-pack",
        name="Loungemesh",
        capability="video.loungemesh",
        entitlement_value="true",
    )
    oa = OrganizerAddon.objects.create(
        organizer=organizer,
        addon=addon,
        status=AddonStatus.ACTIVE,
    )

    decision = check_entitlement(organizer, "video.loungemesh")
    assert decision.allowed is True

    # Deactivate addon
    oa.status = AddonStatus.CANCELED
    oa.save()

    decision = check_entitlement(organizer, "video.loungemesh")
    assert decision.allowed is False


@pytest.mark.django_db
def test_integer_addon_additive_quota(test_setup):
    organizer = test_setup

    # Tier allows 1 room
    assert (
        check_entitlement(organizer, "video.jitsi.concurrent_rooms", quantity=1).allowed
        is True
    )
    assert (
        check_entitlement(organizer, "video.jitsi.concurrent_rooms", quantity=2).allowed
        is False
    )

    # Add extra 3 rooms addon
    addon = AddonDefinition.objects.create(
        slug="extra-rooms",
        name="3 Extra Rooms",
        capability="video.jitsi.concurrent_rooms",
        entitlement_value="3",
        quantity=1,
    )
    OrganizerAddon.objects.create(
        organizer=organizer,
        addon=addon,
        quantity=1,
        status=AddonStatus.ACTIVE,
    )

    # Total limit is now 1 + 3 = 4
    decision_3 = check_entitlement(
        organizer, "video.jitsi.concurrent_rooms", quantity=3
    )
    assert decision_3.allowed is True
    assert decision_3.limit == 4

    decision_4 = check_entitlement(
        organizer, "video.jitsi.concurrent_rooms", quantity=4
    )
    assert decision_4.allowed is True
    assert decision_4.limit == 4

    decision_5 = check_entitlement(
        organizer, "video.jitsi.concurrent_rooms", quantity=5
    )
    assert decision_5.allowed is False
    assert decision_5.limit == 4


@pytest.mark.django_db
def test_event_scoped_addon_entitlement(test_setup):
    organizer = test_setup
    event1 = Event.objects.create(
        organizer=organizer, name="Event 1", slug="event-1", date_from=now()
    )
    event2 = Event.objects.create(
        organizer=organizer, name="Event 2", slug="event-2", date_from=now()
    )

    addon = AddonDefinition.objects.create(
        slug="event-space",
        name="Event Spatial Lounge",
        capability="video.loungemesh",
        entitlement_value="true",
        assignment_scope=AddonAssignmentScope.EVENT,
    )
    EventAddon.objects.create(
        event=event1,
        addon=addon,
        status=AddonStatus.ACTIVE,
    )

    # Allowed for event1
    assert (
        check_entitlement(organizer, "video.loungemesh", event=event1).allowed is True
    )

    # Denied for event2
    assert (
        check_entitlement(organizer, "video.loungemesh", event=event2).allowed is False
    )

    # Denied when no event is passed
    assert check_entitlement(organizer, "video.loungemesh").allowed is False
