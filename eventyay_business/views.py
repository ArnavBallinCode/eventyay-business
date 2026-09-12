from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.views.generic import (
    CreateView,
    DetailView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)
from eventyay.base.models import Event, Organizer
from eventyay.control.permissions import (
    AdministratorPermissionRequiredMixin,
    EventPermissionRequiredMixin,
    OrganizerPermissionRequiredMixin,
)
from eventyay.control.views.organizer_views.organizer_detail_view_mixin import (
    OrganizerDetailViewMixin,
)

from .capabilities import CapabilityValueType, get_all_capabilities, get_capability
from .forms import (
    AddonDefinitionForm,
    EventAddonForm,
    EventAddonPurchaseForm,
    OrganizerAddonForm,
    OrganizerAddonPurchaseForm,
    SubscriptionAdminForm,
    TierEntitlementFormSet,
    TierForm,
    TierPriceFormSet,
)
from .models import (
    AddonAssignmentScope,
    AddonDefinition,
    AddonStatus,
    EventAddon,
    OrganizerAddon,
    Subscription,
    SubscriptionStatus,
    Tier,
    TierStatus,
    TierVersion,
)
from .services import migrate_addon_assignments, migrate_tier_subscribers


class TierListView(AdministratorPermissionRequiredMixin, ListView):
    model = Tier
    template_name = "eventyay_business/tiers/list.html"
    context_object_name = "tiers"


class TierCreateView(AdministratorPermissionRequiredMixin, CreateView):
    model = Tier
    form_class = TierForm
    template_name = "eventyay_business/tiers/form.html"

    @transaction.atomic
    def form_valid(self, form):
        self.object = form.save()
        # Create the initial draft TierVersion
        TierVersion.objects.create(
            tier=self.object, version=1, created_by=self.request.user
        )
        messages.success(
            self.request,
            _("Tier created successfully. You can now add prices and entitlements."),
        )
        return redirect(
            reverse(
                "plugins:eventyay_business:tiers.edit", kwargs={"pk": self.object.pk}
            )
        )


class TierUpdateView(AdministratorPermissionRequiredMixin, UpdateView):
    model = Tier
    form_class = TierForm
    template_name = "eventyay_business/tiers/form.html"

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.latest_version = self.object.versions.first()

        if not self.latest_version:
            self.latest_version = TierVersion.objects.create(
                tier=self.object, version=1, created_by=request.user
            )

        # If the latest version is published, redirect to detail view or duplicate prompt
        if self.latest_version and self.latest_version.published_at:
            messages.info(
                request,
                _(
                    "This tier is published. To edit prices or entitlements, please create a new draft version."
                ),
            )
            return redirect(
                reverse(
                    "plugins:eventyay_business:tiers.detail",
                    kwargs={"pk": self.object.pk},
                )
            )

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context["price_formset"] = TierPriceFormSet(
                self.request.POST, instance=self.latest_version
            )
            context["entitlement_formset"] = TierEntitlementFormSet(
                self.request.POST, instance=self.latest_version
            )
        else:
            context["price_formset"] = TierPriceFormSet(instance=self.latest_version)
            context["entitlement_formset"] = TierEntitlementFormSet(
                instance=self.latest_version
            )
        return context

    @transaction.atomic
    def form_valid(self, form):
        context = self.get_context_data()
        price_formset = context["price_formset"]
        entitlement_formset = context["entitlement_formset"]

        if (
            form.is_valid()
            and price_formset.is_valid()
            and entitlement_formset.is_valid()
        ):
            latest_version = (
                TierVersion.objects.select_for_update()
                .filter(pk=self.latest_version.pk)
                .first()
            )
            if latest_version and latest_version.published_at:
                messages.error(
                    self.request,
                    _("Cannot save edits: this version was published concurrently."),
                )
                return redirect(
                    reverse(
                        "plugins:eventyay_business:tiers.detail",
                        kwargs={"pk": self.object.pk},
                    )
                )

            self.object = form.save()
            price_formset.save()
            entitlement_formset.save()
            messages.success(self.request, _("Tier draft saved successfully."))
            return redirect(reverse("plugins:eventyay_business:tiers.list"))
        else:
            return self.render_to_response(self.get_context_data(form=form))


