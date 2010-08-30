from StringIO import StringIO
from tarfile import TarFile as StandardTarFile, TarInfo


def get_arg_with_default(kwargs, arg, default=None):
    if arg in kwargs:
        result = kwargs[arg]
        del kwargs[arg]
    else:
        result = default
    return result


class TarFile(StandardTarFile):

    def __init__(self, *args, **kwargs):
        default_mtime = get_arg_with_default(kwargs, "default_mtime")
        default_uid = get_arg_with_default(kwargs, "default_uid")
        super(TarFile, self).__init__(*args, **kwargs)
        self.default_mtime = default_mtime
        self.default_uid = default_uid

    def add_file_from_string(self, filename, content):
        tarinfo = TarInfo(name=filename)
        tarinfo.size = len(content)
        if self.default_mtime is not None:
            tarinfo.mtime = self.default_mtime
        if self.default_uid is not None:
            tarinfo.uid = self.default_uid
        fileobj = StringIO(content)
        self.addfile(tarinfo, fileobj=fileobj)
