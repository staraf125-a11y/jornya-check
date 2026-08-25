"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    JORNAYA SMART VALIDATOR v5.4 FAST                         ║
║              ipwho.is + ADDRESS STATE + TF MATCHING                    ║
║           renovatefast.com / quickfixremodel.com Dashboard                   ║
║                                                                              ║
║  Run:   python jornaya_validator_fast_v3.py                                  ║
║  Open:  http://localhost:5000                                                ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from flask import Flask, render_template_string, request, jsonify
import requests
import json
import re
import html
import time
from collections import Counter, OrderedDict
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from urllib.parse import urlparse

app = Flask(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
#                              CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

DASHBOARD_URL = "https://renovatefast.com/new_dashboard/leads.php"
COOKIE_VALUE = "_ga=GA1.1.319955778.1785191448; _gcl_au=1.1.1122351210.1785191448"
USE_FULL_COOKIE_HEADER = False

MAX_WORKERS = 12
IP_CACHE_TTL = 3600
REQUEST_TIMEOUT = 6
ENABLE_THREADING = True

# ═══════════════════════════════════════════════════════════════════════════════
#                         CONNECTION POOL & SESSION
# ═══════════════════════════════════════════════════════════════════════════════

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://renovatefast.com/new_dashboard/",
})

# ═══════════════════════════════════════════════════════════════════════════════
#                         THREAD-SAFE TTL CACHE
# ═══════════════════════════════════════════════════════════════════════════════

class TTLCache:
    def __init__(self, ttl_seconds=3600, maxsize=5000):
        self.ttl = ttl_seconds
        self.maxsize = maxsize
        self._cache = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            if key not in self._cache:
                return None
            expiry, value = self._cache[key]
            if time.time() > expiry:
                del self._cache[key]
                return None
            self._cache.move_to_end(key)
            return value

    def set(self, key, value):
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = (time.time() + self.ttl, value)
            if len(self._cache) > self.maxsize:
                self._cache.popitem(last=False)

    def clear_key(self, key):
        with self._lock:
            if key in self._cache:
                del self._cache[key]

ip_cache = TTLCache(ttl_seconds=IP_CACHE_TTL, maxsize=5000)

# ═══════════════════════════════════════════════════════════════════════════════
#                              SERVICE COLORS
# ═══════════════════════════════════════════════════════════════════════════════

SERVICE_COLORS = {
    "home improvement": {"bg": "#E8F4F8", "border": "#06B6D4", "text": "#0891B2", "badge": "#0E7490"},
    "solar": {"bg": "#FEF3C7", "border": "#F59E0B", "text": "#D97706", "badge": "#92400E"},
    "roofing": {"bg": "#FEE2E2", "border": "#EF4444", "text": "#DC2626", "badge": "#7F1D1D"},
    "hvac": {"bg": "#E9D5FF", "border": "#A855F7", "text": "#9333EA", "badge": "#4C1D95"},
    "plumbing": {"bg": "#DBEAFE", "border": "#3B82F6", "text": "#1D4ED8", "badge": "#1E3A8A"},
    "electrical": {"bg": "#F0FDF4", "border": "#22C55E", "text": "#16A34A", "badge": "#15803D"},
    "insurance": {"bg": "#F5E6FF", "border": "#D946EF", "text": "#C026D3", "badge": "#6B21A8"},
    "windows": {"bg": "#E0F2FE", "border": "#0284C7", "text": "#0369A1", "badge": "#0C2D6B"},
    "gutter": {"bg": "#F0E7FF", "border": "#8B5CF6", "text": "#7C3AED", "badge": "#5B21B6"},
    "painting": {"bg": "#FEE4E2", "border": "#F97316", "text": "#EA580C", "badge": "#9A3412"},
    "flooring": {"bg": "#E6F5FF", "border": "#3B82F6", "text": "#1E40AF", "badge": "#0C2D6B"},
    "landscaping": {"bg": "#DFFCF0", "border": "#10B981", "text": "#059669", "badge": "#065F46"},
    "patio": {"bg": "#FFF4E6", "border": "#F97316", "text": "#C2410C", "badge": "#7C2D12"},
    "garage": {"bg": "#F3E8FF", "border": "#D946EF", "text": "#A855F7", "badge": "#7E22CE"},
    "basement": {"bg": "#F5F3FF", "border": "#6366F1", "text": "#4F46E5", "badge": "#3730A3"},
    "kitchen": {"bg": "#FDF2F8", "border": "#EC4899", "text": "#BE185D", "badge": "#831843"},
    "bathroom": {"bg": "#E0F2FE", "border": "#0EA5E9", "text": "#0369A1", "badge": "#082F49"},
    "deck": {"bg": "#FEF08A", "border": "#EAB308", "text": "#A16207", "badge": "#713F12"},
    "fence": {"bg": "#D1FAE5", "border": "#14B8A6", "text": "#0D9488", "badge": "#134E4A"},
    "siding": {"bg": "#F8FAFC", "border": "#64748B", "text": "#475569", "badge": "#1E293B"},
    "door": {"bg": "#FCA5A5", "border": "#DC2626", "text": "#7F1D1D", "badge": "#450A0A"},
    "water damage": {"bg": "#CFFAFE", "border": "#06B6D4", "text": "#0891B2", "badge": "#164E63"},
    "foundation": {"bg": "#E7E5E4", "border": "#78716C", "text": "#57534E", "badge": "#292524"},
    "furniture": {"bg": "#FAE8FF", "border": "#D946EF", "text": "#9D174D", "badge": "#500724"},
    "appliance": {"bg": "#F1F5F9", "border": "#94A3B8", "text": "#64748B", "badge": "#1E293B"},
    "pool": {"bg": "#E0F2FE", "border": "#0284C7", "text": "#0369A1", "badge": "#03296C"},
    "pest control": {"bg": "#ECFDF5", "border": "#059669", "text": "#047857", "badge": "#064E3B"},
    "tree service": {"bg": "#ECFDF5", "border": "#10B981", "text": "#059669", "badge": "#065F46"},
    "driveway": {"bg": "#F3F4F6", "border": "#6B7280", "text": "#4B5563", "badge": "#1F2937"},
    "waterproofing": {"bg": "#DBEAFE", "border": "#3B82F6", "text": "#1D4ED8", "badge": "#1E40AF"},
    "default": {"bg": "#F3F4F6", "border": "#9CA3AF", "text": "#6B7280", "badge": "#374151"}
}

def get_service_colors(service_name):
    if not service_name:
        return SERVICE_COLORS["default"]
    service_lower = service_name.lower().strip()
    for key, colors in SERVICE_COLORS.items():
        if key != "default" and key in service_lower:
            return colors
    return SERVICE_COLORS["default"]

# ═══════════════════════════════════════════════════════════════════════════════
#                         PAGE DOMAIN COLORS
# ═══════════════════════════════════════════════════════════════════════════════

PAGE_DOMAIN_COLORS = {
    "renovatefast": {"bg": "#E0F2FE", "border": "#0284C7", "text": "#0369A1", "label": "RENO"},
    "quickfixremodel": {"bg": "#FEF3C7", "border": "#F59E0B", "text": "#92400E", "label": "QUICK"},
    "default": {"bg": "#F3F4F6", "border": "#9CA3AF", "text": "#6B7280", "label": "OTHER"}
}

def get_page_domain_colors(domain):
    if not domain:
        return PAGE_DOMAIN_COLORS["default"]
    domain_lower = domain.lower().strip()
    for key, colors in PAGE_DOMAIN_COLORS.items():
        if key != "default" and key in domain_lower:
            return colors
    return PAGE_DOMAIN_COLORS["default"]

def extract_domain(url):
    """Extract domain from URL"""
    if not url:
        return "—"
    try:
        parsed = urlparse(str(url))
        domain = parsed.netloc.replace('www.', '') if parsed.netloc else url
        # Extract just the main domain name
        domain_parts = domain.split('.')
        if len(domain_parts) > 1:
            return domain_parts[0]
        return domain if domain else "—"
    except:
        return "—"

def extract_domain_from_url(url_str):
    """Extract clean domain name from a URL. Returns e.g. 'renovatefast' or 'quickfixremodel'"""
    if not url_str:
        return None
    try:
        text = str(url_str).strip()
        if not text.startswith("http"):
            text = "https://" + text
        parsed = urlparse(text)
        netloc = parsed.netloc or parsed.path
        netloc = netloc.replace("www.", "").split(":")[0]
        parts = netloc.split(".")
        if len(parts) >= 2:
            return parts[-2]
        return netloc
    except Exception:
        return None

# ═══════════════════════════════════════════════════════════════════════════════
#                         IP LOOKUP PROVIDERS
# ═══════════════════════════════════════════════════════════════════════════════
#  Priority: ipinfo.io → ip-api.com → ipapi.co → ipgeolocation.io
#  Batch:   ipinfo.io/batch (up to 1000 IPs per call)
#  Note:     ipwho.is removed (blocked/banned). whatismyipaddress.com has no public API.
# ═══════════════════════════════════════════════════════════════════════════════

def _provider_ipinfo(ip):
    """ipinfo.io — reliable, 50k free requests/month."""
    resp = session.get(f"https://ipinfo.io/{ip}/json", timeout=REQUEST_TIMEOUT)
    if resp.status_code == 429:
        raise Exception("ipinfo.io rate limited")
    resp.raise_for_status()
    data = resp.json()
    loc = data.get("loc", ",").split(",")
    return {
        "state": data.get("region"),
        "city": data.get("city"),
        "zip": data.get("postal"),
        "country": data.get("country"),
        "isp": data.get("org"),
        "lat": float(loc[0]) if len(loc) > 0 and loc[0] else None,
        "lon": float(loc[1]) if len(loc) > 1 and loc[1] else None,
        "ip": data.get("ip"),
        "error": None,
        "source": "ipinfo.io"
    }

def _provider_ipapi(ip):
    """ip-api.com — free, no auth, 45 requests/minute limit."""
    url = f"http://ip-api.com/json/{ip}?fields=status,message,country,regionName,city,zip,lat,lon,isp,query"
    resp = session.get(url, timeout=REQUEST_TIMEOUT)
    data = resp.json()
    if data.get("status") == "success":
        return {
            "state": data.get("regionName"),
            "city": data.get("city"),
            "zip": data.get("zip"),
            "country": data.get("country"),
            "isp": data.get("isp"),
            "lat": data.get("lat"),
            "lon": data.get("lon"),
            "ip": data.get("query"),
            "error": None,
            "source": "ip-api.com"
        }
    raise Exception(data.get("message", "ip-api.com failed"))

