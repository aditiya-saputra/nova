from datetime import datetime, timedelta, timezone


def get_timestamp():
    return datetime.now(timezone.utc)


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
