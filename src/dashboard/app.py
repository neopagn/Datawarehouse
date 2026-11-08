"""Launch from repo root: python -m streamlit run src/dashboard/app.py."""
from decimal import Decimal
from pathlib import Path
import re
import sys

# Streamlit executes a file, not a package; resolve imports independently of cwd.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from src.dashboard import charts, service, theme
from src.dashboard.filters import (Filters, SCREENS, WEEK_SCREENS, available_weeks,
                                   default_week, options, selected_offerings, week_label)


SNAPSHOT_NOTE = (
    'Snapshot gồm lượt ghi danh theo quy ước baseline, kể cả tuần không click. '
    'Ngày đăng ký không rõ không chặn snapshot; ngày hủy không rõ/không áp dụng không tạo mốc loại. '
    'Vì vậy một lượt có kết quả cuối Withdrawn nhưng thiếu ngày hủy vẫn có thể xuất hiện. '
    'Tuần cuối giữ cutoff tròn 7*w+6, không cắt theo ngày cuối khóa.'
)
RETROSPECTIVE_NOTE = 'Tương quan hồi cứu với kết quả cuối khóa; không phải mô hình dự báo hoặc bằng chứng hiệu quả can thiệp.'
PRESENTATION_NOTE = 'Chỉ so sánh các lần mở (presentation) trong cùng một module; không dùng mã lần mở để so sánh chéo module.'
EXAM_NOTE = 'Không so sánh điểm Exam ngoài CCC/DDD: chỉ CCC và DDD có điểm Exam được ghi nhận. Thiếu điểm ở module khác không có nghĩa là điểm 0 hoặc không nộp bài.'

COLUMN_LABELS = {
    'domain': 'Lĩnh vực', 'code_module': 'Module', 'code_presentation': 'Lần mở',
    'label': 'Nhóm phân tích', 'enrollments': 'Lượt ghi danh', 'students': 'Sinh viên phân biệt',
    'at_risk': 'Lượt Fail + Withdrawn', 'withdrawn': 'Lượt Withdrawn',
    'risk_pct': 'Fail + Withdrawn (%)', 'withdrawn_pct': 'Withdrawn (%)',
    'previous_attempts': 'Số lần học trước', 'phase': 'Giai đoạn', 'share_pct': 'Tỷ trọng (%)',
    'final_result': 'Kết quả cuối khóa', 'avg_clicks': 'Click TB / lượt / tuần',
    'zero_click': 'Lượt không click', 'zero_click_pct': 'Không click (%)',
    'avg_missed': 'Bài bỏ lỡ lũy kế TB', 'activity_group': 'Nhóm tài nguyên',
    'activity_type': 'Loại hoạt động', 'clicks': 'Tổng click',
    'assessment_type': 'Loại bài', 'assessments': 'Số bài đánh giá',
    'records': 'Bản ghi (gồm banked)', 'banked': 'Bản ghi banked',
    'scored': 'Bản ghi có điểm', 'avg_score': 'Điểm trung bình',
    'below_40': 'Bản ghi dưới 40', 'below_40_pct': 'Dưới 40 (%)',
    'eligible_late': 'Bản ghi đủ điều kiện tính trễ', 'late': 'Bản ghi trễ', 'late_pct': 'Trễ (%)',
    'id_assessment': 'Mã bài đánh giá', 'effective_due_day': 'Ngày hạn hiệu lực',
    'is_due_estimated': 'Hạn ước tính', 'is_formative': 'Bài formative',
    'has_recorded_results': 'Có kết quả ghi nhận', 'weight': 'Trọng số (%)',
    'record_pct': 'Bản ghi / lượt ghi danh (%)', 'due_note': 'Nguồn ngày hạn',
    'result_note': 'Tình trạng ghi nhận', 'missed_bucket': 'Số bài bỏ lỡ lũy kế',
}
PERCENT_COLUMNS = {label for key, label in COLUMN_LABELS.items() if key.endswith('_pct')}
PLAIN_COLUMNS = {COLUMN_LABELS[key] for key in ('id_assessment', 'effective_due_day')}
WEIGHT_COLUMN = COLUMN_LABELS['weight']
ATTEMPT_LABELS = {0: '0 lần', 1: '1 lần', 2: 'Từ 2 lần trở lên'}
MISSED_LABELS = {0: '0 bài', 1: '1 bài', 2: 'Từ 2 bài trở lên'}
ENROLLMENT_TIP = (('enrollments', 'Lượt ghi danh', ',.0f'),)