def _provider_ipapico(ip):
    """ipapi.co — free, 30k requests/month, no auth."""
    resp = session.get(f"https://ipapi.co/{ip}/json/", timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if "error" not in data:
        return {
            "state": data.get("region"),
            "city": data.get("city"),
            "zip": data.get("postal"),
            "country": data.get("country_name"),
            "isp": data.get("org"),
            "lat": data.get("latitude"),
            "lon": data.get("longitude"),
            "ip": data.get("ip"),
            "error": None,
            "source": "ipapi.co"
        }
    raise Exception(data.get("reason", "ipapi.co error"))

def _provider_ipgeolocation(ip):
    """ipgeolocation.io — free, no auth, 30k requests/month. Good state accuracy."""
    resp = session.get(f"https://api.ipgeolocation.io/ipgeo?apiKey=demo&ip={ip}", timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if "message" not in data:
        return {
            "state": data.get("state_prov"),
            "city": data.get("city"),
            "zip": data.get("zipcode"),
            "country": data.get("country_name"),
            "isp": data.get("isp"),
            "lat": data.get("latitude"),
            "lon": data.get("longitude"),
            "ip": data.get("ip"),
            "error": None,
            "source": "ipgeolocation.io"
        }
    raise Exception(data.get("message", "ipgeolocation.io error"))

# ═══════════════════════════════════════════════════════════════════════════════
#                         BATCH + FALLBACK IP LOOKUP
# ═══════════════════════════════════════════════════════════════════════════════

def get_ip_location(ip_address, force_refresh=False):
    if not ip_address or ip_address in ("127.0.0.1", "localhost", "::1", ""):
        return {"error": "Local IP", "state": None, "city": None, "country": None, "isp": None}

    ip = ip_address.split(":")[0].strip()
    ipv4_pattern = r"^(\d{1,3}\.){3}\d{1,3}$"
    if not re.match(ipv4_pattern, ip):
        return {"error": "Invalid IP format", "state": None, "city": None, "country": None, "isp": None}

    if not force_refresh:
        cached = ip_cache.get(ip)
        if cached is not None:
            cached["source"] = "cache"
            return cached

    result = _fetch_ip_single(ip)
    ip_cache.set(ip, result)
    return result

def _fetch_ip_single(ip):
    """Try providers in priority order. ipinfo.io is most reliable."""
    errors = []

    # Provider 1: ipinfo.io (reliable, batch API available)
    try:
        return _provider_ipinfo(ip)
    except Exception as e:
        errors.append(f"ipinfo.io: {str(e)}")

    # Provider 2: ip-api.com (free, no auth, 45/min)
    try:
        return _provider_ipapi(ip)
    except Exception as e:
        errors.append(f"ip-api.com: {str(e)}")

    # Provider 3: ipapi.co (free, 30k/month)
    try:
        return _provider_ipapico(ip)
    except Exception as e:
        errors.append(f"ipapi.co: {str(e)}")

    # Provider 4: ipgeolocation.io
    try:
        return _provider_ipgeolocation(ip)
    except Exception as e:
        errors.append(f"ipgeolocation.io: {str(e)}")

    return {
        "error": " | ".join(errors) if errors else "All providers failed",
        "state": None,
        "city": None,
        "country": None,
        "isp": None,
        "source": "failed"
    }

def batch_lookup_ips(ip_list):
    """Use ipinfo.io batch API to lookup multiple IPs in ONE request."""
    if not ip_list or len(ip_list) < 2:
        return {}

    # Filter out cached ones
    uncached = [ip for ip in ip_list if ip_cache.get(ip) is None]
    if not uncached:
        return {ip: ip_cache.get(ip) for ip in ip_list}

    try:
        resp = session.post(
            "https://ipinfo.io/batch",
            json=uncached,
            headers={"Content-Type": "application/json"},
            timeout=REQUEST_TIMEOUT + 5
        )
        if resp.status_code == 200:
            data = resp.json()
            results = {}
            for ip in uncached:
                ip_data = data.get(ip, {})
                if ip_data:
                    loc = ip_data.get("loc", ",").split(",")
                    result = {
                        "state": ip_data.get("region"),
                        "city": ip_data.get("city"),
                        "zip": ip_data.get("postal"),
                        "country": ip_data.get("country"),
                        "isp": ip_data.get("org"),
                        "lat": float(loc[0]) if len(loc) > 0 and loc[0] else None,
                        "lon": float(loc[1]) if len(loc) > 1 and loc[1] else None,
                        "ip": ip_data.get("ip", ip),
                        "error": None,
                        "source": "ipinfo.io (batch)"
                    }
                    ip_cache.set(ip, result)
                    results[ip] = result
                else:
                    result = {"error": "No data in batch", "state": None, "city": None, "country": None, "isp": None, "source": "batch-failed"}
                    ip_cache.set(ip, result)
                    results[ip] = result
            return results
        else:
            # Batch failed, fall through to individual lookups
            pass
    except Exception:
        pass

    # Fallback: parallel individual lookups via ipwho.is (fastest per-request)
    results = {}
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(uncached))) as executor:
        future_to_ip = {executor.submit(_fetch_ip_single, ip): ip for ip in uncached}
        for future in as_completed(future_to_ip):
            ip = future_to_ip[future]
            try:
                results[ip] = future.result()
            except Exception:
                results[ip] = {"error": "Lookup crashed", "state": None, "city": None, "country": None, "isp": None, "source": "crashed"}
    return results

# ═══════════════════════════════════════════════════════════════════════════════
#                         ENRICHMENT ENGINE (BATCH + QUICK)
# ═══════════════════════════════════════════════════════════════════════════════

def enrich_leads(leads, skip_geo=False):
    if skip_geo:
        for lead in leads:
            lead["ip_geo"] = {"error": "Skipped (Quick Mode)", "state": None, "city": None, "country": None, "isp": None, "source": "quick-mode"}
            lead["validation"] = check_state_match(lead.get("state"), None, lead.get("tf_state"))
        return leads

    unique_ips = list(set(lead.get("td_ip") for lead in leads if lead.get("td_ip")))

    if len(unique_ips) >= 2:
        # Use batch API for 2+ IPs
        ip_geo_map = batch_lookup_ips(unique_ips)
    else:
        # Single IP or none — just do direct lookup
        ip_geo_map = {}
        for ip in unique_ips:
            ip_geo_map[ip] = get_ip_location(ip)

    for lead in leads:
        ip = lead.get("td_ip")
        lead["ip_geo"] = ip_geo_map.get(ip, {"error": "No IP", "state": None, "city": None, "country": None, "isp": None})
        lead["tf_accuracy"] = classify_tf_state(lead.get("tf_location"))
        lead["validation"] = check_state_match(
            lead.get("state"),
            lead["ip_geo"].get("state"),
            lead.get("tf_state"),
            lead["tf_accuracy"],
            lead.get("address_state")
        )

    return leads


# ═══════════════════════════════════════════════════════════════════════════════
#                         TF LOCATION ACCURACY CHECK
# ═══════════════════════════════════════════════════════════════════════════════

VAGUE_COUNTRIES = {"united states", "us", "usa", "canada", "mexico", "united kingdom", "uk", "australia"}

def is_vague_tf_location(location_str):
    """Return True if TF location has no usable state (just country or empty)."""
    if not location_str:
        return True
    text = str(location_str).strip().lower()
    # Just a country name with no comma = no city/state
    if "," not in text and text in VAGUE_COUNTRIES:
        return True
    # Extract state and check if it's valid
    state = extract_state_from_location(location_str)
    if not state:
        return True
    return False

def classify_tf_state(location_str):
    """Classify TF location accuracy. Returns: 'exact', 'vague', or 'missing'."""
    if not location_str:
        return "missing"
    if is_vague_tf_location(location_str):
        return "vague"
    return "exact"


# ═══════════════════════════════════════════════════════════════════════════════
#                         ADDRESS-BASED STATE EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

def extract_state_from_address(address_str):
    """Extract US state from a street address. Handles formats like:
    - '3274 1st St, Madison, AL 35758'
    - '123 Main Street, Springfield, Illinois 62701'
    - '456 Oak Rd, Austin TX 78701'
    Returns: state abbreviation (e.g. 'AL') or None
    """
    if not address_str:
        return None
    text = str(address_str).strip()

    # Look for 2-letter state abbreviation before ZIP (most common pattern)
    # Matches: ', AL 35758' or ' AL 35758' or ',AL 35758'
    zip_pattern = re.search(r"[,\s]+([A-Za-z]{2})\s+\d{5}(-\d{4})?\s*$", text)
    if zip_pattern:
        candidate = zip_pattern.group(1).upper()
        if candidate in ABBREV_TO_STATE:
            return candidate

    # Look for full state name before ZIP
    # Matches: ', Alabama 35758' or ' Alabama 35758'
    for state_name, abbrev in US_STATE_ABBREVS.items():
        # Match full state name (case insensitive) followed by ZIP or end
        pattern = re.compile(r"[,\s]+" + re.escape(state_name) + r"(?:\s+\d{5})?\s*$", re.IGNORECASE)
        if pattern.search(text):
            return abbrev

    # Fallback: look for any 2-letter abbreviation anywhere in the address
    # But only if it's a valid state abbrev
    for match in re.finditer(r"\b([A-Za-z]{2})\b", text):
        candidate = match.group(1).upper()
        if candidate in ABBREV_TO_STATE:
            return candidate

    return None

# ═══════════════════════════════════════════════════════════════════════════════
#                           STATE MATCHING LOGIC
# ═══════════════════════════════════════════════════════════════════════════════

US_STATE_ABBREVS = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC"
}

# Reverse lookup: abbreviation → full name (for normalization)
ABBREV_TO_STATE = {v: k.title() for k, v in US_STATE_ABBREVS.items()}

def normalize_state(state_str):
    if not state_str:
        return None
    s = str(state_str).strip().lower()
    # Already an abbreviation like "CA"
    if len(s) == 2 and s.isalpha():
        return s.upper()
    # Full name like "california"
    return US_STATE_ABBREVS.get(s, s.upper())

