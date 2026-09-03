"""Dynamic language discovery.

Adding a new UI language is just: drop a new `<code>.json` file into
static/i18n/ with the same keys as en.json. This endpoint scans that
folder on every request, so the new language shows up in the UI
language switcher automatically - no code change, no settings edit.
"""
import json

from django.conf import settings
from django.http import JsonResponse


def languages_view(request):
    i18n_dir = settings.BASE_DIR / "static" / "i18n"
    languages = []
    if i18n_dir.exists():
        for path in sorted(i18n_dir.glob("*.json")):
            code = path.stem
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue
            languages.append({
                "code": code,
                "name": data.get("__name", code),
                "rtl": str(data.get("__rtl", "False")).lower() == "true",
            })
    return JsonResponse({"languages": languages})
