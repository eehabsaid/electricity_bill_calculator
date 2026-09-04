"""Slice-count-agnostic electricity bill calculation engine.

Nothing here assumes a fixed number of slices or fixed boundaries - those
live in TariffSlice rows the end user edits through the UI.

Billing mode is per-slice, not per-tariff, because Egypt's real
residential tariff mixes two behaviours in the same ladder: slices 1-6
are billed progressively (each slice's own kWh at its own rate, like a
tax bracket), while slice 7 (>1000 kWh) is billed as a flat rate on the
ENTIRE consumption once reached - confirmed by Ministry of Electricity /
EgyptERA reporting, not an assumption baked into this code. Which slices
behave which way is fully editable per tariff.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional

from core.models import Tariff, TariffSlice

CENT = Decimal("0.01")


class TariffCalculationError(Exception):
    pass


def _q(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


class CalculationResult:
    def __init__(self, consumption, energy_charge, customer_service_fee,
                 transition_deduction, other_fees, unread_meter_fee, total, details):
        self.consumption = consumption
        self.energy_charge = energy_charge
        self.customer_service_fee = customer_service_fee
        self.transition_deduction = transition_deduction
        self.other_fees = other_fees
        self.unread_meter_fee = unread_meter_fee
        self.total = total
        self.details = details

    def to_dict(self) -> Dict:
        return {
            "consumption_kwh": str(self.consumption),
            "energy_charge": str(self.energy_charge),
            "customer_service_fee": str(self.customer_service_fee),
            "transition_deduction": str(self.transition_deduction),
            "other_fees": str(self.other_fees),
            "unread_meter_fee": str(self.unread_meter_fee),
            "total": str(self.total),
            "details": self.details,
        }


class TariffCalculator:
    """Calculates a bill against whatever slice ladder is currently configured."""

    def __init__(self, tariff: Tariff):
        self.tariff = tariff
        self.slices: List[dict] = list(
            tariff.slices.all().order_by("order").values(
                "id", "order", "min_kwh", "max_kwh", "rate_piastres",
                "customer_service_fee", "billing_mode",
            )
        )
        self.transition_rules: List[dict] = list(
            tariff.transition_rules.filter(is_active=True).order_by("order").values(
                "id", "triggering_slice_id", "deduction_amount", "note"
            )
        )
        if not self.slices:
            raise TariffCalculationError("This tariff has no configured slices yet.")
        self._validate_ladder()

    def _validate_ladder(self):
        """Make sure slices, whatever their count, form a contiguous 0..∞ ladder."""
        expected_start = Decimal("0")
        for i, s in enumerate(self.slices):
            minimum = Decimal(str(s["min_kwh"]))
            if minimum != expected_start:
                raise TariffCalculationError(
                    f"Slice {i + 1} starts at {minimum} kWh but is expected to start at "
                    f"{expected_start} kWh (slices must be contiguous, no gaps or overlaps)."
                )
            maximum = s["max_kwh"]
            if maximum is None:
                if i != len(self.slices) - 1:
                    raise TariffCalculationError(f"Slice {i + 1} is open-ended but is not the last slice.")
            else:
                maximum = Decimal(str(maximum))
                if maximum < minimum:
                    raise TariffCalculationError(f"Slice {i + 1} has max_kwh below its min_kwh.")
                expected_start = maximum + Decimal("0.01")
        if self.slices[-1]["max_kwh"] is not None:
            raise TariffCalculationError("The last configured slice must be open-ended (no max_kwh).")

    def _find_slice(self, consumption: Decimal) -> dict:
        for s in self.slices:
            minimum = Decimal(str(s["min_kwh"]))
            maximum = s["max_kwh"]
            if consumption >= minimum and (maximum is None or consumption <= Decimal(str(maximum))):
                return s
        raise TariffCalculationError(f"No configured slice covers {consumption} kWh.")

    def _slice_width_consumed(self, s: dict, consumption: Decimal) -> Decimal:
        """How many of the kWh in `consumption` fall inside this slice's own band."""
        minimum = Decimal(str(s["min_kwh"]))
        maximum = s["max_kwh"]
        if consumption < minimum:
            return Decimal("0")
        upper = consumption if maximum is None else min(consumption, Decimal(str(maximum)))
        if upper < minimum:
            return Decimal("0")
        width = upper - minimum
        if minimum > 0:
            width += Decimal("0.01")
        return max(Decimal("0"), width)

    def _energy_charge(self, consumption: Decimal, current_slice: dict):
        """Sum marginal charges slice-by-slice, UNLESS the reached slice is
        flagged flat_full - in which case the whole consumption is billed
        at that one slice's rate instead."""
        if current_slice["billing_mode"] == TariffSlice.MODE_FLAT_FULL:
            rate = Decimal(str(current_slice["rate_piastres"])) / Decimal("100")
            charge = _q(consumption * rate)
            breakdown = [{
                "slice_order": current_slice["order"], "kwh": str(consumption),
                "rate_egp": str(rate.quantize(Decimal("0.0001"))), "charge": str(charge),
                "note": "Flat rate on entire consumption (this slice's billing mode).",
            }]
            return charge, breakdown

        charge = Decimal("0")
        breakdown = []
        for s in self.slices:
            kwh = self._slice_width_consumed(s, consumption)
            if kwh <= 0:
                continue
            rate = Decimal(str(s["rate_piastres"])) / Decimal("100")
            line = _q(kwh * rate)
            charge += line
            breakdown.append({"slice_order": s["order"], "kwh": str(kwh),
                               "rate_egp": str(rate.quantize(Decimal("0.0001"))), "charge": str(line)})
            if s["order"] == current_slice["order"]:
                break
        return _q(charge), breakdown

    def _transition_deduction(self, current_slice: dict):
        applied, total = [], Decimal("0")
        for rule in self.transition_rules:
            if rule["triggering_slice_id"] == current_slice["id"]:
                amount = Decimal(str(rule["deduction_amount"]))
                total += amount
                applied.append({"note": rule["note"], "deduction_amount": str(amount)})
        return _q(total), applied

    def _service_fee(self, current_slice: dict):
        """Postpaid bills typically show one fee for the slice reached.
        Prepaid ('abu كارت') meters deduct a fee at EVERY slice crossing in
        real time as the balance depletes, so those fees accumulate across
        every slice from 1 up to and including the current one. Which
        applies is a per-tariff setting (service_fee_mode), not hardcoded."""
        if self.tariff.service_fee_mode == Tariff.SERVICE_FEE_CUMULATIVE:
            breakdown = []
            total = Decimal("0")
            for s in self.slices:
                if s["order"] > current_slice["order"]:
                    break
                fee = Decimal(str(s["customer_service_fee"]))
                total += fee
                breakdown.append({"slice_order": s["order"], "fee": str(_q(fee))})
            return _q(total), breakdown

        fee = _q(Decimal(str(current_slice["customer_service_fee"])))
        return fee, [{"slice_order": current_slice["order"], "fee": str(fee)}]

    def calculate(self, consumption, unread_meter: bool = False,
                  additional_fees: Optional[List[dict]] = None) -> CalculationResult:
        consumption = Decimal(str(consumption))
        if consumption < 0:
            raise TariffCalculationError("Consumption cannot be negative.")

        current_slice = self._find_slice(consumption)
        energy_charge, energy_breakdown = self._energy_charge(consumption, current_slice)
        service_fee, service_fee_breakdown = self._service_fee(current_slice)
        transition_deduction, transition_breakdown = self._transition_deduction(current_slice)

        other_fees = Decimal("0")
        fee_breakdown = []
        for fee in additional_fees or []:
            amount = Decimal(str(fee.get("amount", "0")))
            fee_type = fee.get("fee_type", "fixed")
            if fee_type == "percentage":
                amount = _q(energy_charge * amount / Decimal("100"))
            elif fee_type == "per_kwh":
                amount = _q(consumption * amount)
            else:
                amount = _q(amount)
            other_fees += amount
            fee_breakdown.append({"name": fee.get("name", "Fee"), "fee_type": fee_type, "amount": str(amount)})

        unread_fee = _q(Decimal(str(self.tariff.unread_meter_fee))) if unread_meter else Decimal("0.00")
        total = _q(energy_charge + service_fee + transition_deduction + other_fees + unread_fee)

        details = {
            "tariff": self.tariff.name,
            "tariff_version": self.tariff.version,
            "applied_slice_order": current_slice["order"],
            "applied_billing_mode": current_slice["billing_mode"],
            "service_fee_mode": self.tariff.service_fee_mode,
            "energy_breakdown": energy_breakdown,
            "service_fee_breakdown": service_fee_breakdown,
            "transition_breakdown": transition_breakdown,
            "fees_breakdown": fee_breakdown,
        }
        return CalculationResult(
            consumption=consumption, energy_charge=energy_charge, customer_service_fee=service_fee,
            transition_deduction=transition_deduction, other_fees=other_fees, unread_meter_fee=unread_fee,
            total=total, details=details,
        )
