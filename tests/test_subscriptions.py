import pytest
from django.test import override_settings
from eventyay.base.models import Organizer

from eventyay_business.models import Subscription


@pytest.fixture
def business_admin_client(admin_client, admin_user):
    from eventyay.base.models.auth import StaffSession

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
def test_organizer_auto_assign_free_tier():
    # Creating an organizer should trigger the post_save signal
    org = Organizer.objects.create(name="Test Organizer", slug="test-org")

    # Check if a subscription was created
    sub = Subscription.objects.filter(organizer=org).first()
    assert sub is not None
    assert sub.status == "active"
    assert sub.tier_version.tier.slug == "free"


@pytest.mark.django_db
def test_subscription_admin_form_valid_with_split_datetime():
    from eventyay_business.forms import SubscriptionAdminForm

    org = Organizer.objects.create(name="Form Test Org", slug="form-test-org")
    sub = Subscription.objects.get(organizer=org)

    data = {
        "organizer": org.pk,
        "tier_version": sub.tier_version.pk,
        "status": "active",
        "billing_interval": "monthly",
        "currency": "USD",
        "starts_at_0": "2026-09-11",
        "starts_at_1": "10:00:00",
        "ends_at_0": "2026-10-11",
        "ends_at_1": "10:00:00",
        "cancel_at_0": "",
        "cancel_at_1": "",
        "stripe_customer_id": "cus_123",
        "stripe_subscription_id": "sub_123",
    }
    form = SubscriptionAdminForm(data=data, instance=sub)
    assert form.is_valid(), form.errors
    saved_sub = form.save()
    assert saved_sub.starts_at.year == 2026
    assert saved_sub.ends_at.month == 10
    assert saved_sub.cancel_at is None


@pytest.mark.django_db
def test_subscription_edit_view_post(business_admin_client):
    from django.urls import reverse

    org = Organizer.objects.create(name="Edit View Org", slug="edit-view-org")
    sub = Subscription.objects.get(organizer=org)

    url = reverse("plugins:eventyay_business:subscriptions.edit", kwargs={"pk": sub.pk})
    get_response = business_admin_client.get(url)
    assert get_response.status_code == 200

    post_data = {
        "organizer": org.pk,
        "tier_version": sub.tier_version.pk,
        "status": "active",
        "billing_interval": "monthly",
        "currency": "EUR",
        "starts_at_0": "2026-09-01",
        "starts_at_1": "08:00:00",
        "ends_at_0": "",
        "ends_at_1": "",
        "cancel_at_0": "",
        "cancel_at_1": "",
        "stripe_customer_id": "",
        "stripe_subscription_id": "",
    }
    post_response = business_admin_client.post(url, post_data, follow=True)
    assert post_response.status_code == 200
    sub.refresh_from_db()
    assert sub.currency == "EUR"


@pytest.mark.django_db
@override_settings(SITE_URL="https://testserver")
def test_organizer_plan_view_shows_active_addons(business_admin_client):
    from django.urls import reverse
    from django.utils.timezone import now
    from eventyay.base.models import Event

    from eventyay_business.models import (
        AddonAssignmentScope,
        AddonDefinition,
        AddonStatus,
        EventAddon,
        OrganizerAddon,
    )

    org = Organizer.objects.create(name="Plan View Org", slug="plan-view-org")
    event = Event.objects.create(
        organizer=org, name="Plan View Event", slug="plan-view-event", date_from=now()
    )

    # 1. Active Organizer Add-on
    org_addon_def = AddonDefinition.objects.create(
        name="Extra Admin Pack",
        slug="extra-admin-pack",
        capability="organizer.full_admins",
        entitlement_value="3",
        assignment_scope=AddonAssignmentScope.ORGANIZER,
    )
    OrganizerAddon.objects.create(
        organizer=org,
        addon=org_addon_def,
        quantity=1,
        status=AddonStatus.ACTIVE,
    )

    # 2. Active Event Add-on
    event_addon_def = AddonDefinition.objects.create(
        name="Live Interpretation Pack",
        slug="live-interpretation-pack",
        capability="video.interpretation",
        entitlement_value="true",
        assignment_scope=AddonAssignmentScope.EVENT,
    )
    EventAddon.objects.create(
        event=event,
        addon=event_addon_def,
        quantity=2,
        status=AddonStatus.ACTIVE,
    )

    # 3. Inactive/Expired Add-on (should not show)
    inactive_addon_def = AddonDefinition.objects.create(
        name="Expired Addon Pack",
        slug="expired-addon-pack",
        capability="video.loungemesh",
        entitlement_value="true",
        assignment_scope=AddonAssignmentScope.ORGANIZER,
    )
    OrganizerAddon.objects.create(
        organizer=org,
        addon=inactive_addon_def,
        quantity=1,
        status=AddonStatus.EXPIRED,
    )

    url = reverse(
        "plugins:eventyay_business:organizer.plan", kwargs={"organizer": org.slug}
    )
    response = business_admin_client.get(url)
    assert response.status_code == 200
    content = response.content.decode()

    # Active Add-ons section and items should be present
    assert "Active Add-ons" in content
    assert "Extra Admin Pack" in content
    assert "Live Interpretation Pack" in content
    assert "Plan View Event" in content

    # Inactive add-on should not be displayed
    assert "Expired Addon Pack" not in content
