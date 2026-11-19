"""Create editable submission documents as standard OOXML; render with native Word."""
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED
import json
import re

PAPER=Path(__file__).resolve().parents[1]
OUT=PAPER/'output/submission'
TITLE=re.search(r'\\title\{([^}]+)\}',(PAPER/'JMS_Submission_EN.tex').read_text('utf-8'))[1]
AFFILIATION='Department of Control Science and Engineering, University of Science and Technology Beijing, No. 30 Xueyuan Road, Haidian District, Beijing 100083, China'
HIGHLIGHTS=[
 'PW-pair modeling links full occupancy, cleaning, and finite auxiliary reuse.',
 'Two-stage solving improves the secondary objective at equal 300 s budgets.',
 'Structured initialization improves mixed-recipe schedules within limited time.',
 'Variable-role features guide learned cut selection and structural reranking.',
 'Shared-start ablations and event replay validate the proposed methods.'
]
COI='The authors declare that they have no known competing financial interests or personal relationships that could have appeared to influence the work reported in this paper.'
FUNDING='This research did not receive any specific grant from funding agencies in the public, commercial, or not-for-profit sectors.'
CREDIT=[
 ('Lincong Wei','Conceptualization, Methodology, Software, Validation, Formal analysis, Investigation, Data curation, Visualization, Writing - original draft, Writing - review & editing.'),
 ('Lizhen Shao','Conceptualization, Methodology, Formal analysis, Writing - review & editing, Project administration.'),
 ('Wei Wang','Formal analysis, Investigation, Writing - review & editing, Supervision.')
]
COVER=[
 ('Normal','The Editors'),
 ('Normal','Journal of Manufacturing Systems'),
 ('Normal','Dear Editors,'),
 ('Normal',f'Please consider our research article, "{TITLE}," for publication in the Journal of Manufacturing Systems.'),
 ('Normal','Advanced fabrication combines complex process requirements with high throughput, requiring timely schedules for rotating-chamber cluster tools. Full occupancy, continuous processing, cleaning, and a finite reusable auxiliary inventory couple wafer pairing and processing with shared transport. Four-finger vacuum and two-finger atmospheric robots motivate two-wafer PW pairs as the minimum modeling unit, while individual wafer operations retain their own timing variables.'),
 ('Normal','The study makes three contributions. A two-stage mixed-integer linear programming model first minimizes batch makespan, then minimizes a weighted objective for waiting time and rhythm deviation while preserving the makespan bound and principal discrete structure. Structured initialization progressively releases resource service orders to improve the starting schedule. Variable-role features and structure-aware reranking combine with reinforcement-learning-based cut selection to account for cut quality and complementarity.'),
 ('Normal','With equal 300 s solve budgets, the two-stage method matches the batch makespans of normalized joint objectives on two 16-product instances and reduces the weighted objective for waiting time and rhythm deviation by 31.45% and 5.47%. Structured initialization reduces mean batch makespan for mixed S2 from 521 to 492 s. With shared initial solutions, the complete cut-selection combination improves on all three ablations on two instances and ties on the other four. Full-model checks and independent event replay also validate the two- and 16-product schedules.'),
 ('Normal','We believe the work will interest readers studying the integrated operation and control of semiconductor manufacturing equipment, particularly the interaction of reusable material resources, processing cycles, and shared handling systems.'),
 ('Normal','Thank you for considering our manuscript.'),
 ('Normal','Sincerely,'),
 ('Normal','Lizhen Shao\nCorresponding author\nUniversity of Science and Technology Beijing\nlshao@ustb.edu.cn'),
]

def paragraph(style,text):
    props=f'<w:pStyle w:val="{style}"/>'
    if style=='ListBullet':props+='<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>'
    runs='<w:br/>'.join('<w:t xml:space="preserve">'+escape(line)+'</w:t>' for line in text.split('\n'))
    return '<w:p><w:pPr>'+props+'</w:pPr><w:r>'+runs+'</w:r></w:p>'

