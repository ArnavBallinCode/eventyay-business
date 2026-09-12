from django import forms
from django.forms import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from .capabilities import get_capability_choices
from .models import (
    AddonDefinition,
    EventAddon,
    OrganizerAddon,
    Subscription,
    SubscriptionStatus,
    Tier,
    TierEntitlement,
    TierPrice,
    TierVersion,
)

try:
    from eventyay.base.forms.widgets import SplitDateTimePickerWidget
    from eventyay.control.forms import SplitDateTimeField
except ImportError:
    from django.forms import (
        SplitDateTimeField,
        SplitDateTimeWidget as SplitDateTimePickerWidget,
    )


class TierForm(forms.ModelForm):
    class Meta:
        model = Tier
        fields = ["name", "slug", "description", "is_public", "display_order"]


class TierVersionForm(forms.ModelForm):
    class Meta:
        model = TierVersion
        fields = []  # No fields editable directly on version in this form


class TierEntitlementForm(forms.ModelForm):
    class Meta:
        model = TierEntitlement
        fields = [
            "capability",
            "value",
            "unit",
            "overage_allowed",
            "overage_price",
            "currency",
            "overage_block_size",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [("", "---------")] + get_capability_choices()
        if self.instance and self.instance.capability:
            existing_caps = [c[0] for c in choices]
            if self.instance.capability not in existing_caps:
                choices.append((self.instance.capability, self.instance.capability))
        self.fields["capability"].widget = forms.Select(choices=choices)

    def clean(self):
        cleaned_data = super().clean()
        capability_name = cleaned_data.get("capability")
        value = cleaned_data.get("value")

        if capability_name and value:
            from .capabilities import CapabilityValueType, get_capability

            cap = get_capability(capability_name)
            if cap:
                if cap.value_type == CapabilityValueType.INTEGER:
                    try:
                        int(value)
                    except ValueError:
                        self.add_error(
                            "value",
                            forms.ValidationError(
                                _("Value must be a valid whole number (integer).")
                            ),
                        )
                elif cap.value_type in (
                    CapabilityValueType.DECIMAL,
                    CapabilityValueType.MONEY,
                ):
                    from decimal import Decimal, InvalidOperation

                    try:
                        val = Decimal(value)
                        if not val.is_finite():
                            raise InvalidOperation
                    except (InvalidOperation, TypeError):
                        self.add_error(
                            "value",
                            forms.ValidationError(
                                _("Value must be a valid number or decimal.")
                            ),
                        )
                elif (
                    cap.value_type == CapabilityValueType.BOOLEAN
                    and value.lower() not in ("true", "false", "1", "0", "yes", "no")
                ):
                    self.add_error(
                        "value",
                        forms.ValidationError(
                            _("Value must be a boolean (e.g. 1, 0, true, false).")
                        ),
                    )
        return cleaned_data


TierPriceFormSet = inlineformset_factory(
    TierVersion,
    TierPrice,
    fields=["billing_interval", "currency", "amount", "stripe_price_id", "active"],
    extra=1,
    can_delete=True,
)


TierEntitlementFormSet = inlineformset_factory(
    TierVersion,
    TierEntitlement,
    form=TierEntitlementForm,
    fields=[
        "capability",
        "value",
        "unit",
        "overage_allowed",
        "overage_price",
        "currency",
        "overage_block_size",
    ],
    extra=1,
    can_delete=True,
)


class SubscriptionAdminForm(forms.ModelForm):
    class Meta:
        model = Subscription
        fields = [
            "organizer",
            "tier_version",
            "status",
            "billing_interval",
            "currency",
            "starts_at",
            "ends_at",
            "cancel_at",
            "stripe_customer_id",
            "stripe_subscription_id",
        ]
        field_classes = {
            "starts_at": SplitDateTimeField,
            "ends_at": SplitDateTimeField,
            "cancel_at": SplitDateTimeField,
        }
        widgets = {
            "starts_at": SplitDateTimePickerWidget(),
            "ends_at": SplitDateTimePickerWidget(),
            "cancel_at": SplitDateTimePickerWidget(),
        }

    def clean(self):
        cleaned_data = super().clean()
        organizer = cleaned_data.get("organizer")
        status = cleaned_data.get("status")

        if organizer and status in [
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.PENDING,
        ]:
            qs = Subscription.objects.filter(
                organizer=organizer,
                status__in=[SubscriptionStatus.ACTIVE, SubscriptionStatus.PENDING],
            )
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)

            if qs.exists():
                raise forms.ValidationError(
                    _("This organizer already has an active or pending subscription.")
                )
        return cleaned_data


