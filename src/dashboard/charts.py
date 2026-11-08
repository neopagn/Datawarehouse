"""Altair chart builders. Pure presentation: records in, chart specs out, no I/O."""
import altair as alt
import pandas as pd


FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'
INK, INK_2, INK_3 = '#0b0b0b', '#52514e', '#6f6d68'
GRID, BASELINE, SURFACE = '#ebeae4', '#c3c2b7', '#ffffff'
ACCENT = '#2a78d6'
# Validated with --pairs all on #ffffff. Two pairs sit in the 6-8 CVD band, so every
# use also carries an axis label, legend or table: colour is never the only channel.
OUTCOME_COLORS = {'Distinction': '#2a78d6', 'Pass': '#1baf7a', 'Withdrawn': '#eda100', 'Fail': '#e34948'}
ORDINAL_BLUES = ('#86b6ef', '#3987e5', '#104281')
ROW_HEIGHT = 34


def _style(chart, height):
    # fit-x: width follows the card, height stays literal, so a caption above the
    # plot adds space instead of squeezing the bars into each other.
    return (chart.properties(height=height, width='container', background='transparent',
                             autosize=alt.AutoSizeParams(type='fit-x', contains='padding'),
                             padding={'left': 2, 'right': 8, 'top': 6, 'bottom': 4})
            .configure(font=FONT)
            .configure_view(stroke=None)
            .configure_axis(labelColor=INK_2, titleColor=INK_3, labelFontSize=12, titleFontSize=11.5,
                            titleFontWeight='normal', grid=False, domain=False, ticks=False)
            .configure_legend(labelColor=INK_2, labelFontSize=12, title=None, orient='top',
                              symbolStrokeWidth=3, symbolSize=120, columnPadding=16, padding=2))


def hbars(records, category, value, *, unit='', decimals=1, reference=None, reference_label='',
          colors=None, sort=False, tooltip=(), x_max=None):
    """Horizontal bars with value at the tip; the labels replace an x axis.

    colors: list of hexes aligned to the rows; None draws one colour for every bar.
    reference: a vertical rule, e.g. the scope-wide rate the bars are compared with.
    """
    keep = [index for index, row in enumerate(records) if row.get(value) is not None]
    if not keep:
        return None
    rows = [records[index] for index in keep]
    # PostgreSQL NUMERIC arrives as Decimal; Vega needs plain floats.
    reference = None if reference is None else float(reference)
    data = pd.DataFrame({
        'category': [str(row[category]) for row in rows],
        'value': [float(row[value]) for row in rows],
        'fill': [colors[index] for index in keep] if colors else [ACCENT] * len(rows),
    })
    for name, _, _ in tooltip:
        data[name] = [None if row.get(name) is None else float(row[name]) for row in rows]
    if sort:
        data = data.sort_values('value', ascending=False, kind='stable')
    limit = x_max or max(data['value'].max(), reference or 0) * 1.14 or 1
    height = ROW_HEIGHT * len(data) + 6
    shared = alt.FacetedEncoding(
        y=alt.Y('category:O', sort=list(data['category']), title=None,
                axis=alt.Axis(labelLimit=240, labelPadding=8)),
        x=alt.X('value:Q', title=None, axis=None, scale=alt.Scale(domain=[0, limit], nice=False)),
    )
    tips = [alt.Tooltip('category:N', title=' '), alt.Tooltip('value:Q', title='Giá trị', format=f',.{decimals}f')]
    tips += [alt.Tooltip(f'{name}:Q', title=title, format=fmt) for name, title, fmt in tooltip]
    layers = [alt.Chart().mark_bar(cornerRadiusEnd=4, size=20).encode(
        color=alt.Color('fill:N', scale=None), tooltip=tips)]
    if reference is not None:
        # The rule's caption sits above the plot so it can never collide with a bar.
        mark = pd.DataFrame({'value': [reference], 'text': [f'{reference_label} {reference:.1f}{unit}']})
        layers.append(alt.Chart(mark).mark_rule(color=INK_2, strokeWidth=1).encode(
            x='value:Q', y=alt.value(-3), y2=alt.value(height)))
        layers.append(alt.Chart(mark).mark_text(align='center', color=INK_2, fontSize=11.5).encode(
            x='value:Q', y=alt.value(-11), text='text:N'))
    label = alt.Chart().transform_calculate(label=f"format(datum.value, ',.{decimals}f') + '{unit}'")
    # A surface-coloured halo keeps a value legible where the reference rule crosses it.
    layers.append(label.mark_text(align='left', dx=6, fontSize=12.5, fontWeight=600, color=SURFACE,
                                  stroke=SURFACE, strokeWidth=4).encode(text='label:N'))
    layers.append(label.mark_text(align='left', dx=6, color=INK, fontSize=12.5, fontWeight=600).encode(text='label:N'))
    return _style(alt.LayerChart(data=data, encoding=shared, layer=layers), height)


