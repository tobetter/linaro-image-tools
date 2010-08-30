from StringIO import StringIO
from tarfile import DIRTYPE, TarFile as StandardTarFile, TarInfo


def get_arg_with_default(kwargs, arg, default=None):
    if arg in kwargs:
        result = kwargs[arg]
        del kwargs[arg]
    else:
        result = default
    return result


class TarFile(StandardTarFile):

    def __init__(self, *args, **kwargs):
        self.default_mtime = get_arg_with_default(kwargs, "default_mtime")
        self.default_uid = get_arg_with_default(kwargs, "default_uid")
        self.default_gid = get_arg_with_default(kwargs, "default_gid")
        self.default_uname = get_arg_with_default(kwargs, "default_uname")
        self.default_gname = get_arg_with_default(kwargs, "default_gname")
        super(TarFile, self).__init__(*args, **kwargs)

    def add_file_from_string(self, filename, content):
        tarinfo = TarInfo(name=filename)
        tarinfo.size = len(content)
        if self.default_mtime is not None:
            tarinfo.mtime = self.default_mtime
        if self.default_uid is not None:
            tarinfo.uid = self.default_uid
        if self.default_gid is not None:
            tarinfo.gid = self.default_gid
        if self.default_uname is not None:
            tarinfo.uname = self.default_uname
        if self.default_gname is not None:
            tarinfo.gname = self.default_gname
        fileobj = StringIO(content)
        self.addfile(tarinfo, fileobj=fileobj)

    def add_dir(self, path):
        tarinfo = TarInfo(name=path)
        tarinfo.type = DIRTYPE
        self.addfile(tarinfo)
