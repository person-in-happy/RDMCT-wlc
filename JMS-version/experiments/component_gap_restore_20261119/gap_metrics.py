"""Recompute metrics from events and independently replay the original chamber model."""
from component import HERE, JMS, read
from design import EPS
import sys


def replay(folder, evidence):
    sys.path.insert(0, str(JMS/'model4_pjob_nonprocessing_20261103'))
    from validate import validate
    sys.path.insert(0, str(HERE.parent/'gap_both_stages_20261118'))
    from gap_two_stage import f
    schedule=read(folder/'schedule.json')
    if not schedule['original_model_check'] or not schedule['validation']['valid'] or not validate(schedule)['valid']:
        raise ValueError(f'Physical replay failed: {folder}')
    metrics=f.physical_metrics(schedule)
    if any(abs(metrics[key]-evidence['metrics'][key])>EPS for key in ('cmax','wait_sum','wait_max','rhythm','rhythm_centers','secondary')):
        raise ValueError(f'Physical objective differs: {folder}')
    return metrics
