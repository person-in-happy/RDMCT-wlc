"""Input schema only: processing groups specify seconds per exposure."""
import math,re


def validate_groups(cfg,products):
    groups=cfg.processing_groups
    if not isinstance(groups,dict):raise ValueError('processing_groups must be a dictionary')
    if not groups:return {}
    expected={w.identifier for w in products};mapping={}
    for group,spec in groups.items():
        if not isinstance(group,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',group):
            raise ValueError('Group names must be ASCII identifiers beginning with a letter')
        if not isinstance(spec,dict) or set(spec)!={'wafers','4x1','2x2'}:
            raise ValueError('Every group requires wafers, 4x1 and 2x2')
        if not isinstance(spec['wafers'],list) or not spec['wafers']:
            raise ValueError('Every group needs an explicit nonempty wafer list')
        for mode in ('4x1','2x2'):
            duration=spec[mode]
            if isinstance(duration,bool) or not isinstance(duration,(int,float)) or not math.isfinite(duration) or duration<=0:
                raise ValueError('Group durations must be positive finite seconds per exposure')
        for wafer in spec['wafers']:
            if not isinstance(wafer,str) or wafer not in expected:raise ValueError('Unknown product wafer: '+str(wafer))
            if wafer in mapping:raise ValueError('Wafer occurs in multiple groups: '+wafer)
            mapping[wafer]=group
    if set(mapping)!=expected:raise ValueError('Processing groups must partition all product wafers')
    return mapping