class TierDetailView(AdministratorPermissionRequiredMixin, DetailView):
    model = Tier
    template_name = "eventyay_business/tiers/detail.html"
    context_object_name = "tier"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        latest_version = self.object.versions.first()
        context["latest_version"] = latest_version
        if latest_version and not latest_version.published_at:
            prev_versions = self.object.versions.filter(published_at__isnull=False)
            has_prev = prev_versions.exists()
            context["has_previous_published_version"] = has_prev
            if has_prev:
                context["previous_subscribers_count"] = Subscription.objects.filter(
                    tier_version__in=prev_versions,
                    status__in=[SubscriptionStatus.ACTIVE, SubscriptionStatus.PENDING],
                ).count()
        return context


class TierVersionDetailView(AdministratorPermissionRequiredMixin, DetailView):
    """Show all details for a specific historical TierVersion."""

    model = TierVersion
    template_name = "eventyay_business/tiers/version_detail.html"
    context_object_name = "version"
    pk_url_kwarg = "version_pk"

    def get_object(self, queryset=None):
        tier = get_object_or_404(Tier, pk=self.kwargs["pk"])
        return get_object_or_404(TierVersion, pk=self.kwargs["version_pk"], tier=tier)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tier"] = self.object.tier
        context["active_subscriber_count"] = Subscription.objects.filter(
            tier_version=self.object,
            status__in=[SubscriptionStatus.ACTIVE, SubscriptionStatus.PENDING],
        ).count()
        return context


class TierNewDraftView(AdministratorPermissionRequiredMixin, View):
    """Creates a new DRAFT TierVersion from the latest PUBLISHED version."""

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        tier = get_object_or_404(Tier.objects.select_for_update(), pk=kwargs.get("pk"))
        latest_version = tier.versions.first()

        if not latest_version or not latest_version.published_at:
            messages.error(
                request,
                _("Cannot create a new draft: there is already an unpublished draft."),
            )
            return redirect(
                reverse("plugins:eventyay_business:tiers.edit", kwargs={"pk": tier.pk})
            )

        # Duplicate version
        new_version = TierVersion.objects.create(
            tier=tier, version=latest_version.version + 1, created_by=request.user
        )

        # Duplicate prices
        for price in latest_version.prices.all():
            price.pk = None
            price.tier_version = new_version
            price.save()

        # Duplicate entitlements
        for ent in latest_version.entitlements.all():
            ent.pk = None
            ent.tier_version = new_version
            ent.save()

        messages.success(
            request, _("New draft version created. You can now make changes.")
        )
        return redirect(
            reverse("plugins:eventyay_business:tiers.edit", kwargs={"pk": tier.pk})
        )


class TierPublishView(AdministratorPermissionRequiredMixin, View):
    @transaction.atomic
    def post(self, request, *args, **kwargs):
        tier = get_object_or_404(Tier, pk=kwargs.get("pk"))
        latest_version = tier.versions.first()

        if tier.status == TierStatus.ARCHIVED:
            messages.error(
                request,
                _("Cannot publish a draft for an archived tier. Unarchive it first."),
            )
            return redirect(reverse("plugins:eventyay_business:tiers.list"))

        if latest_version and not latest_version.published_at:
            latest_version.published_at = now()
            latest_version.save()

            if tier.status == TierStatus.DRAFT:
                tier.status = TierStatus.PUBLISHED
                tier.save()

            migrate_subs = request.POST.get("migrate_subscribers") in (
                "1",
                "true",
                "on",
            )
            if migrate_subs:
                count = migrate_tier_subscribers(tier, latest_version)
                messages.success(
                    request,
                    _(
                        "Tier published successfully. Migrated %(count)d subscriber(s) to v%(version)d."
                    )
                    % {"count": count, "version": latest_version.version},
                )
            else:
                messages.success(request, _("Tier published successfully."))
        else:
            messages.error(request, _("This tier has no unpublished draft."))

        return redirect(reverse("plugins:eventyay_business:tiers.list"))


class TierArchiveView(AdministratorPermissionRequiredMixin, View):
    @transaction.atomic
    def post(self, request, *args, **kwargs):
        tier = get_object_or_404(Tier, pk=kwargs.get("pk"))
        tier.status = TierStatus.ARCHIVED
        tier.save()
        messages.success(request, _("Tier archived successfully."))
        return redirect(reverse("plugins:eventyay_business:tiers.list"))


class SubscriptionListView(AdministratorPermissionRequiredMixin, ListView):
    model = Subscription
    template_name = "eventyay_business/subscriptions/list.html"
    context_object_name = "subscriptions"


