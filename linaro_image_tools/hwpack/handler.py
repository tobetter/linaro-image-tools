# Copyright (C) 2010, 2011, 2012 Linaro
#
# Author: Guilherme Salgado <guilherme.salgado@linaro.org>
#
# This file is part of Linaro Image Tools.
#
# Linaro Image Tools is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Linaro Image Tools is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Linaro Image Tools.  If not, see <http://www.gnu.org/licenses/>.

from StringIO import StringIO
import ConfigParser
import logging
import os
import re
import shutil
import tarfile
import tempfile

from linaro_image_tools.hwpack.config import Config
from linaro_image_tools.hwpack.package_unpacker import PackageUnpacker
from linaro_image_tools.utils import DEFAULT_LOGGER_NAME


logger = logging.getLogger(DEFAULT_LOGGER_NAME)


class HardwarepackHandler(object):
    FORMAT_1 = '1.0'
    FORMAT_2 = '2.0'
    FORMAT_3 = '3.0'
    FORMAT_MIXED = '1.0and2.0'
    metadata_filename = 'metadata'
    format_filename = 'FORMAT'
    main_section = 'main'
    hwpack_tarfiles = []
    tempdir = None

    def __init__(self, hwpacks, bootloader=None, board=None):
        self.hwpacks = hwpacks
        self.hwpack_tarfiles = []
        self.bootloader = bootloader
        self.board = board
        self.tempdirs = {}
        # Used to store the config created from the metadata.
        self.config = None

    class FakeSecHead(object):
        """ Add a fake section header to the metadata file.

        This is done so we can use ConfigParser to parse the file.
        """
        def __init__(self, fp):
            self.fp = fp
            self.sechead = '[%s]\n' % HardwarepackHandler.main_section

        def readline(self):
            if self.sechead:
                try:
                    return self.sechead
                finally:
                    self.sechead = None
            else:
                return self.fp.readline()

    def __enter__(self):
        self.tempdir = tempfile.mkdtemp()
        for hwpack in self.hwpacks:
            hwpack_tarfile = tarfile.open(hwpack, mode='r:gz')
            self.hwpack_tarfiles.append(hwpack_tarfile)
        return self

    def __exit__(self, type, value, traceback):
        for hwpack_tarfile in self.hwpack_tarfiles:
            if hwpack_tarfile is not None:
                hwpack_tarfile.close()
        self.hwpack_tarfiles = []
        if self.tempdir is not None and os.path.exists(self.tempdir):
            shutil.rmtree(self.tempdir)

        for name in self.tempdirs:
            tempdir = self.tempdirs[name]
            if tempdir is not None and os.path.exists(tempdir):
                shutil.rmtree(tempdir)

    def _get_config_from_metadata(self, metadata):
        """
        Retrieves a Config object associated with the metadata.

        :param metadata: The metadata to parse.
        :return: A Config instance.
        """
        if not self.config:
            lines = metadata.readlines()
            if re.search("=", lines[0]) and not re.search(":", lines[0]):
                # Probably V2 hardware pack without [hwpack] on the first line
                lines = ["[hwpack]\n"] + lines
            self.config = Config(StringIO("".join(lines)))
            self.config.board = self.board
            self.config.bootloader = self.bootloader
        return self.config

    def get_field(self, field, return_keys=False):
        data = None
        hwpack_with_data = None
        keys = None
        for hwpack_tarfile in self.hwpack_tarfiles:
            metadata = hwpack_tarfile.extractfile(self.metadata_filename)
            parser = self._get_config_from_metadata(metadata)
            try:
                new_data = parser.get_option(field)
                if new_data is not None:
                    assert data is None, "The metadata field '%s' is set to " \
                        "'%s' and new value '%s' is found" % (field, data,
                                                              new_data)
                    data = new_data
                    hwpack_with_data = hwpack_tarfile
                    if return_keys:
                        keys = parser.get_last_used_keys()
            except ConfigParser.NoOptionError:
                continue

        if return_keys:
            return data, hwpack_with_data, keys
        return data, hwpack_with_data

    def get_format(self):
        format = None
        supported_formats = [self.FORMAT_1, self.FORMAT_2, self.FORMAT_3]
        for hwpack_tarfile in self.hwpack_tarfiles:
            format_file = hwpack_tarfile.extractfile(self.format_filename)
            format_string = format_file.read().strip()
            if not format_string in supported_formats:
                raise AssertionError(
                    "Format version '%s' is not supported." % format_string)
            if format is None:
                format = format_string
            elif format != format_string:
                return self.FORMAT_MIXED
        return format

    def get_file(self, file_alias):
        """Get file(s) from a hwpack.
        :param file_alias: Property name (not field name) which contains
                           file reference(s)
        :return: path to a file or list of paths to files
        """
        file_names, hwpack_tarfile, keys = self.get_field(file_alias,
                                                          return_keys=True)
        if not file_names:
            return file_names
        single = False
        if not isinstance(file_names, list):
            single = True
            file_names = [file_names]
        out_files = []

        # Depending on if board and/or bootloader were used to look up the
        # file we are getting, we need to prepend those names to the path
        # to get the correct extracted file from the hardware pack.
        config_names = [("board", "boards"), ("bootloader", "bootloaders")]
        base_path = ""
        if keys:
            # If keys is non-empty, we have a V3 config option that was
            # modified by the bootloader and/or boot option...
            for name, key in config_names:
                if self.get_field(name):
                    value = self.get_field(name)[0]
                    if keys[0] == key:
                        base_path = os.path.join(base_path, value)
                        keys = keys[1:]

        for f in file_names:
            # Check that the base path is needed. If the file doesn't exist,
            # try without it (this provides fallback to V2 style directory
            # layouts with a V3 config).
            path_inc_board_and_bootloader = os.path.join(base_path, f)
            if path_inc_board_and_bootloader in hwpack_tarfile.getnames():
                f = path_inc_board_and_bootloader
            hwpack_tarfile.extract(f, self.tempdir)
            f = os.path.join(self.tempdir, f)
            out_files.append(f)
        if single:
            return out_files[0]
        return out_files

    def list_packages(self):
        """Return list of (package names, TarFile object containing them)"""
        packages = []
        for tf in self.hwpack_tarfiles:
            for name in tf.getnames():
                if name.startswith("pkgs/") and name.endswith(".deb"):
                    packages.append((tf, name))
        return packages

    def find_package_for(self, name, version=None, revision=None,
                         architecture=None):
        """Find a package that matches the name, version, rev and arch given.

        Packages are named according to the debian specification:
        http://www.debian.org/doc/manuals/debian-faq/ch-pkg_basics.en.html
        <name>_<Version>-<DebianRevisionNumber>_<DebianArchitecture>.deb
        DebianRevisionNumber seems to be optional.
        Use this spec to return a package matching the requirements given.
        """
        for tar_file, package in self.list_packages():
            file_name = os.path.basename(package)
            dpkg_chunks = re.search("^(.+)_(.+)_(.+)\.deb$",
                                    file_name)
            assert dpkg_chunks, "Could not split package file name into"\
                "<name>_<Version>_<DebianArchitecture>.deb"

            pkg_name = dpkg_chunks.group(1)
            pkg_version = dpkg_chunks.group(2)
            pkg_architecture = dpkg_chunks.group(3)

            ver_chunks = re.search("^(.+)-(.+)$", pkg_version)
            if ver_chunks:
                pkg_version = ver_chunks.group(1)
                pkg_revision = ver_chunks.group(2)
            else:
                pkg_revision = None

            if name != pkg_name:
                continue
            if version is not None and str(version) != pkg_version:
                continue
            if revision is not None and str(revision) != pkg_revision:
                continue
            if (architecture is not None and
                    str(architecture) != pkg_architecture):
                continue

            # Got a matching package - return its path inside the tarball
            return tar_file, package

        # Failed to find a matching package - return None
        return None

    def get_file_from_package(self, file_path, package_name,
                              package_version=None, package_revision=None,
                              package_architecture=None):
        """Extract named file from package specified by name, ver, rev, arch.

        File is extracted from the package matching the given specification
        to a temporary directory. The absolute path to the extracted file is
        returned.
        """

        package_info = self.find_package_for(package_name,
                                             package_version,
                                             package_revision,
                                             package_architecture)
        if package_info is None:
            return None
        tar_file, package = package_info

        # Avoid unpacking hardware pack more than once by assigning each one
        # its own tempdir to unpack into.
        # TODO: update logic that uses self.tempdir so we can get rid of this
        # by sharing nicely.
        if not package in self.tempdirs:
            self.tempdirs[package] = tempfile.mkdtemp()
        tempdir = self.tempdirs[package]

        # We extract everything in the hardware pack so we don't have to worry
        # about chasing links (extract a link, find where it points to, extract
        # that...). This is slower, but more reliable.
        tar_file.extractall(tempdir)
        package_path = os.path.join(tempdir, package)

        with PackageUnpacker() as self.package_unpacker:
            extracted_file = self.package_unpacker.get_file(package_path,
                                                            file_path)
            after_tmp = re.sub(self.package_unpacker.tempdir, "",
                               extracted_file).lstrip("/\\")
            extract_dir = os.path.join(tempdir, "extracted",
                                       os.path.dirname(after_tmp))
            os.makedirs(extract_dir)
            shutil.move(extracted_file, extract_dir)
            extracted_file = os.path.join(extract_dir,
                                          os.path.basename(extracted_file))
        return extracted_file
