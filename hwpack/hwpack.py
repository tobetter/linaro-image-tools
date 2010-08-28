from StringIO import StringIO
import tarfile


def add_file(tf, name, content):
    tarinfo = tarfile.TarInfo(name=name)
    tarinfo.size = len(content)
    # TODO: set other attributes
    fileobj = StringIO(content)
    tf.addfile(tarinfo, fileobj=fileobj)


class HardwarePack(object):

    FORMAT = "1.0"
    FORMAT_FILENAME = "FORMAT"
    METADATA_FILENAME = "metadata"

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

    def to_f(self, fileobj):
        tf = tarfile.open(mode="w:gz", fileobj=fileobj)
        try:
            add_file(tf, self.FORMAT_FILENAME, self.FORMAT + "\n")
            add_file(tf, self.METADATA_FILENAME, """Name: %s
Version: %s
""" % (self.name, self.version))
        finally:
            tf.close()
