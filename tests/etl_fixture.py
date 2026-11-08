"""Hand-calculated SYNTHETIC edge cases; not OULAD acceptance data."""
import csv

from src.etl.source import SOURCES


def write_sources(raw):
    data = {
        'courses': [('AAA', '2013J', 14), ('AAA', '2014J', 14)],
        'assessments': [('AAA', '2013J', 10, 'TMA', 3, 12.5), ('AAA', '2013J', 11, 'CMA', 10, 0),
                        ('AAA', '2013J', 12, 'Exam', '', 100), ('AAA', '2014J', 13, 'TMA', 10, 100)],
        'vle': [(100, 'AAA', '2013J', 'oucontent', '', ''), (101, 'AAA', '2013J', 'forumng', 0, 1),
                (102, 'AAA', '2014J', 'quiz', '', '')],
        'student_info': [
            ('AAA', '2013J', 1, 'M', 'London Region', 'A Level or Equivalent', '10-20', '0-35', 0, 60, 'N', 'Pass'),
            ('AAA', '2014J', 1, 'M', 'London Region', 'A Level or Equivalent', '10-20', '35-55', 1, 60, 'N', 'Distinction'),
            ('AAA', '2013J', 2, 'F', 'London Region', 'No Formal quals', '', '0-35', 0, 60, 'N', 'Withdrawn'),
            ('AAA', '2013J', 3, 'F', 'London Region', 'No Formal quals', '', '0-35', 0, 60, 'N', 'Fail'),
            ('AAA', '2013J', 4, 'F', 'London Region', 'No Formal quals', '', '0-35', 0, 60, 'N', 'Withdrawn'),
        ],
        'student_registration': [('AAA', '2013J', 1, -5, ''), ('AAA', '2014J', 1, -1, ''),
                                 ('AAA', '2013J', 2, -10, -5), ('AAA', '2013J', 3, 7, ''),
                                 ('AAA', '2013J', 4, '', '')],
        'student_assessment': [(10, 1, 4, 0, 81), (11, 1, 12, 0, ''), (12, 1, 15, 0, 90),
                               (10, 2, -1, 1, 60), (11, 3, 14, 0, 40), (10, 4, -1, 1, 60)],
        'student_vle': [('AAA', '2013J', 1, 100, -1, 2), ('AAA', '2013J', 1, 100, 0, 2),
                        ('AAA', '2013J', 1, 100, 0, 3), ('AAA', '2013J', 1, 101, 0, 4),
                        ('AAA', '2013J', 1, 100, 7, 5), ('AAA', '2013J', 1, 100, 14, 99),
                        ('AAA', '2013J', 3, 100, 8, 4), ('AAA', '2013J', 2, 100, -4, 1)],
    }
    for filename, table, columns in SOURCES:
        with (raw / filename).open('w', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream, quoting=csv.QUOTE_ALL)
            writer.writerow(columns)
            writer.writerows(data[table])
