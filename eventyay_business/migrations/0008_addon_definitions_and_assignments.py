# Generated manually for Issue #9: Add-on definitions and assignments

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0001_initial"),
        ("eventyay_business", "0007_seed_free_tier_entitlements"),
    ]

    operations = [
        migrations.CreateModel(
            name="AddonDefinition",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "slug",
                    models.SlugField(unique=True, verbose_name="Slug"),
                ),
                (
                    "name",
                    models.CharField(max_length=200, verbose_name="Name"),
                ),
                (
                    "description",
                    models.TextField(blank=True, verbose_name="Description"),
                ),
                (
                    "assignment_scope",
                    models.CharField(
                        choices=[("organizer", "Organizer"), ("event", "Event")],
                        default="organizer",
                        max_length=20,
                        verbose_name="Assignment scope",
                    ),
                ),
                (
                    "pricing_mode",
                    models.CharField(
                        choices=[("one_time", "One-time"), ("recurring", "Recurring")],
                        default="recurring",
                        max_length=20,
                        verbose_name="Pricing mode",
                    ),
                ),
                (
                    "currency",
                    models.CharField(
                        default="USD", max_length=3, verbose_name="Currency"
                    ),
                ),
                (
                    "price",
                    models.DecimalField(
                        decimal_places=2,
                        default=0.0,
                        max_digits=10,
                        verbose_name="Price",
                    ),
                ),
                (
                    "capability",
                    models.CharField(max_length=100, verbose_name="Capability"),
                ),
                (
                    "entitlement_value",
                    models.CharField(
                        blank=True,
                        default="true",
                        max_length=100,
                        verbose_name="Entitlement value",
                    ),
                ),
                (
                    "quantity",
                    models.PositiveIntegerField(
                        default=1, verbose_name="Included quantity / allowance"
                    ),
                ),
                (
                    "active",
                    models.BooleanField(default=True, verbose_name="Active"),
                ),
                (
                    "public",
                    models.BooleanField(default=True, verbose_name="Public"),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="Created at"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="Updated at"),
                ),
            ],
            options={
                "verbose_name": "Add-on definition",
                "verbose_name_plural": "Add-on definitions",
                "ordering": ["name", "slug"],
            },
        ),
        migrations.AddConstraint(
            model_name="AddonDefinition",
            constraint=models.CheckConstraint(
                condition=models.Q(price__gte=0),
                name="addondefinition_price_nonnegative",
            ),
        ),
        migrations.AddConstraint(
            model_name="AddonDefinition",
            constraint=models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="addondefinition_quantity_positive",
            ),
        ),
        migrations.CreateModel(
            name="OrganizerAddon",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "quantity",
                    models.PositiveIntegerField(default=1, verbose_name="Quantity"),
                ),
                (
                    "starts_at",
                    models.DateTimeField(
                        default=django.utils.timezone.now, verbose_name="Starts at"
                    ),
                ),
                (
                    "ends_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="Ends at"),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("expired", "Expired"),
                            ("canceled", "Canceled"),
                        ],
                        default="active",
                        max_length=20,
                        verbose_name="Status",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="Created at"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="Updated at"),
                ),
                (
                    "addon",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="organizer_assignments",
                        to="eventyay_business.addondefinition",
                        verbose_name="Add-on",
                    ),
                ),
                (
                    "organizer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="business_addons",
                        to="base.organizer",
                        verbose_name="Organizer",
                    ),
                ),
            ],
            options={
                "verbose_name": "Organizer add-on",
                "verbose_name_plural": "Organizer add-ons",
                "ordering": ["-starts_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="EventAddon",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "quantity",
                    models.PositiveIntegerField(default=1, verbose_name="Quantity"),
                ),
                (
                    "starts_at",
                    models.DateTimeField(
                        default=django.utils.timezone.now, verbose_name="Starts at"
                    ),
                ),
                (
                    "ends_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="Ends at"),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("expired", "Expired"),
                            ("canceled", "Canceled"),
                        ],
                        default="active",
                        max_length=20,
                        verbose_name="Status",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="Created at"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="Updated at"),
                ),
                (
                    "addon",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="event_assignments",
                        to="eventyay_business.addondefinition",
                        verbose_name="Add-on",
                    ),
                ),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="business_addons",
                        to="base.event",
                        verbose_name="Event",
                    ),
                ),
            ],
            options={
                "verbose_name": "Event add-on",
                "verbose_name_plural": "Event add-ons",
                "ordering": ["-starts_at", "-id"],
            },
        ),
    ]
