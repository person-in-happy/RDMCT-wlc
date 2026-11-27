"""Assemble the reviewed English translation and order references by first citation."""
from pathlib import Path
import hashlib
import json
import re

PAPER = Path(__file__).resolve().parents[1]
CN = PAPER / "JMS_Review_CN.tex"
BODY = PAPER / "submission/manuscript_body_en.tex"
FRAME = PAPER / "submission/manuscript_frame_en.tex"
REVIEWED_CN = "d46c152e5af552042ce74c3f279c0c7e707ac8346ef8136b51b71f0ca9f115e3"


def environments(source, kind):
    pattern = r"\\begin\{" + kind + r"\*?\}.*?\\end\{" + kind + r"\*?\}"
    return {re.search(r"\\label\{([^}]+)\}", m[0])[1]: m[0]
            for m in re.finditer(pattern, source, re.S)}


def main():
    source = CN.read_text(encoding="utf-8")
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if digest != REVIEWED_CN:
        raise ValueError("Review the changed Chinese source before assembling the translation.")
    body = BODY.read_text(encoding="utf-8")
    frame = FRAME.read_text(encoding="utf-8")
    bio = re.search(r"\\begin\{thebibliography\}\{99\}(.*?)\\end\{thebibliography\}", source, re.S)[1]
    entries = {m[1]: m[0].strip() for m in re.finditer(r"\\bibitem\{([^}]+)\}.*?(?=\\bibitem|\Z)", bio, re.S)}
    keys = list(dict.fromkeys(k for group in re.findall(r"\\citep\{([^}]+)\}", body) for k in group.split(",")))
    if set(keys) != entries.keys():
        raise ValueError(f"Citations and references differ: {set(keys) ^ entries.keys()}")
    ordered = "\n\n".join(entries[k] for k in keys)
    bibliography = "\\begin{thebibliography}{99}\n\\interlinepenalty=10000\n\n" + ordered + "\n\\end{thebibliography}"
    target = PAPER / "JMS_Submission_EN.tex"
    manuscript = frame.replace(r"\input{submission/manuscript_body_en}", body.strip()).replace(r"\input{ordered-bibliography}", bibliography)
    assert not re.search(r"[\u4e00-\u9fff]|@@|\{\{(?:EQ|TABLE|FIG):", manuscript)
    target.write_text(manuscript, encoding="utf-8")
    abstract = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", manuscript, re.S)[1]
    words = len(abstract.replace("~", " ").split())
    assert words <= 250
    report = {"chinese_source_sha256_lf": digest,
              "english_source_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
              "equations": len(environments(body, "equation")), "tables": len(environments(body, "table")),
              "figures": len(environments(body, "figure")), "figure_assets": body.count(r"\includegraphics"),
              "bibliography_items": len(keys), "abstract_word_count": words}
    (PAPER / "submission/translation_checks.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
