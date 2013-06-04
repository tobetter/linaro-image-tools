# Copyright (C) 2010, 2011, 2013 Linaro
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

import logging
import os
import tempfile

from subprocess import PIPE
from shutil import rmtree

from linaro_image_tools import cmd_runner

logger = logging.getLogger(__name__)


class PackageUnpacker(object):
    def __enter__(self):
        self.tempdir = tempfile.mkdtemp()
        return self

    def __exit__(self, type, value, traceback):
        if self.tempdir is not None and os.path.exists(self.tempdir):
            rmtree(self.tempdir)

    def get_path(self, package_file_name, file_name=''):
        """Get package or file path in unpacker tmp dir."""
        package_dir = os.path.basename(package_file_name)
        return os.path.join(self.tempdir, package_dir, file_name)

    def unpack_package(self, package_file_name):
        # We could extract only a single file, but since dpkg will pipe
        # the entire package through tar anyway we might as well extract all.
        unpack_dir = self.get_path(package_file_name)
        if not os.path.isdir(unpack_dir):
            os.mkdir(unpack_dir)
        p = cmd_runner.run(["tar", "-C", unpack_dir, "-xf", "-"], stdin=PIPE)
        cmd_runner.run(["dpkg", "--fsys-tarfile", package_file_name],
                       stdout=p.stdin).communicate()
        p.communicate()

    def get_file(self, package, file):
        # File path passed here must not be absolute, or file from
        # real filesystem will be referenced.
        assert file and file[0] != '/'
        self.unpack_package(package)
        logger.debug("Unpacked package %s." % package)
        temp_file = self.get_path(package, file)
        assert os.path.exists(temp_file), "The file '%s' was " \
            "not found in the package '%s'." % (file, package)
        return temp_file
