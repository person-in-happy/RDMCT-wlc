"""Render the three manuscript displays from their verified schedules."""
from gantt import draw,plt
from protocol import OUT,read,rel,save,sha


SCHEDULES={
    'n2': ('runs/D_n2_4x1_sameLP__structure_joint_s1','schedule.json'),
    'n16': ('runs/D_n16_4x1__budget_A_s1','schedule.json'),
    'n75': ('scale75','result.json'),
}


def main():
    published={}
    for size,(folder,file) in SCHEDULES.items():
        path=OUT/folder/file
        expected=read(OUT/folder/'evidence.json')['schedule_sha256']
        if sha(path)!=expected:raise ValueError('Schedule hash mismatch: '+size)
        target=OUT/'figures'/size
        with plt.rc_context({'axes.labelpad':.8,'xtick.major.pad':1.5,'legend.labelspacing':.25,
                             'legend.borderaxespad':.1}):
            settings=draw(read(path),target)
        published[size]=dict(source=rel(path),schedule_sha256=expected,metrics=settings,
                             files={ext:sha(target/f'gantt.{ext}') for ext in ('pdf','svg','png')})
    save(OUT/'figures'/'index.json',published)


if __name__=='__main__':
    main()
