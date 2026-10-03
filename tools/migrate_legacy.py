"""Import the legacy catalogue into a new database: a wrapper over iqdm.legacy (D66).

The packaged app runs the same code as `IQDataManager-check.exe migrate-legacy`. The
mapping rules, the report and the exit codes are in that module; run this script with
--help.

Run it on a copy of the legacy database. Importing this module gives the package
module itself.
"""

import sys

from iqdm import legacy as _impl

if __name__ == "__main__":
    sys.exit(_impl.main())
sys.modules[__name__] = _impl
