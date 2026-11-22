"""Render the staged thesis, map scientific claims to pages, and check the installed output."""
from pathlib import Path
import re
import subprocess
import sys
from PIL import Image, ImageDraw, ImageChops

from manuscript import STAGE, THESIS, REPORT, MANIFEST, page_texts
from large75 import digest, read, save

DEST=REPORT/"page_review"/digest(STAGE/"main.pdf")[:12]


def thumbnail_sheets(files,prefix,width,height,columns,per_sheet):
    for start in range(0,len(files),per_sheet):
        batch=files[start:start+per_sheet]
        sheet=Image.new("RGB",(columns*(width+12),((len(batch)+columns-1)//columns)*(height+25)),"#e5e7e9")
        draw=ImageDraw.Draw(sheet)
        for index,(page,path) in enumerate(batch):
            with Image.open(path) as candidate:
                im=candidate.convert("RGB")
                im.thumbnail((width,height))
                x,y=(index%columns)*(width+12),(index//columns)*(height+25)
                sheet.paste(im,(x+(width-im.width)//2+6,y+4))
                draw.text((x+9,y+height+5),f"PDF {page}",fill="#182734")
        sheet.save(DEST/f"{prefix}_{start//per_sheet+1}.jpg",quality=88)


def images_for(folder,prefix,dpi):
    subprocess.run(["pdftoppm","-r",str(dpi),"-png",str(folder/"main.pdf"),str(DEST/prefix)],
                   check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    files=sorted((int(p.stem.split("-")[-1]),p) for p in DEST.glob(prefix+"-*.png"))
    return files


def prepare():
    DEST.mkdir(parents=True,exist_ok=True)
    pages=page_texts(STAGE)
    flat=[re.sub(r"\s+","",p) for p in pages]
    search=["从固定工期精修到交付与等待的权衡","以配对方式筛选邻域","结构调整、重定时与验证",
            "两目标的冲突与可认证前沿","等预算对照与扰动","75片混合批次的可行前沿","交付与路线等待的双目标权衡"]
    matched={key:[i+1 for i,p in enumerate(flat) if key in p] for key in search}
    assert all(matched.values()),matched
    details={4,5}
    for numbers in matched.values():
        details.update(numbers)
    tokens=("0.44494","0.43287","0.43898","0.27137","0.54479","817","26331","非支持点","2.45","24,271,470","24 271 470")
    for i,p in enumerate(flat,1):
        if any(token in p for token in tokens):
            details.add(i)
    method_start=matched[search[0]][-1]
    method_end=matched[search[2]][-1]
    exper_start=matched[search[3]][-1]
    exper_end=matched[search[-1]][-1]
    details.update(range(method_start,min(len(pages),method_end+2)+1))
    details.update(range(exper_start,exper_end+1))
    allfiles=images_for(STAGE,"page",76)
    assert list(range(1,len(pages)+1))==[p for p,_ in allfiles]
    thumbnail_sheets(allfiles,"all",178,248,5,15)
    selected=[]
    for p in sorted(details):
        dest=DEST/f"detail_{p}"
        subprocess.run(["pdftoppm","-f",str(p),"-l",str(p),"-r","118","-png","-singlefile",
                        str(STAGE/"main.pdf"),str(dest)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        selected.append((p,dest.with_suffix(".png")))
    thumbnail_sheets(selected,"selected",355,485,3,6)
    save(DEST/"pages.json",dict(pages=len(pages),selected=sorted(details),anchors=matched,
         overfull=[s for s in (STAGE/"main.log").read_text(encoding="utf-8",errors="replace").splitlines()
                   if "Overfull" in s],contents=[(i,p[:120]) for i,p in enumerate(pages,1)]))
    print("PDF pages",len(pages),"detailed review",sorted(details),"anchors",matched,flush=True)


def accept():
    data=read(DEST/"pages.json")
    assert len(list(DEST.glob("detail_*.png")))>=len(data["selected"])
    save(REPORT/"visual_qa.json",dict(pdf_hash=digest(STAGE/"main.pdf"),pages=data["pages"],
         visually_reviewed=data["selected"],anchors=data["anchors"],overfull=data["overfull"]))


def installed():
    original=dict((n,p) for n,p in images_for(THESIS,"installed",76))
    staged={int(p.stem.split("-")[-1]):p for p in DEST.glob("page-*.png")}
    assert original.keys()==staged.keys()
    for page in original:
        with Image.open(original[page]) as a, Image.open(staged[page]) as b:
            assert a.size==b.size and not ImageChops.difference(a,b).getbbox(),f"Pixel mismatch at page {page}"
    data=read(REPORT/"installed.json")
    data["all_pages_pixel_identical_76dpi"]=len(original)
    save(REPORT/"installed.json",data)
    print("Installed PDF matches the reviewed render on all",len(original),"pages",flush=True)


if __name__=="__main__":
    {"prepare":prepare,"accept":accept,"installed":installed}[sys.argv[1]]()
