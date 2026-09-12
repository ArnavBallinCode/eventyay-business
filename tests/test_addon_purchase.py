import pytest
from decimal import Decimal
from django.test import override_settings
from django.urls import reverse
from django.utils.timezone import now
from eventyay.base.models import Event, Organizer
from eventyay.base.models.auth import StaffSession

from eventyay_business.models import (
    AddonAssignmentScope,
    AddonDefinition,
    AddonPricingMode,
    AddonStatus,
    EventAddon,
    OrganizerAddon,
)


@pytest.fixture
def business_admin_client(admin_client, admin_user):
    session = admin_client.session
    session.save()
    StaffSession.objects.create(
        user=admin_user,
        session_key=session.session_key,
        comment="test",
    )
    admin_user.is_staff = True
    admin_user.save()
    return admin_client


@pytest.fixture
def organizer_setup():
    organizer = Organizer.objects.create(name="Acme Corp", slug="acme-corp")
    event = Event.objects.create(
        organizer=organizer,
        name="Acme Summit",
        slug="acme-summit",
        date_from=now(),
    )
    return organizer, event


@pytest.mark.django_db
@override_settings(SITE_URL="https://testserver")
def test_organizer_plan_displays_available_addons(
    business_admin_client, organizer_setup
):
    organizer, event = organizer_setup

    AddonDefinition.objects.create(
        name="Public Loungemesh",
        slug="public-loungemesh",
        capability="video.loungemesh",
        entitlement_value="true",
        assignment_scope=AddonAssignmentScope.ORGANIZER,
        price=Decimal("49.00"),
        currency="USD",
        pricing_mode=AddonPricingMode.RECURRING,
        active=True,
        public=True,
    )
    AddonDefinition.objects.create(
        name="Private Custom Feature",
        slug="private-feature",
        capability="plugin.custom",
        entitlement_value="true",
        active=True,
        public=False,
    )
    AddonDefinition.objects.create(
        name="Inactive Addon",
        slug="inactive-addon",
        capability="video.youtube",
        entitlement_value="true",
        active=False,
        public=True,
    )

    url = reverse(
        "plugins:eventyay_business:organizer.plan", kwargs={"organizer": organizer.slug}
    )
    response = business_admin_client.get(url)
    assert response.status_code == 200
    content = response.content.decode()

    assert "Available Add-ons & Extensions" in content
    assert "Public Loungemesh" in content
    assert "Private Custom Feature" not in content
    assert "Inactive Addon" not in content
    assert "Add to Plan" in content


@pytest.mark.django_db
@override_settings(SITE_URL="https://testserver")
def test_purchase_organizer_scoped_addon(business_admin_client, organizer_setup):
    organizer, _ = organizer_setup
    addon = AddonDefinition.objects.create(
        name="Jitsi Room Booster",
        slug="jitsi-room-booster",
        capability="video.jitsi.concurrent_rooms",
        entitlement_value="5",
        quantity=5,
        assignment_scope=AddonAssignmentScope.ORGANIZER,
        price=Decimal("25.00"),
        currency="USD",
        pricing_mode=AddonPricingMode.RECURRING,
        active=True,
        public=True,
    )

    purchase_url = reverse(
        "plugins:eventyay_business:organizer.addon.purchase",
        kwargs={"organizer": organizer.slug, "pk": addon.pk},
    )

    # GET displays details
    resp_get = business_admin_client.get(purchase_url)
    assert resp_get.status_code == 200
    assert "Jitsi Room Booster" in resp_get.content.decode()

    # POST purchases
    resp_post = business_admin_client.post(purchase_url, {"quantity": 10}, follow=True)
    assert resp_post.status_code == 200

    assignment = OrganizerAddon.objects.get(organizer=organizer, addon=addon)
    assert assignment.quantity == 10
    assert assignment.capability == "video.jitsi.concurrent_rooms"
    assert assignment.entitlement_value == "5"
    assert assignment.price == Decimal("25.00")
    assert assignment.currency == "USD"
    assert assignment.status == AddonStatus.ACTIVE