class SubscriptionCreateView(AdministratorPermissionRequiredMixin, CreateView):
    model = Subscription
    form_class = SubscriptionAdminForm
    template_name = "eventyay_business/subscriptions/form.html"

    def get_success_url(self):
        messages.success(self.request, _("Subscription created successfully."))
        return reverse("plugins:eventyay_business:subscriptions.list")


class SubscriptionUpdateView(AdministratorPermissionRequiredMixin, UpdateView):
    model = Subscription
    form_class = SubscriptionAdminForm
    template_name = "eventyay_business/subscriptions/form.html"

    def get_success_url(self):
        messages.success(self.request, _("Subscription updated successfully."))
        return reverse("plugins:eventyay_business:subscriptions.list")


class OrganizerPlanView(
    OrganizerPermissionRequiredMixin, OrganizerDetailViewMixin, TemplateView
):
    permission = "can_change_organizer_settings"
    template_name = "eventyay_business/organizer/plan.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        organizer = self.request.organizer

        current_time = now()
        sub = (
            Subscription.objects.filter(
                organizer=organizer,
                status="active",
                starts_at__lte=current_time,
            )
            .exclude(ends_at__lt=current_time)
            .select_related("tier_version__tier")
            .first()
        )

        ctx["subscription"] = sub

        # Build effective entitlement values from the active subscription override
        override_dict = {}
        if sub and sub.tier_version:
            for ent in sub.tier_version.entitlements.all():
                override_dict[ent.capability] = ent.get_typed_value()

        organizer_entitlements = []
        developer_entitlements = []

        for cap in get_all_capabilities():
            val = override_dict.get(cap.name, cap.default_value)
            entry = {
                "capability": cap,
                "effective_value": val,
                "is_overridden": cap.name in override_dict,
            }
            audience = cap.metadata.get("audience", "organizer")
            if audience == "developer":
                developer_entitlements.append(entry)
            else:
                organizer_entitlements.append(entry)

        ctx["organizer_entitlements"] = sorted(
            organizer_entitlements, key=lambda x: x["capability"].category
        )
        ctx["developer_entitlements"] = sorted(
            developer_entitlements, key=lambda x: x["capability"].category
        )

        ctx["active_organizer_addons"] = (
            OrganizerAddon.objects.filter(
                organizer=organizer,
                addon__active=True,
                status=AddonStatus.ACTIVE,
                starts_at__lte=current_time,
            )
            .exclude(ends_at__lt=current_time)
            .select_related("addon")
            .order_by("addon__name")
        )

        ctx["active_event_addons"] = (
            EventAddon.objects.filter(
                event__organizer=organizer,
                addon__active=True,
                status=AddonStatus.ACTIVE,
                starts_at__lte=current_time,
            )
            .exclude(ends_at__lt=current_time)
            .select_related("addon", "event")
            .order_by("event__name", "addon__name")
        )

        available_addons = list(
            AddonDefinition.objects.filter(
                active=True,
                public=True,
            ).order_by("assignment_scope", "name")
        )

        active_org_addons = list(
            OrganizerAddon.objects.filter(
                organizer=organizer,
                status=AddonStatus.ACTIVE,
                starts_at__lte=current_time,
            ).exclude(ends_at__lt=current_time)
        )
        active_by_addon_id = {
            oa.addon_id: oa for oa in active_org_addons if oa.addon_id
        }
        active_by_capability = {
            oa.capability: oa for oa in active_org_addons if oa.capability
        }

        for addon in available_addons:
            active_assignment = active_by_addon_id.get(
                addon.id
            ) or active_by_capability.get(addon.capability)
            addon.active_assignment = active_assignment
            addon.is_active_for_organizer = active_assignment is not None

        ctx["available_addons"] = available_addons
        return ctx


