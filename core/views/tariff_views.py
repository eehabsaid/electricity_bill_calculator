"""Views for viewing/editing the shared tariff configuration.

Everything here is intentionally open (no login) per the app's scope: a
single household tool, not a multi-tenant product. There is one active
Tariff; slices, transition rules, and fees hang off it and are edited
freely through these endpoints from the settings screen in the UI.
"""
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from core.models import Fee, Tariff, TariffSlice, TransitionRule
from core.views._helpers import bad_request, not_found, parse_json_body


def _get_active_tariff():
    tariff = Tariff.get_active()
    if tariff is None:
        tariff = Tariff.objects.create(name="Egyptian Residential Tariff", version="1.0")
    return tariff


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH"])
def tariff_detail_view(request):
    tariff = _get_active_tariff()

    if request.method == "GET":
        return JsonResponse(tariff.to_dict())

    payload = parse_json_body(request)
    if payload is None:
        return bad_request("Invalid JSON body.")

    for field in ("name", "version", "description"):
        if field in payload:
            setattr(tariff, field, payload[field])
    if "unread_meter_fee" in payload:
        try:
            tariff.unread_meter_fee = payload["unread_meter_fee"]
        except (TypeError, ValueError):
            return bad_request("'unread_meter_fee' must be a number.")

    tariff.save()
    return JsonResponse(tariff.to_dict())


@csrf_exempt
@require_http_methods(["GET", "POST"])
def slice_list_view(request):
    tariff = _get_active_tariff()

    if request.method == "GET":
        return JsonResponse({"slices": [s.to_dict() for s in tariff.slices.order_by("order")]})

    payload = parse_json_body(request)
    if payload is None:
        return bad_request("Invalid JSON body.")

    required = ("order", "min_kwh", "rate_piastres", "customer_service_fee")
    missing = [f for f in required if f not in payload]
    if missing:
        return bad_request(f"Missing required field(s): {', '.join(missing)}")

    try:
        slice_ = TariffSlice.objects.create(
            tariff=tariff,
            order=payload["order"],
            label=payload.get("label", ""),
            min_kwh=payload["min_kwh"],
            max_kwh=payload.get("max_kwh"),
            rate_piastres=payload["rate_piastres"],
            customer_service_fee=payload["customer_service_fee"],
            billing_mode=payload.get("billing_mode", TariffSlice.MODE_MARGINAL),
        )
    except Exception as exc:  # noqa: BLE001 - surface validation/integrity errors to the UI
        return bad_request(str(exc))

    return JsonResponse(slice_.to_dict(), status=201)


@csrf_exempt
@require_http_methods(["PUT", "PATCH", "DELETE"])
def slice_detail_view(request, slice_id):
    tariff = _get_active_tariff()
    slice_ = get_object_or_404(TariffSlice, pk=slice_id, tariff=tariff)

    if request.method == "DELETE":
        slice_.delete()
        return JsonResponse({"deleted": True})

    payload = parse_json_body(request)
    if payload is None:
        return bad_request("Invalid JSON body.")

    for field in ("order", "label", "min_kwh", "max_kwh", "rate_piastres", "customer_service_fee", "billing_mode"):
        if field in payload:
            setattr(slice_, field, payload[field])

    try:
        slice_.full_clean()
        slice_.save()
    except Exception as exc:  # noqa: BLE001
        return bad_request(str(exc))

    return JsonResponse(slice_.to_dict())


@csrf_exempt
@require_http_methods(["GET", "POST"])
def transition_rule_list_view(request):
    tariff = _get_active_tariff()

    if request.method == "GET":
        return JsonResponse({
            "transition_rules": [r.to_dict() for r in tariff.transition_rules.order_by("order")]
        })

    payload = parse_json_body(request)
    if payload is None:
        return bad_request("Invalid JSON body.")

    slice_id = payload.get("triggering_slice_id")
    if not slice_id:
        return bad_request("'triggering_slice_id' is required.")
    triggering_slice = get_object_or_404(TariffSlice, pk=slice_id, tariff=tariff)

    if "deduction_amount" not in payload:
        return bad_request("'deduction_amount' is required.")

    try:
        rule = TransitionRule.objects.create(
            tariff=tariff,
            order=payload.get("order", 0),
            triggering_slice=triggering_slice,
            deduction_amount=payload["deduction_amount"],
            is_active=payload.get("is_active", True),
            note=payload.get("note", ""),
        )
    except Exception as exc:  # noqa: BLE001
        return bad_request(str(exc))

    return JsonResponse(rule.to_dict(), status=201)


@csrf_exempt
@require_http_methods(["PUT", "PATCH", "DELETE"])
def transition_rule_detail_view(request, rule_id):
    tariff = _get_active_tariff()
    rule = get_object_or_404(TransitionRule, pk=rule_id, tariff=tariff)

    if request.method == "DELETE":
        rule.delete()
        return JsonResponse({"deleted": True})

    payload = parse_json_body(request)
    if payload is None:
        return bad_request("Invalid JSON body.")

    if "triggering_slice_id" in payload:
        rule.triggering_slice = get_object_or_404(TariffSlice, pk=payload["triggering_slice_id"], tariff=tariff)
    for field in ("order", "deduction_amount", "is_active", "note"):
        if field in payload:
            setattr(rule, field, payload[field])

    try:
        rule.full_clean()
        rule.save()
    except Exception as exc:  # noqa: BLE001
        return bad_request(str(exc))

    return JsonResponse(rule.to_dict())


@csrf_exempt
@require_http_methods(["GET", "POST"])
def fee_list_view(request):
    tariff = _get_active_tariff()

    if request.method == "GET":
        return JsonResponse({"fees": [f.to_dict() for f in tariff.fees.order_by("name")]})

    payload = parse_json_body(request)
    if payload is None:
        return bad_request("Invalid JSON body.")

    if not payload.get("name"):
        return bad_request("'name' is required.")
    if "amount" not in payload:
        return bad_request("'amount' is required.")

    try:
        fee = Fee.objects.create(
            tariff=tariff,
            name=payload["name"],
            fee_type=payload.get("fee_type", "fixed"),
            amount=payload["amount"],
            description=payload.get("description", ""),
            is_active=payload.get("is_active", True),
        )
    except Exception as exc:  # noqa: BLE001
        return bad_request(str(exc))

    return JsonResponse(fee.to_dict(), status=201)


@csrf_exempt
@require_http_methods(["PUT", "PATCH", "DELETE"])
def fee_detail_view(request, fee_id):
    tariff = _get_active_tariff()
    fee = get_object_or_404(Fee, pk=fee_id, tariff=tariff)

    if request.method == "DELETE":
        fee.delete()
        return JsonResponse({"deleted": True})

    payload = parse_json_body(request)
    if payload is None:
        return bad_request("Invalid JSON body.")

    for field in ("name", "fee_type", "amount", "description", "is_active"):
        if field in payload:
            setattr(fee, field, payload[field])

    try:
        fee.full_clean()
        fee.save()
    except Exception as exc:  # noqa: BLE001
        return bad_request(str(exc))

    return JsonResponse(fee.to_dict())