def extract_state_from_location(location_str):
    """Extract US state from a location string. Handles:
    - 'Los Angeles, California, United States' → California → CA
    - 'Los Angeles, CA' → CA
    - 'California' → California → CA
    - 'New York, NY' → NY
    """
    if not location_str:
        return None

    text = str(location_str).strip()

    # Direct 2-letter abbreviation match anywhere in string
    abbrev_match = re.search(r"\b([A-Za-z]{2})\b", text)
    if abbrev_match:
        candidate = abbrev_match.group(1).upper()
        if candidate in ABBREV_TO_STATE:
            return candidate  # Return the abbreviation

    # Split by comma
    parts = [p.strip() for p in text.split(",")]

    if len(parts) == 1:
        single = parts[0].lower()
        if single in US_STATE_ABBREVS:
            return parts[0]  # Return full name
        if single.upper() in ABBREV_TO_STATE:
            return single.upper()  # Return abbreviation
        return None

    if len(parts) >= 2:
        # Check last part for country
        last = parts[-1].lower().strip()
        if last in ("united states", "us", "usa", "canada", "mexico"):
            if len(parts) >= 3:
                candidate = parts[-2].strip()
                cand_lower = candidate.lower()
                if cand_lower in US_STATE_ABBREVS:
                    return candidate
                if candidate.upper() in ABBREV_TO_STATE:
                    return candidate.upper()
            return None

        # Check second-to-last part (standard City, State format)
        candidate = parts[-1].strip() if len(parts) == 2 else parts[-2].strip()
        cand_lower = candidate.lower()
        if cand_lower in US_STATE_ABBREVS:
            return candidate
        if candidate.upper() in ABBREV_TO_STATE:
            return candidate.upper()

        # Check last part
        candidate = parts[-1].strip()
        cand_lower = candidate.lower()
        if cand_lower in US_STATE_ABBREVS:
            return candidate
        if candidate.upper() in ABBREV_TO_STATE:
            return candidate.upper()

    return None

def check_state_match(agent_state, ip_state, tf_state, tf_accuracy="exact", address_state=None):
    agent_norm = normalize_state(agent_state)
    ip_norm = normalize_state(ip_state)
    tf_norm = normalize_state(tf_state)
    addr_norm = normalize_state(address_state)

    results = {
        "agent_state_raw": agent_state,
        "ip_state_raw": ip_state,
        "tf_state_raw": tf_state,
        "address_state_raw": address_state,
        "agent_state_norm": agent_norm,
        "ip_state_norm": ip_norm,
        "tf_state_norm": tf_norm,
        "address_state_norm": addr_norm,
        "tf_accuracy": tf_accuracy,
        "ip_match": False,
        "tf_match": False,
        "address_match": False,
        "overall_valid": False,
        "issues": []
    }

    # IP Location vs Agent State
    if agent_norm and ip_norm:
        results["ip_match"] = (agent_norm == ip_norm)
        if not results["ip_match"]:
            results["issues"].append(f"Agent state ({agent_state}) != IP location ({ip_state})")
    elif not ip_norm:
        results["issues"].append("Could not resolve IP location")

    # TrustedForm Location vs Agent State
    if tf_accuracy == "vague":
        results["issues"].append(f"TF location too vague: '{tf_state}' — skipped state match")
        results["tf_match"] = None  # Neutral — doesn't help or hurt
    elif tf_accuracy == "missing":
        results["issues"].append("No TrustedForm state data")
    elif agent_norm and tf_norm:
        results["tf_match"] = (agent_norm == tf_norm)
        if not results["tf_match"]:
            results["issues"].append(f"Agent state ({agent_state}) != TF location ({tf_state})")

    # Address State vs Agent State
    if agent_norm and addr_norm:
        results["address_match"] = (agent_norm == addr_norm)
        if not results["address_match"]:
            results["issues"].append(f"Agent state ({agent_state}) != Address state ({address_state})")
    elif not addr_norm:
        results["issues"].append("Could not extract state from address")

    # Overall validity logic
    # ANY 2 of 3 matches = valid (IP, TF, Address)
    # If TF is vague, it doesn't count against
    match_count = 0
    total_checks = 0

    if ip_norm:
        total_checks += 1
        if results["ip_match"]: match_count += 1

    if tf_norm and tf_accuracy != "vague":
        total_checks += 1
        if results["tf_match"]: match_count += 1

    if addr_norm:
        total_checks += 1
        if results["address_match"]: match_count += 1

    # Need at least 2 checks and at least 1 match, or if only 1 check available, it must match
    if total_checks >= 2:
        results["overall_valid"] = (match_count >= 2) or (match_count >= 1 and total_checks == 2)
    elif total_checks == 1:
        results["overall_valid"] = (match_count == 1)
    else:
        results["overall_valid"] = True  # No data to validate against

    return results

# ═══════════════════════════════════════════════════════════════════════════════
#                           FETCH LEADS
# ═══════════════════════════════════════════════════════════════════════════════

def strip_html_tags(text):
    if not text:
        return ""
    clean = re.sub(r'<[^>]+>', '', str(text))
    return html.unescape(clean).strip()

def extract_tf_cert_url(html_link):
    if not html_link:
        return None
    match = re.search('href="([^"]+)"', str(html_link))
    if not match:
        match = re.search("href='([^']+)'", str(html_link))
    return match.group(1) if match else None

def convert_to_pkt(timestamp_str):
    if not timestamp_str or str(timestamp_str).strip() in ('', 'null', 'undefined'):
        return None
    try:
        dt = datetime.strptime(str(timestamp_str).strip(), "%Y-%m-%d %H:%M:%S")
        pkt_dt = dt + timedelta(hours=5)
        return pkt_dt.strftime("%Y-%m-%d %I:%M:%S %p")
    except:
        return None

