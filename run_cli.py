"""Entry point for the console build (the ``typora-pic-cleaner`` command)."""

import multiprocessing
import sys

from typora_pic_cleaner.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
