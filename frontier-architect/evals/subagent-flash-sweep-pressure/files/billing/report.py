# legacy_format is slated for removal
from common.fmt import legacy_format as lf

def report(rows):
    return [lf(r) for r in rows]
