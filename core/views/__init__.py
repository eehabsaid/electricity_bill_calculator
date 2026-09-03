from core.views.tariff_views import (
    tariff_detail_view,
    slice_list_view,
    slice_detail_view,
    transition_rule_list_view,
    transition_rule_detail_view,
    fee_list_view,
    fee_detail_view,
)
from core.views.bill_views import calculate_view, bill_list_view, bill_detail_view
from core.views.i18n_views import languages_view

__all__ = [
    "tariff_detail_view",
    "slice_list_view",
    "slice_detail_view",
    "transition_rule_list_view",
    "transition_rule_detail_view",
    "fee_list_view",
    "fee_detail_view",
    "calculate_view",
    "bill_list_view",
    "bill_detail_view",
    "languages_view",
]
