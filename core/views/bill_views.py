from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from core.models import Bill, Tariff
from core.services.calculator import TariffCalculationError, TariffCalculator
from core.views._helpers import bad_request, parse_json_body


@csrf_exempt
@require_http_methods(["POST"])
def calculate_view(request):
    """Calculate a bill against the active tariff. Optionally persist it."""
    payload = parse_json_body(request)
    if payload is None:
        return bad_request("Invalid JSON body.")

    if "consumption_kwh" not in payload:
        return bad_request("'consumption_kwh' is required.")

    tariff = Tariff.get_active()
    if tariff is None:
        return bad_request("No tariff has been configured yet.", status=422)

    try:
        calculator = TariffCalculator(tariff)
        result = calculator.calculate(
            consumption=payload["consumption_kwh"],
            unread_meter=bool(payload.get("unread_meter", False)),
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
