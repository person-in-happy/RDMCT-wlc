"""Stage a reviewed revision and publish only against the original, fingerprinted source."""
from pathlib import Path
import json
import re
import shutil
import subprocess
import sys
import time

from review import HERE, REPORT, read, rows, save, digest

THESIS=Path("D:/git/git/硕士毕设/论文初稿_20261110")
STAGE=HERE/"manuscript_build"
PRIOR=HERE/"manuscript_backup"
MANIFEST=REPORT/"manuscript_manifest.json"
NOTES=("README.md","缺口与实验命令.md")


def get(p):
    return p.read_text(encoding="utf-8-sig")


def put(path,text):
    path.write_text(text,encoding="utf-8")


def once(text,old,new):
    if text.count(old)!=1:
        raise ValueError(f"Expected one occurrence: {old[:70]}")
    return text.replace(old,new)


def fmt(x):
    return f"{float(x):g}"


def filelist():
    fixed=["main.tex","template_compat.tex","ustbthesis.cls","build.ps1",*NOTES]
    extra=[p.relative_to(THESIS).as_posix() for sub in ("contents","figures","images")
           for p in (THESIS/sub).rglob("*") if p.is_file() and p.suffix not in (".aux",".log")]
    return list(dict.fromkeys(fixed+extra))


def latex(folder):
    for k in range(1,4):
        with (folder/f"pass_{k}.txt" if folder==STAGE else REPORT/f"installed_xelatex_{k}.txt").open("wb") as log:
            run=subprocess.run(["xelatex","-synctex=1","-interaction=nonstopmode","-halt-on-error","-file-line-error",
                                "main.tex"],cwd=folder,stdout=log,stderr=subprocess.STDOUT)
        if run.returncode:
            raise RuntimeError(f"XeLaTeX failed in {folder}, pass {k}")
    log=get(folder/"main.log")
    if re.search(r"(undefined references|Citation .+ undefined|Reference .+ undefined|multiply defined|Missing character:)",log,re.I):
        raise ValueError("Unresolved references, duplicate labels, or missing characters in main.log")
    return log


def page_texts(folder):
    result=subprocess.run(["pdftotext","-layout","-enc","UTF-8",str(folder/"main.pdf"),"-"],
                          capture_output=True,check=True)
    return result.stdout.decode("utf-8","replace").rstrip("\f").split("\f")


