from decimal import Decimal

from django.test import TestCase

from core.models import Tariff, TariffSlice, TransitionRule
from core.services.calculator import TariffCalculationError, TariffCalculator


def make_seeded_tariff(service_fee_mode=Tariff.SERVICE_FEE_CURRENT_SLICE):
    """Mirrors seed_tariff: slices 1-6 progressive, slice 7 flat on total consumption -
    the verified real structure (Ministry of Electricity / EgyptERA reporting)."""
    tariff = Tariff.objects.create(name="Test Tariff", unread_meter_fee=Decimal("30.00"),
                                    service_fee_mode=service_fee_mode)
    data = [
        (1, "0", "50", "68", "3", TariffSlice.MODE_MARGINAL),
        (2, "50.01", "100", "98", "6", TariffSlice.MODE_MARGINAL),
        (3, "100.01", "200", "115", "12", TariffSlice.MODE_MARGINAL),
        (4, "200.01", "350", "173", "20", TariffSlice.MODE_MARGINAL),
        (5, "350.01", "650", "214", "50", TariffSlice.MODE_MARGINAL),
        (6, "650.01", "1000", "251", "60", TariffSlice.MODE_MARGINAL),
        (7, "1000.01", None, "274", "100", TariffSlice.MODE_FLAT_FULL),
    ]
    slices = {}
    for order, mn, mx, rate, fee, mode in data:
        slices[order] = TariffSlice.objects.create(
            tariff=tariff, order=order, min_kwh=Decimal(mn),
            max_kwh=Decimal(mx) if mx else None,
            rate_piastres=Decimal(rate), customer_service_fee=Decimal(fee),
            billing_mode=mode,
        )
    return tariff, slices


class ServiceFeeModeTests(TestCase):
    """Postpaid bills show one fee for the slice reached; prepaid ('abu كارت')
    meters deduct a fee at every slice crossing, so those accumulate."""

    def test_current_slice_only_is_the_default(self):
        tariff, _ = make_seeded_tariff()  # default mode
        result = TariffCalculator(tariff).calculate(500)
        # 500 kWh lands in slice 5 - only slice 5's fee (50) applies.
        self.assertEqual(result.customer_service_fee, Decimal("50.00"))

    def test_cumulative_mode_sums_every_slice_up_to_current(self):
        tariff, _ = make_seeded_tariff(service_fee_mode=Tariff.SERVICE_FEE_CUMULATIVE)
        result = TariffCalculator(tariff).calculate(500)
        # 500 kWh lands in slice 5: 3 + 6 + 12 + 20 + 50 = 91.
        self.assertEqual(result.customer_service_fee, Decimal("91.00"))
        self.assertEqual(len(result.details["service_fee_breakdown"]), 5)

    def test_cumulative_mode_slice_1_only_charges_slice_1(self):
        tariff, _ = make_seeded_tariff(service_fee_mode=Tariff.SERVICE_FEE_CUMULATIVE)
        result = TariffCalculator(tariff).calculate(30)
        self.assertEqual(result.customer_service_fee, Decimal("3.00"))

    def test_cumulative_mode_slice_7_sums_all_seven(self):
        tariff, _ = make_seeded_tariff(service_fee_mode=Tariff.SERVICE_FEE_CUMULATIVE)
        result = TariffCalculator(tariff).calculate(1200)
        # 3 + 6 + 12 + 20 + 50 + 60 + 100 = 251
        self.assertEqual(result.customer_service_fee, Decimal("251.00"))


