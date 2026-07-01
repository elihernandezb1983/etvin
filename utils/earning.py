import re
from datetime import datetime, timezone

_WORD_RE = re.compile(r"\S+")


def effective_words(
    content: str,
    last_content: str | None,
    last_at: str | None,
    now: datetime,
) -> int:
    words = _WORD_RE.findall(content)
    if not words:
        return 0

    if last_content and content.strip().lower() == last_content.strip().lower():
        return 0

    if last_at:
        try:
            prev = datetime.fromisoformat(last_at)
            if prev.tzinfo is None:
                prev = prev.replace(tzinfo=timezone.utc)
            delta = (now - prev).total_seconds()
            if delta < 1:
                return 0
            if delta < 2 and len(words) < 4:
                return 0
        except ValueError:
            pass

    if len(words) == 1:
        return 1

    lowered = [w.lower() for w in words]
    if len(set(lowered)) == 1 and len(lowered) >= 4:
        return 0

    if len(words) >= 15:
        unique_ratio = len(set(lowered)) / len(lowered)
        if unique_ratio < 0.25:
            return max(1, int(len(words) * 0.5))

    compact = content.replace(" ", "")
    if len(compact) > 8 and len(set(compact)) <= 2:
        return 0

    return len(words)
