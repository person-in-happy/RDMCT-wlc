"""Construct and audit distinct action orders; never claim exhaustive coverage.

The explicit subset consists of one-product chamber batches, serial material
handling, selectable cleaning cadence and one selected chamber. All physical
actions (including auxiliary wafers) are retained. Numeric witnesses are saved
separately; order identity depends only on ordered start/end groups.
"""
from pathlib import Path
from dataclasses import asdict
from collections import Counter,defaultdict
from datetime import datetime,timezone
import argparse,copy,gzip,hashlib,itertools,json,math,sys,time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'JMS-version/joint_model'))
from model import Config
from seed import construct
from validate import validate
from feasible_order_titles import filename,heading


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def encoded(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'))
def display(name):
    if name.startswith('LP') and '_W' in name:return name.replace('_W','.')
    if name.startswith('D') and name[1:].isdigit():return 'PEC'+name[1:]
    return name


def permutation_at(items,rank):
    pool=list(items);result=[]
    if not 0<=rank<math.factorial(len(pool)):raise ValueError('Permutation rank out of range')
    while pool:
        block=math.factorial(len(pool)-1);index,rank=divmod(rank,block);result.append(pool.pop(index))
    return result


def template(order,recipe,threshold,chamber,cadence):
    pairs=[];cycles=[];counter=0
    def pair(mode,members):
        p=len(pairs);pairs.append(dict(id=p,mode=mode,chamber=chamber,members=members));return p
    def cycle(mode,back,front):
        nonlocal counter
        counter=0 if mode=='clean' else counter+1
        cycles.append(dict(chamber=chamber,index=len(cycles),mode=mode,pairs=[back,front],front=front,counter=counter))
    def clean():
        back=pair('clean',[None,None]);front=pair('clean',[None,None]);cycle('clean',back,front)
    for product in order:
        exposures=1 if recipe=='4x1' else 2
        if counter+exposures>threshold:clean()
        back=pair(recipe,[None,None]);front=pair(recipe,[product,None]);cycle(recipe,back,front)
        if recipe=='2x2':
            incoming=pair(recipe,[None,None]);cycle(recipe,front,incoming)
        if cadence=='early' or counter==threshold:clean()
    return dict(pairs=pairs,cycles=cycles)


def audit_projection(data):
    """Supplement physical replay with finite-candidate/time/symmetry checks."""
    cfg=data['config'];n=sum(sum(v.values()) for v in cfg['load_ports'].values())
    nf=sum(v['4x1'] for v in cfg['load_ports'].values());productive=nf+2*(n-nf)
    assert len(data['pairs'])<=n+3*productive
    assert len(data['cycles'])<=2*productive
    assert sum(c['mode']=='clean' for c in data['cycles'])<=productive
    assert all(0<=e['start']<=e['end']<=cfg['horizon'] for e in data['events'])
    assert all(0<=c['start']<=c['end']<=cfg['horizon'] for c in data['cycles'])
    assert data['cmax']<=cfg['horizon']
    seen=set();previous=0
    for pair in data['pairs']:
        assert pair['id']==previous;previous+=1
        assert not (pair['members'][0].startswith('D') and pair['members'][1].startswith('LP'))
        for member in pair['members']:
            if member.startswith('D'):
                number=int(member[1:]);assert number==1 or 'D'+str(number-1) in seen;seen.add(member)
    replay=validate(data)
    if not replay['valid']:raise ValueError(replay['errors'])
    return dict(physical=replay,candidate_capacity=True,time_horizon=True,label_symmetry=True,
                full_milp_solver_certification=False)


def actions(data):
    jobs={j['name']:j for j in data['jobs']};pairs={p['id']:p for p in data['pairs']}
    def members(pid):return '+'.join(display(w) for w in pairs[pid]['members'])
    loc={'U':'LL.upper','L':'LL.lower','VS':'PECstorage(VS)','AS':'AtmosphericStorage'}
    items=[]
    for event in data['events']:
        kind=event['kind'];location=loc.get(event['location'],event['location'])
        if kind=='rotate':label=location+' rotate'
        elif 'pair' in event:
            verb='place to' if kind=='pair_load' else 'pick from'
            label=f'[{members(event["pair"])}] VTR {verb} {location}'
        else:
            wafer=display(jobs[event['job']]['identity'])
            verb='pick from' if kind in ('origin_pick','al_pick','source_pick','lower_pick') else 'place to'
            label=f'{wafer} {event["robot"]} {verb} {location}'
        items.append(dict(start=event['start'],end=event['end'],label=label))
    for cycle in data['cycles']:
        label=f'CH{cycle["chamber"]} '+('CLEAN' if cycle['mode']=='clean' else 'PROCESS '+cycle['mode'])
        label+=' ['+' | '.join(members(p) for p in cycle['pairs'])+']'
        items.append(dict(start=cycle['start'],end=cycle['end'],label=label))
    groups=defaultdict(list)
    for item in items:
        # Constructed times are exact integral seconds. No tolerance-based
        # merging of unequal instants or artificial serialization is applied.
        assert item['start']==round(item['start']) and item['end']==round(item['end'])
        groups[int(item['start'])].append(('START',item['label']))
        groups[int(item['end'])].append(('END',item['label']))
    sequence=[sorted(group) for _,group in sorted(groups.items())]
    digest=hashlib.sha256(encoded(sequence).encode('utf-8')).hexdigest()
    return sequence,digest,len(items)


def make_config(n,recipe,h):
    return Config(load_ports={f'LP{i}':{'4x1':n//4 if recipe=='4x1' else 0,
                                        '2x2':n//4 if recipe=='2x2' else 0} for i in range(1,5)},cleaning_interval=h)


def run(a):
    output=Path(a.output).resolve()
    if not output.is_relative_to(ROOT/'JMS-version/gif/kexingyu'):raise ValueError('Use JMS-version/gif/kexingyu or its subdirectory')
    output.mkdir(parents=True,exist_ok=True)
    evidence=output/'evidence'
    if evidence.exists():raise ValueError('Output already has evidence; preserve it and choose a new subdirectory')
    evidence.mkdir()
    dependencies=[Path(__file__),ROOT/'JMS-version/joint_model/seed.py',ROOT/'JMS-version/joint_model/model.py',
                  ROOT/'JMS-version/joint_model/validate.py',ROOT/'JMS-version/joint_model/grippers.py',
                  ROOT/'joint_chamber_cycle_model.py',ROOT/'joint_pairing_model.py']
    manifest=dict(created_utc=datetime.now(timezone.utc).isoformat(),complete_enumeration=False,
                  global_sequence_count=None,permutation_ranks_per_family=a.permutations,
                  counting='Unique ordered groups of physical action START/END labels; numeric timestamps excluded; H merged when order identical.',
                  sampling='Evenly spaced lexicographic permutation ranks; 4 serial construction families per configuration.',
                  dependencies={str(p.relative_to(ROOT)):sha(p) for p in dependencies},files=[])
    for n in a.sizes:
        started=time.monotonic();unique={};case_counts={};case_hashes=defaultdict(set);max_horizon=0;checks=0
        factorial=math.factorial(n);k=min(a.permutations,factorial)
        ranks=[0] if k==1 else [i*(factorial-1)//(k-1) for i in range(k)]
        witness_path=evidence/f'{n}wafer-witnesses.jsonl.gz'
        with gzip.open(witness_path,'wt',encoding='utf-8') as witnesses:
            for recipe,h in itertools.product(('4x1','2x2'),(3,10)):
                cfg=make_config(n,recipe,h);case=f'{recipe}_H{h}';attempts=0
                ids=[f'LP{lp}_W{w}' for lp in range(1,5) for w in range(1,n//4+1)]
                for chamber,cadence,rank in itertools.product((1,2),('early','late'),ranks):
                    order=permutation_at(ids,rank)
                    data=construct(cfg,template(order,recipe,h,chamber,cadence))
                    audit=audit_projection(data);sequence,key,count=actions(data);attempts+=1;checks+=audit['physical']['checks']
                    record=dict(case=case,rank=str(rank),chamber=chamber,cadence=cadence,order_hash=key,
                                audit=audit,witness=data)
                    witnesses.write(encoded(record)+'\n')
                    max_horizon=max(max_horizon,max(e['end'] for e in data['events']))
                    case_hashes[case].add(key)
                    if key not in unique:unique[key]=dict(sequence=sequence,actions=count,cases=[],witnesses=[],first=record)
                    entry=unique[key]
                    if case not in entry['cases']:entry['cases'].append(case)
                    entry['witnesses'].append(dict(case=case,rank=str(rank),chamber=chamber,cadence=cadence))
                    if attempts%8==0:print(f'n={n} {case} generated={attempts}/{4*k} unique={len(case_hashes[case])} elapsed={time.monotonic()-started:.1f}s',flush=True)
                case_counts[case]=len(case_hashes[case])
        path=output/filename(n,len(unique),False)
        with path.open('w',encoding='utf-8-sig',newline='\n') as stream:
            stream.write(heading(n,len(unique),False))
            stream.write('这不是完整枚举结果，也不是最优排程集合。仅是确定性选取、逐条物理验解通过的可行子集。\n')
            stream.write('配置：双源；CH1/CH2两腔可用；8片辅助片；4个LP均分产品；工艺4x1/2x2与H=3/10的四组分别核验。\n')
            stream.write('每条包含全部产品以及实际使用的辅助片、旋转、生产和清洁动作（含已激活末端清洁）。未使用辅助片无动作。\n')
            stream.write('LP1.1对应LP1_W1；PEC1对应模型辅助片D1；PECstorage对应VS。PEC编号不是VTR手爪编号。\n')
            stream.write('START/END表示动作边界； -> 表示先后；同一{... || ...}组为同一时刻的边界。START之后、END之前动作仍在执行。\n')
            stream.write('时间数值不参与去重。保留相同起止时刻与重叠关系；仅改变具体秒数而不改变边界顺序不重复计数。\n')
            stream.write('模型中的搬运间隔、AL对准、抽气/放气和复位通过时间下限或占用约束表达，不虚构成额外独立机器人动作。\n')
            stream.write('当前构造族采用串行处理和单腔选择；未覆盖双腔并行、所有配对、所有清洁位置、所有资源交错。不能由此推断全空间占比。\n')
            stream.write('每条经过独立物理验解、容量上界、时间域与标签规范检查；未对每条另建完整MILP求解认证，不声称完整MILP最优证明。\n')
            stream.write(f'各配置内部去重数：{encoded(case_counts)}；跨H相同动作顺序合并，因此配置内计数之和可能大于本文件唯一条数。\n')
            stream.write(f'每个配置的构造性顺序数下界：N! = {factorial}。理由：每次只安排一个产品，完成其全部加工/回片与清洁后处理下一个；N个带身份产品的任意排列都可构造，首次LP取片顺序不同保证顺序不同。\n')
            stream.write('上述N!是整个串行构造族的数学下界，不是已写出的条数；本文件只选取其中的排列并扩展清洁/腔室选择。\n')
            stream.write('所有该单产品批次的耗时与LP身份无关：产品前总以固定辅助片取片开始，上一产品已回片，LP间机器人跨站时间统一；各LP产品工艺相同。故置换身份不破坏可行性或100000秒时域。\n')
            stream.write(f'本次最大完整动作终点={max_horizon:g}秒（仅作时间证据，不参与顺序计数）。\n')
            stream.write(f'逐条数值证据：evidence/{witness_path.name}；哈希及配置见manifest.json。\n\n')
            for index,(key,entry) in enumerate(unique.items(),1):
                first=entry['first'];stream.write(f'===== 排程 {index:06d} | 适用配置 {", ".join(entry["cases"])} =====\n')
                stream.write(f'顺序SHA256: {key}\n动作数: {entry["actions"]}; 边界组数: {len(entry["sequence"])}\n')
                stream.write(f'构造依据: chamber={first["chamber"]}, cadence={first["cadence"]}, permutation_rank={first["rank"]}\n')
                stream.write('动作序列（完整）：\n')
                stream.write(' ->\n'.join('{ '+' || '.join(phase+' '+label for phase,label in group)+' }' for group in entry['sequence'])+'\n\n')
        manifest['files'].append(dict(n=n,path=str(path.relative_to(output)),sha256=sha(path),unique_orders=len(unique),
            per_configuration=case_counts,constructed_lower_bound_per_configuration=str(factorial),all_feasible_orders=None,
            witnesses=str(witness_path.relative_to(output)),witness_sha256=sha(witness_path),physical_checks=checks,
            full_milp_solver_certified=False,max_complete_horizon=max_horizon,seconds=time.monotonic()-started))
        (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f'WROTE {path.name} | complete_enumeration=False | {time.monotonic()-started:.1f}s',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(__doc__);parser.add_argument('--output',default='JMS-version/gif/kexingyu')
    parser.add_argument('--sizes',nargs='+',type=int,default=[8,16,32]);parser.add_argument('--permutations',type=int,default=16)
    args=parser.parse_args()
    if any(n not in (8,16,32) for n in args.sizes) or args.permutations<1:parser.error('Use sizes 8/16/32 and positive permutation count')
    run(args)