def stage():
    info=read(REPORT/"verified.json")
    assert info["sources_match"] and info["pooled_equals_all_internal"] and info["small"]["checked_original_again"]
    STAGE.mkdir(exist_ok=True)
    PRIOR.mkdir(exist_ok=True)
    inputs=filelist()
    before={p:digest(THESIS/p) for p in [*inputs,"main.pdf"]}
    if MANIFEST.exists():
        assert read(MANIFEST)["before"]==before,"Thesis changed after initial staging"
    for name in inputs:
        dest=STAGE/name
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(THESIS/name,dest)
    book={f:get(STAGE/f) for f in (["main.tex",*NOTES]+
          ["contents/"+n+".tex" for n in ("abstract","chap1","chap2","chap3","chap4","chap5","chap6","bibliography")])}
    large=info["medians"]
    points=rows(REPORT/"front75.csv")
    raw=rows(REPORT/"runs75.csv")
    a0,b0=float(points[0]["A"]),float(points[0]["B"])
    an,bn=float(points[-1]["A"]),float(points[-1]["B"])
    small=info["small"]["main_HV"]
    small_lines=[]
    for case,s in (("S1",40),("M4",45),("H4",45),("H8",55),("H16",80)):
        small_lines.append(f"{case} & {s} & "+" & ".join(f"{small[case][m]:.5f}" for m in
                           ("domain","rl_domain","epsilon","nsga2","moead","legacy"))+r" \\")
    name={"domain":"领域搜索","nsga2":"NSGA-II","moead":"MOEA/D","fixed":"固定结构扫描"}
    med={r["method"]:r for r in large}
    large_lines=[f"{name[r['method']]} & {r['HV_median']:.5f} & "
                 f"{r['HV_min']:.5f}--{r['HV_max']:.5f} & {fmt(r['A_median'])} & {fmt(r['B_median'])} "+r"\\"
                 for r in large]
    replacements=dict(SMALL_TABLE="\n".join(small_lines),LARGE_TABLE="\n".join(large_lines),
        DHV=f"{med['domain']['HV_median']:.5f}",MHV=f"{med['moead']['HV_median']:.5f}",
        BESTSEED=f"{float(next(r['HV'] for r in raw if r['method']=='moead' and r['seed']=='2')):.5f}",
        NFRONT=str(info["full_observed"]),AMIN=fmt(a0),BATAMIN=fmt(b0),AATBMIN=fmt(an),BMIN=fmt(bn),
        DELTA_A=fmt(an-a0),DELTA_B=fmt(b0-bn),A2000=fmt(min(float(r["A"]) for r in points if float(r["B"])<=2000)),
        NSUB=str(info["returned"]),NCERT=str(info["distinct_original_checks"]))
    exp=get(HERE/"results_thesis.tex").replace("；","。")
    for k,v in replacements.items():
        exp=once(exp,"@@"+k+"@@",v)
    assert "@@" not in exp
    key="contents/chap5.tex"
    marker=r"\section{产品完工瓶颈改进算法的比较与消融}"
    assert marker in book[key]
    base=book[key].split(marker)[0]
    base=once(base,r"\subsection{默认模型的100片排程与清洁、加工模式对照}"+"\n"+r"\vspace*{6cm}","")
    base=once(base,"不纳入D的性能排名。",r"不纳入D的性能排名。默认配置D的75片混合批次见第~\ref{sec:pareto-evidence}~节，100片完整对照仍待验证。")
    book[key]=base+exp
    key="contents/chap4.tex"
    marker=r"\section{产品完工瓶颈驱动的原始解改进方法}"
    assert marker in book[key]
    method=get(HERE/"method_thesis.tex").replace("采购交期","给定交期").replace("；","。")
    book[key]=book[key].split(marker)[0]+method
    key="contents/chap1.tex"
    a=book[key]
    first=a.index(r"\item 设计结构化初始解策略")
    end=a.index(r"\end{enumerate}",first)
    a=a[:first]+r"""\item 设计结合结构化初始化与学习选割的RL-DMCT。先确定配对、分腔和加工周期，再逐层放开资源次序。根据候选割的变量角色特征进行学习排序，并按角色覆盖和候选相似度重排割子集。
\item 提出基于配对等待下界的双目标邻域搜索。由配对方式推导路线等待下界，结合指标上限筛选候选，对关联的配对、取放与设备次序联合调整，给出可按交期或等待要求选择的非支配排程。
"""+a[end:]
    a=once(a,"实验同时报告可行上界、有效下界和停止状态。","双目标实验还比较同预算下各方法的超体积，用两片算例的认证前沿检验覆盖度，并用75片批次考察排程能否逐片执行。")
    a=once(a,"并为产品完工瓶颈驱动的原始解改进保留独立研究位置","进而给出以配对等待下界筛选邻域的双目标搜索方法")
    a=once(a,"并区分历史100片实例与当前模型的扩展任务","比较两片认证前沿与75片混合批次的经验前沿")
    book[key]=a
    key="contents/chap2.tex"
    last=next(line for line in book[key].splitlines() if line.startswith("第三章以晶圆对为单位连接"))
    book[key]=once(book[key],last,r"第三章用晶圆对连接周期占位、辅助片借还与逐片路线。Sakai和Nishi已联合考察完工与腔内驻留时间\citep{sakai2017}。本文计量全路线等待与留片链节拍。第四章分别研究初始化、选割和基于配对等待下界的搜索，第五章在相同预算下比较上下界和前沿覆盖。")
    key="contents/chap3.tex"
    a=book[key]
    a=once(a,"驻留上限仍作为硬约束执行。",r"驻留上限仍作为硬约束执行。第~\ref{sec:third-innovation}~节在同一配置D可行域上同时最小化产品完工时间与上述综合指标，考察放宽交期所能换取的等待与节拍改善。")
    book[key]=a
    key="contents/chap6.tex"
    marker=r"\section{产品完工瓶颈改进研究的结论}"
    assert marker in book[key]
    conclusion=book[key].split(marker)[0]
    for beginning,new in [
        ("本文以PW对连接","本文以PW对连接成对搬运与腔室周期。两阶段MILP先最小化产品完工时间，再固定完工上界和主要结构改进时序。配置E的30组对照均保持工期并降低等待。配置D的单产品链式工况将总等待由642降至54~s。权重变化使16片实例以16~s额外等待换取8~s节拍偏差下降，24片实例保持不变。"),
        ("结构化初始解改善",r"四实例168次对照中，两个混合实例在三个训练种子下均从结构化初始化获益。场景S2的平均工期由521降至492~s。六个2片实例共享SPBS起点的414次比较中，完整选割组合相对HEM加SPBS的实例平均配对改善为0.0776\%，两胜四平。根分离下贪心解码优于束搜索，表明收益随解码设置变化。"),
        ("有限辅助库存影响","单产品链式工况的辅助库存从4片增至8片，已证最优工期由309降至303~s，并行配方保持296~s。四片辅助片可通过重复借用完成链式加工与满片清洁。身份、原模型与事件复核验证了2片324~s最优排程和16片920~s可行排程。")]:
        old=next(line for line in conclusion.splitlines() if line.startswith(beginning))
        conclusion=once(conclusion,old,new)
    book[key]=conclusion+(
        r"\section{交付与路线等待的双目标权衡}"+"\n"+
        f"配对等待下界把指标上限转化为结构筛选条件。两片算例的七个认证点含三个非支持点。四片标称实例的配对下界、领域邻域和对内取放改动均提高了三个种子的超体积。八片与十六片由MOEA/D取得最高HV中位数。75片混合批次得到{len(points)}个经原模型复验的经验非支配点，两个端点的交付时间相差{fmt(an-a0)}~s，等待与节拍指标相差{fmt(b0-bn)}加权秒。\n\n"+
        r"\section{未来展望}"+"\n"+
        "75片经验前沿仍受生产块和离散次序邻域限制。后续可用工期与等待的联合下界逐段排除未知区间，并改变配方比例、库存和清洁阈值，检验大批次的前沿覆盖度。向配置D的100片批次扩展时，还需测量构造、构模、搜索与验解的总耗时。\n")
    key="contents/abstract.tex"
    a=book[key]
    a=once(a,"结果分别验证了联合模型的设备时序表达、结构化初始化的可行解改善，以及共享起点后的学习选割增量。",
           f"基于配对等待下界的双目标搜索进一步刻画了交付与等待的取舍。两片专用子模型重现全部七个认证点。75片混合批次获得{len(points)}个经原模型复验的经验非支配点，两个端点的工期相差{fmt(an-a0)}~s，等待与节拍指标相差{fmt(b0-bn)}加权秒。")
    a=once(a,"These results establish the roles of joint modeling, structured initialization, and subsequent learning-based search.",
           f"A pair-based waiting bound guides a bi-objective search. A two-wafer submodel recovers all seven certified Pareto points. For 75 product wafers, {len(points)} empirically nondominated schedules pass full-model checks. The two extremes differ by {fmt(an-a0)} s in makespan and {fmt(b0-bn)} weighted seconds in waiting and cycle regularity.")
    a=once(a,"Thirty paired refinements under extended residence limits preserve makespan and reduce route waiting. Under the default limits, increasing auxiliary inventory from four to eight reduces the certified optimum from 309 to 303 s for a single-product sequential-processing case.",
           "Thirty refinements preserve makespan and reduce waiting. With default residence limits, increasing auxiliary inventory from four to eight reduces the certified single-product makespan from 309 to 303 s for sequential processing.")
    book[key]=a
    key="contents/bibliography.tex"
    ref=HERE.parents[1]/"review/pareto_objectives_20261118/thesis_pareto_new_bibitems.tex"
    entries=re.split(r"(?=\\bibitem\{)",get(ref))
    added=[entry.strip() for entry in entries if any(entry.startswith(r"\bibitem{"+k+"}") for k in
                 ("sakai2017","deb2002","zhangli2007","mavrotas2009"))]
    assert len(added)==4 and all(entry.splitlines()[0] not in book[key] for entry in added)
    book[key]=once(book[key],r"\end{thebibliography}","\n\n".join(added)+"\n"+r"\end{thebibliography}")
    nrefs=book[key].count(r"\bibitem{")
    key="main.tex"
    book[key]=once(book[key],"58页规划稿连续起页","规划稿连续起页")
    for key in book:
        put(STAGE/key, book[key])
    for dest in ("pareto_75.pdf","pareto_s1.pdf"):
        assert not (THESIS/"figures"/dest).exists()
        shutil.copy2(REPORT/"figures"/dest,STAGE/"figures"/dest)
    latex(STAGE)
    pages=page_texts(STAGE)
    n_pages=len(pages)
    key="README.md"
    a=re.sub(r"参考文献\d+条",f"参考文献{nrefs}条",book[key])
    a=re.sub(r"当前仍为包含研究预留位置的.*?\n",f"当前编译版共 {n_pages} 页。第四、五、六章已纳入配对等待下界、双目标搜索、消融和75片混合排程。两片算例有完整前沿证书，75片提供经逐行验证的经验前沿。默认配置D的100片结果仍待验证。\n",a,count=1)
    put(STAGE/key,a)
    key="缺口与实验命令.md"
    a=book[key]
    first=a.index("\n")+1
    a=a[:first]+"\n2026-11-19 更新。第三个创新点已改为基于配对等待下界的双目标邻域搜索。两片完整前沿与75片混合批次对照已复核并纳入第四至六章。下文保留11月16日方案与运行记录。当前复核见 [实验记录](D:/git/git/RDMCT-A3C/JMS-version/experiments/pareto75_thesis_20261119/review/review_CN.md)。\n"+a[first:]
    put(STAGE/key,a)
    changed=[p for p in book if digest(STAGE/p)!=before[p]]
    new=["figures/pareto_s1.pdf","figures/pareto_75.pdf"]
    for p in [*changed,"main.pdf"]:
        dest=PRIOR/p
        dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists():
            shutil.copy2(THESIS/p,dest)
        assert digest(dest)==before[p]
    staged={p:digest(STAGE/p) for p in [*changed,*new,"main.pdf"]}
    save(MANIFEST,dict(before=before,changed=changed,new=new,staged=staged,pages=n_pages,references=nrefs))
    print(f"Staged {n_pages} pages, {nrefs} references, {len(changed)} changed sources/notes",flush=True)


