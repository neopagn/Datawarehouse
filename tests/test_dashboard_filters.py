import unittest

from src.dashboard.filters import (FilterError, Filters, available_weeks, default_week,
                                   normalize, options, selected_offerings, validate, week_label)


OFFERINGS = [
    {'offering_key': 1, 'domain': 'STEM', 'code_module': 'AAA', 'code_presentation': '2014J', 'length_weeks': 2},
    {'offering_key': 2, 'domain': 'Social Sciences', 'code_module': 'BBB', 'code_presentation': '2014J', 'length_weeks': 9},
    {'offering_key': 3, 'domain': 'STEM', 'code_module': 'AAA', 'code_presentation': '2013J', 'length_weeks': 3},
]


class FilterTests(unittest.TestCase):
    def test_cascade_resets_only_invalid_children(self):
        result = normalize(OFFERINGS, Filters('STEM', 'BBB', '2014J'))
        self.assertEqual(result, Filters('STEM', None, '2014J'))
        self.assertEqual(normalize(OFFERINGS, Filters('Social Sciences', 'AAA', '2013J')),
                         Filters('Social Sciences'))

    def test_presentation_alone_is_not_an_offering(self):
        self.assertEqual(len(selected_offerings(OFFERINGS, Filters(presentation='2014J'))), 2)
        self.assertEqual(options(OFFERINGS, 'code_presentation', 'STEM', 'AAA'), ['2013J', '2014J'])

    def test_invalid_filters_are_rejected_not_silently_widened(self):
        for value in (Filters(module='BBB', domain='STEM'), Filters(module="AAA' OR TRUE --")):
            with self.assertRaises(FilterError):
                selected_offerings(OFFERINGS, value)
        with self.assertRaises(FilterError):
            options(OFFERINGS, 'arbitrary_column')

    def test_weeks_are_union_of_offering_lengths(self):
        self.assertEqual(available_weeks(OFFERINGS), list(range(9)))
        self.assertEqual(default_week(available_weeks(OFFERINGS)), 7)
        self.assertEqual(default_week([0, 1]), 0)
        self.assertIsNone(default_week([]))
        self.assertIn('ngày 49–55', week_label(7))

    def test_validate_weeks_and_screens(self):
        self.assertEqual(len(validate(OFFERINGS, Filters(week=7), 'signals')), 3)
        for filters, screen in ((Filters(week=7), 'overview'), (Filters(week=9), 'signals'),
                                (Filters(week=True), 'engagement'), (Filters(), 'unknown')):
            with self.assertRaises(FilterError):
                validate(OFFERINGS, filters, screen)
        self.assertEqual(validate([], Filters(), 'overview'), [])
