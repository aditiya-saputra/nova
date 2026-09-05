import pytz
from datetime import datetime, timedelta, timezone

# WIB = Asia/Jakarta (UTC+7, tanpa DST).
WIB = pytz.timezone("Asia/Jakarta")


def get_timestamp():
    # Storage tetap UTC agar perbandingan (TTL, expired) konsisten antar zona.
    return datetime.now(timezone.utc)


def to_wib(dt):
    """Konversi datetime aware apa pun ke zona WIB; naive dianggap UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(WIB)


def to_wib_iso(value=None):
    dt = to_wib(value if value is not None else get_timestamp())
    return dt.isoformat()


def format_wib(value, fmt="%d %b %Y %H:%M"):
    """Format ISO string / epoch / datetime ke string WIB untuk ditampilkan."""
    if isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(value, tz=timezone.utc)
    elif isinstance(value, datetime):
        dt = value
    else:
        dt = from_iso(str(value))
    if dt is None:
        return "N/A"
    return to_wib(dt).strftime(fmt)


def to_iso(dt):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def from_iso(iso_string):
    try:
        dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        return dt
    except (ValueError, AttributeError):
        return None


def is_expired(expiry_string):
    expiry = from_iso(expiry_string)
    if not expiry:
        return True
    return get_timestamp() > expiry


def time_until_expiry(expiry_string):
    expiry = from_iso(expiry_string)
    if not expiry:
        return timedelta(0)
    delta = expiry - get_timestamp()
    return max(delta, timedelta(0))


def format_duration(td):
    total_seconds = int(td.total_seconds())
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")

    return " ".join(parts) if parts else "0m"


def is_recent(timestamp_string, seconds=3600):
    ts = from_iso(timestamp_string)
    if not ts:
        return False
    delta = get_timestamp() - ts
    return delta.total_seconds() <= seconds