class MarginalCalculationTests(TestCase):
    """Slices 1-6: progressive, tax-bracket-style billing."""

    def setUp(self):
        self.tariff, self.slices = make_seeded_tariff()

    def test_50_kwh(self):
        result = TariffCalculator(self.tariff).calculate(50)
        self.assertEqual(result.energy_charge, Decimal("34.00"))
        self.assertEqual(result.customer_service_fee, Decimal("3.00"))
        self.assertEqual(result.total, Decimal("37.00"))

    def test_100_kwh(self):
        result = TariffCalculator(self.tariff).calculate(100)
        # 50*0.68 + 50*0.98 = 34 + 49 = 83
        self.assertEqual(result.energy_charge, Decimal("83.00"))

    def test_200_kwh_is_marginal_not_flat(self):
        result = TariffCalculator(self.tariff).calculate(200)
        # 34 + 49 + 100*1.15 = 34 + 49 + 115 = 198. NOT 230 (a flat-rate
        # read of "230" appears in some press coverage but doesn't match
        # the verified progressive-through-slice-6 rule).
        self.assertEqual(result.energy_charge, Decimal("198.00"))
        self.assertEqual(result.details["applied_billing_mode"], "marginal")

    def test_zero_consumption(self):
        result = TariffCalculator(self.tariff).calculate(0)
        self.assertEqual(result.energy_charge, Decimal("0.00"))
        self.assertEqual(result.customer_service_fee, Decimal("3.00"))

    def test_negative_consumption_rejected(self):
        with self.assertRaises(TariffCalculationError):
            TariffCalculator(self.tariff).calculate(-5)

    def test_unread_meter_fee_applied(self):
        result = TariffCalculator(self.tariff).calculate(50, unread_meter=True)
        self.assertEqual(result.unread_meter_fee, Decimal("30.00"))
        self.assertEqual(result.total, Decimal("67.00"))


class FlatFullSliceTests(TestCase):
    """Slice 7 only: flat rate on the ENTIRE consumption, not just the portion above 1000."""

    def setUp(self):
        self.tariff, self.slices = make_seeded_tariff()

    def test_just_above_threshold_is_flat_on_whole_amount(self):
        result = TariffCalculator(self.tariff).calculate(1001)
        # Flat: 1001 * 2.74 = 2742.74, NOT marginal-through-1000 + 1kWh at slice 7 rate.
        self.assertEqual(result.energy_charge, Decimal("2742.74"))
        self.assertEqual(result.details["applied_billing_mode"], "flat_full")

    def test_large_consumption_stays_flat(self):
        result = TariffCalculator(self.tariff).calculate(2000)
        self.assertEqual(result.energy_charge, Decimal("5480.00"))
        self.assertEqual(result.details["applied_slice_order"], 7)

    def test_1000_exactly_still_marginal_slice_6(self):
        # 1000 kWh is the top of slice 6 (marginal), not yet slice 7.
        result = TariffCalculator(self.tariff).calculate(1000)
        self.assertEqual(result.details["applied_slice_order"], 6)
        self.assertEqual(result.details["applied_billing_mode"], "marginal")


class TransitionRuleTests(TestCase):
    def setUp(self):
        self.tariff, self.slices = make_seeded_tariff()

    def test_transition_deduction_applies_only_when_active_and_matching_slice(self):
        TransitionRule.objects.create(
            tariff=self.tariff, order=2, triggering_slice=self.slices[2],
            deduction_amount=Decimal("49.00"), is_active=True, note="abu kart",
        )
        result = TariffCalculator(self.tariff).calculate(80)
        self.assertEqual(result.transition_deduction, Decimal("49.00"))

        result_slice1 = TariffCalculator(self.tariff).calculate(30)
        self.assertEqual(result_slice1.transition_deduction, Decimal("0.00"))

    def test_inactive_rule_ignored(self):
        TransitionRule.objects.create(
            tariff=self.tariff, order=2, triggering_slice=self.slices[2],
            deduction_amount=Decimal("49.00"), is_active=False,
        )
        result = TariffCalculator(self.tariff).calculate(80)
        self.assertEqual(result.transition_deduction, Decimal("0.00"))


