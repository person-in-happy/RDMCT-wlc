import re
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
_DATE_SUFFIX_RE = re.compile(r"(?:^|[_-])(?:\d{8}|\d{4}_\d{2}_\d{2})$")


def resolve_path(path_like, base_dir=None) -> Path:
    path = Path(path_like).expanduser()
    if path.is_absolute():
        return path
    base_path = Path(base_dir) if base_dir is not None else PROJECT_ROOT
    return (base_path / path).resolve()


def project_path(*parts) -> Path:
    return PROJECT_ROOT.joinpath(*parts)


def current_date_tag() -> str:
    return datetime.now().strftime("%Y%m%d")


def has_date_suffix(stem: str) -> bool:
    return bool(_DATE_SUFFIX_RE.search(stem))


def append_date_to_filename(filename: str, date_tag: str = None) -> str:
    path = Path(filename)
    stem = path.stem
    if has_date_suffix(stem):
        return str(path)
    tag = date_tag or current_date_tag()
    return str(path.with_name(f"{stem}_{tag}{path.suffix}"))
