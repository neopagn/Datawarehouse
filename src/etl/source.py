"""Source contract for the seven unmodified OULAD CSV files."""
import csv
from pathlib import Path

# CSV name, staging table, ordered columns (same order as 00_ddl_staging.sql).
SOURCES = (
    ('courses.csv', 'courses', ('code_module', 'code_presentation', 'module_presentation_length')),
    ('assessments.csv', 'assessments', ('code_module', 'code_presentation', 'id_assessment', 'assessment_type', 'date', 'weight')),
    ('vle.csv', 'vle', ('id_site', 'code_module', 'code_presentation', 'activity_type', 'week_from', 'week_to')),
    ('studentInfo.csv', 'student_info', ('code_module', 'code_presentation', 'id_student', 'gender', 'region', 'highest_education', 'imd_band', 'age_band', 'num_of_prev_attempts', 'studied_credits', 'disability', 'final_result')),
    ('studentRegistration.csv', 'student_registration', ('code_module', 'code_presentation', 'id_student', 'date_registration', 'date_unregistration')),
    ('studentAssessment.csv', 'student_assessment', ('id_assessment', 'id_student', 'date_submitted', 'is_banked', 'score')),
    ('studentVle.csv', 'student_vle', ('code_module', 'code_presentation', 'id_student', 'id_site', 'date', 'sum_click')),
)


def validate_sources(raw_dir: Path) -> None:
    """Read only headers; validate all files before any staging/DW reset."""
    for filename, _, columns in SOURCES:
        path = raw_dir / filename
        if not path.is_file():
            raise ValueError(f'Missing source file: {filename}')
        with path.open(encoding='utf-8-sig', newline='') as stream:
            header = next(csv.reader(stream), None)
        if header != list(columns):
            raise ValueError(f'Invalid header: {filename}; expected {list(columns)}')


def copy_sources(conn, raw_dir: Path) -> dict[str, int]:
    """Client-side COPY streams blocks, preserving quoted empty strings."""
    from psycopg import sql

    counts = {}
    for filename, table, _ in SOURCES:
        with conn.cursor() as cursor:
            statement = sql.SQL('COPY staging.{} FROM STDIN WITH (FORMAT csv, HEADER true)').format(sql.Identifier(table))
            with cursor.copy(statement) as copy:
                with (raw_dir / filename).open('rb') as stream:
                    first = stream.read(1024 * 1024)
                    copy.write(first.removeprefix(b'\xef\xbb\xbf'))
                    while block := stream.read(1024 * 1024):
                        copy.write(block)
            counts[table] = cursor.rowcount
    return counts
