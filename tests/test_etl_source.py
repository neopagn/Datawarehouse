import csv
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from src.etl.source import SOURCES, validate_sources


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='oulad source ')
        self.addCleanup(self.tmp.cleanup)
        self.raw = Path(self.tmp.name)
        for filename, _, columns in SOURCES:
            with (self.raw / filename).open('w', encoding='utf-8', newline='') as stream:
                csv.writer(stream).writerow(columns)

    def test_valid_headers_and_bom(self):
        path = self.raw / 'courses.csv'
        path.write_bytes(b'\xef\xbb\xbf' + path.read_bytes())
        validate_sources(self.raw)

    def test_missing_file(self):
        (self.raw / 'vle.csv').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing source file: vle.csv'):
            validate_sources(self.raw)

    def test_bad_header(self):
        (self.raw / 'courses.csv').write_text('code_module,code_module\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Invalid header: courses.csv'):
            validate_sources(self.raw)

    def test_empty_file(self):
        (self.raw / 'courses.csv').write_text('', encoding='utf-8')
        with self.assertRaises(ValueError):
            validate_sources(self.raw)

    def test_cli_requires_explicit_reload_and_dedicated_database(self):
        for args in (['--database', 'postgres'], ['--database', 'oulad_test']):
            result = subprocess.run([sys.executable, '-m', 'src.etl', *args], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertNotIn('password', result.stderr.lower())

    def test_cli_help(self):
        result = subprocess.run([sys.executable, '-m', 'src.etl', '--help'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn('--allow-full-reload', result.stdout)


if __name__ == '__main__':
    unittest.main()
