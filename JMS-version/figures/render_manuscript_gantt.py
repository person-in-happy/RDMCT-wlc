"""Render Figs 5-8 up to each product makespan, auditing process duration and geometry."""
from pathlib import Path
import json,sys,re
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import gantt_build as g
OUT=Path(__file__).resolve().parent

def main():
 audits=[]
 for folder,stem,wait in g.REPRESENTATIVE_CASES:
  tasks,lanes,m=g.parse_source(g.source_path(folder));tasks=list(dict.fromkeys(tasks))
  expected=90 if stem.endswith('_22') else 180
  process=[t for t in tasks if t.lane.startswith('CH') and t.source_color=='#E45756']
  assert all(abs(t.end-t.start-expected)<1e-5 for t in process)
  assert all(t.end<=m.cmax+1e-5 for t in process)
  for p in process:
   assert not any(t.lane==p.lane and t.source_color in ['#F2A09A','#BAB0AC','#2A9D8F'] and min(p.end,t.end)-max(p.start,t.start)>1e-5 for t in tasks)
  # Keep the established product-return horizon; end the axis at the final product return.
  visible=[g.Task(t.lane,t.start,min(t.end,m.cmax),t.source_color,t.source_y) for t in tasks if t.start<m.cmax and t.end>t.start]
  for lang in ['cn','en']:
   g.configure(lang);fig=plt.figure(figsize=(3.5,3.15));ax=fig.add_axes([.24,.37,.745,.56])
   g.draw_gantt(ax,[t for t in visible if not (t.lane.startswith('CH') and t.source_color=='#E45756')],lanes,0,m.cmax,lang);step=200 if m.cmax<1100 else 300; ticks=list(range(0,int(m.cmax)-70,step))+[m.cmax];ax.set_xticks(ticks);ax.set_xticklabels([f'{v:.0f}' for v in ticks]);ax.tick_params(labelsize=5.8)
   ax.set_yticklabels([re.sub(r'CH[23](?!\d)',lambda m: {'CH2':'CH1','CH3':'CH2'}[m[0]],t.get_text()) for t in ax.get_yticklabels()])
   ch_y={len(lanes)-1-lanes.index(lane) for lane in lanes if lane.startswith('CH')}
   for patch in ax.patches:
    if round(patch.get_y()+patch.get_height()/2) in ch_y:
     patch.set_linewidth(0);patch.set_antialiased(False)
   ax.get_xticklabels()[0].set_ha('left');ax.get_xticklabels()[-1].set_ha('right')
   ax.set_xlabel('时间 / s' if lang=='cn' else 'Time / s',fontsize=6.3)
   widths=[]
   for p in process:
    y=len(lanes)-1-lanes.index(p.lane)
    patch=ax.barh(y,p.end-p.start,left=p.start,height=.62,color=g.COLOR_MAP['#E45756'],edgecolor='none',lw=0,antialiased=False,zorder=5)[0]
    widths.append(patch.get_width())
   ax.axvline(m.cmax,color='#303030',ls=(0,(3,2)),lw=.7)
   ax.text(m.cmax,len(lanes)-.33,f'Cmax {m.cmax:.0f} s',ha='right',va='bottom',fontsize=6)
   metric_artist=fig.text(.59,.255,f'WPH {m.wph:.2f} | '+(('路线总等待 ' if lang=='cn' else 'Total route wait ')+f'{wait:.0f} s'),ha='center',fontsize=6.3)
   short=['ATR pick','ATR move','AL / ATR place','AL exchange','LL pump','LL vacuum wait','LL vent','LL atm. wait','VTR load','VTR transfer','VTR unload','Processing','Cleaning','Chamber wait','Exchange / reset']
   handles=[Patch(facecolor=target,label=cn if lang=='cn' else short[i]) for i,(source,target,en,cn) in enumerate(g.ACTION_STYLE) if any(t.source_color==source for t in tasks)]
   fig.legend(handles=handles,loc='lower center',ncol=3,fontsize=4.8,bbox_to_anchor=(.52,.003),frameon=False,columnspacing=.8)
   fig.canvas.draw();ren=fig.canvas.get_renderer();assert not ax.get_tightbbox(ren).overlaps(fig.legends[0].get_window_extent(ren))
   assert not ax.get_tightbbox(ren).overlaps(metric_artist.get_window_extent(ren))
   assert not metric_artist.get_window_extent(ren).overlaps(fig.legends[0].get_window_extent(ren))
   for ext in ['pdf','svg','png','tiff']:fig.savefig(OUT/f'{stem}_{lang}_nature.{ext}',dpi=450)
   plt.close(fig)
  audits.append({'stem':stem,'source':str(folder),'process_count':len(process),'duration_s':expected,'axis_limits':[0,m.cmax],'axes_width_fraction':.745,'figure_width_inches':3.5,'process_rect_width_points':3.5*72*.745*expected/m.cmax,'duplicates_removed':True,'process_overlaps':0,'cmax':m.cmax})
 (OUT/'gantt_manifest.json').write_text(json.dumps(audits,indent=2),encoding='utf-8');print(json.dumps(audits,indent=2))
if __name__=='__main__':main()
