"""Write a foreign-key-consistent sample of OULAD to data/sample/: one offering, every related row."""
import argparse
from pathlib import Path

import pandas as pd


MODULE, PRESENTATION = 'GGG', '2014J'
STUDENT_SAMPLE = 200
SEED = 4031


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--raw-dir', default='archive (3)')
    parser.add_argument('--out-dir', default='data/sample')
    args = parser.parse_args()
    raw, out = Path(args.raw_dir), Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    offering = lambda frame: frame[(frame['code_module'] == MODULE) & (frame['code_presentation'] == PRESENTATION)]
    info = offering(pd.read_csv(raw / 'studentInfo.csv', dtype=str, keep_default_na=False))
    info = info.sample(n=STUDENT_SAMPLE, random_state=SEED).sort_values('id_student')
    students = set(info['id_student'])
    assessments = offering(pd.read_csv(raw / 'assessments.csv', dtype=str, keep_default_na=False))
    keep = {
        'courses': offering(pd.read_csv(raw / 'courses.csv', dtype=str, keep_default_na=False)),
        'assessments': assessments,
        'vle': offering(pd.read_csv(raw / 'vle.csv', dtype=str, keep_default_na=False)),
        'studentInfo': info,
    }
    registration = offering(pd.read_csv(raw / 'studentRegistration.csv', dtype=str, keep_default_na=False))
    keep['studentRegistration'] = registration[registration['id_student'].isin(students)]
    scores = pd.read_csv(raw / 'studentAssessment.csv', dtype=str, keep_default_na=False)
    keep['studentAssessment'] = scores[scores['id_assessment'].isin(set(assessments['id_assessment']))
                                       & scores['id_student'].isin(students)]
    chunks = pd.read_csv(raw / 'studentVle.csv', dtype=str, keep_default_na=False, chunksize=1_000_000)
    keep['studentVle'] = pd.concat(offering(chunk).pipe(lambda c: c[c['id_student'].isin(students)]) for chunk in chunks)

    for name, frame in keep.items():
        frame.to_csv(out / f'{name}.csv', index=False)
        print(name, len(frame))


if __name__ == '__main__':
    main()
