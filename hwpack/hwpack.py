class HardwarePack(object):

    FORMAT = "1.0"

    def __init__(self, name, version, origin=None, maintainer=None,
                 support=None):
        self.name = name
        self.version = version
        self.origin = origin
        self.maintainer = maintainer
        self.support = support
