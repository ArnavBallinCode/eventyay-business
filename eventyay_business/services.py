import logging
from django.db import IntegrityError, transaction
from django.utils.timezone import now

logger = logging.getLogger(__name__)


def record_usage(
    organizer,
    capability,
    quantity,
    unit,
    source_type,
    source_id,
    idempotency_key,
    event=None,
    metadata=None,
):
    """
    Atomically records a usage event.
    Relies on database unique constraints for idempotency.
    Returns the created UsageRecord or None if it was already processed.
    """
    from .models import UsageRecord

    try:
        with transaction.atomic():
            record = UsageRecord.objects.create(
                organizer=organizer,
                event=event,
                capability=capability,
                quantity=quantity,
                unit=unit,
                source_type=source_type,
                source_id=source_id,
                idempotency_key=idempotency_key,
                metadata=metadata or {},
                occurred_at=now(),
            )
            return record
    except IntegrityError as exc:
        cause = getattr(exc, "__cause__", None)
        diag = getattr(cause, "diag", None) if cause else None
        constraint_name = getattr(diag, "constraint_name", None) if diag else None

        if constraint_name == "unique_usage_idempotency_per_organizer":
            logger.info(
                f"Usage record with idempotency key {idempotency_key} already exists for organizer {organizer.slug}."
            )
            return None

        # Re-raise all other integrity errors
        raise


def seed_standard_entitlements_for_version(tier_version, TierEntitlementModel=None):
    """
    Populates standard catalogue capabilities as TierEntitlement database records
    for the given tier_version if they do not already exist.
    """
    if TierEntitlementModel is None:
        from .models import TierEntitlement as TierEntitlementModel

    from .capabilities import STANDARD_CAPABILITIES, CapabilityValueType

    existing_caps = set(
        TierEntitlementModel.objects.filter(tier_version=tier_version).values_list(
            "capability", flat=True
        )
    )

    entitlements_to_create = []
    for cap in STANDARD_CAPABILITIES:
        if cap.name in existing_caps:
            continue

        raw_val = cap.default_value
        if cap.value_type == CapabilityValueType.BOOLEAN:
            str_val = "true" if raw_val else "false"
        elif raw_val is not None:
            str_val = str(raw_val)
        else:
            str_val = ""

        entitlements_to_create.append(
            TierEntitlementModel(
                tier_version=tier_version,
                capability=cap.name,
                value=str_val,
                unit=cap.unit or "",
                overage_allowed=False,
            )
        )

    if entitlements_to_create:
        try:
            TierEntitlementModel.objects.bulk_create(
                entitlements_to_create, ignore_conflicts=True
            )
        except IntegrityError:
            pass


def migrate_tier_subscribers(tier, target_version, from_version=None):
    """
    Migrates active and pending subscriptions belonging to a tier (or specific from_version)
    to target_version.
    Returns the number of subscriptions updated.
    """
    from .models import Subscription, SubscriptionStatus

    if target_version.tier_id != tier.pk:
        raise ValueError("Target version does not belong to the specified tier.")
    if from_version and from_version.tier_id != tier.pk:
        raise ValueError("From version does not belong to the specified tier.")

    qs = Subscription.objects.filter(
        tier_version__tier=tier,
        status__in=[SubscriptionStatus.ACTIVE, SubscriptionStatus.PENDING],
    ).exclude(tier_version=target_version)

    if from_version:
        qs = qs.filter(tier_version=from_version)

    count = qs.update(tier_version=target_version, updated_at=now())
    return count