def number(value, digits=0):
    if value is None:
        return '—'
    return f'{value:,.{digits}f}'


def metric(label, value, digits=0, percent=False):
    st.metric(label, number(value, digits) + ('%' if percent and value is not None else ''))


def frame(records):
    return pd.DataFrame([{key: float(value) if isinstance(value, Decimal) else value
                          for key, value in row.items()} for row in records])


def clean_phase(text):
    # SQL prefixes "1. " only to sort buckets; readers never need the digit.
    return re.sub(r'^\d+\.\s*', '', text)


def display_frame(records, hide=()):
    data = frame(records).drop(columns=['grouping', *hide], errors='ignore')
    for column, labels in (('missed_bucket', MISSED_LABELS), ('previous_attempts', ATTEMPT_LABELS)):
        if column in data:
            data[column] = data[column].map(labels)
    if 'phase' in data:
        data['phase'] = data['phase'].map(clean_phase)
    return data.rename(columns=COLUMN_LABELS)


def styled(data):
    """Thousands separators, % suffix, and an em dash wherever a value was not observed."""
    formats = {}
    for column in data.columns:
        if column in PERCENT_COLUMNS:
            formats[column] = '{:.2f}%'
        elif column == WEIGHT_COLUMN:
            formats[column] = '{:g}'
        elif (column not in PLAIN_COLUMNS and pd.api.types.is_numeric_dtype(data[column])
              and not pd.api.types.is_bool_dtype(data[column])):
            whole = data[column].dropna().mod(1).eq(0).all()
            formats[column] = '{:,.0f}' if whole else '{:,.2f}'
    # The grid ignores Styler na_rep on numeric cells, so columns with gaps become text.
    data = data.copy()
    for column in data.columns[data.isna().any()]:
        pattern = formats.pop(column, '{}')
        data[column] = data[column].astype(object).map(lambda value: '—' if pd.isna(value) else pattern.format(value))
    return data.style.format(formats)


def table(records, hide=(), collapsed=True):
    """The chart leads; its exact figures stay one click away in a table view."""
    if not records:
        st.info('Không có bản ghi trong phạm vi đã chọn.')
        return
    data = styled(display_frame(records, hide))
    if collapsed:
        with st.expander('Xem bảng số liệu'):
            st.dataframe(data, hide_index=True, width='stretch')
    else:
        st.dataframe(data, hide_index=True, width='stretch')


def draw(chart):
    if chart is not None:
        # theme=None: the validated palette and surface come from charts.py alone.
        st.altair_chart(chart, theme=None, width='stretch')


def headline(text):
    st.markdown(theme.insight(text), unsafe_allow_html=True)


def choice(label, key, values, format_func=None):
    # Reset before widget creation; never mutate a widget value after creation.
    if st.session_state.get(key) not in values:
        st.session_state[key] = values[0]
    return st.sidebar.selectbox(label, values, key=key, format_func=format_func or (lambda value: value),
                                placeholder='Tất cả')


def show_error(error):
    st.error(str(error))
    if error.code == 'connection':
        st.caption('Kiểm tra PostgreSQL và PGHOST/PGPORT/PGUSER/PGDATABASE theo docs/dashboard_runbook.md. Ứng dụng không tự start hoặc reload kho.')
    st.button('Thử lại', key='retry')


