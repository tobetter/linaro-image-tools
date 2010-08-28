from StringIO import StringIO
from tarfile import TarFile as StandardTarFile, TarInfo


class TarFile(StandardTarFile):

    def add_file_from_string(self, filename, content):
        tarinfo = TarInfo(name=filename)
        tarinfo.size = len(content)
        fileobj = StringIO(content)
        self.addfile(tarinfo, fileobj=fileobj)
