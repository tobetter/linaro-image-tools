class HardwarePack(object):

    FORMAT = "1.0"

    def __init__(self, name, version, origin=None, maintainer=None,
                 support=None):
        self.name = name
        self.version = version
        self.origin = origin
        self.maintainer = maintainer
        self.support = support

    def filename(self):
        if self.support is None:
            support_suffix = ""
        else:
            support_suffix = "_%s" % self.support
        return "hwpack_%s_%s%s.tar.gz" % (
            self.name, self.version, support_suffix)
