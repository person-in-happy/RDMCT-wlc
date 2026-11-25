"""Verify and decode rerouting proposals using the full 16-wafer model and physical replay."""
from native_caps import OUT
import native

if __name__=="__main__":
    native.OUT=OUT
    native.main()
