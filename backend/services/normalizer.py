import re
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Tuple, List, Dict, Any
from dateutil import parser as date_parser

class DataNormalizer:
    @staticmethod
    def parse_date(date_str: Any) -> Tuple[Optional[date], Optional[str]]:
        if not date_str or not str(date_str).strip():
            return None, "DATE_EMPTY"

        clean_str = str(date_str).strip()
        
        if any(w in clean_str.lower() for w in ["tbd", "next", "unknown", "na", "n/a", "null", "none"]):
            return None, f"INVALID_DATE_TEXT: '{clean_str}'"

        try:
            if re.match(r"^\d{4}-\d{2}-\d{2}", clean_str):
                return datetime.strptime(clean_str[:10], "%Y-%m-%d").date(), None
        except Exception:
            pass

        try:
            parsed = date_parser.parse(clean_str, dayfirst=True)
            return parsed.date(), None
        except Exception:
            pass

        try:
            parsed = date_parser.parse(clean_str)
            return parsed.date(), None
        except Exception:
            return None, f"UNPARSEABLE_DATE: '{clean_str}'"

    @staticmethod
    def parse_amount(amount_val: Any) -> Tuple[Optional[float], Optional[str]]:
        if amount_val is None:
            return None, "AMOUNT_NULL"

        val_str = str(amount_val).strip()
        if not val_str or val_str.lower() in ["none", "null", "na", "n/a", "tbd"]:
            return None, "AMOUNT_EMPTY"

        multiplier = 1.0
        val_lower = val_str.lower()
        if val_lower.endswith("k"):
            multiplier = 1000.0
            val_str = val_str[:-1]
        elif val_lower.endswith("m"):
            multiplier = 1000000.0
            val_str = val_str[:-1]

        cleaned = re.sub(r"[^\d.-]", "", val_str)
        if not cleaned or cleaned in ["-", "."]:
            return None, f"INVALID_NUMERIC_VALUE: '{amount_val}'"

        try:
            num = float(cleaned) * multiplier
            if num < 0:
                return num, f"NEGATIVE_AMOUNT: {num}"
            if num == 0:
                return 0.0, "ZERO_AMOUNT"
            return round(num, 2), None
        except ValueError:
            return None, f"UNPARSEABLE_AMOUNT: '{amount_val}'"

    @staticmethod
    def normalize_sector(sector_str: Any) -> Tuple[str, Optional[str]]:
        if not sector_str or not str(sector_str).strip():
            return "Unassigned", "SECTOR_MISSING"

        s = str(sector_str).strip().lower()

        if any(w in s for w in ["energy", "solar", "wind", "renewable", "power", "utility", "utilities"]):
            return "Energy", None
        elif any(w in s for w in ["mining", "metal", "metals", "bauxite", "coal", "ore", "steel"]):
            return "Mining", None
        elif any(w in s for w in ["infra", "infrastructure", "highway", "road", "expressway", "construction", "bridge"]):
            return "Infrastructure", None
        elif any(w in s for w in ["telecom", "tower", "5g", "telecommunication", "cellular"]):
            return "Telecom", None
        elif any(w in s for w in ["agri", "agriculture", "crop", "farm", "farming"]):
            return "Agriculture", None
        elif any(w in s for w in ["survey", "mapping", "geospatial", "gis"]):
            return "Geospatial", None
        else:
            return " ".join(word.capitalize() for word in s.split()), "SECTOR_UNRECOGNIZED"

    @staticmethod
    def normalize_client_name(client_str: Any) -> Tuple[str, str, Optional[str]]:
        if not client_str or not str(client_str).strip():
            return "Unknown Client", "unknown_client", "CLIENT_MISSING"

        display = str(client_str).strip()
        key = display.lower()

        suffixes = [
            r"\bpvt\b", r"\bltd\b", r"\blimited\b", r"\binc\b", r"\bcorp\b", 
            r"\bcorporation\b", r"\bllc\b", r"\bco\b", r"\bcompany\b", r"\bgroup\b",
            r"\benterprise\b", r"\benterprises\b"
        ]
        for suf in suffixes:
            key = re.sub(suf, "", key)

        key = re.sub(r"[^\w\s]", "", key)
        key = re.sub(r"\s+", " ", key).strip()

        if "adani" in key:
            key = "adani"
        elif "tata" in key:
            key = "tata"
        elif "vedanta" in key:
            key = "vedanta"
        elif "jsw" in key:
            key = "jsw"
        elif "nhai" in key or "highways authority" in key:
            key = "nhai"
        elif "reliance" in key or "jio" in key:
            key = "reliance"
        elif "ntpc" in key:
            key = "ntpc"
        elif "lt" in key or "larsen" in key:
            key = "lt"

        return display, key, None

    @staticmethod
    def normalize_deal_stage(stage_str: Any) -> Tuple[str, Optional[str]]:
        if not stage_str or not str(stage_str).strip():
            return "Unknown", "DEAL_STAGE_MISSING"

        s = str(stage_str).strip().lower()
        if "won" in s or "closed won" in s:
            return "Won", None
        elif "lost" in s or "closed lost" in s:
            return "Lost", None
        elif "negotiat" in s:
            return "Negotiation", None
        elif "propos" in s or "quote" in s:
            return "Proposal", None
        elif "discover" in s or "qualif" in s or "lead" in s:
            return "Discovery", None
        elif "hold" in s or "pause" in s:
            return "On Hold", None
        else:
            return s.title(), "NON_STANDARD_STAGE"

    @staticmethod
    def normalize_work_order_status(status_str: Any) -> Tuple[str, Optional[str]]:
        if not status_str or not str(status_str).strip():
            return "Unknown", "WO_STATUS_MISSING"

        s = str(status_str).strip().lower()
        if "complete" in s or "done" in s or "finished" in s or "delivered" in s:
            return "Completed", None
        elif "progress" in s or "ongoing" in s or "flying" in s or "active" in s:
            return "In Progress", None
        elif "schedule" in s or "planned" in s or "booked" in s:
            return "Scheduled", None
        elif "delay" in s or "late" in s or "overdue" in s or "blocked" in s:
            return "Delayed", None
        elif "cancel" in s or "terminated" in s:
            return "Cancelled", None
        elif "hold" in s or "pause" in s:
            return "On Hold", None
        else:
            return s.title(), "NON_STANDARD_STATUS"

normalizer = DataNormalizer()