def outcome_colors(rows, field='final_result'):
    return [OUTCOME_COLORS.get(row[field], ACCENT) for row in rows]


def order_outcomes(rows, field='final_result'):
    ranks = {name: index for index, name in enumerate(OUTCOME_COLORS)}
    return sorted(rows, key=lambda row: ranks.get(row[field], len(ranks)))


def weekly_lines(records, selected_week=None, height=340):
    """Outcome lines over course weeks, with a nearest-week crosshair tooltip."""
    rows = [row for row in records if row.get('avg_clicks') is not None]
    if not rows:
        return None
    data = pd.DataFrame([{'week': row['week_no'], 'outcome': row['final_result'],
                          'clicks': float(row['avg_clicks'])} for row in rows])
    present = [name for name in OUTCOME_COLORS if name in set(data['outcome'])]
    color = alt.Color('outcome:N', sort=present, legend=alt.Legend(symbolType='stroke'),
                      scale=alt.Scale(domain=present, range=[OUTCOME_COLORS[name] for name in present]))
    x = alt.X('week:Q', title='Tuần của khóa', axis=alt.Axis(tickMinStep=1, format='d', labelPadding=6),
              scale=alt.Scale(nice=False, zero=False))
    y = alt.Y('clicks:Q', title='Click TB / lượt / tuần', scale=alt.Scale(zero=True),
              axis=alt.Axis(grid=True, gridColor=GRID, tickCount=5, labelPadding=6))
    wide = data.pivot(index='week', columns='outcome', values='clicks').reset_index()
    wide.columns = [str(column) for column in wide.columns]
    nearest = alt.selection_point(name='hover', fields=['week'], nearest=True, on='pointerover',
                                  empty=False, clear='pointerout')
    hover_tips = [alt.Tooltip('week:Q', title='Tuần')] + [
        alt.Tooltip(f'{name}:Q', title=name, format='.1f') for name in present]
    layers = [alt.Chart(data).mark_line(strokeWidth=2, strokeCap='round', strokeJoin='round').encode(x=x, y=y, color=color)]
    if selected_week is not None and selected_week in set(data['week']):
        layers.insert(0, alt.Chart(pd.DataFrame({'week': [selected_week]})).mark_rule(
            color=BASELINE, strokeWidth=1).encode(x=x))
    layers.append(alt.Chart(wide).mark_rule(color=INK_3, strokeWidth=1).encode(
        x=x, opacity=alt.condition(nearest, alt.value(.75), alt.value(0)), tooltip=hover_tips).add_params(nearest))
    layers.append(alt.Chart(data).mark_point(filled=True, size=70, stroke='white', strokeWidth=2, opacity=1).encode(
        x=x, y=y, color=color, opacity=alt.condition(nearest, alt.value(1), alt.value(0))))
    return _style(alt.layer(*layers).resolve_scale(color='shared'), height)


def assessment_decay(records, height=280):
    """Share of enrollments with a record per assessment, in due-date order, for one offering."""
    rows = [row for row in records if row.get('record_pct') is not None
            and row.get('effective_due_day') is not None and row.get('assessment_type') != 'Exam']
    if len(rows) < 2:
        return None
    data = pd.DataFrame([{'due': row['effective_due_day'], 'pct': float(row['record_pct']),
                          'type': row['assessment_type'], 'id': row.get('id_assessment')} for row in rows])
    types = sorted(set(data['type']))
    color = alt.Color('type:N', legend=alt.Legend(symbolType='stroke') if len(types) > 1 else None,
                      scale=alt.Scale(domain=types, range=['#2a78d6', '#eda100'][:len(types)]))
    x = alt.X('due:Q', title='Ngày hạn (tính từ khai giảng)', axis=alt.Axis(labelPadding=6, tickCount=8),
              scale=alt.Scale(nice=False, zero=False, padding=14))
    y = alt.Y('pct:Q', title='Bản ghi / lượt ghi danh (%)', scale=alt.Scale(domain=[0, 100]),
              axis=alt.Axis(grid=True, gridColor=GRID, tickCount=5, labelPadding=6))
    base = alt.Chart(data).encode(x=x, y=y, color=color)
    tips = [alt.Tooltip('id:N', title='Mã bài'), alt.Tooltip('type:N', title='Loại'),
            alt.Tooltip('due:Q', title='Ngày hạn'), alt.Tooltip('pct:Q', title='Tỷ lệ', format='.1f')]
    return _style(base.mark_line(strokeWidth=2, strokeCap='round')
                  + base.mark_point(filled=True, size=80, stroke='white', strokeWidth=2, opacity=1).encode(tooltip=tips),
                  height)