class AddonDefinitionForm(forms.ModelForm):
    class Meta:
        model = AddonDefinition
        fields = [
            "name",
            "slug",
            "description",
            "assignment_scope",
            "pricing_mode",
            "currency",
            "price",
            "capability",
            "entitlement_value",
            "quantity",
            "active",
            "public",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [("", "---------")] + get_capability_choices()
        if self.instance and self.instance.capability:
            existing_caps = [c[0] for c in choices]
            if self.instance.capability not in existing_caps:
                choices.append((self.instance.capability, self.instance.capability))
        self.fields["capability"].widget = forms.Select(choices=choices)

    def clean(self):
        cleaned_data = super().clean()
        capability_name = cleaned_data.get("capability")
        value = cleaned_data.get("entitlement_value")

        if capability_name:
            from .capabilities import CapabilityValueType, get_capability

            cap = get_capability(capability_name)
            is_existing_unchanged = (
                self.instance
                and self.instance.pk
                and self.instance.capability == capability_name
            )
            if not cap and not is_existing_unchanged:
                self.add_error(
                    "capability",
                    forms.ValidationError(
                        _("Unknown capability: %(name)s"),
                        params={"name": capability_name},
                    ),
                )
            elif cap and value:
                if cap.value_type == CapabilityValueType.INTEGER:
                    try:
                        int(value)
                    except ValueError:
                        self.add_error(
                            "entitlement_value",
                            forms.ValidationError(
                                _("Value must be a valid whole number (integer).")
                            ),
                        )
                elif cap.value_type in (
                    CapabilityValueType.DECIMAL,
                    CapabilityValueType.MONEY,
                ):
                    from decimal import Decimal, InvalidOperation

                    try:
                        val = Decimal(value)
                        if not val.is_finite():
                            raise InvalidOperation
                    except (InvalidOperation, TypeError):
                        self.add_error(
                            "entitlement_value",
                            forms.ValidationError(
                                _("Value must be a valid number or decimal.")
                            ),
                        )
                elif (
                    cap.value_type == CapabilityValueType.BOOLEAN
                    and value.lower() not in ("true", "false", "1", "0", "yes", "no")
                ):
                    self.add_error(
                        "entitlement_value",
                        forms.ValidationError(
                            _(
                                "Value must be 'true' or 'false' for boolean capabilities."
                            )
                        ),
                    )
        return cleaned_data


class OrganizerAddonForm(forms.ModelForm):
    class Meta:
        model = OrganizerAddon
        fields = ["organizer", "addon", "quantity", "starts_at", "ends_at", "status"]
        field_classes = {
            "starts_at": SplitDateTimeField,
            "ends_at": SplitDateTimeField,
        }
        widgets = {
            "starts_at": SplitDateTimePickerWidget(),
            "ends_at": SplitDateTimePickerWidget(),
        }


class EventAddonForm(forms.ModelForm):
    class Meta:
        model = EventAddon
        fields = ["event", "addon", "quantity", "starts_at", "ends_at", "status"]
        field_classes = {
            "starts_at": SplitDateTimeField,
            "ends_at": SplitDateTimeField,
        }
        widgets = {
            "starts_at": SplitDateTimePickerWidget(),
            "ends_at": SplitDateTimePickerWidget(),
        }
