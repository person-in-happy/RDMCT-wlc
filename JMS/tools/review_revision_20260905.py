"""Apply evidence-bounded Chinese manuscript review; preserve the source snapshot."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "JMS_Review_CN.tex"
BACKUP = ROOT / "_work" / "review_20260905" / "JMS_Review_CN.before_review.tex"


def main():
    original = SOURCE.read_bytes()
    text = original.decode("utf-8-sig")
    text = text.replace("\r\n", "\n")
    changes = []

    def replace(old, new, reason):
        nonlocal text
        count = text.count(old)
        if count != 1:
            raise ValueError(f"Expected one match, got {count}: {old[:70]}")
        text = text.replace(old, new, 1)
        changes.append({"reason": reason, "before": old, "after": new})

    # Replacement blocks are appended below before execution.

    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    if BACKUP.exists():
        raise FileExistsError(f"Refusing to overwrite review snapshot: {BACKUP}")
    BACKUP.write_bytes(original)
    SOURCE.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    (BACKUP.parent / "changes.json").write_text(json.dumps({
        "source": str(SOURCE), "backup": str(BACKUP),
        "sha256_before": hashlib.sha256(original).hexdigest(),
        "sha256_after": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "changes": changes,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Applied {len(changes)} reviewed changes; original preserved at {BACKUP}")


if __name__ == "__main__":
    main()
