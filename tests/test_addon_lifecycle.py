import pytest
from datetime import timedelta
from decimal import Decimal
from django.test import override_settings
from django.urls import reverse
from django.utils.timezone import now
from eventyay.base.entitlements import check_entitlement
from eventyay.base.models import Event, Organizer, Team, User
from eventyay.base.models.auth import StaffSession

from eventyay_business.models import (
    AddonAssignmentScope,
    AddonDefinition,
    AddonStatus,
    EventAddon,
    OrganizerAddon,
)
from eventyay_business.tasks import (
    expire_addon_assignments,
    expire_addon_assignments_task,
    periodic_expire_addon_assignments,
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
def setup_data():
    organizer = Organizer.objects.create(name="Lifecycle Org", slug="lifecycle-org")
    event = Event.objects.create(
        organizer=organizer,
        name="Lifecycle Event",
        slug="lifecycle-event",
        date_from=now(),
        live=True,
    )
    org_addon_def = AddonDefinition.objects.create(
        name="API Write Access",
        slug="api-write-access",
        capability="api.write",
        entitlement_value="true",
        price=Decimal("49.00"),
        currency="USD",
        active=True,
        public=True,
        assignment_scope=AddonAssignmentScope.ORGANIZER,
    )
    event_addon_def = AddonDefinition.objects.create(
        name="Spatial Lounge",
        slug="spatial-lounge",
        capability="video.loungemesh",
        entitlement_value="true",
        price=Decimal("19.00"),
        currency="USD",
        active=True,
        public=True,
        assignment_scope=AddonAssignmentScope.EVENT,
    )
    return organizer, event, org_addon_def, event_addon_def


@pytest.mark.django_db
def test_organizer_addon_cancel_immediate(setup_data):
    organizer, _, org_addon_def, _ = setup_data
    current = now()
    addon = OrganizerAddon.objects.create(
        organizer=organizer,
        addon=org_addon_def,
        starts_at=current,
        ends_at=current + timedelta(days=30),
        status=AddonStatus.ACTIVE,
    )
    assert addon.is_active is True

    addon.cancel(immediate=True)
    addon.refresh_from_db()

    assert addon.status == AddonStatus.CANCELED
    assert addon.cancel_at is not None
    assert addon.canceled_at is not None
    assert addon.is_active is False


@pytest.mark.django_db
def test_organizer_addon_cancel_period_end(setup_data):
    organizer, _, org_addon_def, _ = setup_data
    current = now()
    period_end = current + timedelta(days=30)
    addon = OrganizerAddon.objects.create(
        organizer=organizer,
        addon=org_addon_def,
        starts_at=current,
        ends_at=period_end,
        status=AddonStatus.ACTIVE,
    )

    addon.cancel(immediate=False)
    addon.refresh_from_db()

    assert addon.status == AddonStatus.ACTIVE
    assert addon.cancel_at == period_end
    assert addon.canceled_at is not None
    # Still active because cancel_at is in the future
    assert addon.is_active is True


@pytest.mark.django_db
def test_organizer_addon_cancel_continuous_without_ends_at(setup_data):
    organizer, _, org_addon_def, _ = setup_data
    addon = OrganizerAddon.objects.create(
        organizer=organizer,
        addon=org_addon_def,
        status=AddonStatus.ACTIVE,
    )

    addon.cancel(immediate=False)
    addon.refresh_from_db()

    # When no ends_at, immediate cancellation occurs
    assert addon.status == AddonStatus.CANCELED
    assert addon.cancel_at is not None
    assert addon.is_active is False


@pytest.mark.django_db
def test_event_addon_cancel_immediate_and_period_end(setup_data):
    _, event, _, event_addon_def = setup_data
    current = now()
    period_end = current + timedelta(days=14)

    addon = EventAddon.objects.create(
        event=event,
        addon=event_addon_def,
        starts_at=current,
        ends_at=period_end,
        status=AddonStatus.ACTIVE,
    )

    # Cancel at period end
    addon.cancel(immediate=False)
    addon.refresh_from_db()
    assert addon.status == AddonStatus.ACTIVE
    assert addon.cancel_at == period_end
    assert addon.is_active is True

    # Immediate cancel
    addon.cancel(immediate=True)
    addon.refresh_from_db()
    assert addon.status == AddonStatus.CANCELED
    assert addon.is_active is False


@pytest.mark.django_db
def test_is_active_with_past_cancel_at(setup_data):
    organizer, _, org_addon_def, _ = setup_data
    current = now()
    addon = OrganizerAddon.objects.create(
        organizer=organizer,
        addon=org_addon_def,
        starts_at=current - timedelta(days=10),
        cancel_at=current - timedelta(seconds=1),
        status=AddonStatus.ACTIVE,
    )
    assert addon.is_active is False


@pytest.mark.django_db
def test_entitlements_respects_canceled_and_scheduled_addons(setup_data):
    organizer, event, org_addon_def, event_addon_def = setup_data
    current = now()

    # Active addon grants entitlement
    addon = OrganizerAddon.objects.create(
        organizer=organizer,
        addon=org_addon_def,
        starts_at=current,
        status=AddonStatus.ACTIVE,
    )
    assert check_entitlement(organizer, "api.write").allowed is True

    # Scheduled to cancel in future still grants entitlement
    addon.cancel_at = current + timedelta(days=5)
    addon.save()
    assert check_entitlement(organizer, "api.write").allowed is True

    # Past cancel_at does not grant entitlement
    addon.cancel_at = current - timedelta(minutes=5)
    addon.save()
    assert check_entitlement(organizer, "api.write").allowed is False

    # Event addon past cancel_at does not grant entitlement
    event_addon = EventAddon.objects.create(
        event=event,
        addon=event_addon_def,
        starts_at=current,
        cancel_at=current - timedelta(minutes=1),
        status=AddonStatus.ACTIVE,
    )
    assert (
        check_entitlement(organizer, "video.loungemesh", event=event).allowed is False
    )

    # But future cancel_at on event addon allows
    event_addon.cancel_at = current + timedelta(days=2)
    event_addon.save()
    assert check_entitlement(organizer, "video.loungemesh", event=event).allowed is True


@pytest.mark.django_db
@override_settings(SITE_URL="https://testserver")
def test_organizer_addon_cancel_view_get_and_post(business_admin_client, setup_data):
    organizer, _, org_addon_def, _ = setup_data
    current = now()
    period_end = current + timedelta(days=30)
    addon = OrganizerAddon.objects.create(
        organizer=organizer,
        addon=org_addon_def,
        starts_at=current,
        ends_at=period_end,
        status=AddonStatus.ACTIVE,
    )

    url = reverse(
        "plugins:eventyay_business:organizer.addon.cancel",
        kwargs={"organizer": organizer.slug, "pk": addon.pk},
    )

    # GET returns confirmation page
    resp = business_admin_client.get(url)
    assert resp.status_code == 200
    assert "Confirm Cancellation" in resp.content.decode()

    # POST with immediate=0 schedules cancellation at period end
    resp = business_admin_client.post(url, {"immediate": "0"})
    assert resp.status_code == 302
    addon.refresh_from_db()
    assert addon.status == AddonStatus.ACTIVE
    assert addon.cancel_at == period_end

    # POST with immediate=1 cancels immediately
    resp = business_admin_client.post(url, {"immediate": "1"})
    assert resp.status_code == 302
    addon.refresh_from_db()
    assert addon.status == AddonStatus.CANCELED


@pytest.mark.django_db
@override_settings(SITE_URL="https://testserver")
def test_event_addon_cancel_view_get_and_post(business_admin_client, setup_data):
    organizer, event, _, event_addon_def = setup_data
    current = now()
    period_end = current + timedelta(days=15)
    addon = EventAddon.objects.create(
        event=event,
        addon=event_addon_def,
        starts_at=current,
        ends_at=period_end,
        status=AddonStatus.ACTIVE,
    )

    url = reverse(
        "plugins:eventyay_business:event.addon.cancel",
        kwargs={"organizer": organizer.slug, "event": event.slug, "pk": addon.pk},
    )

    # GET returns confirmation page
    resp = business_admin_client.get(url)
    assert resp.status_code == 200
    assert "Confirm Cancellation" in resp.content.decode()

    # POST with immediate=1 cancels immediately
    resp = business_admin_client.post(url, {"immediate": "1"})
    assert resp.status_code == 302
    addon.refresh_from_db()
    assert addon.status == AddonStatus.CANCELED


@pytest.mark.django_db
@override_settings(SITE_URL="https://testserver")
def test_organizer_cancel_permission_denied_for_unprivileged(client, setup_data):
    organizer, _, org_addon_def, _ = setup_data
    user = User.objects.create_user(
        email="unprivileged@example.com", password="password"
    )
    team = Team.objects.create(
        organizer=organizer,
        name="View Only",
        can_change_organizer_settings=False,
    )
    team.members.add(user)
    client.force_login(user)

    addon = OrganizerAddon.objects.create(
        organizer=organizer,
        addon=org_addon_def,
        status=AddonStatus.ACTIVE,
    )

    url = reverse(
        "plugins:eventyay_business:organizer.addon.cancel",
        kwargs={"organizer": organizer.slug, "pk": addon.pk},
    )
    resp = client.get(url)
    assert resp.status_code == 403


@pytest.mark.django_db
@override_settings(SITE_URL="https://testserver")
def test_admin_revoke_actions(business_admin_client, setup_data):
    organizer, event, org_addon_def, event_addon_def = setup_data
    org_addon = OrganizerAddon.objects.create(
        organizer=organizer,
        addon=org_addon_def,
        status=AddonStatus.ACTIVE,
    )
    event_addon = EventAddon.objects.create(
        event=event,
        addon=event_addon_def,
        status=AddonStatus.ACTIVE,
    )

    # Revoke organizer addon
    org_revoke_url = reverse(
        "plugins:eventyay_business:addons.assignments.organizer.revoke",
        kwargs={"pk": org_addon.pk},
    )
    resp = business_admin_client.post(org_revoke_url)
    assert resp.status_code == 302
    org_addon.refresh_from_db()
    assert org_addon.status == AddonStatus.CANCELED

    # Revoke event addon
    event_revoke_url = reverse(
        "plugins:eventyay_business:addons.assignments.event.revoke",
        kwargs={"pk": event_addon.pk},
    )
    resp = business_admin_client.post(event_revoke_url)
    assert resp.status_code == 302
    event_addon.refresh_from_db()
    assert event_addon.status == AddonStatus.CANCELED


@pytest.mark.django_db
def test_expire_addon_assignments_task(setup_data):
    organizer, event, org_addon_def, event_addon_def = setup_data
    current = now()

    # 1. Past cancel_at -> CANCELED
    oa_canceled = OrganizerAddon.objects.create(
        organizer=organizer,
        addon=org_addon_def,
        starts_at=current - timedelta(days=10),
        cancel_at=current - timedelta(minutes=5),
        status=AddonStatus.ACTIVE,
    )

    # 2. Past ends_at -> EXPIRED
    oa_expired = OrganizerAddon.objects.create(
        organizer=organizer,
        addon=org_addon_def,
        starts_at=current - timedelta(days=35),
        ends_at=current - timedelta(days=5),
        status=AddonStatus.ACTIVE,
    )

    # 3. Active future -> UNCHANGED
    oa_active = OrganizerAddon.objects.create(
        organizer=organizer,
        addon=org_addon_def,
        starts_at=current,
        ends_at=current + timedelta(days=20),
        status=AddonStatus.ACTIVE,
    )

    # 4. Event addon past cancel_at -> CANCELED
    ea_canceled = EventAddon.objects.create(
        event=event,
        addon=event_addon_def,
        starts_at=current - timedelta(days=10),
        cancel_at=current - timedelta(minutes=10),
        status=AddonStatus.ACTIVE,
    )

    # 5. Event addon past ends_at -> EXPIRED
    ea_expired = EventAddon.objects.create(
        event=event,
        addon=event_addon_def,
        starts_at=current - timedelta(days=20),
        ends_at=current - timedelta(days=2),
        status=AddonStatus.ACTIVE,
    )

    result = expire_addon_assignments()
    assert result["canceled"] == 2
    assert result["expired"] == 2

    oa_canceled.refresh_from_db()
    oa_expired.refresh_from_db()
    oa_active.refresh_from_db()
    ea_canceled.refresh_from_db()
    ea_expired.refresh_from_db()

    assert oa_canceled.status == AddonStatus.CANCELED
    assert oa_expired.status == AddonStatus.EXPIRED
    assert oa_active.status == AddonStatus.ACTIVE
    assert ea_canceled.status == AddonStatus.CANCELED
    assert ea_expired.status == AddonStatus.EXPIRED

    # Also test periodic function wrapper and Celery task execution
    assert expire_addon_assignments_task() == {"canceled": 0, "expired": 0}
    if periodic_expire_addon_assignments:
        assert periodic_expire_addon_assignments(sender=None) == {
            "canceled": 0,
            "expired": 0,
        }
