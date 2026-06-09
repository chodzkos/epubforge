"""Entry point dla `python -m epubforge`."""

import sys

from epubforge.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
