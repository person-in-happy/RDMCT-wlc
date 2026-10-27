"""Audit helpers for continued exact searches; no physical model changes."""
from pathlib import Path


def certificate_asset_changes(previous, current):
    """Allow only the experiment reporting helper to differ.

    The old certificate checks feasibility, not the reporting implementation.
    Model, seed completion, validator, backend and all other dependencies must
    remain byte-identical. The caller records both helper hashes in its manifest.
    """
    if previous.keys() != current.keys():
        raise ValueError('Certificate asset inventory changed; recertify')
    changes = {k: {'certificate': previous[k], 'current': current[k]}
               for k in current if previous[k] != current[k]}
    allowed = 'JMS-version/joint_model/run_experiments.py'
    if any(k.replace('\\', '/') != allowed for k in changes):
        raise ValueError('Model/validation dependency changed; recertify')
    known_transition = (
        'b1ef110c2d205859d614d3588e99fbd99d3826b879c41891ae51e7b96a4635f6',
        '005259e5093256f925cf31ae83f4b9388b98810e009f692e8337f1156aadbfd1')
    if any((v['certificate'],v['current']) != known_transition for v in changes.values()):
        raise ValueError('Unreviewed reporting-helper change; recertify')
    return changes


def reserve_for_growth(active, free_mb, memory_mb, reserve_mb=2048,
                       external_growth_mb=0):
    growth = sum(max(0, memory_mb*1.15-rss) for rss in active)
    return free_mb-growth-reserve_mb-external_growth_mb >= memory_mb*1.15
