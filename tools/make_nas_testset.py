"""Create the NAS field test set: a wrapper over iqdm.diagnostics.testset (D54, D57).

The code moved into the package in Milestone 6. The packaged app runs it as
`IQDataManager-check.exe make-test-set`. Usage and exit codes are in that module; run
this script with --help.

Importing this module gives the package module itself.
"""

import sys

from iqdm.diagnostics import testset as _impl

if __name__ == "__main__":
    sys.exit(_impl.main())
sys.modules[__name__] = _impl