def render_overview(data):
    summary = data['summary']
    if summary['risk_pct'] is not None:
        headline(f"{summary['risk_pct']:.1f}% lượt ghi danh kết thúc bằng Fail hoặc Withdrawn.")
    columns = st.columns(4)
    with columns[0]:
        metric('Lượt ghi danh', summary['enrollments'])
    with columns[1]:
        metric('Sinh viên phân biệt', summary['students'])
    with columns[2]:
        metric('Kết quả Fail + Withdrawn', summary['risk_pct'], 2, True)
    with columns[3]:
        metric('Kết quả Withdrawn', summary['withdrawn_pct'], 2, True)
    fail = summary['at_risk'] - summary['withdrawn']
    success = summary['enrollments'] - summary['at_risk']
    st.markdown(theme.segmented_bar([
        ('Distinction + Pass', success, charts.OUTCOME_COLORS['Distinction'], '#ffffff'),
        ('Withdrawn', summary['withdrawn'], charts.OUTCOME_COLORS['Withdrawn'], '#0b0b0b'),
        ('Fail', fail, charts.OUTCOME_COLORS['Fail'], '#ffffff'),
    ]), unsafe_allow_html=True)
    st.caption('Các tỷ lệ dùng mẫu số lượt ghi danh, không phải số sinh viên phân biệt. Đây là kết quả toàn vòng đời, không phải dự báo rủi ro.')

    st.subheader('Q1 — Tỷ lệ Fail + Withdrawn theo cấp phân tích')
    levels = {3: 'Lĩnh vực', 1: 'Module', 0: 'Lần mở module'}
    level = st.selectbox('Mức phân tích', list(levels), format_func=levels.get, key='rollup_level')
    parts = {3: ('domain',), 1: ('code_module',), 0: ('code_module', 'code_presentation')}[level]
    records = [dict(row, label=' · '.join(str(row[key]) for key in parts if row[key] is not None))
               for row in data['rollup'] if row['grouping'] == level]
    with st.container(border=True):
        # Presentations stay in module order: ranking them would invite cross-module comparison.
        draw(charts.hbars(records, 'label', 'risk_pct', unit='%', reference=summary['risk_pct'],
                          reference_label='Toàn phạm vi', sort=level != 0, tooltip=ENROLLMENT_TIP))
    hidden = {3: ('code_module', 'code_presentation'), 1: ('code_presentation',), 0: ()}[level]
    table(records, hide=('label', *hidden))
    st.caption('Distinct count và tỷ lệ được tính lại ở từng mức, không cộng các nhóm con.')

    st.subheader('Q1 — Theo nhóm sinh viên')
    dimensions = {'imd': 'Mức IMD (0–10% là khu vực khó khăn nhất)', 'education': 'Trình độ đầu vào', 'disability': 'Khuyết tật'}
    dimension = st.selectbox('Chiều phân nhóm (không phải bộ lọc chung)', list(dimensions),
                             format_func=dimensions.get, key='demographic')
    with st.container(border=True):
        draw(charts.hbars(data['breakdowns'][dimension], 'label', 'risk_pct', unit='%', reference=summary['risk_pct'],
                          reference_label='Toàn phạm vi', tooltip=ENROLLMENT_TIP))
    table(data['breakdowns'][dimension])
    st.caption('Unknown là nhóm dữ liệu thiếu thật, không phải Tất cả.')

    st.subheader('Q5 — Số lần học trước và kết quả')
    attempts = [dict(row, bucket=ATTEMPT_LABELS[row['previous_attempts']]) for row in data['attempts']]
    with st.container(border=True):
        draw(charts.hbars(attempts, 'bucket', 'risk_pct', unit='%', tooltip=ENROLLMENT_TIP,
                          colors=[charts.ORDINAL_BLUES[row['previous_attempts']] for row in attempts]))
    table(data['attempts'])
    st.caption('Tỷ lệ theo mẫu số riêng của từng nhóm số lần học trước.')


