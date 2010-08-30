from contextlib import contextmanager
from StringIO import StringIO
from tarfile import DIRTYPE, TarFile as StandardTarFile, TarInfo


@contextmanager
def writeable_tarfile(backing_file, **kwargs):
    tf = TarFile.open(mode="w", fileobj=backing_file, **kwargs)
    try:
        yield tf
    finally:
        tf.close()


@contextmanager
def standard_tarfile(backing_file, seek=True):
    if seek:
        backing_file.seek(0)
    tf = StandardTarFile.open(fileobj=backing_file)
    try:
        yield tf
    finally:
        tf.close()


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

    def _set_defaults(self, tarinfo):
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

    def create_file_from_string(self, filename, content):
        tarinfo = TarInfo(name=filename)
        tarinfo.size = len(content)
        self._set_defaults(tarinfo)
        fileobj = StringIO(content)
        self.addfile(tarinfo, fileobj=fileobj)

    def create_dir(self, path):
        tarinfo = TarInfo(name=path)
        tarinfo.type = DIRTYPE
        tarinfo.mode = 0755
        self._set_defaults(tarinfo)
        self.addfile(tarinfo)
