"""Derive, rather than choose, per-chamber 2x2 blocks under a valid cutoff."""
import math
from cycle_work_bounds import double_exposure_work


def block_certificate(n,chambers,h,processing,cleaning,window,max_productive):
    maxk=max(k for k in range(1,n+1) if double_exposure_work(k,h,processing,cleaning)[2]<=window+1e-6)
    mink=max(0,math.ceil(n/2)-(chambers-1)*maxk)
    result=dict(min_pairs=mink,max_pairs=maxk,forced_cycle_modes=None)
    if mink==0:return result
    minc=math.ceil(mink/(h-1))-1
    # Every nonempty 2x2 block needs at least two productive exposures.
    maxc=min(maxk-1,
             math.floor((window-(mink+1)*processing+1e-6)/(processing+cleaning)),
             math.floor((window-2*processing+1e-6)/(2*processing+cleaning)))
    minp=mink+minc+1
    maxp=min(max_productive,math.floor((window-minc*cleaning+1e-6)/processing))
    result.update(min_nonterminal_cleanings=minc,max_nonterminal_cleanings=maxc,
                  min_productive=minp,max_productive=maxp)
    if minc==maxc and minp==maxp and minp==h*(minc+1):
        result['forced_cycle_modes']=(['2x2']*h+['clean'])*(minc+1)
    return result
