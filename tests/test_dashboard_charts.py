"""Chart builders are pure: no Streamlit, no database."""
from decimal import Decimal
import unittest

from src.dashboard import charts, theme


class HorizontalBarTests(unittest.TestCase):
    def test_decimals_become_floats_and_nulls_are_not_drawn_as_zero(self):
        rows = [{'name': 'A', 'pct': Decimal('33.33')}, {'name': 'B', 'pct': None}]
        spec = charts.hbars(rows, 'name', 'pct', reference=Decimal('50')).to_dict()
        data = next(iter(spec['datasets'].values()))
        self.assertEqual([row['category'] for row in data], ['A'])
        self.assertEqual(data[0]['value'], 33.33)

    def test_colours_stay_with_their_row_when_a_null_row_is_dropped(self):
        rows = [{'name': 'A', 'pct': None}, {'name': 'B', 'pct': 1}]
        spec = charts.hbars(rows, 'name', 'pct', colors=['#111111', '#222222']).to_dict()
        self.assertEqual(next(iter(spec['datasets'].values()))[0]['fill'], '#222222')

    def test_only_null_values_produce_no_chart(self):
        self.assertIsNone(charts.hbars([{'name': 'A', 'pct': None}], 'name', 'pct'))

    def test_sort_ranks_high_to_low_but_default_keeps_given_order(self):
        rows = [{'name': 'A', 'pct': 1}, {'name': 'B', 'pct': 2}]
        order = lambda chart: chart.to_dict()['encoding']['y']['sort']
        self.assertEqual(order(charts.hbars(rows, 'name', 'pct')), ['A', 'B'])
        self.assertEqual(order(charts.hbars(rows, 'name', 'pct', sort=True)), ['B', 'A'])


class OutcomeChartTests(unittest.TestCase):
    def test_outcomes_read_best_to_worst_with_fixed_colours(self):
        rows = charts.order_outcomes([{'final_result': name} for name in ('Fail', 'Pass', 'Withdrawn', 'Distinction')])
        self.assertEqual([row['final_result'] for row in rows], list(charts.OUTCOME_COLORS))
        self.assertEqual(charts.outcome_colors([{'final_result': 'Fail'}]), [charts.OUTCOME_COLORS['Fail']])

    def test_weekly_lines_empty_and_partial_outcomes(self):
        self.assertIsNone(charts.weekly_lines([]))
        rows = [{'week_no': 0, 'final_result': 'Pass', 'avg_clicks': Decimal('2.5')}]
        self.assertTrue(charts.weekly_lines(rows, selected_week=0).to_dict()['layer'])

    def test_assessment_decay_needs_two_coursework_points(self):
        exam = {'record_pct': 10, 'effective_due_day': 200, 'assessment_type': 'Exam'}
        first = {'record_pct': Decimal('77.2'), 'effective_due_day': 20, 'assessment_type': 'TMA'}
        self.assertIsNone(charts.assessment_decay([exam, first]))
        self.assertTrue(charts.assessment_decay([first, dict(first, effective_due_day=40)]).to_dict()['layer'])


class SegmentedBarTests(unittest.TestCase):
    def test_zero_parts_draw_nothing_and_names_are_escaped(self):
        html = theme.segmented_bar([('<b>', 3, '#000', '#fff'), ('Empty', 0, '#111', '#fff')])
        self.assertNotIn('Empty', html)
        self.assertNotIn('<b>', html)
        self.assertEqual(theme.segmented_bar([('A', 0, '#000', '#fff')]), '')

    def test_narrow_block_prints_no_label_but_legend_keeps_the_count(self):
        html = theme.segmented_bar([('Big', 99, '#000', '#fff'), ('Tiny', 1, '#111', '#fff')])
        self.assertIn('Tiny · 1', html)
        self.assertNotIn('>1.0%<', html)


if __name__ == '__main__':
    unittest.main()
