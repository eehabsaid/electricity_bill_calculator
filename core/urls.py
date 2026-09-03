from django.urls import path

from core.views import (
    bill_detail_view,
    bill_list_view,
    calculate_view,
    fee_detail_view,
    fee_list_view,
    languages_view,
    slice_detail_view,
    slice_list_view,
    tariff_detail_view,
    transition_rule_detail_view,
    transition_rule_list_view,
)

urlpatterns = [
    path("tariff/", tariff_detail_view, name="api-tariff-detail"),
    path("tariff/slices/", slice_list_view, name="api-slice-list"),
    path("tariff/slices/<int:slice_id>/", slice_detail_view, name="api-slice-detail"),
    path("tariff/transition-rules/", transition_rule_list_view, name="api-transition-rule-list"),
    path("tariff/transition-rules/<int:rule_id>/", transition_rule_detail_view, name="api-transition-rule-detail"),
    path("tariff/fees/", fee_list_view, name="api-fee-list"),
    path("tariff/fees/<int:fee_id>/", fee_detail_view, name="api-fee-detail"),
    path("calculate/", calculate_view, name="api-calculate"),
    path("bills/", bill_list_view, name="api-bill-list"),
    path("bills/<int:bill_id>/", bill_detail_view, name="api-bill-detail"),
    path("languages/", languages_view, name="api-languages"),
]