def render_registration(data):
    summary = data['summary']
    early = sum(row['enrollments'] for row in data['cancellations']
                if clean_phase(row['phase']) in ('Trước khai giảng', 'Ngày 0'))
    if summary['known_unregistration']:
        share = 100 * early / summary['known_unregistration']
        headline(f'{share:.1f}% ngày hủy đã biết rơi vào trước hoặc đúng ngày khai giảng.')
    columns = st.columns(4)
    for column, label, key in zip(columns, ('Lượt ghi danh', 'Kết quả Withdrawn', 'Ngày hủy đã biết', 'Ngày hủy không rõ'),
                                  ('enrollments', 'withdrawn', 'known_unregistration', 'unknown_unregistration')):
        with column:
            metric(label, summary[key])
    st.caption(f"Ngày hủy không áp dụng: {number(summary['na_unregistration'])}. Final_result và việc có ngày hủy là hai khái niệm khác nhau.")
    st.subheader('Q2 — Phân bố ngày hủy đã biết')
    st.caption('Mẫu số của tỷ trọng chỉ gồm lượt ghi danh có ngày hủy đã biết, bao gồm cả nhãn cuối khác Withdrawn. Không biểu diễn toàn bộ Withdrawn.')
    cancellations = [dict(row, label=clean_phase(row['phase'])) for row in data['cancellations']]
    with st.container(border=True):
        draw(charts.hbars(cancellations, 'label', 'share_pct', unit='%', tooltip=ENROLLMENT_TIP))
    table(data['cancellations'])
    st.subheader('Thời điểm đăng ký và tỷ lệ Withdrawn')
    # n in the label: a tiny group's extreme rate must not read like a large one.
    registrations = [dict(row, label=f"{clean_phase(row['phase'])} (n={row['enrollments']:,})") for row in data['registrations']]
    with st.container(border=True):
        draw(charts.hbars(registrations, 'label', 'withdrawn_pct', unit='%', reference=summary['withdrawn_pct'],
                          reference_label='Toàn phạm vi', tooltip=ENROLLMENT_TIP))
    table(data['registrations'])
    st.caption('Các tỷ lệ có mẫu số riêng trong từng nhóm đăng ký; không có bộ lọc tuần/as-of ở màn hình này.')


def render_engagement(data):
    summary = data['summary']
    clicks = {row['final_result']: row['avg_clicks'] for row in data['outcomes']}
    if clicks.get('Distinction') and clicks.get('Fail'):
        headline(f"Trong tuần này, nhóm Distinction click gấp {clicks['Distinction'] / clicks['Fail']:.1f} lần nhóm Fail.")
    columns = st.columns(4)
    with columns[0]:
        metric('Lượt ghi danh trong snapshot', summary['enrollments'])
    with columns[1]:
        metric('Click TB / lượt / tuần', summary['avg_clicks'], 2)
    with columns[2]:
        metric('Không click trong tuần', summary['zero_click_pct'], 2, True)
    with columns[3]:
        metric('Bài bỏ lỡ lũy kế TB', summary['avg_missed'], 2)
    st.info(SNAPSHOT_NOTE)

    st.subheader('Q3 — Click theo tuần và kết quả cuối khóa')
    st.caption(RETROSPECTIVE_NOTE)
    with st.container(border=True):
        draw(charts.weekly_lines(data['trend'], st.session_state.get('week')))
    st.caption('Chỉ gồm các tuần mà mọi lần mở đã chọn đều có; bỏ điểm dưới 20 lượt ghi danh. Vạch xám là tuần đang chọn. '
               'Nhóm Withdrawn thu hẹp dần vì sinh viên rời snapshot khi hủy.')

    st.subheader('Q3 — Snapshot của tuần đang chọn')
    outcomes = charts.order_outcomes(data['outcomes'])
    columns = st.columns(2)
    for column, value, title, unit in ((columns[0], 'avg_clicks', 'Click TB / lượt / tuần', ''),
                                       (columns[1], 'zero_click_pct', 'Không click trong tuần', '%')):
        with column, st.container(border=True):
            st.markdown(f'**{title}**')
            draw(charts.hbars(outcomes, 'final_result', value, unit=unit, tooltip=ENROLLMENT_TIP,
                              colors=charts.outcome_colors(outcomes)))
    table(data['outcomes'])

    st.subheader('Tài nguyên — nhóm và loại hoạt động')
    st.caption('Click sự kiện trong tuần từ aggregate; cohort khác snapshot cuối tuần, có thể gồm click của lượt đã hủy. '
               'Không chia tổng này cho số lượt snapshot; không lọc demographic/outcome.')
    groups = sorted({row['activity_group'] for row in data['activity']})
    group = st.selectbox('Nhóm tài nguyên (chỉ phần tài nguyên)', [None] + groups, placeholder='Tất cả nhóm',
                         format_func=lambda value: value or 'Tất cả nhóm', key='activity_group')
    records = [row for row in data['activity']
               if (row['grouping'] == 1 if group is None else row['grouping'] == 0 and row['activity_group'] == group)]
    with st.container(border=True):
        draw(charts.hbars(records, 'activity_group' if group is None else 'activity_type', 'clicks', decimals=0,
                          sort=True, tooltip=(('share_pct', 'Tỷ trọng (%)', '.1f'),)))
    table(records, hide=('activity_type',) if group is None else ())
    st.caption('Tỷ trọng luôn tính trên tổng click của phạm vi và tuần đang chọn, kể cả khi xem chi tiết một nhóm.')


