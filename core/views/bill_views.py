from decimal import Decimal

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from core.models import Bill, Tariff
from core.services.calculator import CalculationResult, TariffCalculationError, TariffCalculator
from core.views._helpers import bad_request, parse_json_body


@csrf_exempt
@require_http_methods(["POST"])
def calculate_view(request):
    """Calculate a bill against the active tariff. Optionally persist it."""
    payload = parse_json_body(request)
    if payload is None:
        return bad_request("Invalid JSON body.")

    unread_meter = bool(payload.get("unread_meter", False))
    consumption_raw = payload.get("consumption_kwh")
    no_reading = consumption_raw in (None, "")

    if no_reading and not unread_meter:
        return bad_request("'consumption_kwh' is required.")

    tariff = Tariff.get_active()
    if tariff is None:
        return bad_request("No tariff has been configured yet.", status=422)

    if no_reading:
        # No reading at all: the meter wasn't read, so there's no basis for
        # an energy charge or a slice-specific service fee. Bill ONLY the
        # flat unread-meter fee - nothing else.
        fee = Decimal(str(tariff.unread_meter_fee))
        result = CalculationResult(
            consumption=Decimal("0"),
            energy_charge=Decimal("0.00"),
            customer_service_fee=Decimal("0.00"),
            transition_deduction=Decimal("0.00"),
            other_fees=Decimal("0.00"),
            unread_meter_fee=fee,
            total=fee,
            details={
                "tariff": tariff.name,
                "tariff_version": tariff.version,
                "applied_slice_order": None,
                "applied_billing_mode": None,
                "energy_breakdown": [],
                "transition_breakdown": [],
                "fees_breakdown": [],
                "note": "No meter reading provided - billed the unread-meter fee only.",
            },
        )
    else:
        try:
            calculator = TariffCalculator(tariff)
            result = calculator.calculate(
                consumption=consumption_raw,
                unread_meter=unread_meter,
                additional_fees=[f for f in tariff.fees.filter(is_active=True).values(
                    "name", "fee_type", "amount"
                )] if payload.get("include_active_fees", True) else None,
            )
        except TariffCalculationError as exc:
            return bad_request(str(exc), status=422)
        except (ValueError, TypeError) as exc:
            return bad_request(str(exc))

    response = result.to_dict()

    if payload.get("save", False):
        raw_billing_month = payload.get("billing_month")
        if not raw_billing_month:
            return bad_request("'billing_month' is required when 'save' is true.")
        billing_month = parse_date(raw_billing_month)
        if billing_month is None:
            return bad_request("'billing_month' must be a valid date (YYYY-MM-DD).")
        bill = Bill.objects.create(
            billing_month=billing_month,
            consumption_kwh=result.consumption,
            tariff=tariff,
            energy_charge=result.energy_charge,
            customer_service_fee=result.customer_service_fee,
            transition_deduction=result.transition_deduction,
            other_fees=result.other_fees,
            unread_meter_fee=result.unread_meter_fee,
            total=result.total,
            calculation_details=result.details,
        )
        response["bill"] = bill.to_dict()

    return JsonResponse(response)


@csrf_exempt
@require_http_methods(["GET"])
def bill_list_view(request):
    bills = Bill.objects.all()[:100]
    return JsonResponse({"bills": [b.to_dict() for b in bills]})


@csrf_exempt
@require_http_methods(["GET", "DELETE"])
def bill_detail_view(request, bill_id):
    bill = get_object_or_404(Bill, pk=bill_id)
    if request.method == "DELETE":
        bill.delete()
        return JsonResponse({"deleted": True})
    return JsonResponse(bill.to_dict())
