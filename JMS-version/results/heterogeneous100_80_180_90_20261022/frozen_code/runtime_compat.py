import os
import platform


def configure_openmp_runtime() -> None:
    # Intel OpenMP may be loaded both by PyTorch and other native deps on Windows.
    # Allow the duplicate runtime so training/test/ablation scripts can continue.
    if platform.system().lower() == "windows":
        os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