def render_assessments(data):
    records = data['by_type']
    columns = st.columns(4)
    for column, label, key in zip(columns, ('Bài đánh giá', 'Bản ghi kết quả, gồm banked', 'Bản ghi banked', 'Bản ghi đủ điều kiện tính trễ'),
                                  ('assessments', 'records', 'banked', 'eligible_late')):
        with column:
            metric(label, sum(row[key] for row in records))
    st.subheader('Q4 — Kết quả theo loại bài')
    st.caption('Điểm TB chỉ từ điểm có giá trị, gồm banked; điểm thiếu không thành 0. Trễ chỉ tính TMA/CMA không banked. Mẫu số 0 hiển thị —, không mặc định 0%.')
    st.warning(EXAM_NOTE)
    with st.container(border=True):
        draw(charts.hbars(records, 'assessment_type', 'avg_score', x_max=112, tooltip=(('records', 'Bản ghi', ',.0f'),)))
    table(records, collapsed=False)

    st.subheader('Tỷ lệ có bản ghi qua từng bài')
    offerings = {(row.get('code_module'), row.get('code_presentation')) for row in data['detail']}
    decay = charts.assessment_decay(data['detail']) if len(offerings) == 1 else None
    if decay is None:
        st.caption('Chọn một module và một lần mở ở thanh bên để xem biểu đồ này; không gộp nhiều lần mở vì lịch bài khác nhau.')
    else:
        with st.container(border=True):
            draw(decay)
        st.caption('Theo thứ tự ngày hạn, không gồm Exam. Tỷ lệ gồm banked, mẫu số là mọi lượt ghi danh của lần mở. '
                   'Đường giảm dần gợi ý sinh viên bỏ dở nhưng không chứng minh nguyên nhân.')

    st.subheader('Chi tiết từng bài đánh giá')
    types = sorted({row['assessment_type'] for row in data['detail']})
    assessment_type = st.selectbox('Loại bài (chỉ bảng chi tiết)', [None] + types, placeholder='Tất cả loại',
                                   format_func=lambda value: value or 'Tất cả loại', key='assessment_type')
    detail = [dict(row, due_note='Ước tính' if row['is_due_estimated'] else 'Nguồn ghi nhận',
                   result_note='Có kết quả ghi nhận' if row['has_recorded_results'] else 'Không có kết quả được ghi nhận')
              for row in data['detail'] if assessment_type is None or row['assessment_type'] == assessment_type]
    table(detail, hide=('is_due_estimated', 'has_recorded_results'), collapsed=False)
    st.info('Bản ghi / lượt ghi danh = số bản ghi kết quả (gồm banked) / lượt ghi danh của cùng lần mở. Không đồng nghĩa nộp mới. '
            'Bài không có kết quả ghi nhận, đặc biệt Exam, không chứng minh tất cả sinh viên không nộp. '
            'Ngày hạn ước tính không phải ngày quan sát thực tế.')


