# -*- coding: utf-8 -*-

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from path_utils import append_date_to_filename, resolve_path
from Producedocs.docx_markdown_renderer import RenderOptions, render_markdown_to_docx


DEFAULT_TEMPLATE = ROOT / "template_patent.docx"
DEFAULT_SOURCE = ROOT / "docs" / "patent_disclosure_dual_source_rotary_a3c_beam_20260329.md"
DEFAULT_OUTPUT = ROOT / "docs" / append_date_to_filename("patent_disclosure_dual_source_rotary_a3c_beam.docx")


def parse_args():
    parser = argparse.ArgumentParser(description="Render the patent disclosure markdown into docx.")
    parser.add_argument("--template", type=str, default=str(DEFAULT_TEMPLATE))
    parser.add_argument("--source", type=str, default=str(DEFAULT_SOURCE))
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def main():
    args = parse_args()
    target = render_markdown_to_docx(
        template_path=resolve_path(args.template, ROOT),
        source_path=resolve_path(args.source, ROOT),
        output_path=resolve_path(args.output, ROOT),
        options=RenderOptions(
            top_level_as_title=False,
            center_following_paragraph_after=("发明名称",),
        ),
    )
    print(f"generated: {target}")


if __name__ == "__main__":
    main()
