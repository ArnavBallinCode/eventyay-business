import pytest
from decimal import Decimal
from django.urls import reverse
from eventyay.base.models.auth import StaffSession

from eventyay_business.models import (
    AddonAssignmentScope,
    AddonDefinition,
    AddonPricingMode,
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
