from django.db import migrations


def seed_free_tier_entitlements(apps, schema_editor):
    Tier = apps.get_model("eventyay_business", "Tier")
    TierVersion = apps.get_model("eventyay_business", "TierVersion")
    TierEntitlement = apps.get_model("eventyay_business", "TierEntitlement")

    free_tier = Tier.objects.filter(slug="free").first()
    if not free_tier:
        return

    if free_tier.status == "draft":
        free_tier.status = "published"
        free_tier.save(update_fields=["status"])

    versions = list(free_tier.versions.all())
    if not versions:
        v1 = TierVersion.objects.create(
            tier=free_tier,
            version=1,
            published_at=free_tier.created_at,
        )
        versions = [v1]

    # Standard capabilities definition to seed
    standard_defaults = [
        ("video.youtube", "true", "", False),
        ("video.jitsi", "true", "", False),
        ("video.jitsi.concurrent_rooms", "1", "rooms", False),
        ("video.loungemesh", "false", "", False),
        ("email.bulk.monthly", "1000", "emails", False),
        ("organizer.full_admins", "2", "admins", False),
        ("api.read", "true", "", False),
        ("api.write", "false", "", False),
        ("api.webhooks", "false", "", False),
        ("commerce.platform_fee_percent", "0.0", "%", False),
        ("registration.free_allowance_per_event", "100", "registrations", False),
        ("registration.free_overage_price", "0.0", "per registration", False),
        ("support.priority", "false", "", False),
    ]

    for version in versions:
        if version.published_at is None:
            version.published_at = free_tier.created_at
            version.save(update_fields=["published_at"])

        existing_caps = set(
            TierEntitlement.objects.filter(tier_version=version).values_list(
                "capability", flat=True
            )
        )
        to_create = []
        for cap_name, val, unit, overage in standard_defaults:
            if cap_name not in existing_caps:
                to_create.append(
                    TierEntitlement(
                        tier_version=version,
                        capability=cap_name,
                        value=val,
                        unit=unit,
                        overage_allowed=overage,
                    )
                )
        if to_create:
            TierEntitlement.objects.bulk_create(to_create)


class Migration(migrations.Migration):

    dependencies = [
        ("eventyay_business", "0006_usagerecord"),
    ]

    operations = [
        migrations.RunPython(seed_free_tier_entitlements, migrations.RunPython.noop),
    ]
