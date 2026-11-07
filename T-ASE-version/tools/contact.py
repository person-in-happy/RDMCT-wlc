from pathlib import Path
import pymupdf
from PIL import Image,ImageOps,ImageDraw
p=Path('T-ASE-version')
d=pymupdf.open(p/'TASE_Submission_EN.pdf')
for i,pg in enumerate(d):
 text=pg.get_text()
 print(i+1, text[:100].replace('\n',' '),len(text))
for start in range(0,len(d),6):
 imgs=[]
 for i in range(start,min(start+6,len(d))):
  im=Image.open(p/f'output/qa/TASE_Submission_EN/page-{i+1:02d}.png').convert('RGB');im.thumbnail((420,570))
  tile=Image.new('RGB',(440,600),'#ddd');tile.paste(im,((440-im.width)//2,20));ImageDraw.Draw(tile).text((10,580),str(i+1),fill='black');imgs.append(tile)
 grid=Image.new('RGB',(1320,1200),'white')
 for n,im in enumerate(imgs):grid.paste(im,((n%3)*440,(n//3)*600))
 grid.save(p/f'output/qa/contact-{start//6+1}.png')

