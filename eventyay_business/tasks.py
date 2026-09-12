import logging
from django.db import transaction
from django.dispatch import receiver
from django.utils.timezone import now

logger = logging.getLogger(__name__)

try:
    from django_scopes import scopes_disabled
except ModuleNotFoundError as err:
    if err.name != "django_scopes":
        raise
    from contextlib import nullcontext as scopes_disabled

try:
    from eventyay.celery_app import app
except ImportError:

    class _App:
        def task(self, *args, **kwargs):
            def decorator(fn):
                return fn

            return decorator

    app = _App()

try:
    from eventyay.base.signals import periodic_task
except ImportError:
    periodic_task = None


def expire_addon_assignments():
    """
    Scans active add-on assignments (both OrganizerAddon and EventAddon) and:
    1. Cancels assignments where cancel_at <= now().
    2. Expires assignments where ends_at <= now().
    Invalidates entitlement cache and logs audit actions.
    """
    from .models import AddonStatus, EventAddon, OrganizerAddon
    from .services import invalidate_entitlement_cache, log_addon_lifecycle_action
    from .signals import addon_canceled, addon_expired

    current_time = now()
    canceled_count = 0
    expired_count = 0

    with scopes_disabled():
        # 1. Process scheduled cancellations for OrganizerAddon
        org_canceled = list(
            OrganizerAddon.objects.filter(
                status=AddonStatus.ACTIVE,
                cancel_at__isnull=False,
                cancel_at__lte=current_time,
            ).select_related("organizer", "addon")
        )
        for item in org_canceled:
            with transaction.atomic():
                rows_updated = OrganizerAddon.objects.filter(
                    pk=item.pk,
                    status=AddonStatus.ACTIVE,
                ).update(
                    status=AddonStatus.CANCELED,
                    canceled_at=current_time,
                    updated_at=current_time,
                )
                if not rows_updated:
                    continue
                item.status = AddonStatus.CANCELED
                item.canceled_at = current_time
                canceled_count += 1
                log_addon_lifecycle_action(item, "canceled")
                invalidate_entitlement_cache(organizer=item.organizer)
                addon_canceled.send(
                    sender=OrganizerAddon, instance=item, immediate=False
                )

        # 2. Process expiration for OrganizerAddon
        org_expired = list(
            OrganizerAddon.objects.filter(
                status=AddonStatus.ACTIVE,
                ends_at__isnull=False,
                ends_at__lte=current_time,
            ).select_related("organizer", "addon")
        )
        for item in org_expired:
            with transaction.atomic():
                rows_updated = OrganizerAddon.objects.filter(
                    pk=item.pk,
                    status=AddonStatus.ACTIVE,
                ).update(
                    status=AddonStatus.EXPIRED,
                    updated_at=current_time,
                )
                if not rows_updated:
                    continue
                item.status = AddonStatus.EXPIRED
                expired_count += 1
                log_addon_lifecycle_action(item, "expired")
                invalidate_entitlement_cache(organizer=item.organizer)
                addon_expired.send(sender=OrganizerAddon, instance=item)

        # 3. Process scheduled cancellations for EventAddon
        event_canceled = list(
            EventAddon.objects.filter(
                status=AddonStatus.ACTIVE,
                cancel_at__isnull=False,
                cancel_at__lte=current_time,
            ).select_related("event", "event__organizer", "addon")
        )
        for item in event_canceled:
            with transaction.atomic():
                rows_updated = EventAddon.objects.filter(
                    pk=item.pk,
                    status=AddonStatus.ACTIVE,
                ).update(
                    status=AddonStatus.CANCELED,
                    canceled_at=current_time,
                    updated_at=current_time,
                )
                if not rows_updated:
                    continue
                item.status = AddonStatus.CANCELED
                item.canceled_at = current_time
                canceled_count += 1
                log_addon_lifecycle_action(item, "canceled")
                invalidate_entitlement_cache(
                    organizer=item.event.organizer, event=item.event
                )
                addon_canceled.send(sender=EventAddon, instance=item, immediate=False)

        # 4. Process expiration for EventAddon
        event_expired = list(
            EventAddon.objects.filter(
                status=AddonStatus.ACTIVE,
                ends_at__isnull=False,
                ends_at__lte=current_time,
            ).select_related("event", "event__organizer", "addon")
        )
        for item in event_expired:
            with transaction.atomic():
                rows_updated = EventAddon.objects.filter(
                    pk=item.pk,
                    status=AddonStatus.ACTIVE,
                ).update(
                    status=AddonStatus.EXPIRED,
                    updated_at=current_time,
                )
                if not rows_updated:
                    continue
                item.status = AddonStatus.EXPIRED
                expired_count += 1
                log_addon_lifecycle_action(item, "expired")
                invalidate_entitlement_cache(
                    organizer=item.event.organizer, event=item.event
                )
                addon_expired.send(sender=EventAddon, instance=item)

    logger.info(
        "expire_addon_assignments completed: %d canceled, %d expired",
        canceled_count,
        expired_count,
    )
    return {"canceled": canceled_count, "expired": expired_count}


@app.task(name="eventyay_business.expire_addon_assignments")
def expire_addon_assignments_task():
    return expire_addon_assignments()


if periodic_task:

    @receiver(periodic_task, dispatch_uid="business_expire_addon_assignments")
    def periodic_expire_addon_assignments(sender, **kwargs):
        return expire_addon_assignments()