def install():
    assert (REPORT/"visual_qa.json").exists() and read(REPORT/"visual_qa.json")["pdf_hash"]==digest(STAGE/"main.pdf")
    mf=read(MANIFEST)
    assert (THESIS/"ustbthesis.cls").is_file()
    assert all(digest(THESIS/p)==h for p,h in mf["before"].items()),"Original source or PDF changed"
    assert all(not (THESIS/p).exists() for p in mf["new"])
    for p,h in mf["staged"].items():
        assert digest(STAGE/p)==h
    files=[*mf["changed"],*mf["new"],"main.pdf"]
    assert all((THESIS/p).resolve().is_relative_to(THESIS.resolve()) for p in files)
    temps={}
    committed=[]
    try:
        for p in files:
            path=THESIS/p
            tmp=path.with_name(path.name+".pareto-update.tmp")
            assert not tmp.exists()
            temps[p]=tmp
            shutil.copy2(STAGE/p,tmp)
            assert digest(tmp)==mf["staged"][p]
        for p in files:
            path=THESIS/p
            if p in mf["before"]:
                assert digest(path)==mf["before"][p]
            else:
                assert not path.exists()
            temps[p].replace(path)
            committed.append(p)
        latex(THESIS)
        physical=page_texts(THESIS)
        assert physical==page_texts(STAGE) and len(physical)==mf["pages"]
        for p in [*mf["changed"],*mf["new"]]:
            assert digest(THESIS/p)==mf["staged"][p]
    except BaseException:
        for p in reversed(committed):
            path=THESIS/p
            if p!="main.pdf" and digest(path)!=mf["staged"][p]:
                continue
            if p in mf["before"]:
                shutil.copy2(PRIOR/p,path)
            else:
                path.unlink()
        raise
    finally:
        for tmp in temps.values():
            tmp.unlink(missing_ok=True)
    save(REPORT/"installed.json",dict(pdf=str(THESIS/"main.pdf"),sha256=digest(THESIS/"main.pdf"),pages=len(physical),
                                     equal_page_text_to_reviewed=True,checked_sources=True,source_changes=mf["changed"]))
    print("Installed and compiled verified manuscript",THESIS/"main.pdf",len(physical),"pages")


if __name__=="__main__":
    if len(sys.argv)==2 and sys.argv[1]=="--install":
        install()
    else:
        stage()
