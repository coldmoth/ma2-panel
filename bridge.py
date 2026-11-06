"""Stable source and Windows entry point; recover before importing the backend."""
import os
from pathlib import Path
import subprocess
import sys

# Run the stable recovery copy before importing any replaceable application module.
if __name__ == '__main__':
    recovery = Path(__file__).parent.parent / '.updates/recovery.py'
    if recovery.exists():
        version_file = Path(__file__).parent.parent / 'VERSION'
        before_recovery = version_file.read_bytes() if version_file.exists() else b''
        subprocess.run([sys.executable, str(recovery), '--recover', str(Path(__file__).parent.parent)], check=True)
        after_recovery = version_file.read_bytes() if version_file.exists() else b''
        if before_recovery != after_recovery:
            os.execv(sys.executable, [sys.executable, *sys.argv])

if __name__ == "__main__":
    from ma2panel.bridge import main
    main()
