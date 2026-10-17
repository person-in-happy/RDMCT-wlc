"""Audit manually reviewed equation-to-notation coverage for model section 2."""
from pathlib import Path
import re,json
PAPER=Path(__file__).resolve().parents[1]
# Canonical table entries. Indexed instances inherit the listed variable family.
COVERAGE={'joint-membership': ['a_{wpr}', 'd_{pr}', 'v_p', '\\mathcal W', '\\mathcal P'],
 'joint-chamber': ['\\mu_{pm}', 'z_{pc}', 'v_p', 'a_{wpr}', 'm_w', '\\mathcal C(m)', '\\mathcal M'],
 'source-membership': ['\\chi_{is}', '\\mathcal S', '\\mathcal I'],
 'route-union': ['\\mathcal A',
                 '\\mathcal A^{\\rm int}',
                 '\\mathcal A_{is}(\\gamma)',
                 '\\mathcal S',
                 '\\chi_{is}',
                 '\\mathcal I',
                 '\\gamma_{pa}'],
 'operation-time': ['s_o', 'e_o', 'd_o', 'b_o', 'M'],
 'precedence': ['b_o', 's_o', 'e_o', '\\delta_{oo\\prime}', 'M'],
 'clean-time': ['s_v',
                'e_v',
                'a_{vce}',
                's^{\\rm cl}_{ce}',
                'e^{\\rm cl}_{ce}',
                's^{\\rm cl,\\nu}_{ce}',
                'e^{\\rm cl,\\nu}_{ce}',
                'q^{\\rm cl}_{ce}',
                'r_c',
                'M'],
 'dummy-assign': ['g_{j\\tau}', 'd_{pr}', '\\mathcal T_c', '\\mathcal J_c^D'],
 'slot-select': ['h_{o\\ell}', '\\Gamma_o', 'b_o'],
 'resource-order': ['s_o', 'e_o', '\\rho^r_{oo\\prime}', 'y^r_{oo\\prime}', 'h_{o\\ell}', 'M'],
 'stage-link': ['x', 's_o', 'e_o', 's^{\\rm ref}', 'e^{\\rm ref}', 'M'],
 'double-transfer': ['\\gamma_{pa}', 's_{wa}', 'e_{wa}', 'M'],
 'single-source-accompany': ['\\gamma_{pa}',
                             's_{wa}',
                             'e_{wa}',
                             '\\mathrm{pick,ALput,ALpick,LLput}',
                             '\\gamma^{\\rm early}_p',
                             '\\gamma^{\\rm late}_p'],
 'residence': ['s_o', 'e_o', '\\operatorname{out}(w,r)', '\\operatorname{in}(w,r)', '\\overline R_{wr}'],
 'primary-objective': ['C_w', 'C_{\\max}', 'e_o', '\\mathcal W', '\\mathcal F', '\\xi'],
 'secondary-objective': ['\\xi',
                         '\\widehat\\xi',
                         '\\mathcal D_{\\rm fix}',
                         'C_{\\max}',
                         '\\widehat C',
                         '\\varepsilon_C',
                         'L_{\\rm sum}',
                         'L_{\\max}',
                         '\\omega_\\alpha',
                         '\\mathcal Q^w',
                         '\\Delta_{ceq}',
                         'h_{ceq}',
                         'v_{ceq}',
                         '\\eta_\\alpha',
                         '\\bar\\omega_\\alpha',
                         '\\Phi',
                         '\\lambda_1',
                         '\\mathcal I_h'],
 'pair-type': ['B_p', 'B_p^{\\psi}', 'a_{wpr}', '\\mu_{pm}'],
 'candidate-bounds': ['N_{\\zeta}', 'N_{\\psi}', 'T', 'H', 'J_{\\max}', 'P_{\\max}', 'Q_{\\max}'],
 'cycle-capacity': ['U_{cq}', 'K_{cqm}', 'X_{pcq}', 'X^P_{pcq}', 'z_{pc}', '\\mu_{pm}', 'Q_{\\max}', 'J_{\\max}'],
 'cycle-products': ['X^P_{pcq}', 'X_{pcq}', 'B_p'],
 'cycle-exposures': ['A_{pcq}', 'Z_{pcq}', 'X_{pcq}', 'v_p', 'B_p^{\\psi}', 'A^{\\psi}_{pcq}', 'Z^{\\psi}_{pcq}'],
 'cycle-time': ['S_{cq}', 'E_{cq}', 'd_m', 'K_{cqm}', 'U_{cq}', '\\overline T', 'M'],
 'cycle-side': ['\\kappa_{cq}',
                '\\upsilon_{cq}',
                'X_{pcq}',
                'A_{pcq}',
                'Z_{pcq}',
                'U_{cq}',
                'f_{pcq}',
                'B_p',
                'K_{cqm}'],
 'cycle-load': ['X_{pcq}',
                'A_{pcq}',
                'f_{pcq}',
                '\\kappa_{cq}',
                'S_{cq}',
                'E_{cq}',
                's^{\\rm load}_p',
                'e^{\\rm load}_p',
                's^{\\rm unload}_p',
                's^{\\rm rot\\pm}_{cq}',
                'e^{\\rm rot\\pm}_{cq}'],
 'cycle-unload': ['Z_{pcq}',
                  'f_{pcq}',
                  '\\upsilon_{cq}',
                  's^{\\rm unload}_p',
                  'e^{\\rm unload}_p',
                  's^{\\rm rot\\pm}_{cq}',
                  'e^{\\rm rot\\pm}_{cq}'],
 'clean-counter': ['n_{cq}', 'H', 'U_{cq}', 'K_{cqm}'],
 'location-travel': ['z_{pc}', 'y^r_{oo\\prime}', 's_o', 'e_o', '\\rho^{\\rm VTR}_{cc\\prime}']}
def norm(s):return re.sub(r'[\s{}]','',s).replace(r'\prime',"'")
def audit():
    results={};table_columns={}
    for lang,name in [('cn','JMS_Review_CN.tex'),('en','JMS_Submission_EN.tex')]:
        text=(PAPER/name).read_text('utf-8')
        start=text.index(r'\section{',text.index(r'\section{')+1)
        end=text.index(r'\section{',start+1);model=text[start:end]
        labels=re.findall(r'\\label\{eq:([^}]+)-'+lang+r'\}',model)
        assert set(labels)==set(COVERAGE),(lang,set(labels)^set(COVERAGE))
        table_rows=[]
        for key in ('a','b'):
            a=text.index(r'\label{tab:symbol-'+lang+'-'+key+'}');b=text.index(r'\end{table*}',a)
            rows=[line for line in text[a:b].splitlines() if line.startswith('$')]
            assert all(row.count('&')==2 for row in rows)
            table_columns[lang,key]=[norm(row.split('&')[0]) for row in rows]
            table_rows.extend(rows)
        symbols=norm('\n'.join(row.split('&')[0] for row in table_rows))
        misses={eq:[x for x in items if norm(x) not in symbols] for eq,items in COVERAGE.items()}
        misses={k:v for k,v in misses.items() if v};assert not misses,(lang,misses)
        results[lang]={'equations':len(labels),'table_rows':len(table_rows),'missing':misses}
    for key in ('a','b'):assert table_columns['cn',key]==table_columns['en',key]
    return results
if __name__=='__main__':print(json.dumps(audit(),indent=2))
