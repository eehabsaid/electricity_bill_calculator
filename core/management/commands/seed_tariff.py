"""Seed a default tariff using Egypt's post-increase (August 2026) residential rates.

This is just starting data - every number here (slice count, boundaries,
rates, fees, billing mode, transition deductions) is editable afterwards
from the UI. Run with: python manage.py seed_tariff [--reset]

Billing mode is set per the verified real structure: slices 1-6 are
progressive (marginal), slice 7 (>1000 kWh) is a flat rate applied to the
entire consumption once reached - confirmed by Ministry of Electricity /
EgyptERA reporting, not a hardcoded assumption baked into the calculator.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Fee, Tariff, TariffSlice, TransitionRule

# (order, min_kwh, max_kwh, rate_piastres, customer_service_fee, billing_mode)
SLICES = [
    (1, "0", "50", "68", "3", TariffSlice.MODE_MARGINAL),
    (2, "50.01", "100", "98", "6", TariffSlice.MODE_MARGINAL),
    (3, "100.01", "200", "115", "12", TariffSlice.MODE_MARGINAL),
    (4, "200.01", "350", "173", "20", TariffSlice.MODE_MARGINAL),
    (5, "350.01", "650", "214", "50", TariffSlice.MODE_MARGINAL),
    (6, "650.01", "1000", "251", "60", TariffSlice.MODE_MARGINAL),
    (7, "1000.01", None, "274", "100", TariffSlice.MODE_FLAT_FULL),
]

# (triggering_slice_order, deduction_amount, note) - the "abu كارت" prepaid
# transition surcharges. Inactive by default since they only apply to
# prepaid-meter billing, not the standard postpaid marginal calculation.
TRANSITION_RULES = [
    (2, "49.00", "Prepaid abu-kart deduction entering slice 2"),
    (3, "147.00", "Prepaid abu-kart deduction entering slice 3"),
    (4, "173.00", "Prepaid abu-kart deduction entering slice 4"),
    (5, "194.00", "Prepaid abu-kart deduction entering slice 5"),
    (6, "251.50", "Prepaid abu-kart deduction entering slice 6"),
    (7, "328.00", "Prepaid abu-kart deduction entering slice 7"),
]


class Command(BaseCommand):
    help = "Seed a default residential electricity tariff."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing tariffs first.")

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            Tariff.objects.all().delete()
            self.stdout.write("Cleared existing tariffs.")

        if Tariff.objects.exists():
            self.stdout.write(self.style.WARNING("A tariff already exists. Use --reset to replace it."))
            return

        tariff = Tariff.objects.create(
            name="Egyptian Residential Tariff",
            version="2026-post-increase",
            description=(
                "Seeded from published August 2026 residential rates. Slices 1-6 are "
                "progressive; slice 7 is flat on total consumption once reached, per "
                "Ministry of Electricity / EgyptERA reporting. Service fee mode set to "
                "cumulative to match prepaid ('abu كارت') meter behavior. Fully editable."
            ),
            is_active=True,
            service_fee_mode=Tariff.SERVICE_FEE_CUMULATIVE,
            unread_meter_fee=Decimal("30.00"),
        )

        slices_by_order = {}
        for order, min_kwh, max_kwh, rate, fee, billing_mode in SLICES:
            slices_by_order[order] = TariffSlice.objects.create(
                tariff=tariff,
                order=order,
                label=f"Slice {order}",
                min_kwh=Decimal(min_kwh),
                max_kwh=Decimal(max_kwh) if max_kwh else None,
                rate_piastres=Decimal(rate),
                customer_service_fee=Decimal(fee),
                billing_mode=billing_mode,
            )

        for order, amount, note in TRANSITION_RULES:
            TransitionRule.objects.create(
                tariff=tariff,
                order=order,
                triggering_slice=slices_by_order[order],
                deduction_amount=Decimal(amount),
                is_active=False,
                note=note,
            )

        self.stdout.write(self.style.SUCCESS(
            f"Seeded '{tariff.name}' with {len(SLICES)} slices and {len(TRANSITION_RULES)} transition rules."
        ))
