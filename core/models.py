"""Database models for the electricity bill calculator.

No user accounts: the app has a single, shared tariff configuration that
anyone using it can edit through the UI. Everything about the tariff -
how many slices there are, their boundaries, their rates, their customer
service fees, and the "progressive consumption" transition surcharges
that appear when a reading crosses into a new slice - is data, not code.
"""
from datetime import datetime
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


class Tariff(models.Model):
    """A named, versioned set of pricing rules. Exactly one is ever active."""

    name = models.CharField(max_length=100, default="Egyptian Residential Tariff")
    version = models.CharField(max_length=50, default="1.0")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    unread_meter_fee = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Flat fee charged when the meter could not be read this cycle.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.name} v{self.version}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_active:
            Tariff.objects.exclude(pk=self.pk).update(is_active=False)

    @classmethod
    def get_active(cls):
        tariff = cls.objects.filter(is_active=True).order_by("-updated_at").first()
        if tariff is None:
            tariff = cls.objects.order_by("-updated_at").first()
        return tariff

    def to_dict(self):
        return {
            "id": self.pk,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "is_active": self.is_active,
            "unread_meter_fee": str(self.unread_meter_fee),
            "slices": [s.to_dict() for s in self.slices.order_by("order")],
            "transition_rules": [r.to_dict() for r in self.transition_rules.order_by("order")],
            "fees": [f.to_dict() for f in self.fees.filter(is_active=True).order_by("name")],
            "updated_at": self.updated_at.isoformat(),
        }


class TariffSlice(models.Model):
    """One consumption slice (a.k.a. tier/bracket).

    Slices are fully editable: the end user can add, remove, reorder, and
    resize them from the UI. `order` is the only thing that defines slice
    sequence - there is no assumption of exactly N slices anywhere.
    `max_kwh = null` marks the open-ended final slice ("more than X").

    `billing_mode` is per-slice because Egypt's real tariff mixes both
    behaviours in the same ladder: slices 1-6 are billed progressively
    (each slice's own kWh at its own rate, like a tax bracket), while
    slice 7 (>1000 kWh) is billed as a flat rate on the ENTIRE
    consumption once it's reached - confirmed by the Electricity
    Ministry / EgyptERA reporting, not just the slice's own portion.
    Which slices behave which way is data, not a hardcoded assumption.
    """

    MODE_MARGINAL = "marginal"
    MODE_FLAT_FULL = "flat_full"
    BILLING_MODE_CHOICES = [
        (MODE_MARGINAL, "Progressive - only this slice's own kWh at its own rate"),
        (MODE_FLAT_FULL, "Flat - entire consumption billed at this slice's rate once reached"),
    ]

    tariff = models.ForeignKey(Tariff, on_delete=models.CASCADE, related_name="slices")
    order = models.PositiveIntegerField(help_text="1-based position of this slice in the ladder.")
    label = models.CharField(max_length=100, blank=True)
    min_kwh = models.DecimalField(max_digits=12, decimal_places=2,
                                   validators=[MinValueValidator(Decimal("0.00"))])
    max_kwh = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                   validators=[MinValueValidator(Decimal("0.00"))],
                                   help_text="Leave blank for the open-ended last slice.")
    rate_piastres = models.DecimalField(max_digits=10, decimal_places=2,
                                         validators=[MinValueValidator(Decimal("0.00"))],
                                         help_text="Price per kWh, in piastres (100 pt = 1 EGP).")
    customer_service_fee = models.DecimalField(max_digits=12, decimal_places=2,
                                                validators=[MinValueValidator(Decimal("0.00"))],
                                                help_text="EGP service fee that applies once this slice is reached.")
    billing_mode = models.CharField(max_length=20, choices=BILLING_MODE_CHOICES, default=MODE_MARGINAL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["tariff", "order"], name="unique_slice_order_per_tariff"),
        ]

    def __str__(self):
        return f"Slice {self.order} ({self.min_kwh}-{self.max_kwh or '∞'} kWh)"

    @property
    def rate_egp(self) -> Decimal:
        return (self.rate_piastres / Decimal("100")).quantize(Decimal("0.0001"))

    def to_dict(self):
        return {
            "id": self.pk,
            "order": self.order,
            "label": self.label,
            "min_kwh": str(self.min_kwh),
            "max_kwh": str(self.max_kwh) if self.max_kwh is not None else None,
            "rate_piastres": str(self.rate_piastres),
            "customer_service_fee": str(self.customer_service_fee),
            "billing_mode": self.billing_mode,
        }


