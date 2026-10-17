"""Isolated, dependency-free insurance policy field extraction prototype.

Not wired into production. No external requests, persistence or customer-data logging.
"""
from __future__ import annotations
import re
import unicodedata
from datetime import datetime

ALIASES = {
    "policy_number": ("poliçe no", "poliçe numarası", "poliçe numarasi", "policy no", "policy number", "sözleşme no", "sozlesme no"),
    "customer_name": ("sigortalı adı soyadı", "sigortalının adı soyadı", "sigortalı ad soyad", "sigortalı", "sigorta ettiren", "müşteri adı", "adi soyadi", "insured name", "policyholder"),
    "start_date": ("poliçe başlangıç tarihi", "başlangıç tarihi", "vade başlangıcı", "sigorta başlangıç tarihi", "teminat başlangıcı", "inception date", "effective date", "coverage start"),
    "end_date": ("poliçe bitiş tarihi", "bitiş tarihi", "vade bitişi", "vade sonu", "sigorta bitiş tarihi", "teminat bitişi", "expiry date", "expiration date", "coverage end"),
    "premium": ("toplam brüt prim", "toplam prim", "brüt prim", "prim tutarı", "ödenecek prim", "total premium", "gross premium"),
    "insurer": ("sigorta şirketi", "sigortacı", "sigorta kuruluşu", "insurance company", "insurer"),
}
DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](\d{4})(?!\d)")
AMOUNT_RE = re.compile(r"(?<!\w)(?:₺|TL|TRY\s*)?\s*([0-9][0-9., ]{0,18}[0-9]|[0-9]+)\s*(?:TL|TRY|₺)?", re.I)
POLICY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/._-]{2,79}$")

def _fold(s: str) -> str:
    s = s.casefold().replace("ı", "i")
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))

def _date(s: str):
    m = DATE_RE.search(s)
    if not m:
        return None
    try:
        return datetime(int(m[3]), int(m[2]), int(m[1])).date().isoformat()
    except ValueError:
        return None

def _amount(s: str):
    m = AMOUNT_RE.search(s)
    if not m:
        return None
    raw = m[1].replace(" ", "")
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".") if raw.rfind(",") > raw.rfind(".") else raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(",", ".") if len(raw.split(",")[-1]) <= 2 else raw.replace(",", "")
    elif "." in raw and len(raw.split(".")[-1]) == 3:
        raw = raw.replace(".", "")
    try:
        v = float(raw)
        return v if 0 <= v <= 1e12 else None
    except ValueError:
        return None

def extract_fields(text: str) -> dict:
    """Return verified candidates only; never infer missing values."""
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    result = {}
    for key, aliases in ALIASES.items():
        aliases = sorted(aliases, key=len, reverse=True)
        for idx, line in enumerate(lines):
            folded = _fold(line)
            match = None
            for alias in aliases:
                alias_f = _fold(alias)
                m = re.search(r"(?<![\w])" + re.escape(alias_f) + r"(?![\w])", folded)
                if m and (m.start() <= 4 or folded[:m.start()].strip(" :-|") == ""):
                    match = m
                    break
            if not match:
                continue
            tail = line[match.end():].strip(" :-|\t")
            # A label on one line can have its value on the next line.
            candidate = tail or (lines[idx + 1] if idx + 1 < len(lines) else "")
            if not candidate or any(_fold(candidate).startswith(_fold(a)) for a in aliases):
                continue
            value = (_date(candidate) if key.endswith("_date") else
                     _amount(candidate) if key == "premium" else
                     candidate.strip())
            if key == "policy_number" and not POLICY_RE.fullmatch(str(value or "")):
                continue
            if key in ("customer_name", "insurer") and (not value or len(value) > 120 or len(value) < 3):
                continue
            if value is not None:
                result[key] = value
                break
    if result.get("start_date") and result.get("end_date") and result["end_date"] < result["start_date"]:
        result.pop("start_date")
        result.pop("end_date")
    return result
