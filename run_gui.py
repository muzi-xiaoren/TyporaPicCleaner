"""Entry point for the windowed build.

Packaged with ``--windowed`` there is no console attached, so this script only
ever opens the interface: printing a usage message would go nowhere the user
can see it.  The console build uses ``run_cli.py`` instead.
"""

import multiprocessing
import sys

from typora_pic_cleaner.gui import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
