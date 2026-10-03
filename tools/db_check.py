"""Check a scratch catalogue database: a wrapper over iqdm.diagnostics.db_check (D57).

The code moved into the package in Milestone 6. The packaged app runs it as
`IQDataManager-check.exe db-check`. Commands, the locking test and exit codes are in
that module; run this script with --help.

Use a scratch database only, never the real catalogue. Importing this module gives the
package module itself.
"""

import sys

from iqdm.diagnostics import db_check as _impl

if __name__ == "__main__":
    sys.exit(_impl.main())
sys.modules[__name__] = _impl