class OrganizerAddonPurchaseView(
    OrganizerPermissionRequiredMixin, OrganizerDetailViewMixin, FormView
):
    permission = "can_change_organizer_settings"
    template_name = "eventyay_business/organizer/addon_purchase.html"
    form_class = OrganizerAddonPurchaseForm

    def get_addon(self):
        return get_object_or_404(
            AddonDefinition,
            pk=self.kwargs["pk"],
            active=True,
            public=True,
        )

    def dispatch(self, request, *args, **kwargs):
        self.addon = self.get_addon()
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["organizer"] = self.request.organizer
        kwargs["addon"] = self.addon
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["addon"] = self.addon
        ctx["capability"] = get_capability(self.addon.capability)
        return ctx

    def form_valid(self, form):
        cap = get_capability(self.addon.capability)

        with transaction.atomic():
            if self.addon.assignment_scope == AddonAssignmentScope.EVENT:
                event = form.cleaned_data["event"]
                Event.objects.select_for_update().get(pk=event.pk)
                if cap and cap.value_type == CapabilityValueType.BOOLEAN:
                    if EventAddon.objects.filter(
                        event=event,
                        capability=self.addon.capability,
                        status=AddonStatus.ACTIVE,
                    ).exists():
                        messages.warning(
                            self.request,
                            _("This add-on is already active for %(event)s.")
                            % {"event": event.name},
                        )
                        return redirect(
                            "plugins:eventyay_business:organizer.plan",
                            organizer=self.request.organizer.slug,
                        )
            else:
                Organizer.objects.select_for_update().get(pk=self.request.organizer.pk)
                if cap and cap.value_type == CapabilityValueType.BOOLEAN:
                    if OrganizerAddon.objects.filter(
                        organizer=self.request.organizer,
                        capability=self.addon.capability,
                        status=AddonStatus.ACTIVE,
                    ).exists():
                        messages.warning(
                            self.request,
                            _("This add-on is already active for your organisation."),
                        )
                        return redirect(
                            "plugins:eventyay_business:organizer.plan",
                            organizer=self.request.organizer.slug,
                        )

            form.save()

        messages.success(
            self.request,
            _("Add-on '%(name)s' has been successfully added to your plan.")
            % {"name": self.addon.name},
        )
        return redirect(
            "plugins:eventyay_business:organizer.plan",
            organizer=self.request.organizer.slug,
        )


class EventDashboardAddonsView(EventPermissionRequiredMixin, TemplateView):
    permission = "can_change_event_settings"
    template_name = "eventyay_business/event/addons.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        event = self.request.event
        current_time = now()

        active_addons = list(
            EventAddon.objects.filter(
                event=event,
                status=AddonStatus.ACTIVE,
                starts_at__lte=current_time,
            )
            .exclude(ends_at__lt=current_time)
            .order_by("-starts_at", "addon__name")
        )
        ctx["active_addons"] = active_addons

        available_addons = list(
            AddonDefinition.objects.filter(
                active=True,
                public=True,
                assignment_scope=AddonAssignmentScope.EVENT,
            ).order_by("name")
        )

        active_by_addon_id = {ea.addon_id: ea for ea in active_addons if ea.addon_id}
        active_by_capability = {
            ea.capability: ea for ea in active_addons if ea.capability
        }

        for addon in available_addons:
            active_assignment = active_by_addon_id.get(
                addon.id
            ) or active_by_capability.get(addon.capability)
            addon.active_assignment = active_assignment
            addon.is_active_for_event = active_assignment is not None

        ctx["available_addons"] = available_addons
        return ctx


class EventDashboardAddonPurchaseView(EventPermissionRequiredMixin, FormView):
    permission = "can_change_event_settings"
    template_name = "eventyay_business/event/addon_purchase.html"
    form_class = EventAddonPurchaseForm

    def get_addon(self):
        return get_object_or_404(
            AddonDefinition,
            pk=self.kwargs["pk"],
            active=True,
            public=True,
            assignment_scope=AddonAssignmentScope.EVENT,
        )

    def dispatch(self, request, *args, **kwargs):
        self.addon = self.get_addon()
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["event"] = self.request.event
        kwargs["addon"] = self.addon
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["addon"] = self.addon
        ctx["capability"] = get_capability(self.addon.capability)
        return ctx

    def form_valid(self, form):
        cap = get_capability(self.addon.capability)
        is_boolean = (cap and cap.value_type == CapabilityValueType.BOOLEAN) or (
            self.addon.entitlement_value
            and str(self.addon.entitlement_value).lower() in ("true", "1")
        )

        with transaction.atomic():
            Event.objects.select_for_update().get(pk=self.request.event.pk)
            if is_boolean:
                if EventAddon.objects.filter(
                    event=self.request.event,
                    capability=self.addon.capability,
                    status=AddonStatus.ACTIVE,
                ).exists():
                    messages.warning(
                        self.request,
                        _("This add-on is already active for %(event)s.")
                        % {"event": self.request.event.name},
                    )
                    return redirect(
                        "plugins:eventyay_business:event.addons",
                        organizer=self.request.organizer.slug,
                        event=self.request.event.slug,
                    )

            form.save()

        messages.success(
            self.request,
            _("Add-on '%(name)s' has been successfully activated for %(event)s.")
            % {"name": self.addon.name, "event": self.request.event.name},
        )
        return redirect(
            "plugins:eventyay_business:event.addons",
            organizer=self.request.organizer.slug,
            event=self.request.event.slug,
        )


