from unittest.mock import Mock

from django.test import RequestFactory
from django.urls import ResolverMatch

from eventyay_business.signals import business_tiers_nav


def test_business_tiers_nav_anonymous():
    factory = RequestFactory()
    request = factory.get("/common")
    request.user = Mock(is_authenticated=False, is_staff=False, is_superuser=False)
    request.resolver_match = ResolverMatch(
        func=lambda r: None,
        args=(),
        kwargs={},
        url_name="dashboard",
        app_names=["eventyay_common"],
        namespaces=["eventyay_common"],
    )

    items = business_tiers_nav(sender=None, request=request)
    assert items == []


def test_business_tiers_nav_non_staff_authenticated():
    factory = RequestFactory()
    request = factory.get("/common")
    request.user = Mock(is_authenticated=True, is_staff=False, is_superuser=False)
    request.resolver_match = ResolverMatch(
        func=lambda r: None,
        args=(),
        kwargs={},
        url_name="dashboard",
        app_names=["eventyay_common"],
        namespaces=["eventyay_common"],
    )

    items = business_tiers_nav(sender=None, request=request)
    assert items == []


def test_business_tiers_nav_staff_on_common_dashboard():
    """Verify that staff visiting public-facing common dashboard do not see Tiers/Subscriptions."""
    factory = RequestFactory()
    request = factory.get("/common")
    request.user = Mock(is_authenticated=True, is_staff=True, is_superuser=False)
    request.resolver_match = ResolverMatch(
        func=lambda r: None,
        args=(),
        kwargs={},
        url_name="dashboard",
        app_names=["eventyay_common"],
        namespaces=["eventyay_common"],
    )

    items = business_tiers_nav(sender=None, request=request)
    assert items == []


def test_business_tiers_nav_staff_on_organizer_plan():
    """Verify that organizer plan route does not show global business tiers nav."""
    factory = RequestFactory()
    request = factory.get("/control/organizer/test-org/business/plan/")
    request.user = Mock(is_authenticated=True, is_staff=True, is_superuser=False)
    request.resolver_match = ResolverMatch(
        func=lambda r: None,
        args=(),
        kwargs={"organizer": "test-org"},
        url_name="organizer.plan",
        app_names=["plugins:eventyay_business"],
        namespaces=["plugins:eventyay_business"],
    )

    items = business_tiers_nav(sender=None, request=request)
    assert items == []


def test_business_tiers_nav_staff_on_admin_page():
    """Verify that staff on admin routes get Tiers and Subscriptions in navigation."""
    factory = RequestFactory()
    request = factory.get("/admin/global/business/")
    request.user = Mock(is_authenticated=True, is_staff=True, is_superuser=False)
    request.resolver_match = ResolverMatch(
        func=lambda r: None,
        args=(),
        kwargs={},
        url_name="admin.global.business",
        app_names=["eventyay_admin"],
        namespaces=["eventyay_admin"],
    )

    items = business_tiers_nav(sender=None, request=request)
    assert len(items) == 2
    assert str(items[0]["label"]) == "Tiers"
    assert str(items[1]["label"]) == "Subscriptions"
    assert items[0]["active"] is False
    assert items[1]["active"] is False


def test_business_tiers_nav_staff_on_tiers_list():
    """Verify that staff on tiers list view have Tiers marked active."""
    factory = RequestFactory()
    request = factory.get("/admin/global/business/tiers/")
    request.user = Mock(is_authenticated=True, is_staff=True, is_superuser=False)
    request.resolver_match = ResolverMatch(
        func=lambda r: None,
        args=(),
        kwargs={},
        url_name="tiers.list",
        app_names=["plugins:eventyay_business"],
        namespaces=["plugins:eventyay_business"],
    )

    items = business_tiers_nav(sender=None, request=request)
    assert len(items) == 2
    assert items[0]["active"] is True
    assert items[1]["active"] is False