class ConfigurabilityTests(TestCase):
    """Slices, boundaries, count, and billing mode can be reshaped via the model
    layer, exactly as the UI would do it, and the engine must follow."""

    def test_reducing_slice_count_works(self):
        tariff = Tariff.objects.create(name="Two Slice Tariff")
        TariffSlice.objects.create(tariff=tariff, order=1, min_kwh=Decimal("0"),
                                    max_kwh=Decimal("100"), rate_piastres=Decimal("50"),
                                    customer_service_fee=Decimal("5"))
        TariffSlice.objects.create(tariff=tariff, order=2, min_kwh=Decimal("100.01"),
                                    max_kwh=None, rate_piastres=Decimal("80"),
                                    customer_service_fee=Decimal("15"))
        result = TariffCalculator(tariff).calculate(150)
        self.assertEqual(result.energy_charge, Decimal("90.00"))
        self.assertEqual(result.customer_service_fee, Decimal("15.00"))

    def test_resizing_last_open_ended_slice_cutoff(self):
        tariff = Tariff.objects.create(name="Resize Tariff")
        TariffSlice.objects.create(tariff=tariff, order=1, min_kwh=Decimal("0"),
                                    max_kwh=Decimal("500"), rate_piastres=Decimal("60"),
                                    customer_service_fee=Decimal("5"))
        TariffSlice.objects.create(tariff=tariff, order=2, min_kwh=Decimal("500.01"),
                                    max_kwh=None, rate_piastres=Decimal("120"),
                                    customer_service_fee=Decimal("25"))
        result = TariffCalculator(tariff).calculate(500)
        self.assertEqual(result.details["applied_slice_order"], 1)
        result2 = TariffCalculator(tariff).calculate(500.01)
        self.assertEqual(result2.details["applied_slice_order"], 2)

    def test_gap_between_slices_is_rejected(self):
        tariff = Tariff.objects.create(name="Bad Tariff")
        TariffSlice.objects.create(tariff=tariff, order=1, min_kwh=Decimal("0"),
                                    max_kwh=Decimal("50"), rate_piastres=Decimal("60"),
                                    customer_service_fee=Decimal("3"))
        TariffSlice.objects.create(tariff=tariff, order=2, min_kwh=Decimal("60"),
                                    max_kwh=None, rate_piastres=Decimal("90"),
                                    customer_service_fee=Decimal("6"))
        with self.assertRaises(TariffCalculationError):
            TariffCalculator(tariff)

    def test_non_final_slice_must_have_max(self):
        tariff = Tariff.objects.create(name="Bad Tariff 2")
        TariffSlice.objects.create(tariff=tariff, order=1, min_kwh=Decimal("0"),
                                    max_kwh=None, rate_piastres=Decimal("60"),
                                    customer_service_fee=Decimal("3"))
        TariffSlice.objects.create(tariff=tariff, order=2, min_kwh=Decimal("50.01"),
                                    max_kwh=None, rate_piastres=Decimal("90"),
                                    customer_service_fee=Decimal("6"))
        with self.assertRaises(TariffCalculationError):
            TariffCalculator(tariff)

    def test_billing_mode_can_be_set_on_any_slice(self):
        """The flat-vs-marginal choice is data, not hardcoded to slice 7."""
        tariff = Tariff.objects.create(name="Custom Mode Tariff")
        TariffSlice.objects.create(tariff=tariff, order=1, min_kwh=Decimal("0"),
                                    max_kwh=Decimal("100"), rate_piastres=Decimal("50"),
                                    customer_service_fee=Decimal("5"),
                                    billing_mode=TariffSlice.MODE_FLAT_FULL)
        TariffSlice.objects.create(tariff=tariff, order=2, min_kwh=Decimal("100.01"),
                                    max_kwh=None, rate_piastres=Decimal("80"),
                                    customer_service_fee=Decimal("15"))
        result = TariffCalculator(tariff).calculate(80)
        # Flat mode on slice 1: 80 * 0.50 = 40.00, not a marginal partial.
        self.assertEqual(result.energy_charge, Decimal("40.00"))
