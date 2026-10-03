"""Generate synthetic IQ recordings: a wrapper over iqdm.diagnostics.fixtures (D57).

The code moved into the package in Milestone 6, so the packaged app can use it.
Usage, options and exit codes are in that module; run this script with --help.

Importing this module gives the package module itself, so tests that import
make_fixtures use the same functions and classes.
"""

import sys

from iqdm.diagnostics import fixtures as _impl

if __name__ == "__main__":
    sys.exit(_impl.main())
sys.modules[__name__] = _impl
