from StringIO import StringIO
from tarfile import TarFile as StandardTarFile, TarInfo


class TarFile(StandardTarFile):

    def __init__(self, *args, **kwargs):
        default_mtime = None
        if "default_mtime" in kwargs:
            default_mtime = kwargs["default_mtime"]
            del kwargs["default_mtime"]
        super(TarFile, self).__init__(*args, **kwargs)
        self.default_mtime = default_mtime

    def add_file_from_string(self, filename, content):
        tarinfo = TarInfo(name=filename)
        tarinfo.size = len(content)
        if self.default_mtime is not None:
            tarinfo.mtime = self.default_mtime
        fileobj = StringIO(content)
        self.addfile(tarinfo, fileobj=fileobj)
