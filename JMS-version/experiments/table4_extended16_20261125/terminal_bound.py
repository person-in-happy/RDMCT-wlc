"""Certify the H=3 makespan bound from chamber batches and the final double-exposure handoff."""
from hashlib import sha256
from pathlib import Path

from bound import OUT, enumerate_batches
from clean_projection import store


def main():
    cap = 1218
    candidates = enumerate_batches(cap, collect=True)
    rows = []
    for _, trace in candidates["patterns"]:
        home = []
        for index,(chamber,mode,count,_,start) in enumerate(trace):
            following = next((s for s in trace[index+1:] if s[0]==chamber), None)
            carries = following is not None and following[3]=="carry"
            lag = 220 if mode==1 else 226 if carries else 227
            home.extend([start+lag]*count)
        lower = max(t+55*((15-i)//2) for i,t in enumerate(sorted(home)))
        rows.append(dict(trace=trace,product_return_lower=lower))
    lower = min([cap+1]+[row["product_return_lower"] for row in rows])
    assert len(rows)==13 and lower==1219
    dest=OUT/"H3_terminal_bound.json"
    store(dest, dict(lower=lower,excluded_cap=cap,enumeration_nodes=candidates["visited"],
        remaining_patterns=rows,signature={p.name:sha256(p.read_bytes()).hexdigest()
        for p in (Path(__file__),Path(__file__).with_name("bound.py"))},
        proof="After the first start of a chain-terminal double pair, its second start is at least 94 s later. "
              "After the final 90 s exposure the front pair must be unloaded (1 s) and the chamber rotated (2 s), "
              "before unloading the rear products can begin. From this unload start at least 40 s are needed for return: "
              "destination put after 3, lower pick after 26, origin put after 7, and origin put duration 4. "
              "Thus each terminal product returns no earlier than start+227. For a continued chain the 226 s "
              "bound is retained. Mandatory outlet-slot reuse separates every other ranked earliest return by 55 s. "
              "The chronological enumeration previously relaxed these lags; it covers all schedules feasible under "
              "the cap. Every remaining pattern now has a lower bound of 1219. For fixed physical event order all "
              "lags are integral differences, so flooring the event times preserves the relaxation and excludes "
              "fractional makespans below 1219 as well."))
    print(dest,lower)


if __name__=="__main__":
    main()
