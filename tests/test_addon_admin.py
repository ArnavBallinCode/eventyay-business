import pytest
from decimal import Decimal
from django.urls import reverse
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


@pytest.mark.django_db
def test_addon_list_view(business_admin_client):
    AddonDefinition.objects.create(
        name="Jitsi Multi-room",
        slug="jitsi-multi-room",
        capability="video.jitsi.concurrent_rooms",
        entitlement_value="4",
        price=Decimal("20.00"),
    )
    url = reverse("plugins:eventyay_business:addons.list")
    response = business_admin_client.get(url)
    assert response.status_code == 200
    assert "Jitsi Multi-room" in response.content.decode()


@pytest.mark.django_db
def test_addon_create_view(business_admin_client):
    url = reverse("plugins:eventyay_business:addons.create")
    response = business_admin_client.post(
        url,
        {
            "name": "Spatial Loungemesh",
            "slug": "spatial-loungemesh",
            "description": "Interactive spatial rooms",
            "assignment_scope": AddonAssignmentScope.ORGANIZER,
            "pricing_mode": AddonPricingMode.RECURRING,
            "currency": "USD",
            "price": "49.00",
            "capability": "video.loungemesh",
            "entitlement_value": "true",
            "quantity": "1",
            "active": "on",
            "public": "on",
        },
    )
    assert response.status_code == 302
    addon = AddonDefinition.objects.get(slug="spatial-loungemesh")
    assert addon.name == "Spatial Loungemesh"
    assert addon.price == Decimal("49.00")
    assert addon.active is True


@pytest.mark.django_db
def test_addon_update_view(business_admin_client):
    addon = AddonDefinition.objects.create(
        name="Old Name",
        slug="old-addon",
        capability="video.youtube",
        entitlement_value="true",
        price=Decimal("10.00"),
    )
    url = reverse("plugins:eventyay_business:addons.edit", kwargs={"pk": addon.pk})
    response = business_admin_client.post(
        url,
        {
            "name": "Updated Name",
            "slug": "old-addon",
            "assignment_scope": AddonAssignmentScope.ORGANIZER,
            "pricing_mode": AddonPricingMode.RECURRING,
            "currency": "USD",
            "price": "15.00",
            "capability": "video.youtube",
            "entitlement_value": "true",
            "quantity": "1",
            "active": "on",
        },
    )
    assert response.status_code == 302
    addon.refresh_from_db()
    assert addon.name == "Updated Name"
    assert addon.price == Decimal("15.00")


@pytest.mark.django_db
def test_addon_toggle_active_view(business_admin_client):
    addon = AddonDefinition.objects.create(
        name="Toggle Addon",
        slug="toggle-addon",
        capability="video.jitsi",
        entitlement_value="true",
        active=True,
    )
    url = reverse("plugins:eventyay_business:addons.toggle", kwargs={"pk": addon.pk})
    response = business_admin_client.post(url)
    assert response.status_code == 302
    addon.refresh_from_db()
    assert addon.active is False

    response = business_admin_client.post(url)
    assert response.status_code == 302
    addon.refresh_from_db()
    assert addon.active is True


@pytest.mark.django_db
def test_addon_admin_unauthorized(client):
    url = reverse("plugins:eventyay_business:addons.list")
    response = client.get(url)
    # Redirects to login
    assert response.status_code in (302, 403)


@pytest.mark.django_db
def test_addon_create_unknown_capability_rejected(business_admin_client):
    url = reverse("plugins:eventyay_business:addons.create")
    response = business_admin_client.post(
        url,
        {
            "name": "Unknown Capability Addon",
            "slug": "unknown-cap-addon",
            "assignment_scope": AddonAssignmentScope.ORGANIZER,
            "pricing_mode": AddonPricingMode.RECURRING,
            "currency": "USD",
            "price": "10.00",
            "capability": "unknown.capability.name",
            "entitlement_value": "true",
            "quantity": "1",
            "active": "on",
        },
    )
    assert response.status_code == 200
    assert "Unknown capability: unknown.capability.name" in response.content.decode()
    assert not AddonDefinition.objects.filter(slug="unknown-cap-addon").exists()


