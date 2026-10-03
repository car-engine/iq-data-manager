"""Measure the copy engine's throughput: a wrapper over iqdm.diagnostics.copy_check (D57).

The code moved into the package in Milestone 6. The packaged app runs it as
`IQDataManager-check.exe copy-check`. Usage, options and exit codes are in that
module; run this script with --help.

Importing this module gives the package module itself.
"""

import sys

from iqdm.diagnostics import copy_check as _impl

if __name__ == "__main__":
    sys.exit(_impl.main())
sys.modules[__name__] = _impl
