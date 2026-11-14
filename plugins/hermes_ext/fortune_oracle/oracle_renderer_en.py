"""English presentation from structured chart facts, without recalculation.

Only explicitly supported fact fields are displayed. Provider prose and raw
input are not interpolated into the report. Traditional proper names can retain
their Chinese characters; birth pillars include romanization.
"""
import math
import re

from .localization import DISCLAIMER_EN, pillar_label

LABELS = {"bazi": "Four Pillars (Bazi)", "western": "Western astrology",
          "vedic": "Vedic astrology", "ziwei": "Ziwei Doushu", "qimen": "Qimen Dunjia"}
SIGNS = ("Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra",
         "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces")


def token(value):
    # Structured identifiers only: never dictionaries, arbitrary provider prose,
    # Korean error text, tracebacks or instructions disguised as chart data.
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return ""
    text = str(value)
    return text if re.fullmatch(r"[A-Za-z0-9_ .+\-\u3400-\u9fff]{1,90}", text) else ""


def number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return float(value)
    return None


def fact_lines(card, *, detailed=False):
    facts = card.facts
    lines = []
    if card.method == "bazi":
        for key, label in (("year", "Year"), ("month", "Month"), ("day", "Day"), ("time", "Hour")):
            value = facts.get("eight_char", {}).get(key)
            if isinstance(value, str) and len(value) == 2:
                try:
                    roman = pillar_label(value)
                except KeyError:
                    continue
                lines.append(f"{label} pillar: {roman} ({value})")
        lines.append("Basis: lunar-javascript birth-pillar calculation; hour is omitted when unknown.")
        basis = facts.get('time_basis', {})
        if basis:
            lines.append("Year/month: birth instant converted to the solar-term table's UTC+8 reference."
                         if basis.get('solar_terms') == 'birth_instant_utc_plus_8' else
                         "Year/month confirmed unchanged throughout the local birth date; hour is unknown."
                         if basis.get('solar_terms') == 'civil_day_interval_confirmed' else
                         "Unresolved year/month pillars near a solar term are omitted; birth time is unknown.")
            lines.append("Day/hour: local civil time, midnight day boundary; true solar time / longitude correction is not applied.")
    elif card.method == "western":
        for planet in facts.get("planet_positions", []):
            name, longitude = token(planet.get("name")), number(planet.get("longitude"))
            if name and longitude is not None and 0 <= longitude < 360:
                lines.append(f"{name}: {SIGNS[int(longitude // 30)]} {longitude % 30:.4f}°"
                             + (" (retrograde)" if planet.get("retrograde") is True else ""))
        for name, value in facts.get("angles", {}).items():
            longitude = number(value)
            if token(name) and longitude is not None and 0 <= longitude < 360:
                lines.append(f"{token(name)}: {SIGNS[int(longitude // 30)]} {longitude % 30:.4f}°")
        houses = [number(value) for value in facts.get("house_cusps", [])]
        if len(houses) == 12 and all(value is not None for value in houses):
            lines.append(f"House system: {token(facts.get('house_system'))}")
            lines.append("House cusps (longitude): " + ", ".join(f"{value:.4f}°" for value in houses))
        for aspect in facts.get("aspect_details", [])[:20 if detailed else 5]:
            first, second, kind = token(aspect.get("planet1")), token(aspect.get("planet2")), token(aspect.get("type"))
            orb = number(aspect.get("orb"))
            if first and second and kind and orb is not None:
                lines.append(f"{first}–{second}: {kind}, orb {orb:.4f}°")
        provenance = facts.get("provenance", {})
        if token(provenance.get("ephemeris")):
            lines.append(f"Ephemeris: {token(provenance['ephemeris'])}")
        digest = provenance.get("sha256", "")
        if isinstance(digest, str) and re.fullmatch(r"[a-f0-9]{64}", digest):
            lines.append(f"SHA256: {digest}")
        lines.extend(["Basis: apparent geocentric tropical ecliptic of date; IANA birth time converted to UTC.",
                      "Retrograde: longitude change across two hours. Planetary-system barycenters are used except for Sun and Moon.",
                      "Whole Sign / Equal House only; missing coordinates or unsupported houses omit house calculations."])
    elif card.method == "vedic":
        for planet in facts.get("graha_positions", []):
            name, rashi, degree = token(planet.get("name")), token(planet.get("rashi")), number(planet.get("degree"))
            if name and rashi and degree is not None:
                lines.append(f"{name}: {rashi} {degree:.4f}°")
        lines.append("Basis: built-in sidereal / Lahiri approximation; these are not precise ephemeris positions.")
        nakshatra = facts.get("nakshatra_details", {})
        if token(nakshatra.get("name")):
            lines.append(f"Moon nakshatra: {token(nakshatra['name'])} · pada {token(nakshatra.get('pada'))}")
        dasha = facts.get("dasha_details", {})
        if token(dasha.get("mahadasha")) and token(dasha.get("antardasha")):
            lines.append(f"Approximate dasha: {token(dasha['mahadasha'])}/{token(dasha['antardasha'])}")
    elif card.method == "ziwei":
        branch = token(facts.get("ming_gong", {}).get("branch"))
        if branch:
            lines.append(f"Life palace branch: {branch}")
        for palace, stars in facts.get("stars", {}).items():
            if isinstance(stars, list):
                names = [token(star) for star in stars]
                names = [name for name in names if name]
                if names and token(palace):
                    lines.append(f"Palace {token(palace)} stars: {', '.join(names)}")
        for key, label in (("祿", "Lu"), ("權", "Quan"), ("科", "Ke"), ("忌", "Ji")):
            star = token(facts.get("sihua", {}).get(key, {}).get("star"))
            if star:
                lines.append(f"{label} transformation: {star}")
        lines.append("Basis: iztro chart placements; traditional star names are preserved.")
    elif card.method == "qimen":
        moment = facts.get('question_time', '')
        if isinstance(moment, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}\+09:00', moment):
            lines.append(f"Calculation time: {moment} · Asia/Seoul")
        ganzhi = token(facts.get("ganzhi"))
        if ganzhi:
            lines.append(f"Question-time pillars: {ganzhi}")
        for palace, values in facts.get("palaces", {}).items():
            door, star = token(values.get("door")), token(values.get("star"))
            if token(palace) and (door or star):
                lines.append(f"Palace {token(palace)}: door {door or 'unavailable'}, star {star or 'unavailable'}")
        lines.append("Basis: kinqimen question-time chart in Asia/Seoul; this is not a birth chart.")
    return lines


