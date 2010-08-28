from tarfile import TarFile as StandardTarFile, TarInfo


class TarFile(StandardTarFile):

    def add_file_from_string(self, filename, content):
        tarinfo = TarInfo(name=filename)
        self.addfile(tarinfo)
