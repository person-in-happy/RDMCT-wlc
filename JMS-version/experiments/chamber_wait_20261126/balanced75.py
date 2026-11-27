"""Retain the aggregate process objective while compressing the largest empty chamber gaps."""
from collections import Counter
import math
from pathlib import Path
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix
import compact75 as campaign

def flexible(timing,starts,records,doc,limits):
    n=len(starts)
    candidates=[]
    for width in sorted({round(limits["residence_range"]),round(campaign.observed(doc)["residence_range"])}):
        # A fixed maximum within-recipe range leaves a linear bound on the sum of residence.
        if width<0 or width**2/2>limits["secondary"]:continue
        row_id=[];col=[];value=[];rhs=[]
        def row(terms,ub):
            for j,v in terms:
                row_id.append(len(rhs));col.append(j);value.append(v)
            rhs.append(ub)
        for a,b,dt in timing.edges:row([(a,1),(b,-1)],-dt)
        mean=Counter();offset=0
        for mode,count,a,b,dt in campaign.pairs(timing):
            low=n+2+int(mode=="2x2")
            row([(low,1),(a,1),(b,-1)],-dt)
            row([(b,1),(a,-1),(low,-1)],width+dt)
            mean[b]+=count;mean[a]-=count;offset+=count*dt
        row(mean.items(),math.floor((limits["secondary"]-width**2/2)*75+1e-6)+offset)
        bounds=[(0,limits["equipment_release"]-tail) for tail in timing.tails]
        for i in timing.returns:bounds[i]=(0,min(bounds[i][1],limits["cmax"]-timing.actions[i].duration))
        held,empty=campaign.chamber_gaps(timing);objective=np.zeros(n+4)
        def group(spans,cap,cost):
            d=Counter();constant=0
            for a,b,dt in spans:
                d[a]-=1;d[b]+=1;constant+=dt
            row(d.items(),cap+constant)
            for i,v in d.items():objective[i]+=cost*v
        for j,ch in enumerate(sorted(held)):
            cap=limits["chambers"][ch]
            bounds.append((0,cap["longest_empty"]));objective[n+j]=3500
            for a,b,dt in empty[ch]:row([(a,-1),(b,1),(n+j,-1)],dt)
            group(held[ch],cap["occupied_wait"],1);group(empty[ch],cap["internal_empty"],220)
        bounds.extend([(0,100)]*2)
        for robot,spans in campaign.robot_gaps(records,starts,doc).items():
            group(spans,limits[robot.lower()+"_held_wait"],.02)
        for i,v in mean.items():objective[i]+=.001*v
        matrix=coo_matrix((value,(row_id,col)),shape=(len(rhs),n+4)).tocsr()
        result=linprog(objective,A_ub=matrix,b_ub=rhs,bounds=bounds,method="highs-ds")
        if not result.success:continue
        if np.max(abs(result.x[:n]-np.rint(result.x[:n])))>1e-6:
            result=linprog(objective,A_ub=matrix,b_ub=rhs,bounds=bounds,integrality=np.ones(n+4),method="highs",options={"time_limit":3})
            if result.x is None or np.max(abs(result.x[:n]-np.rint(result.x[:n])))>1e-5:continue
        vector=np.rint(result.x[:n]).astype(int).tolist();sc=campaign.observed(timing.schedule(vector))
        candidates.append((campaign.compact_key(sc),vector))
    return min(candidates)[1] if candidates else None

if __name__=="__main__":
    campaign.refine=flexible
    campaign.OUT=campaign.PRIOR.parent/"n75_balanced"
    campaign.__file__=__file__
    campaign.run()