class TransitionRule(models.Model):
    """A "progressive consumption" surcharge triggered by crossing into a slice.

    This models the abu-kart / prepaid-meter behaviour from the article: the
    first time a reading enters a new slice, an extra deduction is taken on
    top of that slice's own service fee. Which slice triggers it, and how
    much it deducts, is fully configurable and independent of slice count.
    """

    tariff = models.ForeignKey(Tariff, on_delete=models.CASCADE, related_name="transition_rules")
    order = models.PositiveIntegerField(default=0)
    triggering_slice = models.ForeignKey(TariffSlice, on_delete=models.CASCADE, related_name="transition_rules")
    deduction_amount = models.DecimalField(max_digits=12, decimal_places=2,
                                            validators=[MinValueValidator(Decimal("0.00"))],
                                            help_text="EGP deducted the moment consumption enters this slice.")
    is_active = models.BooleanField(default=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"Transition into slice {self.triggering_slice.order}: -{self.deduction_amount} EGP"

    def to_dict(self):
        return {
            "id": self.pk,
            "order": self.order,
            "triggering_slice_id": self.triggering_slice_id,
            "triggering_slice_order": self.triggering_slice.order,
            "deduction_amount": str(self.deduction_amount),
            "is_active": self.is_active,
            "note": self.note,
        }


class Fee(models.Model):
    """An optional extra charge (fixed, percentage of energy charge, or per kWh)."""

    FEE_TYPE_CHOICES = [
        ("fixed", "Fixed amount"),
        ("percentage", "Percentage of energy charge"),
        ("per_kwh", "Per kWh"),
    ]

    tariff = models.ForeignKey(Tariff, on_delete=models.CASCADE, related_name="fees")
    name = models.CharField(max_length=100)
    fee_type = models.CharField(max_length=20, choices=FEE_TYPE_CHOICES, default="fixed")
    amount = models.DecimalField(max_digits=12, decimal_places=4,
                                  validators=[MinValueValidator(Decimal("0.0000"))])
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def to_dict(self):
        return {
            "id": self.pk,
            "name": self.name,
            "fee_type": self.fee_type,
            "amount": str(self.amount),
            "description": self.description,
            "is_active": self.is_active,
        }


class Bill(models.Model):
    """A saved calculation, kept for the user's own reference (no account needed)."""

    billing_month = models.DateField()
    consumption_kwh = models.DecimalField(max_digits=12, decimal_places=2,
                                           validators=[MinValueValidator(Decimal("0.00"))])
    tariff = models.ForeignKey(Tariff, on_delete=models.PROTECT, related_name="bills")
    energy_charge = models.DecimalField(max_digits=12, decimal_places=2)
    customer_service_fee = models.DecimalField(max_digits=12, decimal_places=2)
    transition_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    other_fees = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    unread_meter_fee = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=12, decimal_places=2)
    calculation_details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-billing_month", "-created_at"]

    def __str__(self):
        return f"Bill {self.billing_month} - {self.consumption_kwh} kWh - {self.total} EGP"

    def to_dict(self):
        return {
            "id": self.pk,
            "billing_month": self.billing_month.isoformat(),
            "consumption_kwh": str(self.consumption_kwh),
            "energy_charge": str(self.energy_charge),
            "customer_service_fee": str(self.customer_service_fee),
            "transition_deduction": str(self.transition_deduction),
            "other_fees": str(self.other_fees),
            "unread_meter_fee": str(self.unread_meter_fee),
            "total": str(self.total),
            "calculation_details": self.calculation_details,
            "created_at": self.created_at.isoformat(),
        }
