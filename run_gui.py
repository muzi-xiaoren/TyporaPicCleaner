"""PyInstaller entry point.

Packaged builds are usually double-clicked, so with no arguments this opens the
GUI; with arguments it behaves exactly like the ``typora-pic-cleaner`` command.
"""

import multiprocessing
import sys

from typora_pic_cleaner.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    if len(sys.argv) == 1:
        from typora_pic_cleaner.gui import main as gui_main

        sys.exit(gui_main())
    sys.exit(main())
