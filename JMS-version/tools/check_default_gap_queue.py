import argparse,json,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,'JMS-version/tools')
import default_gap_experiments as g
out=g.RESULTS/'gap_queuecheck_20261108'
a=argparse.Namespace(suite='cleanup',source_campaign=None,time_limit=300,stage2_limit=60,memory_mb=1024,process_memory_mb=2048,wall_limit=1800)
g.prepare(a,out)
spec=g.read(out/'campaign.json');spec['cells']=spec['cells'][:2]
g.dump(out/'campaign.json',spec);g.dump(out/'contract.json',{'campaign_sha256':g.digest(out/'campaign.json')})
calls=[]
class Child:
    def __init__(self,args,**kw):
        cell=args[-1];calls.append(cell)
        p=out/'runs'/cell;p.mkdir(parents=True)
        g.dump(p/'result.json',{'mock_queue_test':True})
        g.dump(p/'evidence.json',{'valid':False,'state':'mock_queue_complete','result_sha256':g.digest(p/'result.json')})
        self.pid=0
    def poll(self):return 0
    def wait(self,**kw):return 0
    def terminate(self):raise AssertionError('Already finished')
with patch.object(g.subprocess,'Popen',Child):
    g.run(out)
    assert len(calls)==2
    g.run(out)
    assert len(calls)==2, 'Resume reran completed cells'
first=out/'runs'/spec['cells'][0]['id']/'result.json'
g.dump(first,{'mock_queue_test':'tampered'})
try:g.summarize(out)
except RuntimeError:pass
else:raise AssertionError('Tampered result accepted')
g.dump(out/'queue_verification.json',dict(mock_worker_only=True,solver_started=False,complete_cells_skipped=True,result_tamper_rejected=True))
print('QUEUE RESUME AND TAMPER CHECKS PASS; NO SOLVER')
