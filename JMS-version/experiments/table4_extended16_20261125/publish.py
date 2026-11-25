"""Audit and publish per-seed objective pairs, hashes and the two additional Table 4 rows."""
import csv
import statistics
from blocks import OUT,JMS,metrics,read,sha,validate,write


def verify(path,meta):
    sched=path/'schedule.json';assign=path/'assignment.json.gz'
    assert sha(sched)==meta['schedule_sha256'] and sha(assign)==meta['assignment_sha256']
    doc=read(sched);replay=validate(doc)
    assert replay['valid']
    cfg=doc['config']
    assert cfg['module_residency']==cfg['robot_residency']==100 and cfg['horizon']==100000 and cfg['dummy_count']==8
    assert len(cfg['load_ports'])==4 and all(v=={'4x1':2,'2x2':2} for v in cfg['load_ports'].values())
    assert (cfg['full_time'],cfg['mix_time'],cfg['cleaning_time'])==(180,90,500)
    return dict(schedule_path=sched.relative_to(JMS).as_posix(),assignment_path=assign.relative_to(JMS).as_posix(),
                schedule_sha256=sha(sched),assignment_sha256=sha(assign),H=cfg['cleaning_interval'],
                f_A=metrics(doc)['cmax'],f_B=metrics(doc)['secondary'],physical_metrics=metrics(doc),event_checks=replay['checks'])


def publish():
    reports=[];rows=[];snap=[]
    for h in (3,10):
        group=OUT/f'H{h}';ops=[]
        for s in (1,2,3):
            base=group/f's{s}';a=read(base/'A.json');folder=JMS/a['source'];certA=folder/'primary.json'
            d=verify(folder,read(certA))
            assert a['seed']==s and d['H']==h and d['f_A']<=a['lower']*1.01+1.e-5
            assert sha(JMS/a['lower_source'])==a['lower_sha256']
            aa=dict(arm='A',seed=s,certificate=(base/'A.json').relative_to(JMS).as_posix(),
                    certificate_sha256=sha(base/'A.json'),native_rows=a['model_rows'],lower=a['lower'],**d)
            b=read(base/'AB.json');certB=JMS/b['certificate'];original=read(certB)
            assert sha(certB)==b['certificate_sha256'] and original['eligible'] and original['seed']==s
            assert original['target_gap']==.01 and original['mode']=='fixed' and original['parents'][0]['schedule_sha256']==d['schedule_sha256']
            ab=verify(JMS/b['source'],{'schedule_sha256':original['files']['schedule.json'],'assignment_sha256':original['files']['assignment.json.gz']})
            assert ab['H']==h and abs(ab['f_A']-d['f_A'])<2.e-4 and abs(ab['f_B']-b['upper'])<2.e-4
            assert ab['f_B']<=b['lower']*1.01+2.e-5 and original['replayed_rows']==original['original_rows']==aa['native_rows']
            ops.extend((aa,dict(arm='AB',seed=s,certificate=b['certificate'],certificate_sha256=b['certificate_sha256'],
                                native_rows=original['replayed_rows'],lower=b['lower'],parent=d['schedule_sha256'],**ab)))
        options=[]
        for raw in ('free','pack','retime'):
            path=group/raw;cert=path/'result.json'
            if not cert.exists():continue
            orig=read(cert);data=verify(path,orig)
            assert data['H']==h and abs(data['f_B']-orig['lower'])<1e-6 and data['event_checks']>0
            options.append(dict(arm='B',seed=None,certificate=cert.relative_to(JMS).as_posix(),certificate_sha256=sha(cert),
                                native_rows=orig['rows'],lower=orig['lower'],**data))
        best=min(options,key=lambda v:v['f_A']);ops.append(best)
        reports.extend(ops)
        row={'n':16,'H':h}
        for arm in ('A','B','AB'):
            for value in ('f_A','f_B'):
                row[f'{arm}_{value}']=statistics.mean(v[value] for v in ops if v['arm']==arm)
        rows.append(row)
    for h in (3,10):
        p=JMS/f'results/pareto_scales_20261125/four_native_H{h}/417_pinned/result.json'
        if p.exists():
            c=read(p);assert c['replay']['valid'] and (c['metrics']['cmax'],c['metrics']['secondary'])==(417,3.46875)
            snap.append(dict(n=4,H=h,f_A=417,f_B=3.46875,certificate=p.relative_to(JMS).as_posix(),certificate_sha256=sha(p)))
    write(OUT/'publication.json',dict(rows=rows,records=reports,updated_four_wafer_attainments=snap))
    with (OUT/'table4_rows.csv').open('w',encoding='utf-8-sig',newline='') as f:
        out=csv.DictWriter(f,fieldnames=rows[0]);out.writeheader();out.writerows(rows)
    for row in rows:print(row,flush=True)


if __name__=='__main__':publish()
