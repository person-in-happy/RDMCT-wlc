"""Resume one reviewed campaign without changing its frozen asset manifest.

Only the exact three reviewed, unused module additions are excluded. Original
hash checks, checkpoint recovery, process checks and campaign locking remain.
Dry-run is the default. No SCIP tree is recovered; interrupted evaluations restart.
"""
from pathlib import Path
import argparse
import importlib.util
import json
import sys

TOOLS = Path(__file__).resolve().parent

def install_reviewed_inventory_guard(runner, review, manifest_path):
    if manifest_path.resolve() != Path(review['campaign']).resolve():
        raise RuntimeError('This review applies only to the recorded campaign.')
    if runner.sha(manifest_path) != review['campaign_sha256']:
        raise RuntimeError('Campaign metadata changed since inventory review.')
    original_inventory = runner.inventory
    expected_additions = review['added_assets']
    manifest = runner.read_json(manifest_path)
    original_assets = manifest['assets']

    def reviewed_inventory(experiment, commands, files):
        current = original_inventory(experiment, commands, files)
        additions = {p: h for p, h in current.items() if p not in original_assets}
        if additions != expected_additions:
            raise RuntimeError('Unreviewed inventory additions or changed added files; stop for a new review.')
        # Keep missing/modified original assets visible to the original verifier.
        return {p: h for p, h in current.items() if p not in expected_additions}

    runner.inventory = reviewed_inventory
    return manifest

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    review = json.loads((TOOLS/'resume_inventory_review_20260917.json').read_text('utf-8'))
    source = TOOLS/'resumable_experiments.py'
    spec = importlib.util.spec_from_file_location('frozen_resume_runner', source)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    manifest = install_reviewed_inventory_guard(runner, review, args.resume/'campaign.json')
    runner.verify_assets(manifest)
    print('Reviewed inventory: all original assets unchanged; exactly 3 unrelated additions verified.', flush=True)
    argv = ['sensitivity', '--resume', str(args.resume)]
    if args.execute:
        argv.append('--execute')
    runner.main(argv)
    print('For this campaign use resume_reviewed_inventory.py with the same --resume path and --execute.', flush=True)

if __name__ == '__main__':
    main()