def render_signals(data):
    summary = data['summary']
    rates = {row['missed_bucket']: row['risk_pct'] for row in data['buckets']}
    if rates.get(2) is not None and rates.get(0) is not None:
        headline(f'Bỏ lỡ từ 2 bài: {rates[2]:.1f}% kết thúc Fail hoặc Withdrawn, so với {rates[0]:.1f}% ở nhóm không bỏ lỡ bài nào.')
    st.warning(RETROSPECTIVE_NOTE)
    columns = st.columns(2)
    with columns[0]:
        metric('Lượt ghi danh trong snapshot', summary['enrollments'])
    with columns[1]:
        metric('Tỷ lệ nền Fail + Withdrawn trong snapshot', summary['risk_pct'], 2, True)
    st.subheader('Q6 — Bài bỏ lỡ và kết quả cuối khóa')
    buckets = [dict(row, bucket=MISSED_LABELS[row['missed_bucket']]) for row in data['buckets']]
    with st.container(border=True):
        draw(charts.hbars(buckets, 'bucket', 'risk_pct', unit='%', reference=summary['risk_pct'],
                          reference_label='Tỷ lệ nền', x_max=112, tooltip=ENROLLMENT_TIP,
                          colors=[charts.ORDINAL_BLUES[row['missed_bucket']] for row in buckets]))
    table(data['buckets'], collapsed=False)
    st.caption('Nhóm 0 bài / 1 bài / từ 2 bài trở lên là các nhóm rời rạc. Tỷ lệ theo từng nhóm; mẫu số nền là toàn bộ snapshot cùng tuần và bộ lọc, không phải toàn kho. Không xếp hạng cá nhân hoặc đề xuất can thiệp.')
    st.info(SNAPSHOT_NOTE)


RENDERERS = {
    'overview': render_overview, 'registration': render_registration, 'engagement': render_engagement,
    'assessments': render_assessments, 'signals': render_signals,
}


def main():
    st.set_page_config(page_title='OULAD Analytics', layout='wide')
    theme.apply()
    st.sidebar.markdown(theme.brand(), unsafe_allow_html=True)
    screen = st.sidebar.radio('Màn hình', list(SCREENS), format_func=SCREENS.get, key='screen', label_visibility='collapsed')
    st.header(SCREENS[screen])
    st.warning(PRESENTATION_NOTE)
    try:
        metadata = service.load_metadata()
    except service.DashboardError as error:
        show_error(error)
        return
    if not metadata.offerings:
        st.info('Kho đã công bố nhưng không có lần mở module để phân tích.')
        return
    all_label = lambda value: 'Tất cả' if value is None else value
    domain = choice('Lĩnh vực', 'domain', [None] + options(metadata.offerings, 'domain'), all_label)
    module = choice('Module', 'module', [None] + options(metadata.offerings, 'code_module', domain), all_label)
    presentation = choice('Lần mở', 'presentation',
                          [None] + options(metadata.offerings, 'code_presentation', domain, module), all_label)
    selected = selected_offerings(metadata.offerings, Filters(domain, module, presentation))
    week = None
    if screen in WEEK_SCREENS:
        weeks = available_weeks(selected)
        if not weeks:
            st.info('Không có tuần hợp lệ cho phạm vi đã chọn.')
            return
        if st.session_state.get('week') not in weeks:
            st.session_state['week'] = default_week(weeks)
        # Short form: the full wording is in the caption, and the sidebar would truncate it.
        week = choice('Tuần snapshot / hoạt động', 'week', weeks, lambda w: f'Tuần {w} · ngày {7 * w}–{7 * w + 6}')
    else:
        st.sidebar.caption('Toàn vòng đời; màn hình này không áp dụng bộ lọc tuần.')
    filters = Filters(domain, module, presentation, week)
    try:
        payload = service.load_dashboard(screen, filters, expected_run_id=metadata.run_id)
    except service.DashboardError as error:
        show_error(error)
        return
    st.caption(f"Phạm vi: {domain or 'mọi lĩnh vực'} / {module or 'mọi module'} / {presentation or 'mọi lần mở'} — {payload.selected_count} lần mở.")
    if week is not None:
        st.caption(f'{week_label(week)}; {payload.week_coverage}/{payload.selected_count} lần mở có tuần này. Không có snapshot không đồng nghĩa zero-click.')
    RENDERERS[screen](payload.tables)
    st.markdown('<div class="foot"></div>', unsafe_allow_html=True)
    st.caption(f"ETL run_id={payload.run_id} · Tải lúc {payload.loaded_at:%Y-%m-%d %H:%M:%S UTC} · Truy vấn {payload.elapsed_seconds:.3f}s · Không cache")
    st.button('Thử lại', key='retry')


if __name__ == '__main__':
    main()
