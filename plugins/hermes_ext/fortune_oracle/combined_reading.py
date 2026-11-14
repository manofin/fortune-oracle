"""Shared local combined-reading route for CLI, channels and voice output."""
from .localization import language_code
from .oracle_input import from_profile
from .oracle_method_adapters import adapt_all, adapt_qimen
from .oracle_renderer import render_final_reading, is_calculated_card


def prepare_combined_reading(profile=None, *, language=None, detailed=False, question=None):
    profile = profile if isinstance(profile, dict) else {}
    code = language_code(language if language is not None else profile.get("language"))
    inp = from_profile(profile)
    if question is not None:
        # Qimen is explicitly requested and never substituted for a birth chart.
        cards = [adapt_qimen(inp, question=question)]
    else:
        cards = adapt_all(inp, profile=profile)
    ok = any(is_calculated_card(card) for card in cards)
    return {"ok": ok, "kind": "qimen" if question is not None else "combined_reading",
            "language": code, "methods": [{"method": card.method, "status": card.status,
                                             "backend": card.backend, "calculation_mode": card.calculation_mode,
                                             "used_in_reading":is_calculated_card(card)}
                                            for card in cards],
            "text": render_final_reading(cards, language=code, detailed=detailed,
                                         include_qimen=question is not None)}