@pytest.mark.django_db
def test_addon_legacy_unchanged_capability_allowed(business_admin_client):
    addon = AddonDefinition.objects.create(
        name="Legacy Addon",
        slug="legacy-addon",
        capability="legacy.unregistered.cap",
        entitlement_value="true",
        price=Decimal("10.00"),
    )
    url = reverse("plugins:eventyay_business:addons.edit", kwargs={"pk": addon.pk})
    # Submitting with unchanged capability is allowed
    response = business_admin_client.post(
        url,
        {
            "name": "Legacy Addon Renamed",
            "slug": "legacy-addon",
            "assignment_scope": AddonAssignmentScope.ORGANIZER,
            "pricing_mode": AddonPricingMode.RECURRING,
            "currency": "USD",
            "price": "20.00",
            "capability": "legacy.unregistered.cap",
            "entitlement_value": "true",
            "quantity": "1",
            "active": "on",
        },
    )
    assert response.status_code == 302
    addon.refresh_from_db()
    assert addon.name == "Legacy Addon Renamed"
    assert addon.price == Decimal("20.00")


@pytest.mark.django_db
def test_organizer_addon_assignment_views(business_admin_client):
    from eventyay.base.models import Organizer

    org = Organizer.objects.create(name="Assign Org", slug="assign-org")
    addon = AddonDefinition.objects.create(
        name="Org Pack",
        slug="org-pack",
        capability="organizer.full_admins",
        entitlement_value="2",
        assignment_scope=AddonAssignmentScope.ORGANIZER,
    )

    # List view
    list_url = reverse("plugins:eventyay_business:addons.assignments.organizer.list")
    resp = business_admin_client.get(list_url)
    assert resp.status_code == 200

    # Create assignment
    create_url = reverse(
        "plugins:eventyay_business:addons.assignments.organizer.create"
    )
    resp = business_admin_client.post(
        create_url,
        {
            "organizer": org.pk,
            "addon": addon.pk,
            "quantity": 3,
            "status": "active",
            "starts_at_0": "2026-09-01",
            "starts_at_1": "10:00:00",
            "ends_at_0": "",
            "ends_at_1": "",
        },
    )
    assert resp.status_code == 302
    assignment = OrganizerAddon.objects.get(organizer=org, addon=addon)
    assert assignment.quantity == 3
    assert assignment.status == AddonStatus.ACTIVE

    # Edit assignment
    edit_url = reverse(
        "plugins:eventyay_business:addons.assignments.organizer.edit",
        kwargs={"pk": assignment.pk},
    )
    resp = business_admin_client.post(
        edit_url,
        {
            "organizer": org.pk,
            "addon": addon.pk,
            "quantity": 5,
            "status": "canceled",
            "starts_at_0": "2026-09-01",
            "starts_at_1": "10:00:00",
            "ends_at_0": "2026-09-30",
            "ends_at_1": "23:59:59",
        },
    )
    assert resp.status_code == 302
    assignment.refresh_from_db()
    assert assignment.quantity == 5
    assert assignment.status == AddonStatus.CANCELED


@pytest.mark.django_db
def test_event_addon_assignment_views(business_admin_client):
    from django.utils.timezone import now
    from eventyay.base.models import Event, Organizer

    org = Organizer.objects.create(name="Event Org", slug="event-org")
    event = Event.objects.create(
        organizer=org, name="Assign Event", slug="assign-event", date_from=now()
    )
    addon = AddonDefinition.objects.create(
        name="Event Pack",
        slug="event-pack",
        capability="video.jitsi.concurrent_rooms",
        entitlement_value="5",
        assignment_scope=AddonAssignmentScope.EVENT,
    )

    # List view
    list_url = reverse("plugins:eventyay_business:addons.assignments.event.list")
    resp = business_admin_client.get(list_url)
    assert resp.status_code == 200

    # Create assignment
    create_url = reverse("plugins:eventyay_business:addons.assignments.event.create")
    resp = business_admin_client.post(
        create_url,
        {
            "event": event.pk,
            "addon": addon.pk,
            "quantity": 2,
            "status": "active",
            "starts_at_0": "2026-09-01",
            "starts_at_1": "12:00:00",
            "ends_at_0": "",
            "ends_at_1": "",
        },
    )
    assert resp.status_code == 302
    assignment = EventAddon.objects.get(event=event, addon=addon)
    assert assignment.quantity == 2

    # Edit assignment
    edit_url = reverse(
        "plugins:eventyay_business:addons.assignments.event.edit",
        kwargs={"pk": assignment.pk},
    )
    resp = business_admin_client.post(
        edit_url,
        {
            "event": event.pk,
            "addon": addon.pk,
            "quantity": 4,
            "status": "active",
            "starts_at_0": "2026-09-01",
            "starts_at_1": "12:00:00",
            "ends_at_0": "",
            "ends_at_1": "",
        },
    )
    assert resp.status_code == 302
    assignment.refresh_from_db()
    assert assignment.quantity == 4


