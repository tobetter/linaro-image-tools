# Copyright (C) 2010, 2011 Linaro
#
# Author: James Westby <james.westby@linaro.org>
#
# This file is part of Linaro Image Tools.
#
# Linaro Image Tools is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# Linaro Image Tools is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Linaro Image Tools; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
# USA.

from contextlib import contextmanager
from StringIO import StringIO
from tarfile import DIRTYPE, TarFile as StandardTarFile, TarInfo

"""Improvements to the standard library's tarfile module.

In particular this module provides a tarfile.TarFile subclass that aids
in adding paths to the tarfile that aren't present on the filesystem,
with the ability to specify file content as strings, and provide
default values for the mtime, uid, etc. of the created paths.
"""


@contextmanager
def writeable_tarfile(backing_file, mode="w", **kwargs):
    """A context manager to get a writeable better tarfile.

    :param backing_file: a file object to write the tarfile contents
        to.
    :param mode: the mode to open the tarfile with. Default is
        "w".
    :param kwargs: other keyword arguments to pass to the TarFile
        constructor.
    """
    tf = TarFile.open(mode=mode, fileobj=backing_file, **kwargs)
    try:
        yield tf
    finally:
        tf.close()


class TarFile(StandardTarFile):
    """An improvement to tarfile that can add paths not on the filesystem.

    With the standard tarfile implementation adding paths that are not
    present on the filesystem is convoluted. This subclass adds methods
    to create paths in the tarfile that are not present on the filesystem.

    In addition, it can take constructor parameters to set the defaults
    of various attributes of the paths that it adds.
    """

    def __init__(self, *args, **kwargs):
        """Create a TarFile.

        :param default_mtime: the default mtime to create paths with,
            an int or None to use the stdlib default.
        :param default_uid: the default user id to set as the owner of
            created paths, an int or None to use the stdlib default.
        :param default_gid: the default group id to set as the owner of
            created paths, an int or None to use the stdlib default.
        :param default_uname: the default user name to set as the owner
            of created paths, a string, or None to use the stdlib default.
        :param default_gname: the default group name ot set as the owner
            of created paths, a string, or None to use the stdlib default.
        """
        self.default_mtime = kwargs.pop("default_mtime", None)
        self.default_uid = kwargs.pop("default_uid", None)
        self.default_gid = kwargs.pop("default_gid", None)
        self.default_uname = kwargs.pop("default_uname", None)
        self.default_gname = kwargs.pop("default_gname", None)
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
        """Create a file with the contents passed as a string.

        :param filename: the path to put the file at inside the
            tarfile.
        :param content: the content to put in the created file.
        """
        tarinfo = TarInfo(name=filename)
        tarinfo.size = len(content)
        self._set_defaults(tarinfo)
        fileobj = StringIO(content)
        self.addfile(tarinfo, fileobj=fileobj)

    def create_dir(self, path):
        """Create a directory within the tarfile.

        :param path: the path to put the directory at.
        """
        tarinfo = TarInfo(name=path)
        tarinfo.type = DIRTYPE
        tarinfo.mode = 0755
        self._set_defaults(tarinfo)
        self.addfile(tarinfo)