def render_english_reading(cards, *, detailed=False):
    from .oracle_renderer import is_calculated_card
    lines = ["Combined reading", ""]
    for card in cards:
        label = LABELS.get(card.method, "Unsupported method")
        lines.append(f"{label} — {card.status}")
        if not card.is_ok():
            codes = [token(value.split(":", 1)[0]) for value in card.blockers if isinstance(value, str)]
            codes = [code for code in codes if code]
            lines.append("Calculation unavailable; check required inputs and calculation dependencies."
                         + (f" ({', '.join(codes[:3])})" if codes else ""))
        else:
            if not is_calculated_card(card):
                lines.append("Reference only: approximate or unattributed values are excluded from the combined interpretation.")
            lines.append(f"Calculation: {token(card.calculation_mode) or 'unknown'}"
                         f" · backend: {token(card.backend) or 'unspecified'}")
            # Provenance and limitations are retained in both compact and full modes.
            lines.extend(fact_lines(card, detailed=detailed))
            if card.status == "partial":
                lines.append("Partial result: unavailable chart components are omitted.")
            if card.warnings or card.precision_notes:
                lines.append("Input precision and backend limitations apply; this is not a fully verified predictive model.")
        lines.append("")
    if not any(is_calculated_card(card) for card in cards):
        lines.append("No calculated reading is available. Provide a valid birth date and time, IANA birth time zone, and coordinates when needed.")
    lines.extend(["Reflection: treat chart symbols as prompts, not evidence that an event will occur.",
                  "No reliable five-year forecast, health outcome or financial return is inferred from these positions.", DISCLAIMER_EN])
    return "\n".join(lines)
