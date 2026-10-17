"""Engineering data-to-schedule workflow; original vector artwork, real event output."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle,FancyArrowPatch
OUT=Path(__file__).resolve().parent

def implementation_framework(lang='cn'):
 cn=lang=='cn'; ink='#242424'
 plt.rcParams.update({'font.family':['Microsoft YaHei','Arial','DejaVu Sans'] if cn else ['Arial','DejaVu Sans'],'font.size':7,'pdf.fonttype':42,'svg.fonttype':'none'})
 fig,ax=plt.subplots(figsize=(7.2,3.6));fig.subplots_adjust(left=.015,right=.985,bottom=.035,top=.965);ax.set(xlim=(0,180),ylim=(0,100));ax.axis('off')
 def txt(x,y,s,size=7,ha='center',bold=False):
  return ax.text(x,y,s,fontsize=size,ha=ha,va='center',fontweight='bold' if bold else 'normal',linespacing=1.35,color=ink)
 def line(a,b,lw=.6):ax.plot([a[0],b[0]],[a[1],b[1]],color=ink,lw=lw)
 def arr(points):
  for a,b in zip(points[:-2],points[1:-1]):line(a,b)
  ax.add_patch(FancyArrowPatch(points[-2],points[-1],arrowstyle='-|>',mutation_scale=8,lw=.7,color=ink,shrinkA=0,shrinkB=0))
 def box(x,y,w,h,title,body):
  ax.add_patch(Rectangle((x,y),w,h,fill=False,edgecolor=ink,lw=.7))
  txt(x+w/2,y+h-4.5,title,7.5,bold=True);line((x,y+h-9),(x+w,y+h-9))
  txt(x+w/2,y+(h-9)/2,body,6.8)
 for x,w,s in [(2,42,'配置数据' if cn else 'Configuration data'),(56,62,'建模与求解' if cn else 'Model and solution'),(134,44,'排程输出' if cn else 'Schedule outputs')]:
  txt(x+w/2,96,s,8.5,bold=True);line((x,91),(x+w,91),.8)
 txt(23,84,'批次与工艺规则' if cn else 'Lot and process rules',7.5,bold=True)
 entries=[('批量' if cn else 'Lot size',r'$N$'),('预设模式' if cn else 'Preset mode',r'$4\times1,\ 2\times2$'),('清洁间隔' if cn else 'Cleaning interval',r'$H$'),('配方时间' if cn else 'Process times',r'$d_o$')]
 for k,(a,b) in enumerate(entries):txt(3,76-7*k,a,6.7,ha='left');txt(43,76-7*k,b,7,ha='right')
 line((2,49),(44,49))
 txt(23,43,'双源物料与设备资源' if cn else 'Material sources and resources',7.1,bold=True)
 txt(3,35,'产品片：大气侧LP' if cn else 'Products: atmospheric LP',6.6,ha='left')
 txt(3,28,'辅助片：真空存储区' if cn else 'Dummies: vacuum storage',6.6,ha='left')
 txt(3,19,'ATR / AL / LL / VTR / CH2 / CH3',6,ha='left')
 txt(3,11,'容量、库存、驻留与动作时间' if cn else 'Capacity, stock, residency, action times',6.4,ha='left')
 box(56,63,62,23,'PW配对与事件MILP' if cn else 'PW pairing and event MILP','满片占用 · 物料复用 · 资源互斥' if cn else 'Full occupancy / reuse / resource conflicts')
 box(56,31,62,24,'阶段1：完工时间优化' if cn else 'Stage 1: makespan optimization','SPBS初始解 → SCIP搜索\nRDMCT-HBS：候选割选择' if cn else 'SPBS initial solution → SCIP search\nRDMCT-HBS: candidate-cut selection')
 box(56,2,62,21,'阶段2：等待与节拍精修' if cn else 'Stage 2: waiting and cadence','保持完工时间上界与主要离散次序' if cn else 'Retain makespan bound and main discrete order')
 line((44,70),(49,70));ax.plot(49,70,'o',ms=2,color=ink);arr([(44,28),(49,28),(49,77),(56,77)])
 arr([(87,63),(87,55)]);arr([(87,31),(87,23)])
 txt(89,59,r'$\mathcal{F}$',7,ha='left');txt(89,27,r'$\widehat C,\ \widehat x$',7,ha='left')
 # Exported event times from the verified Fig. 8 schedule.
 txt(156,84,'验解与事件导出' if cn else 'Validation and event export',7.5,bold=True)
 txt(156,76,'CH2 | N=16, H=3',6.7)
 line((134,71),(178,71))
 for x,s in [(134,'动作' if cn else 'Action'),(161,'开始/s' if cn else 'Start/s'),(176,'结束/s' if cn else 'End/s')]:txt(x,67,s,6.2,ha='left' if x==134 else 'right')
 line((134,63),(178,63))
 data=[('等待','Wait',1106,1108),('卸片','Unload',1108,1112),('等待','Wait',1112,1116),('装片','Load',1116,1120),('加工','Process',1120,1210)]
 for k,(a,b,start,end) in enumerate(data):
  y=58-k*7;txt(134,y,a if cn else b,6.5,ha='left');txt(161,y,str(start),6.5,ha='right');txt(176,y,str(end),6.5,ha='right')
 line((134,25),(178,25))
 txt(156,19,r'$C_{\max}=1402$ s',7.5)
 txt(156,11,'WPH = 41.08',7.5)
 arr([(118,12),(126,12),(126,84),(132,84)])
 fig.canvas.draw()
 for ext in ['pdf','svg','png','tiff']:fig.savefig(OUT/f'fig_framework_{lang}_nature.{ext}',dpi=450)
 plt.close(fig)
if __name__=='__main__':
 for lang in ['cn','en']:implementation_framework(lang)
