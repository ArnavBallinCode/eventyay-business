import pytest
from decimal import Decimal
from django.test import override_settings
from django.urls import reverse
from django.utils.timezone import now
from eventyay.base.models import Event, Organizer, Team, User
from eventyay.base.models.auth import StaffSession

from eventyay_business.models import (
    AddonAssignmentScope,
    AddonDefinition,
    AddonPricingMode,
    AddonStatus,
    EventAddon,
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
def event_setup():
    organizer = Organizer.objects.create(name="Acme Corp", slug="acme-corp")
    event1 = Event.objects.create(
        organizer=organizer,
        name="Summit 1",
        slug="summit-1",
        date_from=now(),
        live=True,
    )
    event2 = Event.objects.create(
        organizer=organizer,
        name="Summit 2",
        slug="summit-2",
        date_from=now(),
        live=True,
    )
    return organizer, event1, event2


@pytest.mark.django_db
@override_settings(SITE_URL="https://testserver")
def test_event_addons_list_view_shows_active_addons(business_admin_client, event_setup):
    organizer, event1, event2 = event_setup

    addon1 = AddonDefinition.objects.create(
        name="Summit 1 Video Badge",
        slug="summit-1-video",
        capability="video.stream",
        entitlement_value="true",
        assignment_scope=AddonAssignmentScope.EVENT,
        active=True,
        public=True,
    )
    addon2 = AddonDefinition.objects.create(
        name="Summit 2 Exhibition",
        slug="summit-2-exhibition",
        capability="plugin.exhibition",
        entitlement_value="true",
        assignment_scope=AddonAssignmentScope.EVENT,
        active=True,
        public=False,
    )

    EventAddon.objects.create(
        event=event1,
        addon=addon1,
        capability=addon1.capability,
        entitlement_value="true",
        status=AddonStatus.ACTIVE,
    )
    EventAddon.objects.create(
        event=event2,
        addon=addon2,
        capability=addon2.capability,
        entitlement_value="true",
        status=AddonStatus.ACTIVE,
    )

    url = reverse(
        "plugins:eventyay_business:event.addons",
        kwargs={"organizer": organizer.slug, "event": event1.slug},
    )
    resp = business_admin_client.get(url)
    assert resp.status_code == 200
    content = resp.content.decode()

    # Active add-ons for event1 are visible
    assert "Summit 1 Video Badge" in content
    assert "video.stream" in content
    assert "Active" in content

    # Add-ons for event2 are not displayed in event1's dashboard
    assert "Summit 2 Exhibition" not in content


@pytest.mark.django_db
@override_settings(SITE_URL="https://testserver")
def test_event_addons_list_view_available_addons_filtering(
    business_admin_client, event_setup
):
    organizer, event1, _ = event_setup

    AddonDefinition.objects.create(
        name="Public Event Feature",
        slug="public-event-feature",
        capability="plugin.public",
        entitlement_value="true",
        assignment_scope=AddonAssignmentScope.EVENT,
        price=Decimal("49.00"),
        currency="USD",
        pricing_mode=AddonPricingMode.ONE_TIME,
        active=True,
        public=True,
    )
    AddonDefinition.objects.create(
        name="Private Event Feature",
        slug="private-event-feature",
        capability="plugin.private",
        entitlement_value="true",
        assignment_scope=AddonAssignmentScope.EVENT,
        active=True,
        public=False,
    )
    AddonDefinition.objects.create(
        name="Org Scoped Feature",
        slug="org-scoped-feature",
        capability="organizer.custom",
        entitlement_value="true",
        assignment_scope=AddonAssignmentScope.ORGANIZER,
        active=True,
        public=True,
    )

    url = reverse(
        "plugins:eventyay_business:event.addons",
        kwargs={"organizer": organizer.slug, "event": event1.slug},
    )
    resp = business_admin_client.get(url)
    assert resp.status_code == 200
    content = resp.content.decode()

    assert "Public Event Feature" in content
    assert "Private Event Feature" not in content
    assert "Org Scoped Feature" not in content
    assert "Enable for this Event" in content


@pytest.mark.django_db
@override_settings(SITE_URL="https://testserver")
def test_event_addons_list_marks_active_boolean_addon(
    business_admin_client, event_setup
):
    organizer, event1, _ = event_setup

    addon = AddonDefinition.objects.create(
        name="Live Translation Stream",
        slug="live-translation-stream",
        capability="video.interpretation",
        entitlement_value="true",
        assignment_scope=AddonAssignmentScope.EVENT,
        active=True,
        public=True,
    )

    EventAddon.objects.create(
        event=event1,
        addon=addon,
        capability=addon.capability,
        entitlement_value="true",
        status=AddonStatus.ACTIVE,
    )

    url = reverse(
        "plugins:eventyay_business:event.addons",
        kwargs={"organizer": organizer.slug, "event": event1.slug},
    )
    resp = business_admin_client.get(url)
    assert resp.status_code == 200
    content = resp.content.decode()

    assert "Live Translation Stream" in content
    assert "Active" in content


@pytest.mark.django_db
@override_settings(SITE_URL="https://testserver")
def test_event_addon_purchase_get_and_post(business_admin_client, event_setup):
    organizer, event1, _ = event_setup

    addon = AddonDefinition.objects.create(
        name="Exhibitor Booths Pack",
        slug="exhibitor-booths-pack",
        capability="plugin.exhibition.booths",
        entitlement_value="10",
        quantity=5,
        assignment_scope=AddonAssignmentScope.EVENT,
        price=Decimal("150.00"),
        currency="USD",
        pricing_mode=AddonPricingMode.ONE_TIME,
        active=True,
        public=True,
    )

    purchase_url = reverse(
        "plugins:eventyay_business:event.addon.purchase",
        kwargs={"organizer": organizer.slug, "event": event1.slug, "pk": addon.pk},
    )

    # GET displays details and target event
    resp_get = business_admin_client.get(purchase_url)
    assert resp_get.status_code == 200
    content = resp_get.content.decode()
    assert "Exhibitor Booths Pack" in content
    assert "Summit 1" in content

    # POST purchase
    resp_post = business_admin_client.post(purchase_url, {"quantity": 3}, follow=True)
    assert resp_post.status_code == 200

    assignment = EventAddon.objects.get(event=event1, addon=addon)
    assert assignment.quantity == 3
    assert assignment.capability == "plugin.exhibition.booths"
    assert assignment.entitlement_value == "10"
    assert assignment.price == Decimal("150.00")
    assert assignment.currency == "USD"
    assert assignment.status == AddonStatus.ACTIVE


@pytest.mark.django_db
@override_settings(SITE_URL="https://testserver")
def test_event_addon_purchase_duplicate_boolean_rejected(
    business_admin_client, event_setup
):
    organizer, event1, _ = event_setup

    addon = AddonDefinition.objects.create(
        name="Special Stream Module",
        slug="special-stream-module",
        capability="video.loungemesh",
        entitlement_value="true",
        assignment_scope=AddonAssignmentScope.EVENT,
        active=True,
        public=True,
    )

    # Pre-existing active assignment
    EventAddon.objects.create(
        event=event1,
        addon=addon,
        capability=addon.capability,
        entitlement_value="true",
        status=AddonStatus.ACTIVE,
    )

    purchase_url = reverse(
        "plugins:eventyay_business:event.addon.purchase",
        kwargs={"organizer": organizer.slug, "event": event1.slug, "pk": addon.pk},
    )
    resp = business_admin_client.post(purchase_url, {"quantity": 1})
    assert resp.status_code == 200
    assert "already active" in resp.content.decode()


@pytest.mark.django_db
@override_settings(SITE_URL="https://testserver")
def test_event_addon_purchase_private_or_inactive_returns_404(
    business_admin_client, event_setup
):
    organizer, event1, _ = event_setup

    private_addon = AddonDefinition.objects.create(
        name="Private Addon",
        slug="private-addon",
        capability="video.stream",
        entitlement_value="true",
        assignment_scope=AddonAssignmentScope.EVENT,
        active=True,
        public=False,
    )
    inactive_addon = AddonDefinition.objects.create(
        name="Inactive Addon",
        slug="inactive-addon",
        capability="video.stream",
        entitlement_value="true",
        assignment_scope=AddonAssignmentScope.EVENT,
        active=False,
        public=True,
    )
    org_addon = AddonDefinition.objects.create(
        name="Org Addon",
        slug="org-addon",
        capability="video.stream",
        entitlement_value="true",
        assignment_scope=AddonAssignmentScope.ORGANIZER,
        active=True,
        public=True,
    )

    for addon in [private_addon, inactive_addon, org_addon]:
        purchase_url = reverse(
            "plugins:eventyay_business:event.addon.purchase",
            kwargs={"organizer": organizer.slug, "event": event1.slug, "pk": addon.pk},
        )
        resp = business_admin_client.get(purchase_url)
        assert resp.status_code == 404


@pytest.mark.django_db
@override_settings(SITE_URL="https://testserver")
def test_event_addons_permission_required(client, event_setup):
    organizer, event1, _ = event_setup

    addon = AddonDefinition.objects.create(
        name="Event Module",
        slug="event-module",
        capability="video.stream",
        entitlement_value="true",
        assignment_scope=AddonAssignmentScope.EVENT,
        active=True,
        public=True,
    )

    list_url = reverse(
        "plugins:eventyay_business:event.addons",
        kwargs={"organizer": organizer.slug, "event": event1.slug},
    )
    purchase_url = reverse(
        "plugins:eventyay_business:event.addon.purchase",
        kwargs={"organizer": organizer.slug, "event": event1.slug, "pk": addon.pk},
    )

    # Anonymous redirected to login
    resp_anon = client.get(list_url)
    assert resp_anon.status_code == 302
    assert "/login/" in resp_anon.url

    # Authenticated user without event permission denied
    unprivileged_user = User.objects.create_user(
        "unprivileged_event@example.com", "dummy"
    )
    team = Team.objects.create(
        organizer=organizer,
        name="No Settings Team",
        all_events=True,
        can_view_orders=True,
        can_change_event_settings=False,
    )
    team.members.add(unprivileged_user)
    client.force_login(unprivileged_user)

    resp_denied = client.get(list_url)
    assert resp_denied.status_code == 403

    resp_purchase_denied = client.get(purchase_url)
    assert resp_purchase_denied.status_code == 403