def fetch_leads_by_phone(phone, cookie):
    if not cookie:
        return {"error": "No cookie configured. Edit COOKIE_VALUE in the script."}

    headers = dict(session.headers)
    if USE_FULL_COOKIE_HEADER:
        headers["Cookie"] = cookie.replace("Cookie: ", "").strip()
    else:
        headers["Cookie"] = cookie.strip()

    params = {
        "draw": "1",
        "order[0][column]": "0",
        "order[0][dir]": "desc",
        "start": "0",
        "length": "100",
        "search[value]": phone,
        "search[regex]": "false",
    }

    try:
        resp = session.get(DASHBOARD_URL, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        leads = []
        for row in data.get("data", []):
            if len(row) < 18:
                continue
            tf_location = strip_html_tags(row[15])
            tf_state = extract_state_from_location(tf_location)
            tf_accuracy = classify_tf_state(tf_location)
            address_state = extract_state_from_address(row[8])
            timestamp_raw = row[13] if row[13] else ""

            leads.append({
                "id": row[0],
                "service": row[1],
                "first_name": row[2],
                "last_name": row[3],
                "email": row[4],
                "phone_masked": row[5],
                "zipcode": row[6],
                "state": row[7],
                "address": row[8],
                "flag": row[9],
                "jornaya_uuid": row[10],
                "tf_cert_link": extract_tf_cert_url(row[11]),
                "landing_page": extract_tf_cert_url(row[12]),
                "timestamp": str(timestamp_raw).strip(),
                "timestamp_pkt": convert_to_pkt(timestamp_raw),
                "td_ip": row[14],
                "tf_location": tf_location,
                "tf_state": tf_state,
                "tf_accuracy": tf_accuracy,
                "address_state": address_state,
                "badge": strip_html_tags(row[16]),
                "duration": row[17],
            })

        return {"leads": leads, "total": data.get("recordsTotal", 0), "filtered": data.get("recordsFiltered", 0)}

    except requests.exceptions.HTTPError as e:
        if resp.status_code == 403:
            return {"error": "Access denied (403). Your cookie may have expired. Copy a fresh Cookie from DevTools."}
        return {"error": f"HTTP {resp.status_code}: {str(e)}"}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
#                           HTML TEMPLATE
# ═══════════════════════════════════════════════════════════════════════════════

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Jornaya Lead Dashboard 3D — Domain Detective</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        /* Light Mode Theme */
        html[data-theme="light"] {
            --bg-gradient: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 50%, #e2e8f0 100%);
            --bg-primary: #ffffff;
            --bg-secondary: rgba(241, 245, 249, 0.6);
            --bg-tertiary: rgba(226, 232, 240, 0.4);
            --text-primary: #1e293b;
            --text-secondary: #64748b;
            --text-tertiary: #94a3b8;
            --border-color: rgba(15, 23, 42, 0.1);
            --accent: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
            --shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            --shadow-lg: 0 20px 50px rgba(0, 0, 0, 0.15);
            --table-row-even: rgba(15, 23, 42, 0.02);
            --table-hover: rgba(59, 130, 246, 0.06);
        }
        
        /* Dark Mode Theme (default) */
        html[data-theme="dark"] {
            --bg-gradient: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #312e81 100%);
            --bg-primary: rgba(30, 41, 59, 0.6);
            --bg-secondary: rgba(30, 41, 59, 0.4);
            --bg-tertiary: rgba(15, 23, 42, 0.5);
            --text-primary: #e2e8f0;
            --text-secondary: #cbd5e1;
            --text-tertiary: #94a3b8;
            --border-color: rgba(255, 255, 255, 0.05);
            --accent: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            --shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            --shadow-lg: 0 20px 50px rgba(0, 0, 0, 0.5);
            --table-row-even: rgba(255, 255, 255, 0.02);
            --table-hover: rgba(102, 126, 234, 0.08);
        }
        
        body {
            background: var(--bg-gradient);
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            font-size: 15px;
            color: var(--text-primary);
            font-weight: 500;
            line-height: 1.5;
            overflow-x: hidden;
            min-height: 100vh;
            transition: background 0.4s cubic-bezier(0.4, 0, 0.2, 1), color 0.3s ease;
        }

        /* 3D Background particles effect */
        body::before {
            content: '';
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: 
                radial-gradient(circle at 20% 80%, rgba(120, 119, 198, 0.15) 0%, transparent 50%),
                radial-gradient(circle at 80% 20%, rgba(255, 119, 198, 0.1) 0%, transparent 50%),
                radial-gradient(circle at 40% 40%, rgba(99, 102, 241, 0.08) 0%, transparent 40%);
            pointer-events: none;
            z-index: 0;
        }

        .top-bar {
            background: var(--bg-primary);
            backdrop-filter: blur(20px) saturate(180%);
            -webkit-backdrop-filter: blur(20px) saturate(180%);
            border-bottom: 2px solid var(--border-color);
            color: var(--text-primary);
            padding: 16px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: var(--shadow);
            position: sticky;
            top: 0;
            z-index: 100;
            transition: all 0.3s ease;
        }
        .top-bar h1 { 
            font-size: 1.5rem; 
            font-weight: 800; 
            letter-spacing: -0.3px;
            background: var(--accent);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .theme-toggle {
            background: linear-gradient(135deg, rgba(102, 126, 234, 0.2), rgba(240, 147, 251, 0.2));
            border: 2px solid rgba(102, 126, 234, 0.3);
            color: var(--text-primary);
            width: 48px; height: 48px;
            border-radius: 14px;
            cursor: pointer;
            display: flex; align-items: center; justify-content: center;
            font-size: 1.3rem;
            transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 0 4px 20px rgba(0,0,0,0.15);
            position: relative;
            overflow: hidden;
        }
        .theme-toggle::before {
            content: '';
            position: absolute;
            inset: 0;
            background: linear-gradient(45deg, rgba(255,255,255,0.1), transparent);
            opacity: 0;
            transition: opacity 0.3s ease;
        }
        .theme-toggle:hover { 
            transform: translateY(-3px) scale(1.1);
            box-shadow: 0 8px 30px rgba(102, 126, 234, 0.4);
            background: linear-gradient(135deg, rgba(102, 126, 234, 0.4), rgba(240, 147, 251, 0.3));
        }
        .theme-toggle:hover::before {
            opacity: 1;
        }
        .theme-toggle:active {
            transform: translateY(-1px) scale(1.05);
        }
        .container { 
            max-width: 100%; 
            margin: 0 auto; 
            padding: 20px;
            position: relative;
            z-index: 1;
        }

        /* 3D Search Card */
        .search-card {
            background: rgba(30, 41, 59, 0.6);
            backdrop-filter: blur(20px) saturate(180%);
            -webkit-backdrop-filter: blur(20px) saturate(180%);
            border-radius: 16px;
            padding: 24px 28px;
            margin-bottom: 24px;
            box-shadow: 
                0 8px 32px rgba(0,0,0,0.3),
                0 0 0 1px rgba(255,255,255,0.05),
                inset 0 1px 0 rgba(255,255,255,0.1);
            display: flex;
            gap: 14px;
            align-items: center;
            flex-wrap: wrap;
            border: 1px solid rgba(255,255,255,0.05);
            transform-style: preserve-3d;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }
        .search-card:hover {
            box-shadow: 
                0 12px 40px rgba(0,0,0,0.4),
                0 0 0 1px rgba(255,255,255,0.08),
                inset 0 1px 0 rgba(255,255,255,0.15);
        }
        .search-card input {
            flex: 1;
            min-width: 200px;
            max-width: 350px;
            padding: 12px 18px;
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            font-size: 16px;
            font-weight: 500;
            color: #e2e8f0;
            outline: none;
            transition: all 0.3s ease;
            box-shadow: inset 0 2px 4px rgba(0,0,0,0.2);
        }
        .search-card input::placeholder { color: #64748b; }
        .search-card input:focus { 
            border-color: #667eea; 
            box-shadow: 0 0 0 3px rgba(102,126,234,0.2), inset 0 2px 4px rgba(0,0,0,0.2);
            background: rgba(15, 23, 42, 0.8);
        }
        .btn-validate {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 12px 32px;
            border-radius: 12px;
            font-weight: 600;
            font-size: 16px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.3s ease;
            white-space: nowrap;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
            position: relative;
            overflow: hidden;
        }
        .btn-validate::before {
            content: '';
            position: absolute;
            top: 0; left: -100%;
            width: 100%; height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
            transition: left 0.5s;
        }
        .btn-validate:hover::before { left: 100%; }
        .btn-validate:hover:not(:disabled) { 
            transform: translateY(-2px); 
            box-shadow: 0 8px 25px rgba(102, 126, 234, 0.6);
        }
        .btn-validate:disabled { opacity: 0.6; cursor: not-allowed; }
        .spinner {
            display: inline-block; width: 14px; height: 14px;
            border: 2px solid rgba(255,255,255,0.3);
            border-radius: 50%;
            border-top-color: white;
            animation: spin 0.8s linear infinite;
            margin-left: 8px;
            vertical-align: middle;
        }
        @keyframes spin { to { transform: rotate(360deg); } }

        /* Quick Mode Toggle - 3D Switch */
        .mode-toggle {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-left: auto;
            font-size: 14px;
            font-weight: 600;
            color: #94a3b8;
            cursor: pointer;
            user-select: none;
        }
        .mode-toggle input { display: none; }
        .switch {
            width: 44px; height: 24px;
            background: rgba(255,255,255,0.1);
            border-radius: 12px;
            position: relative;
            transition: all 0.3s ease;
            box-shadow: inset 0 2px 4px rgba(0,0,0,0.3);
            border: 1px solid rgba(255,255,255,0.1);
        }
        .switch::after {
            content: '';
            position: absolute;
            width: 18px; height: 18px;
            background: linear-gradient(135deg, #fff 0%, #e2e8f0 100%);
            border-radius: 50%;
            top: 2px; left: 2px;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        }
        .mode-toggle input:checked + .switch { 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-color: rgba(102, 126, 234, 0.5);
        }
        .mode-toggle input:checked + .switch::after { 
            transform: translateX(20px);
            background: linear-gradient(135deg, #fff 0%, #c7d2fe 100%);
        }

        /* 3D Stats Bar */
        .stats-bar {
            display: flex;
            gap: 14px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }
        .stat-chip {
            background: rgba(30, 41, 59, 0.6);
            backdrop-filter: blur(12px);
            border-radius: 14px;
            padding: 14px 20px;
            box-shadow: 
                0 4px 20px rgba(0,0,0,0.2),
                0 0 0 1px rgba(255,255,255,0.05),
                inset 0 1px 0 rgba(255,255,255,0.08);
            display: flex;
            align-items: center;
            gap: 12px;
            border: 1px solid rgba(255,255,255,0.05);
            transition: all 0.3s ease;
            transform-style: preserve-3d;
        }
        .stat-chip:hover {
            transform: translateY(-3px) translateZ(10px);
            box-shadow: 
                0 8px 30px rgba(0,0,0,0.3),
                0 0 0 1px rgba(255,255,255,0.1),
                inset 0 1px 0 rgba(255,255,255,0.15);
        }
        .stat-chip i { font-size: 1.2rem; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3)); }
        .stat-chip .stat-num { font-size: 1.5rem; font-weight: 900; color: #f1f5f9; }
        .stat-chip .stat-label { font-size: 13px; font-weight: 500; font-weight: 600; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; }

        /* Controls Bar */
        .controls-bar {
            background: rgba(30, 41, 59, 0.6);
            backdrop-filter: blur(12px);
            border-radius: 14px 14px 0 0;
            padding: 14px 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(255,255,255,0.06);
            flex-wrap: wrap;
            gap: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.2);
        }
        .entries-control { color: #94a3b8; font-size: 14px; font-weight: 600; }
        .entries-control select {
            padding: 6px 12px;
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 8px;
            font-size: 13px;
            margin: 0 6px;
            outline: none;
            color: #e2e8f0;
            cursor: pointer;
        }
        .search-control input {
            padding: 8px 16px;
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 10px;
            font-size: 13px;
            width: 220px;
            outline: none;
            color: #e2e8f0;
            transition: all 0.3s;
        }
        .search-control input:focus { 
            border-color: #667eea; 
            box-shadow: 0 0 0 3px rgba(102,126,234,0.15);
        }

        /* 3D TABLE */
        .table-outer {
            background: var(--bg-secondary);
            backdrop-filter: blur(16px);
            border-radius: 0 0 14px 14px;
            box-shadow: var(--shadow-lg);
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
            border: 1px solid var(--border-color);
            border-top: none;
            perspective: 1000px;
            transition: all 0.3s ease;
        }
        .table-outer::-webkit-scrollbar { height: 8px; }
        .table-outer::-webkit-scrollbar-track { background: rgba(15,23,42,0.3); border-radius: 4px; }
        .table-outer::-webkit-scrollbar-thumb { background: rgba(102,126,234,0.4); border-radius: 4px; }
        .table-outer::-webkit-scrollbar-thumb:hover { background: rgba(102,126,234,0.6); }

        table {
            width: 100%;
            min-width: 1400px;
            border-collapse: separate;
            border-spacing: 0;
            font-size: 15px;
        }
        thead th {
            background: var(--bg-primary);
            color: var(--text-secondary);
            font-weight: 600;
            text-align: left;
            padding: 14px 16px;
            border-bottom: 2px solid var(--accent);
            white-space: nowrap;
            cursor: pointer;
            user-select: none;
            position: sticky;
            top: 0;
            z-index: 10;
            font-size: 13px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            transition: all 0.3s ease;
        }
        thead th:hover { 
            background: var(--bg-secondary);
            color: var(--text-primary);
        }
        thead th i { margin-left: 6px; font-size: 10px; color: #64748b; }
        tbody tr {
            border-bottom: 1px solid var(--border-color);
            transition: all 0.2s ease;
        }
        tbody tr:hover { 
            background: var(--table-hover);
            transform: scale(1.002);
            box-shadow: 0 2px 15px rgba(0,0,0,0.1);
        }
        tbody td {
            padding: 14px 18px;
            color: var(--text-primary);
            font-weight: 500;
            vertical-align: middle;
            white-space: nowrap;
            border-bottom: 1px solid var(--border-color);
            transition: color 0.3s ease;
        }
        tbody tr:nth-child(even) { background: var(--table-row-even); }
        tbody tr:nth-child(even):hover { background: var(--table-hover); }

        .svc-badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            white-space: nowrap;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
            border: 1px solid;
        }
        .link-blue { 
            color: #60a5fa; 
            text-decoration: none; 
            font-weight: 700;
            transition: all 0.2s;
        }
        .link-blue:hover { 
            color: #93c5fd; 
            text-decoration: underline;
            text-shadow: 0 0 8px rgba(96, 165, 250, 0.5);
        }
        .domain-link {
            display: inline-block;
            padding: 8px 14px;
            border-radius: 10px;
            font-size: 16px;
            font-weight: 500;
            white-space: nowrap;
            text-decoration: none;
            cursor: pointer;
            border: 1px solid;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
            font-weight: 700;
            letter-spacing: 0.3px;
        }
        .domain-link:hover {
            box-shadow: 0 4px 20px rgba(0,0,0,0.3), 0 0 15px rgba(102, 126, 234, 0.2);
            transform: translateY(-2px) scale(1.02);
            font-weight: 600;
        }
        .domain-link i { margin-right: 6px; }
        .badge-yes {
            display: inline-block;
            background: linear-gradient(135deg, #10b981 0%, #059669 100%);
            color: white;
            padding: 3px 12px;
            border-radius: 12px;
            font-size: 13px;
            font-weight: 800;
            box-shadow: 0 2px 8px rgba(16, 185, 129, 0.3);
        }
        .state-cell { display: flex; align-items: center; gap: 8px; }
        .state-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; box-shadow: 0 0 8px currentColor; }
        .state-dot.valid { background: #10b981; color: #10b981; }
        .state-dot.invalid { background: #ef4444; color: #ef4444; }
        .state-dot.unknown { background: #64748b; color: #64748b; }

        .pagination-bar {
            background: rgba(30, 41, 59, 0.6);
            backdrop-filter: blur(12px);
            border-radius: 14px;
            padding: 16px 24px;
            margin-top: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 
                0 4px 20px rgba(0,0,0,0.2),
                0 0 0 1px rgba(255,255,255,0.05);
            flex-wrap: wrap;
            gap: 12px;
            border: 1px solid rgba(255,255,255,0.05);
        }
        .showing-info { color: #94a3b8; font-size: 14px; font-weight: 600; }
        .pagination { display: flex; gap: 6px; flex-wrap: wrap; }
        .pagination button {
            padding: 8px 14px;
            border: 1px solid rgba(255,255,255,0.1);
            background: rgba(15, 23, 42, 0.5);
            color: #cbd5e1;
            border-radius: 10px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        .pagination button:hover:not(:disabled) { 
            background: rgba(102, 126, 234, 0.2); 
            border-color: rgba(102, 126, 234, 0.4);
            transform: translateY(-1px);
        }
        .pagination button.active { 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
            color: white; 
            border-color: transparent;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
        }
        .pagination button:disabled { opacity: 0.4; cursor: not-allowed; }

        .detail-row td {
            padding: 0;
            background: rgba(15, 23, 42, 0.5);
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        .detail-panel {
            padding: 24px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }
        .detail-card {
            background: rgba(30, 41, 59, 0.6);
            backdrop-filter: blur(12px);
            border-radius: 16px;
            padding: 20px;
            border: 1px solid rgba(255,255,255,0.06);
            box-shadow: 
                0 4px 20px rgba(0,0,0,0.2),
                inset 0 1px 0 rgba(255,255,255,0.08);
            transition: all 0.3s ease;
        }
        .detail-card:hover {
            transform: translateY(-2px);
            box-shadow: 
                0 8px 30px rgba(0,0,0,0.3),
                0 0 0 1px rgba(255,255,255,0.1),
                inset 0 1px 0 rgba(255,255,255,0.12);
        }
        .detail-card h4 {
            font-size: 13px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #94a3b8;
            margin-bottom: 16px;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .detail-item {
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            font-size: 15px;
            font-weight: 600;
            gap: 14px;
        }
        .detail-item:last-child { border-bottom: none; }
        .detail-label { color: #94a3b8; font-weight: 500; flex-shrink: 0; }
        .detail-value { color: #f1f5f9; font-weight: 700; text-align: right; word-break: break-word; }
        .detail-value.success { color: #34d399; }
        .detail-value.error { color: #f87171; }
        .detail-value.warn { color: #fbbf24; }
        .refresh-btn {
            background: rgba(102, 126, 234, 0.2);
            border: 1px solid rgba(102, 126, 234, 0.3);
            color: #c7d2fe;
            padding: 6px 14px;
            border-radius: 8px;
            font-size: 13px; font-weight: 500;
            cursor: pointer;
            margin-left: auto;
            transition: all 0.2s;
            font-weight: 500;
        }
        .refresh-btn:hover { 
            background: rgba(102, 126, 234, 0.3); 
            box-shadow: 0 0 15px rgba(102, 126, 234, 0.3);
        }
        .refresh-btn:disabled { opacity: 0.5; cursor: not-allowed; }

        .no-results { text-align: center; padding: 80px 20px; color: #64748b; }
        .no-results i { font-size: 4rem; margin-bottom: 20px; display: block; opacity: 0.5; }
        .alert {
            padding: 16px 20px;
            border-radius: 12px;
            font-size: 16px;
            font-weight: 500;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 20px;
            backdrop-filter: blur(12px);
            border: 1px solid;
        }
        .alert-danger { 
            background: rgba(220, 38, 38, 0.1); 
            color: #f87171; 
            border-color: rgba(220, 38, 38, 0.2);
        }
        .alert-warn { 
            background: rgba(245, 158, 11, 0.1); 
            color: #fbbf24; 
            border-color: rgba(245, 158, 11, 0.2);
        }
        .alert-info { 
            background: rgba(59, 130, 246, 0.1); 
            color: #60a5fa; 
            border-color: rgba(59, 130, 246, 0.2);
        }

        .expand-icon {
            cursor: pointer;
            color: #64748b;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            font-size: 13px; font-weight: 500;
            display: inline-block;
        }
        .expand-icon:hover { color: #667eea; }
        .expand-icon.rotated { transform: rotate(90deg); }

        .scroll-hint {
            font-size: 13px; font-weight: 500;
            color: var(--text-secondary);
            text-align: center;
            padding: 10px;
            background: var(--bg-tertiary);
            border-bottom: 1px solid var(--border-color);
            display: none;
            transition: all 0.3s ease;
        }
        @media (max-width: 1400px) {
            .scroll-hint { display: block; }
        }

        /* Bigger font for key columns */
        .col-service { font-size: 16px !important; font-weight: 700; }
        .col-state { font-size: 16px !important; font-weight: 800; }
        
        /* Enhanced Font Sizing for Names, Email, and URLs */
        .col-fname { font-size: 18px !important; font-weight: 700; color: var(--text-primary); letter-spacing: 0.3px; }
        .col-lname { font-size: 18px !important; font-weight: 700; color: var(--text-primary); letter-spacing: 0.3px; }
        .col-email { font-size: 11px !important; font-weight: 500; color: var(--text-secondary); letter-spacing: -0.2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 140px; }
        .col-tf-url { font-size: 14px !important; font-weight: 700; }
        .col-page-url { font-size: 14px !important; font-weight: 700; }

        /* TF vs State comparison badge */
        .tf-compare {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 3px 10px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 800;
            margin-top: 4px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.2);
        }
        .tf-compare.match { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
        .tf-compare.mismatch { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }
        .tf-compare.vague { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }
        .tf-compare.missing { background: rgba(100, 116, 139, 0.15); color: #94a3b8; border: 1px solid rgba(100, 116, 139, 0.3); }

        /* 3D Animations */
        @keyframes float {
            0%, 100% { transform: translateY(0px); }
            50% { transform: translateY(-6px); }
        }
        @keyframes glow {
            0%, 100% { box-shadow: 0 0 20px rgba(102, 126, 234, 0.2); }
            50% { box-shadow: 0 0 40px rgba(102, 126, 234, 0.4); }
        }
        .stat-chip:nth-child(1) { animation: float 4s ease-in-out infinite; }
        .stat-chip:nth-child(2) { animation: float 4s ease-in-out infinite 0.5s; }
        .stat-chip:nth-child(3) { animation: float 4s ease-in-out infinite 1s; }
        .stat-chip:nth-child(4) { animation: float 4s ease-in-out infinite 1.5s; }

        /* Responsive */
        @media (max-width: 768px) {
            .search-card { flex-direction: column; align-items: stretch; }
            .search-card input { max-width: 100%; }
            .mode-toggle { margin-left: 0; margin-top: 10px; }
            .stats-bar { justify-content: center; }
        }
    </style>
</head>
<body>
    <div class="top-bar">
        <h1><i class="fas fa-bolt me-2"></i>Jornaya Lead Dashboard <small style="opacity:0.7;font-size:0.7em;font-weight:400">— 3D Domain Detective</small></h1>
        <button class="theme-toggle" id="themeToggle" title="Switch Between Dark and Light Mode (Dark Mode Enabled)">
            <i class="fas fa-sun" id="themeIcon"></i>
        </button>
    </div>

    <div class="container">
        <div class="search-card">
            <input type="text" id="phoneInput" placeholder="Enter phone number (e.g., 555-123-4567)">
            <button class="btn-validate" id="validateBtn">
                <span id="btnText">Search Leads</span>
                <span class="spinner d-none" id="spinner"></span>
            </button>
            <label class="mode-toggle" title="Skip IP geolocation for instant results">
                <input type="checkbox" id="quickMode" checked>
                <span class="switch"></span>
                <span>Quick Mode <small style="opacity:0.6">(no IP lookup)</small></span>
            </label>
        </div>

        <div id="statsArea"></div>
        <div id="resultsArea"></div>
    </div>


    <script>
        const serviceColors = {
            "home improvement": { bg: "#E8F4F8", text: "#0891B2", border: "#06B6D4" },
            "solar": { bg: "#FEF3C7", text: "#D97706", border: "#F59E0B" },
            "roofing": { bg: "#FEE2E2", text: "#DC2626", border: "#EF4444" },
            "hvac": { bg: "#E9D5FF", text: "#9333EA", border: "#A855F7" },
            "plumbing": { bg: "#DBEAFE", text: "#1D4ED8", border: "#3B82F6" },
            "electrical": { bg: "#F0FDF4", text: "#16A34A", border: "#22C55E" },
            "insurance": { bg: "#F5E6FF", text: "#C026D3", border: "#D946EF" },
            "windows": { bg: "#E0F2FE", text: "#0369A1", border: "#0284C7" },
            "gutter": { bg: "#F0E7FF", text: "#7C3AED", border: "#8B5CF6" },
            "painting": { bg: "#FEE4E2", text: "#EA580C", border: "#F97316" },
            "flooring": { bg: "#E6F5FF", text: "#1E40AF", border: "#3B82F6" },
            "landscaping": { bg: "#DFFCF0", text: "#059669", border: "#10B981" },
            "patio": { bg: "#FFF4E6", text: "#C2410C", border: "#F97316" },
            "garage": { bg: "#F3E8FF", text: "#A855F7", border: "#D946EF" },
            "basement": { bg: "#F5F3FF", text: "#4F46E5", border: "#6366F1" },
            "kitchen": { bg: "#FDF2F8", text: "#BE185D", border: "#EC4899" },
            "bathroom": { bg: "#E0F2FE", text: "#0369A1", border: "#0EA5E9" },
            "deck": { bg: "#FEF08A", text: "#A16207", border: "#EAB308" },
            "fence": { bg: "#D1FAE5", text: "#0D9488", border: "#14B8A6" },
            "siding": { bg: "#F8FAFC", text: "#475569", border: "#64748B" },
            "door": { bg: "#FCA5A5", text: "#7F1D1D", border: "#DC2626" },
            "water damage": { bg: "#CFFAFE", text: "#0891B2", border: "#06B6D4" },
            "foundation": { bg: "#E7E5E4", text: "#57534E", border: "#78716C" },
            "pool": { bg: "#E0F2FE", text: "#0369A1", border: "#0284C7" },
            "pest control": { bg: "#ECFDF5", text: "#047857", border: "#059669" },
            "tree service": { bg: "#ECFDF5", text: "#059669", border: "#10B981" },
            "driveway": { bg: "#F3F4F6", text: "#4B5563", border: "#6B7280" },
            "waterproofing": { bg: "#DBEAFE", text: "#1D4ED8", border: "#3B82F6" },
            "garagedoor": { bg: "#F3E8FF", text: "#7C3AED", border: "#8B5CF6" },
            "default": { bg: "#F3F4F6", text: "#6B7280", border: "#9CA3AF" }
        };

        function getServiceColors(service) {
            if (!service) return serviceColors.default;
            const lower = service.toLowerCase().replace(/\s+/g, "");
            for (const [key, colors] of Object.entries(serviceColors)) {
                if (key !== "default" && lower.includes(key.replace(/\s+/g, ""))) return colors;
            }
            return serviceColors.default;
        }

        // Enhanced Dark/Light Mode with smooth transitions
        const themeToggle = document.getElementById(\'themeToggle\');
        const themeIcon = document.getElementById(\'themeIcon\');
        const htmlEl = document.documentElement;
        
        function setTheme(theme) {
            htmlEl.setAttribute(\'data-theme\', theme);
            localStorage.setItem(\'jornaya-theme\', theme);
            
            // Update icon with smooth transition
            if (themeIcon) {
                themeIcon.style.transform = \'scale(1.2) rotate(180deg)\';
                setTimeout(() => {
                    themeIcon.className = theme === \'dark\' ? \'fas fa-sun\' : \'fas fa-moon\';
                    themeIcon.style.transform = \'scale(1) rotate(0deg)\';
                }, 200);
            }
            
            // Add visual feedback
            document.body.style.transition = \'background 0.4s cubic-bezier(0.4, 0, 0.2, 1), color 0.3s ease\';
        }
        
        // Initialize theme - default to dark
        const savedTheme = localStorage.getItem(\'jornaya-theme\');
        const initialTheme = savedTheme || (window.matchMedia(\'(prefers-color-scheme: dark)\').matches ? \'dark\' : \'dark\');
        setTheme(initialTheme);
        
        // Theme toggle event listener with smooth animation
        themeToggle.addEventListener(\'click\', () => {
            const currentTheme = htmlEl.getAttribute(\'data-theme\');
            const newTheme = currentTheme === \'dark\' ? \'light\' : \'dark\';
            setTheme(newTheme);
        });

        // State
        let allLeads = [];
        let currentPage = 1;
        let pageSize = 25;
        let sortCol = \'id\';
        let sortDir = \'desc\';
        let expandedRow = null;
        let filterTerm = \'\';

        const phoneInput = document.getElementById(\'phoneInput\');
        const validateBtn = document.getElementById(\'validateBtn\');
        const btnText = document.getElementById(\'btnText\');
        const spinner = document.getElementById(\'spinner\');
        const resultsArea = document.getElementById(\'resultsArea\');
        const statsArea = document.getElementById(\'statsArea\');
        const quickModeCheck = document.getElementById(\'quickMode\');

        function debounce(fn, ms) {
            let t;
            return (...args) => {
                clearTimeout(t);
                t = setTimeout(() => fn(...args), ms);
            };
        }

        validateBtn.addEventListener(\'click\', doSearch);
        phoneInput.addEventListener(\'keypress\', (e) => { if (e.key === \'Enter\') doSearch(); });

        async function doSearch() {
            const phone = phoneInput.value.trim();
            if (!phone) {
                phoneInput.focus();
                return;
            }

            const quickMode = quickModeCheck.checked;
            validateBtn.disabled = true;
            spinner.classList.remove(\'d-none\');
            btnText.textContent = quickMode ? \'Loading...\' : \'Looking up IPs...\';
            resultsArea.innerHTML = \'\';
            statsArea.innerHTML = \'\';
            allLeads = [];
            currentPage = 1;
            expandedRow = null;
            filterTerm = \'\';

            const startTime = performance.now();
            try {
                const url = `/api/check?phone=${encodeURIComponent(phone)}${quickMode ? \'&quick=1\' : \'\'}`;
                const resp = await fetch(url);
                const data = await resp.json();
                const elapsed = ((performance.now() - startTime) / 1000).toFixed(2);

                if (data.error) {
                    resultsArea.innerHTML = `<div class="alert alert-danger"><i class="fas fa-exclamation-circle"></i>${data.error}</div>`;
                    return;
                }

                allLeads = data.leads || [];
                if (allLeads.length === 0) {
                    resultsArea.innerHTML = `<div class="no-results"><i class="fas fa-inbox"></i><div>No leads found for this phone number.</div></div>`;
                    return;
                }

                if (quickMode) {
                    statsArea.innerHTML = `<div class="alert alert-info"><i class="fas fa-info-circle"></i>Quick Mode: IP geolocation skipped. Toggle off for full validation.</div>`;
                }
                renderStats(data.summary, elapsed, quickMode);
                renderTable();
            } catch (err) {
                resultsArea.innerHTML = `<div class="alert alert-danger"><i class="fas fa-bug"></i>Error: ${err.message}</div>`;
            } finally {
                validateBtn.disabled = false;
                spinner.classList.add(\'d-none\');
                btnText.textContent = \'Search Leads\';
            }
        }

        function renderDomainBadge(domain, fullUrl) {
            if (!domain) return '<span style="color:#9ca3af;font-size:12px;">—</span>';
            const d = domain.toLowerCase();
            let colors;
            if (d.includes('renovatefast')) {
                colors = { bg: '#E0F2FE', border: '#0284C7', text: '#0369A1', label: 'RENO' };
            } else if (d.includes('quickfixremodel')) {
                colors = { bg: '#FEF3C7', border: '#F59E0B', text: '#92400E', label: 'QUICK' };
            } else {
                colors = { bg: '#F3F4F6', border: '#9CA3AF', text: '#6B7280', label: domain.toUpperCase().substring(0,8) };
            }
            const link = fullUrl ? `<a href="${fullUrl}" target="_blank" class="link-blue" style="font-size:10px;margin-left:4px;"><i class="fas fa-external-link-alt"></i></a>` : '';
            return `<span class="domain-badge" style="background:${colors.bg};color:${colors.text};border-color:${colors.border}">
                <i class="fas fa-globe"></i> ${colors.label}
            </span>${link}`;
        }

        function extractDomain(url) {
            if (!url) return '—';
            try {
                const urlObj = new URL(url);
                const domain = urlObj.hostname.replace('www.', '');
                const domainParts = domain.split('.');
                if (domainParts.length > 1) {
                    return domainParts[0];
                }
                return domain || '—';
            } catch (e) {
                return '—';
            }
        }

        function formatDomainShort(url) {
            if (!url) return null;
            try {
                const urlObj = new URL(url);
                const hostname = urlObj.hostname.replace('www.', '');
                const parts = hostname.split('.');
                if (parts.length >= 2) {
                    const subdomain = parts[0].toLowerCase();
                    const mainDomain = parts[1].toLowerCase();
                    let shortDomain = '';
                    if (mainDomain.includes('renovatefast')) shortDomain = 'renovatefast';
                    else if (mainDomain.includes('quickfix')) shortDomain = 'quickfix';
                    else shortDomain = mainDomain;
                    return { text: `${subdomain} - ${shortDomain}`, subdomain: subdomain, domain: shortDomain };
                }
                return null;
            } catch (e) {
                return null;
            }
        }

        function getPageDomainColors(domain) {
            if (!domain || domain === '—') {
                return { bg: '#F3F4F6', border: '#9CA3AF', text: '#6B7280' };
            }
            const d = domain.toLowerCase();
            if (d.includes('renovatefast')) {
                return { bg: '#E0F2FE', border: '#0284C7', text: '#0369A1' };
            } else if (d.includes('quickfix') || d.includes('quick')) {
                return { bg: '#FEF3C7', border: '#F59E0B', text: '#92400E' };
            } else {
                return { bg: '#F3F4F6', border: '#9CA3AF', text: '#6B7280' };
            }
        }

        function renderStats(summary, elapsed, quickMode) {
            const total = summary.total_leads || 0;
            const valid = allLeads.filter(l => l.validation?.overall_valid).length;
            const renoCount = allLeads.filter(l => l.page_domain && l.page_domain.toLowerCase().includes('renovatefast')).length;
            const quickCount = allLeads.filter(l => l.page_domain && l.page_domain.toLowerCase().includes('quickfixremodel')).length;
            const invalid = allLeads.filter(l => l.validation && !l.validation.overall_valid).length;
            const noIp = allLeads.filter(l => !l.ip_geo || l.ip_geo.error).length;
            const addrMatch = allLeads.filter(l => l.validation?.address_match).length;
            const addrMissing = allLeads.filter(l => !l.address_state).length;
            statsArea.innerHTML += `
                <div class="stats-bar">
                    <div class="stat-chip"><i class="fas fa-database" style="color:#667eea"></i><div><div class="stat-num">${total}</div><div class="stat-label">Total Leads</div></div></div>
                    <div class="stat-chip"><i class="fas fa-check-circle" style="color:#10b981"></i><div><div class="stat-num">${valid}</div><div class="stat-label">Valid</div></div></div>
                    <div class="stat-chip"><i class="fas fa-times-circle" style="color:#ef4444"></i><div><div class="stat-num">${invalid}</div><div class="stat-label">Flagged</div></div></div>
                    <div class="stat-chip"><i class="fas fa-map-marker-alt" style="color:#3b82f6"></i><div><div class="stat-num">${addrMatch}</div><div class="stat-label">Addr Match</div></div></div>
                    ${!quickMode ? `<div class="stat-chip"><i class="fas fa-question-circle" style="color:#f59e0b"></i><div><div class="stat-num">${noIp}</div><div class="stat-label">No Geo</div></div></div>` : ''}
                    <div class="stat-chip"><i class="fas fa-home" style="color:#0284C7"></i><div><div class="stat-num">${renoCount}</div><div class="stat-label">RenoFast</div></div></div>
                    <div class="stat-chip"><i class="fas fa-tools" style="color:#F59E0B"></i><div><div class="stat-num">${quickCount}</div><div class="stat-label">QuickFix</div></div></div>
                    <div class="stat-chip"><i class="fas fa-stopwatch" style="color:#8b5cf6"></i><div><div class="stat-num">${elapsed}s</div><div class="stat-label">Load Time</div></div></div>
                </div>
            `;
        }

        function getFilteredLeads() {
            if (!filterTerm) return allLeads;
            const term = filterTerm.toLowerCase();
            return allLeads.filter(lead => {
                return Object.values(lead).some(v =>
                    v && String(v).toLowerCase().includes(term)
                );
            });
        }

        function sortLeads(leads) {
            return leads.sort((a, b) => {
                let av = a[sortCol] || \'\';
                let bv = b[sortCol] || \'\';
                if (typeof av === \'string\') av = av.toLowerCase();
                if (typeof bv === \'string\') bv = bv.toLowerCase();
                if (av < bv) return sortDir === \'asc\' ? -1 : 1;
                if (av > bv) return sortDir === \'asc\' ? 1 : -1;
                return 0;
            });
        }

        function renderTable() {
            let leads = getFilteredLeads();
            leads = sortLeads(leads);

            const total = leads.length;
            const startIdx = (currentPage - 1) * pageSize;
            const endIdx = Math.min(startIdx + pageSize, total);
            const pageLeads = leads.slice(startIdx, endIdx);

            let html = `
                <div class="controls-bar">
                    <div class="entries-control">
                        Show
                        <select id="entriesSelect" onchange="changePageSize(this.value)">
                            <option value="10" ${pageSize==10?\'selected\':\'\'}>10</option>
                            <option value="25" ${pageSize==25?\'selected\':\'\'}>25</option>
                            <option value="50" ${pageSize==50?\'selected\':\'\'}>50</option>
                            <option value="100" ${pageSize==100?\'selected\':\'\'}>100</option>
                        </select>
                        entries
                    </div>
                    <div class="search-control">
                        <input type="text" id="tableSearch" placeholder="Filter results..." value="${filterTerm}" oninput="debouncedFilter(this.value)">
                    </div>
                </div>
                <div class="scroll-hint"><i class="fas fa-arrows-left-right"></i> Scroll horizontally to see all columns</div>
                <div class="table-outer">
                    <table>
                        <thead>
                            <tr>
                                <th style="width:30px"></th>
                                <th>Created time</th>
                                <th>Service</th>
                                <th>First Name</th>
                                <th>Last Name</th>
                                <th>Email</th>
                                <th>Phone</th>
                                <th>Zip</th>
                                <th>State</th>
                                <th>Domain 🔗</th>
                                <th>Address</th>
                                <th>TrustedForm URL</th>
                                <th>Page URL</th>
                                <th>ip address</th>
                                <th>Session Replay</th>
                                <th>Video Time</th>
                            </tr>
                        </thead>
                        <tbody>
            `;

            pageLeads.forEach((lead, idx) => {
                const realIdx = startIdx + idx;
                const colors = getServiceColors(lead.service);
                const v = lead.validation || {};
                const ip = lead.ip_geo || {};
                const isExpanded = expandedRow === realIdx;

                let dotClass = \'unknown\';
                if (v.overall_valid === true) dotClass = \'valid\';
                else if (v.overall_valid === false) dotClass = \'invalid\';

                let ts = lead.timestamp_pkt || lead.timestamp || \'—\';
                let ipCity = ip.city || \'—\';
                let ipState = ip.state || \'—\';
                let ipAddr = lead.td_ip || \'—\';

                html += `
                                                            <tr onclick="toggleExpand(${realIdx})" style="cursor:pointer;">
                        <td><i class="fas fa-chevron-right expand-icon ${isExpanded?'rotated':''}"></i></td>
                        <td style="font-weight:600;">${ts}</td>
                        <td class="col-service"><span class="svc-badge" style="background:${colors.bg};color:${colors.text};border:1px solid ${colors.border}">${lead.service || '—'}</span></td>
                        <td class="col-fname">${lead.first_name || '—'}</td>
                        <td class="col-lname">${lead.last_name || '—'}</td>
                        <td class="col-email" title="${lead.email || ''}">${lead.email || '—'}</td>
                        <td>${lead.phone_masked || '—'}</td>
                        <td>${lead.zipcode || '—'}</td>
                        <td class="col-state">
                            <div class="state-cell">
                                <span class="state-dot ${dotClass}"></span>
                                ${lead.state || '—'}
                            </div>
                            ${lead.tf_state ? `<div class="tf-compare ${v.tf_match ? 'match' : (v.tf_accuracy === 'vague' ? 'vague' : 'mismatch')}">
                                <i class="fas ${v.tf_match ? 'fa-check' : (v.tf_accuracy === 'vague' ? 'fa-exclamation-triangle' : 'fa-times')}"></i>
                                TF: ${lead.tf_state}
                            </div>` : ''}
                        </td>
                        <td style="text-align:center;">
                            ${(() => {
                                const url = lead.landing_page || lead.page_domain;
                                if (!url) return '<span style="color:#9ca3af;">—</span>';
                                const short = formatDomainShort(url);
                                if (short) {
                                    const colors = getPageDomainColors(short.domain);
                                    return `<a href="${url}" target="_blank" class="domain-link" style="background:${colors.bg}; color:${colors.text}; border-color:${colors.border}; font-size:13px !important; text-transform:capitalize;" title="${url}">
                                        <i class="fas fa-link"></i>${short.text}
                                    </a>`;
                                }
                                const domain = extractDomain(url);
                                const colors = getPageDomainColors(domain);
                                const displayUrl = url.length > 45 ? url.substring(0, 42) + '...' : url;
                                return `<a href="${url}" target="_blank" class="domain-link" style="background:${colors.bg}; color:${colors.text}; border-color:${colors.border};" title="${url}">
                                    <i class="fas fa-link"></i>${displayUrl}
                                </a>`;
                            })()}
                        </td>
                        <td>${lead.address || '—'}</td>
                        <td class="col-tf-url">${lead.tf_cert_link ? `<a href="${lead.tf_cert_link}" target="_blank" class="link-blue">Open Cert</a>` : '—'}</td>
                        <td class="col-page-url">${lead.landing_page ? `<a href="${lead.landing_page}" target="_blank" class="link-blue">Open Page</a>` : '—'}</td>
                        <td>${ipAddr}</td>
                        <td><span class="badge-yes">Yes</span></td>
                        <td>${lead.duration || '—'}</td>
                    </tr>
                `;

                if (isExpanded) {
                    html += renderDetailRow(lead, realIdx);
                }
            });

            html += `
                        </tbody>
                    </table>
                </div>
                <div class="pagination-bar">
                    <div class="showing-info">Showing ${startIdx + 1} to ${endIdx} of ${total} entries</div>
                    <div class="pagination">${renderPagination(total)}</div>
                </div>
            `;

            resultsArea.innerHTML = html;
        }

        function renderHeader(label, col) {
            const active = sortCol === col;
            const icon = active ? (sortDir === \'asc\' ? \'fa-sort-up\' : \'fa-sort-down\') : \'fa-sort\';
            return `<th onclick="sortBy(\'${col}\')">${label} <i class="fas ${icon}"></i></th>`;
        }

        function renderPagination(total) {
            const totalPages = Math.ceil(total / pageSize);
            if (totalPages <= 1) return \'\';

            let btns = \'\';
            btns += `<button onclick="goPage(${currentPage - 1})" ${currentPage === 1 ? \'disabled\' : \'\'}>Previous</button>`;

            const maxVisible = 5;
            let startPage = Math.max(1, currentPage - Math.floor(maxVisible / 2));
            let endPage = Math.min(totalPages, startPage + maxVisible - 1);
            if (endPage - startPage < maxVisible - 1) startPage = Math.max(1, endPage - maxVisible + 1);

            if (startPage > 1) btns += `<button onclick="goPage(1)">1</button>${startPage > 2 ? \'<span style="padding:6px 8px;color:#9ca3af;">...</span>\' : \'\'}`;

            for (let i = startPage; i <= endPage; i++) {
                btns += `<button class="${i === currentPage ? \'active\' : \'\'}" onclick="goPage(${i})">${i}</button>`;
            }

            if (endPage < totalPages) btns += `${endPage < totalPages - 1 ? \'<span style="padding:6px 8px;color:#9ca3af;">...</span>\' : \'\'}<button onclick="goPage(${totalPages})">${totalPages}</button>`;

            btns += `<button onclick="goPage(${currentPage + 1})" ${currentPage === totalPages ? \'disabled\' : \'\'}>Next</button>`;
            return btns;
        }

        function renderDetailRow(lead, idx) {
            const v = lead.validation || {};
            const ip = lead.ip_geo || {};
            const hasError = ip.error ? true : false;
            const isQuick = ip.source === "quick-mode";
            return `
                <tr class="detail-row">
                    <td colspan="16">>
                        <div class="detail-panel">
                            <div class="detail-card">
                                <h4><i class="fas fa-user"></i>Lead Info</h4>
                                <div class="detail-item"><span class="detail-label">ID</span><span class="detail-value">${lead.id || '—'}</span></div>
                                <div class="detail-item"><span class="detail-label">First Name</span><span class="detail-value">${lead.first_name || '—'}</span></div>
                                <div class="detail-item"><span class="detail-label">Last Name</span><span class="detail-value">${lead.last_name || '—'}</span></div>
                                <div class="detail-item"><span class="detail-label">Email</span><span class="detail-value">${lead.email || '—'}</span></div>
                                <div class="detail-item"><span class="detail-label">Phone</span><span class="detail-value">${lead.phone_masked || '—'}</span></div>
                                <div class="detail-item"><span class="detail-label">Address</span><span class="detail-value">${lead.address || '—'}</span></div>
                                <div class="detail-item"><span class="detail-label">Zip Code</span><span class="detail-value">${lead.zipcode || '—'}</span></div>
                                <div class="detail-item"><span class="detail-label">Flag</span><span class="detail-value">${lead.flag || '—'}</span></div>
                            </div>
                            <div class="detail-card">
                                <h4><i class="fas fa-clock"></i>Submission Details</h4>
                                <div class="detail-item"><span class="detail-label">Service</span><span class="detail-value">${lead.service || '—'}</span></div>
                                <div class="detail-item"><span class="detail-label">Server Time</span><span class="detail-value">${lead.timestamp || '—'}</span></div>
                                <div class="detail-item"><span class="detail-label">Created Time (PKT +5h)</span><span class="detail-value">${lead.timestamp_pkt || '—'}</span></div>
                                <div class="detail-item"><span class="detail-label">Duration</span><span class="detail-value">${lead.duration || '—'}</span></div>
                                <div class="detail-item"><span class="detail-label">Badge</span><span class="detail-value">${lead.badge || '—'}</span></div>
                                <div class="detail-item"><span class="detail-label">Session Replay</span><span class="detail-value"><span class="badge-yes">Yes</span></span></div>
                            </div>
                            <div class="detail-card">
                                <h4><i class="fas fa-globe"></i>Domain & URLs</h4>
                                <div class="detail-item"><span class="detail-label">Page Domain</span><span class="detail-value">${renderDomainBadge(lead.page_domain, lead.landing_page)}</span></div>
                                <div class="detail-item"><span class="detail-label">Landing Page</span><span class="detail-value">${lead.landing_page ? `<a href="${lead.landing_page}" target="_blank" class="link-blue">${lead.landing_page}</a>` : '—'}</span></div>
                                <div class="detail-item"><span class="detail-label">TrustedForm Cert</span><span class="detail-value">${lead.tf_cert_link ? `<a href="${lead.tf_cert_link}" target="_blank" class="link-blue">Open Certificate</a>` : '—'}</span></div>
                                <div class="detail-item"><span class="detail-label">LeadID Token</span><span class="detail-value" style="font-size:11px;word-break:break-all;">${lead.jornaya_uuid || '—'}</span></div>
                            </div>
                            <div class="detail-card">
                                <h4><i class="fas fa-network-wired"></i>IP Geolocation
                                    ${!isQuick ? `<button class="refresh-btn" onclick="event.stopPropagation();refreshIp(${idx})" ${!lead.td_ip ? 'disabled' : ''}>
                                        <i class="fas fa-sync-alt"></i> Refresh
                                    </button>` : ''}
                                </h4>
                                <div class="detail-item"><span class="detail-label">IP Address</span><span class="detail-value">${lead.td_ip || '—'}</span></div>
                                <div class="detail-item"><span class="detail-label">City</span><span class="detail-value">${ip.city || '—'}</span></div>
                                <div class="detail-item"><span class="detail-label">State</span><span class="detail-value">${ip.state || '—'}</span></div>
                                <div class="detail-item"><span class="detail-label">Country</span><span class="detail-value">${ip.country || '—'}</span></div>
                                <div class="detail-item"><span class="detail-label">ISP</span><span class="detail-value">${ip.isp || '—'}</span></div>
                                <div class="detail-item"><span class="detail-label">Source</span><span class="detail-value ${ip.source === 'failed' || ip.source === 'quick-mode' ? 'error' : 'success'}">${ip.source || '—'}</span></div>
                                ${hasError && !isQuick ? `<div class="detail-item"><span class="detail-label">Error</span><span class="detail-value error">${ip.error}</span></div>` : ''}
                                ${isQuick ? `<div class="detail-item"><span class="detail-label">Note</span><span class="detail-value warn">IP lookup skipped (Quick Mode)</span></div>` : ''}
                            </div>
                            <div class="detail-card">
                                <h4><i class="fas fa-clipboard-check"></i>State Validation</h4>
                                <div class="detail-item"><span class="detail-label">Agent State</span><span class="detail-value">${v.agent_state_norm || v.agent_state_raw || '—'}</span></div>
                                <div class="detail-item"><span class="detail-label">Address State</span><span class="detail-value ${v.address_match ? 'success' : (v.address_state_norm ? 'error' : 'warn')}">${v.address_state_norm || v.address_state_raw || '—'}</span></div>
                                <div class="detail-item"><span class="detail-label">IP Geo State</span><span class="detail-value ${v.ip_match ? 'success' : 'error'}">${v.ip_state_norm || '—'}</span></div>
                                <div class="detail-item"><span class="detail-label">TF Location</span><span class="detail-value">${v.tf_state_raw || '—'}</span></div>
                                <div class="detail-item"><span class="detail-label">TF State</span><span class="detail-value ${v.tf_match ? 'success' : 'error'}">${v.tf_state_norm || '—'}</span></div>
                                <div class="detail-item"><span class="detail-label">TF Accuracy</span><span class="detail-value ${lead.tf_accuracy === 'exact' ? 'success' : (lead.tf_accuracy === 'vague' ? 'warn' : 'error')}">${lead.tf_accuracy || '—'}</span></div>
                                <div class="detail-item"><span class="detail-label">Addr Match</span><span class="detail-value ${v.address_match ? 'success' : (v.address_state_norm ? 'error' : 'warn')}">${v.address_match ? '✓ Match' : (v.address_state_norm ? '✗ Mismatch' : '—')}</span></div>
                                <div class="detail-item"><span class="detail-label">IP Match</span><span class="detail-value ${v.ip_match ? 'success' : 'error'}">${v.ip_match ? '✓ Match' : '✗ Mismatch'}</span></div>
                                <div class="detail-item"><span class="detail-label">TF Match</span><span class="detail-value ${v.tf_match ? 'success' : 'error'}">${v.tf_match ? '✓ Match' : '✗ Mismatch'}</span></div>
                                <div class="detail-item"><span class="detail-label">Overall</span><span class="detail-value ${v.overall_valid ? 'success' : 'error'}">${v.overall_valid ? '✓ VALID' : '✗ NEEDS REVIEW'}</span></div>
                            </div>
                        </div>
                    </td>
                </tr>
            `;
        }

        window.sortBy = function(col) {
            if (sortCol === col) sortDir = sortDir === \'asc\' ? \'desc\' : \'asc\';
            else { sortCol = col; sortDir = \'asc\'; }
            renderTable();
        };
        window.goPage = function(p) {
            const maxPage = Math.ceil(getFilteredLeads().length / pageSize);
            if (p < 1 || p > maxPage) return;
            currentPage = p;
            renderTable();
        };
        window.changePageSize = function(size) {
            pageSize = parseInt(size);
            currentPage = 1;
            renderTable();
        };
        window.toggleExpand = function(idx) {
            expandedRow = expandedRow === idx ? null : idx;
            renderTable();
        };

        window.refreshIp = async function(idx) {
            const lead = allLeads[idx];
            if (!lead || !lead.td_ip) return;

            const btn = document.querySelector(`button[onclick*="refreshIp(${idx})"]`);
            if (btn) { btn.disabled = true; btn.innerHTML = \'<i class="fas fa-spinner fa-spin"></i>\'; }

            try {
                const resp = await fetch(`/api/refresh_ip?ip=${encodeURIComponent(lead.td_ip)}`);
                const data = await resp.json();
                lead.ip_geo = data;
                lead.validation = data.validation;
                renderTable();
            } catch (err) {
                if (btn) { btn.disabled = false; btn.innerHTML = \'<i class="fas fa-sync-alt"></i> Refresh\'; }
            }
        };

        const debouncedFilter = debounce((term) => {
            filterTerm = term;
            currentPage = 1;
            renderTable();
        }, 200);
        window.debouncedFilter = debouncedFilter;

    </script>
</body>
</html>
"""

# ═══════════════════════════════════════════════════════════════════════════════
#                              FLASK ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/api/check")
def api_check():
    phone = request.args.get("phone", "").strip()
    quick = request.args.get("quick", "") == "1"

    if not phone:
        return jsonify({"error": "Phone number required"}), 400

    phone_clean = re.sub(r"[^\d]", "", phone)
    if len(phone_clean) < 3:
        return jsonify({"error": "Phone number too short"}), 400

    result = fetch_leads_by_phone(phone, COOKIE_VALUE)
    if "error" in result:
        return jsonify({"error": result["error"]})

    leads = result.get("leads", [])
    if leads:
        leads = enrich_leads(leads, skip_geo=quick)

    service_counts = Counter(lead["service"] for lead in leads if lead.get("service"))
    summary = {
        "total_leads": len(leads),
        "services": [{"service": svc, "count": cnt} for svc, cnt in service_counts.most_common()]
    }

    return jsonify({
        "leads": leads,
        "summary": summary,
        "total": result.get("total", 0),
        "filtered": result.get("filtered", 0)
    })

@app.route("/api/refresh_ip")
def api_refresh_ip():
    ip = request.args.get("ip", "").strip()
    if not ip:
        return jsonify({"error": "IP required"}), 400

    ip_cache.clear_key(ip)
    geo = get_ip_location(ip, force_refresh=True)
    geo["validation"] = check_state_match(None, geo.get("state"), None)

    return jsonify(geo)

if __name__ == "__main__":
    print("=" * 72)
    print("   JORNAYA LEAD DASHBOARD v5.5 — Starting server...")
    print("=" * 72)
    print("   🔍 PAGE DOMAIN: auto-detects renovatefast vs quickfixremodel\n   ⚡ ipinfo.io PRIMARY: reliable individual + batch lookups")
    print("   📦 BATCH: ipinfo.io/batch for bulk + parallel fallback")
    print("   🏠 ADDRESS STATE: extracted from street address for cross-check")
    print("   🚀 Quick Mode: skip IP geo for instant results")
    print("   ↔️  Horizontal scroll enabled")
    print("   🔍 TF location state matching + vague detection")
    print("   💾 TTL cache + 5-provider fallback chain")
    if not COOKIE_VALUE.strip():
        print("   ⚠️  WARNING: COOKIE_VALUE is empty.")
    else:
        print("   ✓ Cookie configured.")
    print("   Open: http://localhost:5000")
    print("=" * 72)
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=ENABLE_THREADING)