def document(filename,paragraphs):
    ns='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    body=''.join(paragraph(*p) for p in paragraphs)
    sect='<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1080" w:right="1260" w:bottom="1080" w:left="1260" w:header="360" w:footer="360"/></w:sectPr>'
    styles=f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="{ns}">
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:sz w:val="22"/><w:color w:val="000000"/><w:lang w:val="en-US"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="100" w:line="264" w:lineRule="auto"/><w:widowControl/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="200"/><w:keepNext/></w:pPr><w:rPr><w:b/><w:sz w:val="30"/><w:color w:val="000000"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="160" w:after="100"/><w:keepNext/></w:pPr><w:rPr><w:b/><w:sz w:val="24"/><w:color w:val="000000"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="ListBullet"><w:name w:val="List Bullet"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="160"/></w:pPr></w:style></w:styles>'''
    numbering=f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:numbering xmlns:w="{ns}"><w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="singleLevel"/><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="•"/><w:lvlJc w:val="left"/><w:pPr><w:tabs><w:tab w:val="num" w:pos="300"/></w:tabs><w:ind w:left="300" w:hanging="300"/></w:pPr></w:lvl></w:abstractNum><w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num></w:numbering>'''
    content_types='''<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/><Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/></Types>'''
    rels='''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/></Relationships>'''
    docrels='''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/></Relationships>'''
    core=f'''<?xml version="1.0" encoding="UTF-8"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>{escape(filename.replace('_',' '))}</dc:title><dc:creator>Lincong Wei; Lizhen Shao; Wei Wang</dc:creator></cp:coreProperties>'''
    files={'[Content_Types].xml':content_types,'_rels/.rels':rels,'word/_rels/document.xml.rels':docrels,
           'word/document.xml':f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="{ns}"><w:body>{body}{sect}</w:body></w:document>',
           'word/styles.xml':styles,'word/numbering.xml':numbering,'docProps/core.xml':core}
    with ZipFile(OUT/(filename+'.docx'),'w',ZIP_DEFLATED) as z:
        for name,text in files.items():z.writestr(name,text.encode('utf-8'))

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    assert 3<=len(HIGHLIGHTS)<=5 and all(len(x)<=85 for x in HIGHLIGHTS)
    document('Highlights',[('Title','Highlights')]+[('ListBullet',x) for x in HIGHLIGHTS])
    document('Cover_Letter',COVER)
    document('Declaration_of_Interest',[('Title','Declaration of competing interest'),('Normal',TITLE),('Normal','Lincong Wei, Lizhen Shao, Wei Wang'),('Normal',COI)])
    document('Title_Page',[('Title',TITLE),('Normal','Lincong Wei, Lizhen Shao, Wei Wang'),('Normal',AFFILIATION),('Heading1','Corresponding author'),('Normal','Lizhen Shao\nEmail: lshao@ustb.edu.cn\n'+AFFILIATION),('Heading1','Article type'),('Normal','Research article'),('Heading1','Keywords'),('Normal','Semiconductor manufacturing systems; cluster tools; dual-source material flow; mixed-integer linear programming; learning-based cut selection'),('Heading1','Funding'),('Normal',FUNDING)])
    document('CRediT_Statement',[('Title','CRediT authorship contribution statement'),('Normal',TITLE)]+[('Normal',name+': '+roles) for name,roles in CREDIT]+[('Normal','All authors reviewed and approved the final manuscript.')])
    s=(PAPER/'JMS_Submission_EN.tex').read_text('utf-8')
    abstract=re.search(r'\\begin\{abstract\}([\s\S]*?)\\end\{abstract\}',s)[1].strip()
    abstract=abstract.replace('$4\\times1$','4 × 1').replace('$2\\times2$','2 × 2').replace('~',' ').replace('\\%','%')
    metadata={'title':TITLE,'article_type':'Research article','authors':[{'given_name':'Lincong','family_name':'Wei','corresponding':False},{'given_name':'Lizhen','family_name':'Shao','corresponding':True,'email':'lshao@ustb.edu.cn'},{'given_name':'Wei','family_name':'Wang','corresponding':False}],'affiliation':AFFILIATION,'abstract':abstract,'keywords':['semiconductor manufacturing systems','cluster tools','dual-source material flow','mixed-integer linear programming','learning-based cut selection'],'funding':FUNDING,'competing_interests':COI,'highlights':HIGHLIGHTS,'highlight_character_counts':[len(x) for x in HIGHLIGHTS]}
    (PAPER/'submission/submission_metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n','utf-8')
    (OUT/'Submission_Metadata.txt').write_text('TITLE\n'+TITLE+'\n\nAUTHORS\nLincong Wei; Lizhen Shao; Wei Wang\n\nAFFILIATION\n'+AFFILIATION+'\n\nCORRESPONDING AUTHOR\nLizhen Shao; lshao@ustb.edu.cn\n\nABSTRACT\n'+abstract+'\n\nKEYWORDS\n'+'; '.join(metadata['keywords'])+'\n\nFUNDING\n'+FUNDING+'\n','utf-8')
    print('Created five editable Word documents. Highlight lengths:',metadata['highlight_character_counts'])

if __name__=='__main__':main()
