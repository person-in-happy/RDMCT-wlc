"""Physical VTR hands and exact interval-assignment audit, independent of SCIP."""
HANDS = ('D1', 'D2', 'C1', 'C2')
TOL = 2e-4

def hand_intervals(data):
    events = {(e.get('job'), e['kind']): e for e in data['events'] if 'job' in e}
    result = []
    for j in data['jobs']:
        for leg, start, end in (
            ('in', events[j['name'], 'source_pick']['start'], j['load_end']),
            ('out', j['unload_start'], events[j['name'], 'destination_put']['end'])):
            allowed = HANDS[:2] if j['product'] and leg == 'in' else HANDS[2:] if j['product'] else HANDS
            result.append((j['name'] + '_' + leg, start, end, allowed))
    return result

def assign_intervals(intervals):
    """Exact sweep DP. Retain all active hand permutations, not a greedy choice.

    A hand is reserved from pickup start through placement completion. Each
    interval keeps its hand; completed intervals may release it for immediate reuse.
    """
    intervals = sorted(intervals, key=lambda x: (x[1], x[2], x[0]))
    states = {(None, None, None, None): {}}
    ends = {name: end for name, start, end, allowed in intervals}
    for name, start, end, allowed in intervals:
        if end < start - TOL or len(ends) != len(intervals):
            return None
        following = {}
        for active, witness in states.items():
            active = tuple(x if x is not None and ends[x] > start + TOL else None for x in active)
            for slot, hand in enumerate(HANDS):
                if active[slot] is None and hand in allowed:
                    occupied = list(active); occupied[slot] = name; occupied = tuple(occupied)
                    if occupied not in following:
                        following[occupied] = {**witness, name: hand}
        if not following:
            return None
        states = following
    return next(iter(states.values()))

def attach_hands(data):
    """Attach a witness without changing timestamps, routes or material choices."""
    witness = assign_intervals(hand_intervals(data))
    if witness is None:
        return False
    for job in data['jobs']:
        job['vtr_hand_in'] = witness[job['name'] + '_in']
        job['vtr_hand_out'] = witness[job['name'] + '_out']
    return True