@pytest.mark.django_db
@override_settings(SITE_URL="https://testserver")
def test_purchase_event_scoped_addon(business_admin_client, organizer_setup):
    organizer, event = organizer_setup
    addon = AddonDefinition.objects.create(
        name="Event Exhibition Booster",
        slug="event-exhibition",
        capability="plugin.exhibition",
        entitlement_value="true",
        assignment_scope=AddonAssignmentScope.EVENT,
        price=Decimal("99.00"),
        currency="EUR",
        pricing_mode=AddonPricingMode.ONE_TIME,
        active=True,
        public=True,
    )

    purchase_url = reverse(
        "plugins:eventyay_business:organizer.addon.purchase",
        kwargs={"organizer": organizer.slug, "pk": addon.pk},
    )

    # Missing event fails
    resp_missing = business_admin_client.post(purchase_url, {"quantity": 1})
    assert resp_missing.status_code == 200
    assert (
        "This field is required" in resp_missing.content.decode()
        or "Please select an event" in resp_missing.content.decode()
    )

    # Valid event succeeds
    resp_post = business_admin_client.post(
        purchase_url, {"quantity": 1, "event": event.pk}, follow=True
    )
    assert resp_post.status_code == 200

    assignment = EventAddon.objects.get(event=event, addon=addon)
    assert assignment.quantity == 1
    assert assignment.capability == "plugin.exhibition"
    assert assignment.entitlement_value == "true"
    assert assignment.price == Decimal("99.00")
    assert assignment.currency == "EUR"
    assert assignment.status == AddonStatus.ACTIVE


@pytest.mark.django_db
@override_settings(SITE_URL="https://testserver")
def test_purchase_boolean_duplicate_rejected(business_admin_client, organizer_setup):
    organizer, _ = organizer_setup
    addon = AddonDefinition.objects.create(
        name="Loungemesh Space",
        slug="loungemesh-space",
        capability="video.loungemesh",
        entitlement_value="true",
        assignment_scope=AddonAssignmentScope.ORGANIZER,
        active=True,
        public=True,
    )

    # Pre-existing active assignment
    OrganizerAddon.objects.create(
        organizer=organizer, addon=addon, status=AddonStatus.ACTIVE
    )

    purchase_url = reverse(
        "plugins:eventyay_business:organizer.addon.purchase",
        kwargs={"organizer": organizer.slug, "pk": addon.pk},
    )
    resp = business_admin_client.post(purchase_url, {"quantity": 1})
    assert resp.status_code == 200
    assert "already active" in resp.content.decode()


@pytest.mark.django_db
@override_settings(SITE_URL="https://testserver")
def test_purchase_private_or_inactive_addon_returns_404(
    business_admin_client, organizer_setup
):
    organizer, _ = organizer_setup
    private_addon = AddonDefinition.objects.create(
        name="Private Addon",
        slug="private-addon",
        capability="video.loungemesh",
        entitlement_value="true",
        active=True,
        public=False,
    )

    purchase_url = reverse(
        "plugins:eventyay_business:organizer.addon.purchase",
        kwargs={"organizer": organizer.slug, "pk": private_addon.pk},
    )
    resp = business_admin_client.get(purchase_url)
    assert resp.status_code == 404


@pytest.mark.django_db
@override_settings(SITE_URL="https://testserver")
def test_purchase_requires_organizer_permission(client, organizer_setup):
    organizer, _ = organizer_setup
    addon = AddonDefinition.objects.create(
        name="Public Addon",
        slug="public-addon",
        capability="video.loungemesh",
        entitlement_value="true",
        active=True,
        public=True,
    )

    purchase_url = reverse(
        "plugins:eventyay_business:organizer.addon.purchase",
        kwargs={"organizer": organizer.slug, "pk": addon.pk},
    )
    resp = client.get(purchase_url)
    assert resp.status_code in (302, 403)
