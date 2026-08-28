'''Validate a saved CIE SCIP solution and export petri_gantt JSON.'''

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cie.code.analyze_cie_solutions import _parse_solution, _validate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            'Independently validate a CIE .sol file against its frozen LP, '
            'then export the nonzero variables in petri_gantt JSON format.'
        )
    )
    parser.add_argument('--instance', required=True, help='Frozen Petri LP file.')
    parser.add_argument('--solution', required=True, help='SCIP .sol file.')
    parser.add_argument('--output_json', required=True)
    parser.add_argument(
        '--solver_status',
        default='validated_feasible',
        help='Primary solver status copied from the benchmark row.',
    )
    parser.add_argument(
        '--solver_gap',
        type=float,
        default=None,
        help='Primary relative MIP gap copied from the benchmark row.',
    )
    parser.add_argument('--run_label', default='')
    return parser


def main() -> int:
    args = _parser().parse_args()
    instance_path = Path(args.instance).expanduser().resolve()
    solution_path = Path(args.solution).expanduser().resolve()
    output_path = Path(args.output_json).expanduser().resolve()
    solver_status = str(args.solver_status or 'validated_feasible').strip().lower()
    if solver_status == 'optimal' and (
        args.solver_gap is None or float(args.solver_gap) > 1e-8
    ):
        raise ValueError(
            'solver_status=optimal requires an explicit solver_gap <= 1e-8'
        )
    for label, path in (('instance', instance_path), ('solution', solution_path)):
        if not path.is_file():
            raise FileNotFoundError(f'{label} file does not exist: {path}')

    feasible, validation_note = _validate(instance_path, solution_path)
    if not feasible:
        raise RuntimeError(
            f'SCIP rejected {solution_path.name} for {instance_path.name}: '
            f'{validation_note}'
        )
    values = _parse_solution(solution_path)
    if not values or 'c_max' not in values:
        raise RuntimeError(f'No nonzero Petri solution/c_max found in {solution_path}')

    record = {
        'instance': instance_path.name,
        'status': solver_status,
        'gap': args.solver_gap,
        'run_label': str(args.run_label or ''),
        'best_obj': values['c_max'],
        'nonzero_solution_vars': len(values),
        'instance_file': str(instance_path),
        'instance_sha256': _sha256(instance_path),
        'solution_file': str(solution_path),
        'solution_sha256': _sha256(solution_path),
        'independent_validation': True,
        'validation_note': validation_note,
        'solution': values,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps([record], ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    print(f'validated and exported: {output_path}')
    c_max = values['c_max']
    print(f'c_max={c_max}; nonzero variables={len(values)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
