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
KEYWORDS = [k.strip() for k in re.search(r'\\begin\{keyword\}(.*?)\\end\{keyword\}', (PAPER/'JMS_Submission_EN.tex').read_text('utf-8'), re.S)[1].split(r'\sep')]
HIGHLIGHTS = [
 'Production and chamber cleaning compete for the same reusable auxiliary wafers.',
 'With flexible unloading, 2-, 4- and 8-wafer mixed batches attain both bounds.',
 'At 810 seconds, retiming cuts the mean process objective by 65.14% for 16 wafers.',
 'Refining the initial schedule cuts mean makespan from 406.33 to 398 seconds.'
]
COI='The authors declare that they have no known competing financial interests or personal relationships that could have appeared to influence the work reported in this paper.'
FUNDING='This research did not receive any specific grant from funding agencies in the public, commercial, or not-for-profit sectors.'
CREDIT = [
 ('Lincong Wei','Software, Validation, Formal analysis, Investigation, Data curation, Visualization, Writing - original draft, Project administration, Writing - review & editing.'),
 ('Lizhen Shao','Methodology, Formal analysis, Investigation, Writing - review & editing, Supervision.'),
 ('Wei Wang','Conceptualization, Formal analysis, Data curation, Writing - review & editing, Supervision.')
]
COVER = [
 ('Normal','Dear Editors,'),
 ('Normal',f'Please consider our research article, "{TITLE}," for publication in the Journal of Manufacturing Systems.'),
 ('Normal','In a semiconductor cluster tool, a chamber can start processing only when all four positions are occupied. The same reusable wafers fill empty positions in production and occupy the chamber during cleaning. The order in which the robot unloads the pairs determines when products leave the chamber and return to their load ports. It also determines when auxiliary wafers become available for the next operation.'),
 ('Normal','Our model connects wafer pairing and chamber assignment to the actions of the robots and load locks. Allowing the chamber to turn and unload the rear product pair first at the end of a chain yields schedules that attain both objective bounds for equal-mix batches of two, four, and eight products. Under conventional unloading, our two-stage method holds the makespan at 810 seconds in a 16-product mixed batch while reducing the mean process objective by 65.14% relative to makespan-only optimization.'),
 ('Normal','The distinction between product completion and tool release matters when scheduling the next batch. In a 75-product schedule, the last product returns at 6050 seconds, while cleaning and auxiliary returns keep the tool occupied until 6533 seconds. The wafer-level schedules identify the resources responsible for this difference.'),
 ('Normal','Thank you for considering the manuscript.'),
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

def declaration_of_interest():
    template = PAPER / 'submission/elsevier_declaration_template.docx'
    with ZipFile(template) as original, ZipFile(OUT/'Declaration_of_Interest.docx', 'w', ZIP_DEFLATED) as completed:
        for entry in original.infolist():
            data = original.read(entry.filename)
            if entry.filename == 'word/document.xml':
                xml = data.decode('utf-8')
                unchecked = '<w14:checked w14:val="0"/>'
                assert xml.count(unchecked) == 3 and COI in re.sub('<[^>]*>', '', xml.split(unchecked)[1])
                xml = xml.replace(unchecked, '<w14:checked w14:val="1"/>', 1)
                data = xml.replace('☐', '☒', 1).encode('utf-8')
            completed.writestr(entry, data)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    assert 3<=len(HIGHLIGHTS)<=5 and all(len(x)<=85 for x in HIGHLIGHTS)
    document('Highlights',[('Title','Highlights')]+[('ListBullet',x) for x in HIGHLIGHTS])
    document('Cover_Letter',COVER)
    declaration_of_interest()
    document('Title_Page',[('Title',TITLE),('Normal','Lincong Wei, Lizhen Shao, Wei Wang'),('Normal',AFFILIATION),('Heading1','Corresponding author'),('Normal','Lizhen Shao\nEmail: lshao@ustb.edu.cn\n'+AFFILIATION),('Heading1','Article type'),('Normal','Research article'),('Heading1','Keywords'),('Normal','; '.join(KEYWORDS)),('Heading1','Funding'),('Normal',FUNDING)])
    document('CRediT_Statement',[('Title','CRediT authorship contribution statement'),('Normal',TITLE)]+[('Normal',name+': '+roles) for name,roles in CREDIT])
    s=(PAPER/'JMS_Submission_EN.tex').read_text('utf-8')
    abstract=re.search(r'\\begin\{abstract\}([\s\S]*?)\\end\{abstract\}',s)[1].strip()
    abstract=abstract.replace('$4\\times1$','4 × 1').replace('$2\\times2$','2 × 2').replace('~',' ').replace('\\%','%')
    metadata={'title':TITLE,'article_type':'Research article','authors':[{'given_name':'Lincong','family_name':'Wei','corresponding':False},{'given_name':'Lizhen','family_name':'Shao','corresponding':True,'email':'lshao@ustb.edu.cn'},{'given_name':'Wei','family_name':'Wang','corresponding':False}],'affiliation':AFFILIATION,'abstract':abstract,'keywords':KEYWORDS,'funding':FUNDING,'competing_interests':COI,'highlights':HIGHLIGHTS,'highlight_character_counts':[len(x) for x in HIGHLIGHTS]}
    (PAPER/'submission/submission_metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n','utf-8')
    (OUT/'Submission_Metadata.txt').write_text('TITLE\n'+TITLE+'\n\nAUTHORS\nLincong Wei; Lizhen Shao; Wei Wang\n\nAFFILIATION\n'+AFFILIATION+'\n\nCORRESPONDING AUTHOR\nLizhen Shao; lshao@ustb.edu.cn\n\nABSTRACT\n'+abstract+'\n\nKEYWORDS\n'+'; '.join(metadata['keywords'])+'\n\nFUNDING\n'+FUNDING+'\n','utf-8')
    print('Created five editable Word documents. Highlight lengths:',metadata['highlight_character_counts'])

if __name__=='__main__':main()
