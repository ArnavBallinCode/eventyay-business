import gettext
import polib
import pytest
import re
from django.conf import settings as django_settings
from django.core import mail as djmail
from django.urls import reverse
from django.utils import translation
from django.utils.translation import to_locale
from eventyay.base.models import Organizer
from eventyay.base.models.auth import StaffSession
from pathlib import Path

import eventyay_business
from eventyay_business.models import (
    BillingNotificationEventType,
    BillingNotificationRecipientSource,
)
from eventyay_business.notifications import (
    NOTIFICATION_SPECS,
    BillingNotificationRecipient,
    deliver_billing_notification,
    notification_template_overrides,
    notification_template_sources,
    preview_notification_context,
    queue_billing_notification,
)

LOCALE_DIR = Path(eventyay_business.__file__).parent / "locale"
BRACE_PLACEHOLDER = re.compile(r"\{(\w+)\}")
PERCENT_PLACEHOLDER = re.compile(r"%\((\w+)\)[sd]")
INVOICE_ISSUED = BillingNotificationEventType.INVOICE_ISSUED


def placeholders(text: str) -> set[str]:
    return set(BRACE_PLACEHOLDER.findall(text)) | set(PERCENT_PLACEHOLDER.findall(text))


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
    admin_user.save(update_fields=["is_staff"])
    return admin_client


@pytest.fixture
def french_catalog(tmp_path, settings):
    """Install a French catalog translating the invoice issued notification."""
    template = polib.pofile(str(LOCALE_DIR / "django.pot"))
    catalog = polib.POFile()
    catalog.metadata = {
        "Content-Type": "text/plain; charset=UTF-8",
        "Language": "fr",
        "Plural-Forms": "nplurals=2; plural=(n > 1);",
    }
    with translation.override("en"):
        subject = str(NOTIFICATION_SPECS[INVOICE_ISSUED].subject)
    for entry in template:
        in_invoice_email = any(
            path.endswith("email/invoice_issued.txt")
            for path, _line in entry.occurrences
        )
        if in_invoice_email or entry.msgid == subject:
            catalog.append(
                polib.POEntry(msgid=entry.msgid, msgstr=f"[FR] {entry.msgid}")
            )
    target = tmp_path / "fr" / "LC_MESSAGES"
    target.mkdir(parents=True)
    catalog.save_as_mofile(str(target / "django.mo"))
    # Changing LOCALE_PATHS makes Django drop its cached translation catalogs.
    settings.LOCALE_PATHS = [str(tmp_path), *settings.LOCALE_PATHS]
    return catalog


def test_every_platform_language_has_a_catalog():
    missing = [
        code
        for code, _name in django_settings.LANGUAGES
        if not code.startswith("en")
        and not (LOCALE_DIR / to_locale(code) / "LC_MESSAGES" / "django.po").exists()
    ]
    assert missing == []


def test_catalog_contains_notification_subjects_and_bodies():
    template = polib.pofile(str(LOCALE_DIR / "django.pot"))
    msgids = {entry.msgid for entry in template}
    sources = {path for entry in template for path, _line in entry.occurrences}

    with translation.override("en"):
        subjects = {str(spec.subject) for spec in NOTIFICATION_SPECS.values()}
    assert subjects - msgids == set()
    templates = {spec.template_name for spec in NOTIFICATION_SPECS.values()}
    assert {
        name
        for name in templates
        if not any(path.endswith(f"templates/{name}") for path in sources)
    } == set()


def test_catalogs_compile_with_valid_plural_forms(tmp_path):
    for po_path in sorted(LOCALE_DIR.glob("*/LC_MESSAGES/django.po")):
        mo_path = tmp_path / f"{po_path.parent.parent.name}.mo"
        polib.pofile(str(po_path)).save_as_mofile(str(mo_path))
        with mo_path.open("rb") as mo_file:
            # Raises ValueError when the Plural-Forms header is not a valid expression.
            gettext.GNUTranslations(mo_file).ngettext("item", "items", 2)


def test_translations_keep_placeholders():
    broken = []
    for po_path in sorted(LOCALE_DIR.glob("*/LC_MESSAGES/django.po")):
        for entry in polib.pofile(str(po_path)).translated_entries():
            if entry.msgid_plural:
                allowed = placeholders(entry.msgid) | placeholders(entry.msgid_plural)
                if any(
                    not placeholders(text) <= allowed
                    for text in entry.msgstr_plural.values()
                ):
                    broken.append((po_path.parent.parent.name, entry.msgid))
            elif placeholders(entry.msgstr) != placeholders(entry.msgid):
                broken.append((po_path.parent.parent.name, entry.msgid))
    assert broken == []


@pytest.mark.django_db
def test_editor_shows_translated_defaults_and_falls_back_to_english(french_catalog):
    subject, body, is_custom = notification_template_sources(INVOICE_ISSUED, "fr")

    assert subject == "[FR] Eventyay invoice {invoice_number}"
    assert "[FR] Hello {organizer_name}," in body
    assert "[FR] Review and download the invoice in Eventyay:" in body
    assert is_custom is False

    subject, body, _is_custom = notification_template_sources(INVOICE_ISSUED, "sv")
    assert subject == "Eventyay invoice {invoice_number}"
    assert body.startswith("Hello {organizer_name},")


@pytest.mark.django_db
def test_saving_unchanged_translated_default_stores_no_override(
    business_admin_client, french_catalog
):
    edit_url = reverse(
        "plugins:eventyay_business:notifications.template",
        kwargs={"event_type": INVOICE_ISSUED},
    )
    language_codes = [code for code, _name in django_settings.LANGUAGES]
    form_data = {"active_locales": "en,fr", "selected_locale": "fr"}
    for locale in ("en", "fr"):
        subject, body, _is_custom = notification_template_sources(
            INVOICE_ISSUED, locale
        )
        index = language_codes.index(locale)
        form_data[f"subject_{index}"] = subject
        form_data[f"message_{index}"] = body

    response = business_admin_client.post(edit_url, form_data)

    assert response.status_code == 302
    assert notification_template_overrides(INVOICE_ISSUED, "fr") == ("", "")
    edit_page = business_admin_client.get(response.url)
    assert edit_page.context["form"].initial["active_locales"] == "en,fr"
    assert edit_page.context["form"].initial["subject"]["fr"] == (
        "[FR] Eventyay invoice {invoice_number}"
    )


@pytest.mark.django_db
def test_delivery_uses_translated_subject_and_body(french_catalog):
    organizer = Organizer.objects.create(name="Organisateur", slug="organisateur")
    context = preview_notification_context(INVOICE_ISSUED)
    delivery = queue_billing_notification(
        logical_event_key="invoice:translated",
        event_type=INVOICE_ISSUED,
        organizer=organizer,
        recipient=BillingNotificationRecipient(
            email="facturation@example.com",
            locale="fr",
            source=BillingNotificationRecipientSource.BILLING_CONTACT,
        ),
        context=context,
    )
    djmail.outbox = []

    deliver_billing_notification(delivery.pk)

    assert delivery.subject == f"[FR] Eventyay invoice {context['invoice_number']}"
    sent = djmail.outbox[0]
    assert sent.subject == delivery.subject
    assert f"[FR] Hello {context['organizer_name']}," in sent.body
    assert "{" not in sent.body
