"""Pure selection/validation helpers; no database or Streamlit dependency."""
from dataclasses import dataclass


SCREENS = {
    'overview': 'Tổng quan kết quả',
    'registration': 'Đăng ký và ngày hủy',
    'engagement': 'Tương tác học tập',
    'assessments': 'Bài đánh giá',
    'signals': 'Tín hiệu hồi cứu',
}
WEEK_SCREENS = frozenset(('engagement', 'signals'))


class FilterError(ValueError):
    pass


@dataclass(frozen=True)
class Filters:
    domain: str | None = None
    module: str | None = None
    presentation: str | None = None
    week: int | None = None


def options(offerings, field, domain=None, module=None):
    if field not in ('domain', 'code_module', 'code_presentation'):
        raise FilterError('Chiều lọc không hợp lệ.')
    return sorted({row[field] for row in offerings
                   if (domain is None or row['domain'] == domain)
                   and (module is None or row['code_module'] == module)})


def normalize(offerings, filters):
    """Reset obsolete children before creating widgets (never silently in SQL)."""
    domain = filters.domain if filters.domain in options(offerings, 'domain') else None
    module = filters.module if filters.module in options(offerings, 'code_module', domain) else None
    presentation = filters.presentation if filters.presentation in options(
        offerings, 'code_presentation', domain, module) else None
    return Filters(domain, module, presentation, filters.week)


def selected_offerings(offerings, filters):
    if normalize(offerings, filters) != filters:
        raise FilterError('Bộ lọc đã thay đổi hoặc không còn hợp lệ. Hãy chọn lại.')
    return [row for row in offerings
            if (filters.domain is None or row['domain'] == filters.domain)
            and (filters.module is None or row['code_module'] == filters.module)
            and (filters.presentation is None or row['code_presentation'] == filters.presentation)]


def available_weeks(offerings):
    return list(range(max((row['length_weeks'] for row in offerings), default=0)))


def default_week(weeks):
    return 7 if 7 in weeks else (weeks[0] if weeks else None)


def validate(offerings, filters, screen):
    if screen not in SCREENS:
        raise FilterError('Màn hình không hợp lệ.')
    selected = selected_offerings(offerings, filters)
    if screen in WEEK_SCREENS:
        if type(filters.week) is not int or filters.week not in available_weeks(selected):
            raise FilterError('Tuần không hợp lệ trong phạm vi lần mở đã chọn.')
    elif filters.week is not None:
        raise FilterError('Màn hình này không áp dụng bộ lọc tuần.')
    return selected


def week_label(week):
    return f'Tuần {week} — tuần thứ {week + 1}, ngày {7 * week}–{7 * week + 6}'