class AddonDefinitionListView(AdministratorPermissionRequiredMixin, ListView):
    model = AddonDefinition
    template_name = "eventyay_business/addons/list.html"
    context_object_name = "addons"


class AddonDefinitionCreateView(AdministratorPermissionRequiredMixin, CreateView):
    model = AddonDefinition
    form_class = AddonDefinitionForm
    template_name = "eventyay_business/addons/form.html"

    def form_valid(self, form):
        self.object = form.save()
        messages.success(self.request, _("Add-on created successfully."))
        return redirect("plugins:eventyay_business:addons.list")


class AddonDefinitionUpdateView(AdministratorPermissionRequiredMixin, UpdateView):
    model = AddonDefinition
    form_class = AddonDefinitionForm
    template_name = "eventyay_business/addons/form.html"

    def form_valid(self, form):
        self.object = form.save()
        if form.cleaned_data.get("update_existing_assignments"):
            count = migrate_addon_assignments(self.object)
            messages.success(
                self.request,
                _(
                    "Add-on updated successfully and %(count)d existing active assignment(s) updated."
                )
                % {"count": count},
            )
        else:
            messages.success(self.request, _("Add-on updated successfully."))
        return redirect("plugins:eventyay_business:addons.list")


class AddonDefinitionToggleActiveView(AdministratorPermissionRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        addon = get_object_or_404(AddonDefinition, pk=pk)
        addon.active = not addon.active
        addon.save(update_fields=["active"])
        status_text = _("activated") if addon.active else _("deactivated")
        messages.success(
            request,
            _("Add-on %(name)s was %(status)s.")
            % {"name": addon.name, "status": status_text},
        )
        return redirect("plugins:eventyay_business:addons.list")


class OrganizerAddonListView(AdministratorPermissionRequiredMixin, ListView):
    model = OrganizerAddon
    template_name = "eventyay_business/addons/assignments/organizer_list.html"
    context_object_name = "assignments"

    def get_queryset(self):
        return OrganizerAddon.objects.select_related("organizer", "addon").order_by(
            "-starts_at", "-id"
        )


class OrganizerAddonCreateView(AdministratorPermissionRequiredMixin, CreateView):
    model = OrganizerAddon
    form_class = OrganizerAddonForm
    template_name = "eventyay_business/addons/assignments/form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["assignment_type"] = "organizer"
        return ctx

    def form_valid(self, form):
        self.object = form.save()
        messages.success(self.request, _("Organizer add-on assigned successfully."))
        return redirect("plugins:eventyay_business:addons.assignments.organizer.list")


class OrganizerAddonUpdateView(AdministratorPermissionRequiredMixin, UpdateView):
    model = OrganizerAddon
    form_class = OrganizerAddonForm
    template_name = "eventyay_business/addons/assignments/form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["assignment_type"] = "organizer"
        return ctx

    def form_valid(self, form):
        self.object = form.save()
        messages.success(self.request, _("Organizer add-on assignment updated."))
        return redirect("plugins:eventyay_business:addons.assignments.organizer.list")


class EventAddonListView(AdministratorPermissionRequiredMixin, ListView):
    model = EventAddon
    template_name = "eventyay_business/addons/assignments/event_list.html"
    context_object_name = "assignments"

    def get_queryset(self):
        return EventAddon.objects.select_related(
            "event", "event__organizer", "addon"
        ).order_by("-starts_at", "-id")


class EventAddonCreateView(AdministratorPermissionRequiredMixin, CreateView):
    model = EventAddon
    form_class = EventAddonForm
    template_name = "eventyay_business/addons/assignments/form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["assignment_type"] = "event"
        return ctx

    def form_valid(self, form):
        self.object = form.save()
        messages.success(self.request, _("Event add-on assigned successfully."))
        return redirect("plugins:eventyay_business:addons.assignments.event.list")


class EventAddonUpdateView(AdministratorPermissionRequiredMixin, UpdateView):
    model = EventAddon
    form_class = EventAddonForm
    template_name = "eventyay_business/addons/assignments/form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["assignment_type"] = "event"
        return ctx

    def form_valid(self, form):
        self.object = form.save()
        messages.success(self.request, _("Event add-on assignment updated."))
        return redirect("plugins:eventyay_business:addons.assignments.event.list")