@pytest.mark.django_db
def test_addon_update_without_migration(business_admin_client):
    from eventyay.base.models import Organizer

    org = Organizer.objects.create(name="GF Admin Org", slug="gf-admin-org")
    addon = AddonDefinition.objects.create(
        name="Cap Booster",
        slug="cap-booster",
        capability="video.jitsi.concurrent_rooms",
        entitlement_value="2",
        price=Decimal("10.00"),
        currency="USD",
    )
    oa = OrganizerAddon.objects.create(organizer=org, addon=addon, quantity=1)
    assert oa.entitlement_value == "2"

    url = reverse("plugins:eventyay_business:addons.edit", kwargs={"pk": addon.pk})
    response = business_admin_client.post(
        url,
        {
            "name": "Cap Booster Updated",
            "slug": "cap-booster",
            "assignment_scope": AddonAssignmentScope.ORGANIZER,
            "pricing_mode": AddonPricingMode.RECURRING,
            "currency": "USD",
            "price": "20.00",
            "capability": "video.jitsi.concurrent_rooms",
            "entitlement_value": "4",
            "quantity": "1",
            "active": "on",
            # update_existing_assignments is omitted (unchecked)
        },
    )
    assert response.status_code == 302
    addon.refresh_from_db()
    assert addon.name == "Cap Booster Updated"
    assert addon.price == Decimal("20.00")
    assert addon.entitlement_value == "4"

    # Existing assignment must be grandfathered with old snapshot
    oa.refresh_from_db()
    assert oa.entitlement_value == "2"
    assert oa.price == Decimal("10.00")


@pytest.mark.django_db
def test_addon_update_with_migration_checkbox(business_admin_client):
    from eventyay.base.models import Organizer

    org = Organizer.objects.create(name="Migrate Admin Org", slug="mig-admin-org")
    addon = AddonDefinition.objects.create(
        name="Cap Booster 2",
        slug="cap-booster-2",
        capability="video.jitsi.concurrent_rooms",
        entitlement_value="2",
        price=Decimal("10.00"),
        currency="USD",
    )
    oa = OrganizerAddon.objects.create(organizer=org, addon=addon, quantity=1)
    assert oa.entitlement_value == "2"

    url = reverse("plugins:eventyay_business:addons.edit", kwargs={"pk": addon.pk})
    response = business_admin_client.post(
        url,
        {
            "name": "Cap Booster 2 Updated",
            "slug": "cap-booster-2",
            "assignment_scope": AddonAssignmentScope.ORGANIZER,
            "pricing_mode": AddonPricingMode.RECURRING,
            "currency": "USD",
            "price": "30.00",
            "capability": "video.jitsi.concurrent_rooms",
            "entitlement_value": "8",
            "quantity": "1",
            "active": "on",
            "update_existing_assignments": "on",
        },
        follow=True,
    )
    assert response.status_code == 200
    addon.refresh_from_db()
    assert addon.price == Decimal("30.00")
    assert addon.entitlement_value == "8"

    # Existing assignment must be updated
    oa.refresh_from_db()
    assert oa.entitlement_value == "8"
    assert oa.price == Decimal("30.00")

    content = response.content.decode()
    assert "1 existing active assignment(s) updated" in content
