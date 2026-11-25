"""Interrupt an isolated controller and verify adoption of its still-running native SCIP worker."""
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
import psutil
from publish import HERE,JMS,OUT,read,sha,write


def controller(folder):
    import run
    job=next(j for j in read(OUT/'jobs.json') if j['key']=='n8_H3_s1')
    write(folder/'jobs.json',[job])
    run.OUT=folder;run.prepare=lambda:[job];run.publish=lambda:None
    run.run()


def check():
    target=OUT/'recovery_check.json'
    tmp=JMS/'tmp';tmp.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix='sq_table4_resume_',dir=tmp) as t:
        folder=Path(t).resolve()
        argv=[sys.executable,'-B','-u','-X','utf8',str(Path(__file__).resolve()),str(folder)]
        log=folder/'audit.log'
        with log.open('ab') as stream:
            first=subprocess.Popen(argv,stdout=stream,stderr=stream)
            for _ in range(200):
                q=folder/'queue.json'
                if q.exists():
                    saved=read(q);w=saved['workers'].get('n8_H3_s1')
                    if w:break
                time.sleep(.1)
            else:raise RuntimeError('Isolated worker did not start.')
            first.terminate();first.wait(timeout=5)
            proc=psutil.Process(w['pid']);assert proc.is_running() and abs(proc.create_time()-w['birth'])<1
            resumed=subprocess.run(argv,stdout=stream,stderr=stream,timeout=120)
            assert resumed.returncode==0
        final=read(folder/'queue.json');cert=folder/'runs/n8_H3_s1/result.json'
        result=read(cert)
        assert final['success']==['n8_H3_s1'] and not final['failed'] and not final['workers']
        assert result['replay']['valid'] and result['eligible'] and result['objective']=='mean_plus_spread_squared_over_2delta_plus_gamma_E_v1'
        # Input and worker identities are checked by the normal controller before adoption.
        write(target,dict(case='isolated n8 H3 seed1',worker_pid=w['pid'],worker_birth=w['birth'],
              controller_interrupted=True,verified_worker_alive_before_resume=True,completed=1,failed=0,
              objective=result['objective'],input_sha256=result['parents'][0]['schedule_sha256'],
              certificate_sha256=sha(cert),physical_schedule_sha256=result['files']['schedule.json'],
              matched_publication_result=abs(result['measured']['secondary']-read(OUT/'runs/n8_H3_s1/result.json')['measured']['secondary'])<.001))


if __name__=='__main__':
    if len(sys.argv)==2:controller(Path(sys.argv[1]))
    else:check()
