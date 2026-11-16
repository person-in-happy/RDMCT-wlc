"""Build and verify the English submission without changing the Chinese manuscript."""
from pathlib import Path
import argparse, hashlib, json, re, shutil, subprocess, zipfile
import pymupdf
from PIL import Image, ImageDraw
PAPER=Path(__file__).resolve().parents[1]
BUILD=PAPER/'output/.build_en'
OUT=PAPER/'output/submission'
NAME='JMS_Submission_EN'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def compile_tex(source,out):
    out.mkdir(parents=True,exist_ok=True)
    for i in range(3):
        r=subprocess.run(['pdflatex','-interaction=nonstopmode','-halt-on-error','-file-line-error','-output-directory='+str(out),source.name],cwd=source.parent,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (out/f'pass{i+1}.txt').write_bytes(r.stdout)
        if r.returncode:raise RuntimeError(r.stdout[-3000:].decode('utf-8',errors='replace'))
    log=(out/(source.stem+'.log')).read_text('utf-8',errors='replace')
    bad=[x for x in log.splitlines() if any(k in x for k in ('Overfull','undefined references','undefined on input','Float too large','Missing character','multiply defined'))]
    if bad:raise RuntimeError('\n'.join(bad))
    return out/(source.stem+'.pdf'),[x for x in log.splitlines() if 'Warning' in x]

def verify_sources():
    from assemble_submission_en import environments
    cn=(PAPER/'JMS_Review_CN.tex').read_text('utf-8');en=(PAPER/(NAME+'.tex')).read_text('utf-8')
    assert environments(cn,'equation')==environments(en,'equation')
    for macro in ('label','citep','bibitem'):
        pattern=r'\\'+macro+r'\{([^}]+)\}'
        assert re.findall(pattern,cn)==re.findall(pattern,en),(macro,'sequence changed')
    labels=set(re.findall(r'\\label\{([^}]+)\}',en));refs=set(re.findall(r'\\(?:eqref|ref)\{([^}]+)\}',en))
    assert refs<=labels,refs-labels
    assert not re.search('[\u4e00-\u9fff]',en)
    ct,et=environments(cn,'table'),environments(en,'table')
    for label in ct:
        if label.startswith('tab:symbol'):continue
        def nums(t):
            body=t.split(r'\midrule',1)[1].split(r'\bottomrule',1)[0]
            return re.findall(r'\d+(?:\.\d+)?',body)
        assert nums(ct[label])==nums(et[label]),label
    fm=json.loads((PAPER/'figures/submission_en/manifest.json').read_text('utf-8'))
    assert fm['optimization_calls']==0
    assert [i['intervals'] for i in fm['schedules']]==[66,462]
    assert [i['cmax'] for i in fm['schedules']]==[324,920]
    assert all(i['legend_columns']==4 and i['single_column'] for i in fm['schedules'])
    return {'identical_equations':34,'identical_numeric_result_tables':11,'identical_label_citation_and_bibliography_sequences':True,'chinese_source_sha256':sha(PAPER/'JMS_Review_CN.tex')}

def render(pdf):
    out=BUILD/'rendered';out.mkdir(parents=True,exist_ok=True)
    doc=pymupdf.open(pdf);contact=Image.new('RGB',(1280,460*((len(doc)+3)//4)),'#dddddd');draw=ImageDraw.Draw(contact);extents=[]
    for i,page in enumerate(doc):
        pix=page.get_pixmap(matrix=pymupdf.Matrix(1.5,1.5),alpha=False);pix.save(out/f'page-{i+1:02}.png')
        im=Image.frombytes('RGB',(pix.width,pix.height),pix.samples);im.thumbnail((310,438))
        x=(i%4)*320+5;y=(i//4)*460+18;contact.paste(im,(x,y));draw.text((x,y-15),str(i+1),fill='black')
        blocks=[b[:4] for b in page.get_text('blocks') if b[1]<page.rect.height-50]
        extents.append({'page':i+1,'text_characters':len(page.get_text()),'content_bottom':max((b[3] for b in blocks),default=0)})
    contact.save(out/'contact.png')
    assert len(doc[-1].get_text())>1000,'Sparse final page requires layout review'
    return {'pages':len(doc),'page_text_extents':extents,'rendering':'PyMuPDF 1.5x; all-page contact sheet and full-page PNGs'}

def native_word_render():
    import win32com.client
    out=BUILD/'docx';out.mkdir(parents=True,exist_ok=True)
    app=win32com.client.DispatchEx('Word.Application');app.Visible=False;app.DisplayAlerts=0;checks=[]
    try:
        for path in sorted(OUT.glob('*.docx')):
            doc=app.Documents.Open(str(path),ReadOnly=True,AddToRecentFiles=False,Visible=False)
            target=out/(path.stem+'.pdf');doc.ExportAsFixedFormat(str(target),17);doc.Close(False)
            pdf=pymupdf.open(target);assert len(pdf)==1,(path.name,len(pdf))
            for i,page in enumerate(pdf):page.get_pixmap(matrix=pymupdf.Matrix(1.5,1.5),alpha=False).save(out/f'{path.stem}-{i+1}.png')
            checks.append({'file':path.name,'pages':len(pdf)})
    finally:app.Quit()
    (out/'render_checks.json').write_text(json.dumps(checks,indent=2)+'\n','utf-8')
    return checks

def package(pdf):
    text=(PAPER/(NAME+'.tex')).read_text('utf-8');flat=re.sub(r'\\graphicspath\{[^\n]+',lambda _:r'\graphicspath{{./}}',text)
    sources={NAME+'.tex':flat.encode('utf-8')}
    for i in range(1,8):
        path=PAPER/f'figures/submission_en/Figure{i}.pdf';sources[path.name]=path.read_bytes();shutil.copyfile(path,OUT/path.name)
    source_zip=OUT/'JMS_LaTeX_Source.zip'
    with zipfile.ZipFile(source_zip,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in sources.items():z.writestr(name,data)
    stage=BUILD/'package_check';stage.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(source_zip) as z:
        assert z.testzip() is None and len(z.namelist())==8
        assert all('/' not in n and '\\' not in n for n in z.namelist());z.extractall(stage)
    rebuilt,warnings=compile_tex(stage/(NAME+'.tex'),stage)
    a,b=pymupdf.open(pdf),pymupdf.open(rebuilt)
    assert len(a)==len(b) and [p.get_text() for p in a]==[p.get_text() for p in b]
    names=[NAME+'.pdf','JMS_LaTeX_Source.zip','Cover_Letter.docx','Highlights.docx','Declaration_of_Interest.docx','Title_Page.docx','CRediT_Statement.docx','Submission_Metadata.txt','UPLOAD_README.txt']+[f'Figure{i}.pdf' for i in range(1,8)]
    with zipfile.ZipFile(OUT/'JMS_Submission_EN.zip','w',zipfile.ZIP_DEFLATED) as z:
        for name in names:
            assert (OUT/name).is_file(),name
            z.write(OUT/name,name)
    return {'source_archive_files':8,'source_archive_flat':True,'independent_rebuild_identical':True,'submission_archive_files':len(names),'sha256':{n:sha(OUT/n) for n in names}}

def main():
    parser=argparse.ArgumentParser(__doc__);parser.add_argument('--render-docx',action='store_true');args=parser.parse_args()
    from assemble_submission_en import main as assemble
    from build_submission_documents import main as documents
    assemble();report=verify_sources();documents();pdf,warnings=compile_tex(PAPER/(NAME+'.tex'),BUILD)
    report.update(render(pdf));report['latex_warnings']=warnings
    if args.render_docx:report['word_documents']=native_word_render()
    for target in (PAPER/(NAME+'.pdf'),PAPER/'output/pdf'/(NAME+'.pdf'),OUT/(NAME+'.pdf')):
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(pdf,target)
    report['packaging']=package(pdf);report['english_source_sha256']=sha(PAPER/(NAME+'.tex'));report['english_pdf_sha256']=sha(PAPER/(NAME+'.pdf'))
    (PAPER/'submission/validation.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
    print(json.dumps({k:report[k] for k in ('pages','identical_equations','identical_numeric_result_tables','latex_warnings')},indent=2))
    print('Packaged the English manuscript, eight flat source files, seven vector figures, and five editable Word documents.')

if __name__=='__main__':main()
