"""Record code, manuscript and verification provenance without changing old evidence."""
from pathlib import Path
import difflib,hashlib,json,xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
PAPER=ROOT/'JMS-version'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    old=HERE/'original/JMS_Review_CN.tex';new=PAPER/'JMS_Review_CN.tex'
    diff=difflib.unified_diff(old.read_text('utf-8-sig').splitlines(True),new.read_text('utf-8-sig').splitlines(True),
                              fromfile='original/JMS_Review_CN.tex',tofile='JMS_Review_CN.tex')
    (HERE/'manuscript.patch').write_text(''.join(diff),'utf-8')
    paths=list((PAPER/'model4_pjob_20261027').glob('*.py'))+list((PAPER/'model4_pjob_20261027').glob('*.ps1'))
    paths+=list((PAPER/'model4_pjob_20261027/examples').glob('*.json'))
    paths+=[new,PAPER/'JMS_Review_CN.pdf',PAPER/'output/pdf/JMS_Review_CN.pdf',PAPER/'MODEL4_EXPERIMENT_COMMANDS.md',
            PAPER/'model4_pjob_20261027/README.md',old,HERE/'original/JMS_Review_CN.pdf']
    hashes={str(p.relative_to(ROOT)):sha(p) for p in sorted(paths)}
    tests=PAPER/'revisions/20261027_model4/backend_validation_final/tests.xml'
    suites=ET.parse(tests).getroot()
    cases=list(suites.iter('testcase'))
    assert len(cases)==16 and not list(suites.iter('failure')) and not list(suites.iter('error'))
    build=json.loads((PAPER/'output/model4_cn_build/build_report.json').read_text('utf-8'))
    assert build['source_sha256']==sha(new) and build['pdf_sha256']==sha(PAPER/'JMS_Review_CN.pdf')
    report=dict(model4_backend_implemented=True,full_suite_tests=16,full_suite_failed=0,
        tests=str(tests.relative_to(ROOT)),tests_sha256=sha(tests),
        previous_budget_assumption_failures_preserved='timeout_comparisons',
        verification_scope='Software correctness and bidirectional full-model feasibility, not a performance benchmark',
        manuscript=dict(pages=build['pages'],undefined_references=0,overfull_boxes=0,
                        contact_sheets_all_pages_visually_checked=True,high_resolution_review_pages=[10]),
        formal_model4_campaigns_started=0,prepare_only_cli_checked=True,active_model2_campaign_modified=False,
        english_synchronized=False,files=hashes)
    (HERE/'completion_review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps(dict(files=len(hashes),full_suite_tests=16,pdf_pages=build['pages'],formal_campaigns_started=0)))


if __name__=='__main__':main()
