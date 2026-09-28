from collections import OrderedDict
from django import forms
from django.utils.translation import gettext_lazy as _
from eventyay.base.forms import SecretKeySettingsField
from eventyay.control.forms.ext import StripeKeyValidator

def get_business_settings_fields():
    return OrderedDict([
        # Stripe for Organizer Billing
        (
            'payment_stripe_publishable_key',
            forms.CharField(
                label=_('Publishable key (Live)'),
                required=False,
                validators=(StripeKeyValidator('pk_live_'),),
                help_text=_('Live publishable key for organizer billing and platform fees.'),
            ),
        ),
        (
            'payment_stripe_secret_key',
            SecretKeySettingsField(
                label=_('Secret key (Live)'),
                required=False,
                validators=(StripeKeyValidator(['sk_live_', 'rk_live_']),),
                help_text=_('Live secret key for organizer billing and platform fees.'),
            ),
        ),
        (
            'payment_stripe_test_publishable_key',
            forms.CharField(
                label=_('Publishable key (Test)'),
                required=False,
                validators=(StripeKeyValidator('pk_test_'),),
                help_text=_('Test publishable key for organizer billing and platform fees.'),
            ),
        ),
        (
            'payment_stripe_test_secret_key',
            SecretKeySettingsField(
                label=_('Secret key (Test)'),
                required=False,
                validators=(StripeKeyValidator(['sk_test_', 'rk_test_']),),
                help_text=_('Test secret key for organizer billing and platform fees.'),
            ),
        ),
        (
            'stripe_webhook_secret_key',
            SecretKeySettingsField(
                label=_('Webhook secret key'),
                required=False,
                help_text=_('Configure this endpoint in your Stripe dashboard to receive billing events.'),
            ),
        ),
        (
            'billing_validation',
            forms.BooleanField(
                required=False,
                label=_('Billing validation'),
                help_text=_(
                    'Billing validation lets you require organizers to set up a billing method before they can create events. '
                    'When this option is enabled, no new event can be created until a valid billing method has been added.'
                ),
            ),
        ),
        (
            'business_grace_period_days',
            forms.IntegerField(
                label=_('Business subscription grace period (days)'),
                required=False,
                min_value=0,
                initial=7,
                help_text=_('Number of days past-due subscriptions remain active before being expired.'),
            ),
        ),
    ])
