from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NEW = ROOT / 'JMS-version/model4_pjob_fifo_20261029'


def edit(name, old, new):
    path = NEW / name
    text = path.read_text('utf-8')
    assert text.count(old) == 1, (name, old[:100], text.count(old))
    path.write_text(text.replace(old, new), 'utf-8')


edit('model.py', '        self.accompaniment()\n        self.resources()',
     '        from pjob_order import add_release_boundaries\n'
     '        add_release_boundaries(self)\n'
     '        self.accompaniment()\n        self.resources()')
edit('model.py', "                    self.eq(a['s'],b['s'],sync);self.eq(a['e'],b['e'],sync)",
     "                    self.eq(a['s'],b['s'],sync);self.eq(a['e'],b['e'],sync)\n"
     "                    from pjob_order import restrict_pick_sync\n"
     "                    restrict_pick_sync(self,a,b,sync)")
edit('model.py', "'model_scope':'model4_pjob_inventory_v1'",
     "'model_scope':'pjob_global_fifo_v2'")
edit('model.py', "        decoded={};group_at={}",
     "        from pjob_order import encoding\n"
     "        codes=encoding(cfg)\n"
     "        out['product_encoding']=codes\n"
     "        out['release_order_rule']='global_pjob_index_strict_lp_pickup'\n"
     "        decoded={};group_at={}")
edit('model.py', "                out['jobs'][-1].update(pjob=g.pjob,wafer_number=25*(g.load_port-1)+int(identity.split('_W')[1]))",
     "                out['jobs'][-1].update(codes[identity])")
edit('run_experiments.py', "'model.py','pjobs.py','validate.py'",
     "'model.py','pjobs.py','pjob_order.py','validate.py'")
edit('validate.py', "    return result|dict(valid=not errors,checks=checks,errors=errors,pjob_check=True)",
     "    from pjob_order import order_report\n"
     "    try:\n"
     "        ordered=order_report(data,TOL)\n"
     "        checks+=ordered['checks'];errors.extend(ordered['errors'])\n"
     "    except (ValueError,KeyError,TypeError,AttributeError) as exc:\n"
     "        ordered={'valid':False};errors.append('Pjob release order: '+str(exc))\n"
     "    return result|dict(valid=not errors,checks=checks,errors=errors,pjob_check=True,\n"
     "                       pjob_release_order_check=ordered['valid'])")
edit('seed.py', "        for ws in bytask.values():\n            for start in range(0,len(ws),2):\n                pair=ws[start:start+2];allowed=byid[pair[0].identifier].chambers\n                c=min(allowed,key=lambda c:(work[c] if balanced else 0,c))\n                assigned[c].extend(pair);work[c]+=cfg.full_time if pair[0].mode=='4x1' else 2*cfg.mix_time",
     "        for ws in bytask.values():\n"
     "            allowed=sorted(byid[ws[0].identifier].chambers)\n"
     "            chunks=[ws[start:start+2] for start in range(0,len(ws),2)]\n"
     "            # Each chamber receives a consecutive product-index segment.\n"
     "            # The serial template visits chambers in increasing order.\n"
     "            if balanced:\n"
     "                count,extra=divmod(len(chunks),len(allowed))\n"
     "                destinations=[c for i,c in enumerate(allowed) for _ in range(count+(i<extra))]\n"
     "            else:destinations=[allowed[0]]*len(chunks)\n"
     "            for pair,c in zip(chunks,destinations):\n"
     "                assigned[c].extend(pair);work[c]+=cfg.full_time if pair[0].mode=='4x1' else 2*cfg.mix_time")
edit('seed.py', "    out.pop('validation',None)\n    return out",
     "    out.pop('validation',None)\n"
     "    from pjob_order import encoding,order_report\n"
     "    codes=encoding(cfg);out['product_encoding']=codes\n"
     "    out['model_scope']='pjob_global_fifo_physical_reference_v2'\n"
     "    for job in out['jobs']:\n"
     "        if job['product']:job.update(codes[job['identity']])\n"
     "    ordered=order_report(out)\n"
     "    if not ordered['valid']:raise ValueError(ordered['errors'])\n"
     "    return out")
# The physical template constructor visits this tuple in order. Keep it aligned
# with the input numbering, including configurations with reversed chamber input.
edit('physical_seed.py', "        for chamber in cfg.chambers:",
     "        for chamber in sorted(cfg.chambers):")
edit('run_experiments.ps1', '$Campaign="JMS-version/results/model4_${Suite}_${Qualification}_$tag"',
     '$Campaign="JMS-version/results/pjob_fifo_${Suite}_${Qualification}_$tag"')
edit('test_model4.py', "assert result['model_scope']=='model4_pjob_inventory_v1'",
     "assert result['model_scope']=='pjob_global_fifo_v2'")

print('Independent backend prepared:', NEW)
