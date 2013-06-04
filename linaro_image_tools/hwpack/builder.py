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

import logging
import errno
import subprocess
import os
import shutil
from glob import iglob

from debian.debfile import DebFile
from debian.arfile import ArError

from linaro_image_tools import cmd_runner

from linaro_image_tools.hwpack.config import Config
from linaro_image_tools.hwpack.hardwarepack import HardwarePack, Metadata
from linaro_image_tools.hwpack.packages import (
    FetchedPackage,
    LocalArchiveMaker,
    PackageFetcher,
)
from linaro_image_tools.hwpack.package_unpacker import PackageUnpacker

from linaro_image_tools.hwpack.hwpack_fields import (
    PACKAGE_FIELD,
    SPL_PACKAGE_FIELD,
)

# The fields that hold packages to be installed.
PACKAGE_FIELDS = [PACKAGE_FIELD, SPL_PACKAGE_FIELD]
logger = logging.getLogger(__name__)
LOCAL_ARCHIVE_LABEL = 'hwpack-local'


class ConfigFileMissing(Exception):

    def __init__(self, filename):
        self.filename = filename
        super(ConfigFileMissing, self).__init__(
            "No such config file: '%s'" % self.filename)


class HardwarePackBuilder(object):

    def __init__(self, config_path, version, local_debs, out_name=None):
        try:
            with open(config_path) as fp:
                self.config = Config(fp, allow_unset_bootloader=True)
        except IOError, e:
            if e.errno == errno.ENOENT:
                raise ConfigFileMissing(config_path)
            raise
        self.config.validate()
        self.format = self.config.format
        self.version = version
        self.local_debs = local_debs
        self.package_unpacker = None
        self.hwpack = None
        self.packages = None
        self.packages_added_to_hwpack = []
        self.out_name = out_name

    def find_fetched_package(self, packages, wanted_package_name):
        wanted_package = None
        for package in packages:
            if package.name == wanted_package_name:
                wanted_package = package
                break
        else:
            raise AssertionError("Package '%s' was not fetched." %
                                 wanted_package_name)
        return wanted_package

    def add_file_to_hwpack(self, package, wanted_file, target_path):
        if (package.name, wanted_file) in self.packages_added_to_hwpack:
            # Don't bother adding the same package more than once.
            return

        tempfile_name = self.package_unpacker.get_file(
            package.filepath, wanted_file)
        self.packages_added_to_hwpack.append((package.name, target_path))
        return self.hwpack.add_file(target_path, tempfile_name)

    def find_bootloader_packages(self, bootloaders_config):
        """Loop through the bootloaders dictionary searching for packages
        that should be installed, based on known keywords.

        :param bootloaders_config: The bootloaders dictionary to loop through.
        :return A list of packages, without duplicates."""
        boot_packages = []
        for key, value in bootloaders_config.iteritems():
            if isinstance(value, dict):
                boot_packages.extend(self.find_bootloader_packages(value))
            else:
                if key in PACKAGE_FIELDS:
                    boot_packages.append(value)
        # Eliminate duplicates.
        return list(set(boot_packages))

    def do_extract_file(self, package, source_path, dest_path):
        """Extract specified file from package to dest_path."""
        package_ref = self.find_fetched_package(self.packages, package)
        return self.add_file_to_hwpack(package_ref, source_path, dest_path)

    def do_extract_files(self):
        """Go through a bootloader config, search for files to extract."""
        base_dest_path = ""
        if self.config.board:
            base_dest_path = self.config.board
        base_dest_path = os.path.join(base_dest_path, self.config.bootloader)
        # Extract bootloader file
        if self.config.bootloader_package and self.config.bootloader_file:
            dest_path = os.path.join(
                base_dest_path, os.path.dirname(self.config.bootloader_file))
            self.do_extract_file(self.config.bootloader_package,
                                 self.config.bootloader_file,
                                 dest_path)

        # Extract SPL file
        if self.config.spl_package and self.config.spl_file:
            dest_path = os.path.join(base_dest_path,
                                     os.path.dirname(self.config.spl_file))
            self.do_extract_file(self.config.spl_package,
                                 self.config.spl_file,
                                 dest_path)

    def foreach_boards_and_bootloaders(self, function):
        """Call function for each board + bootloader combination in metadata"""
        if self.config.bootloaders is not None:
            for bootloader in self.config.bootloaders:
                self.config.board = None
                self.config.bootloader = bootloader
                function()

        if self.config.boards is not None:
            for board in self.config.boards:
                if self.config.bootloaders is not None:
                    for bootloader in self.config.bootloaders:
                        self.config.board = board
                        self.config.bootloader = bootloader
                        function()

    def extract_files(self):
        """Find bootloaders in config that may contain files to extract."""
        if float(self.config.format.format_as_string) < 3.0:
            # extract files was introduced in version 3 configurations and is
            # a null operation for earlier configuration files
            return

        self.foreach_boards_and_bootloaders(self.do_extract_files)

    def do_find_copy_files_packages(self):
        """Find packages referenced by copy_files (single board, bootloader)"""
        copy_files = self.config.bootloader_copy_files
        if copy_files:
            self.copy_files_packages.extend(copy_files.keys())

    def find_copy_files_packages(self):
        """Find all packages referenced by copy_files sections in metadata."""
        self.copy_files_packages = []
        self.foreach_boards_and_bootloaders(
            self.do_find_copy_files_packages)
        packages = self.copy_files_packages
        del self.copy_files_packages
        return packages

    def build(self):
        for architecture in self.config.architectures:
            logger.info("Building for %s" % architecture)
            metadata = Metadata.from_config(
                self.config, self.version, architecture)
            self.hwpack = HardwarePack(metadata)
            sources = self.config.sources
            with LocalArchiveMaker() as local_archive_maker:
                self.hwpack.add_apt_sources(sources)
                if sources:
                    sources = sources.values()
                else:
                    sources = []
                self.packages = self.config.packages[:]
                # Loop through multiple bootloaders.
                # In V3 of hwpack configuration, all the bootloaders info and
                # packages are in the bootloaders section.
                if self.format.format_as_string == '3.0':
                    if self.config.bootloaders is not None:
                        self.packages.extend(self.find_bootloader_packages(
                            self.config.bootloaders))
                    if self.config.boards is not None:
                        self.packages.extend(self.find_bootloader_packages(
                            self.config.boards))

                    self.packages.extend(self.find_copy_files_packages())
                else:
                    if self.config.bootloader_package is not None:
                        self.packages.append(self.config.bootloader_package)
                    if self.config.spl_package is not None:
                        self.packages.append(self.config.spl_package)
                local_packages = [
                    FetchedPackage.from_deb(deb)
                    for deb in self.local_debs]
                sources.append(
                    local_archive_maker.sources_entry_for_debs(
                        local_packages, LOCAL_ARCHIVE_LABEL))
                self.packages.extend([lp.name for lp in local_packages])
                logger.info("Fetching packages")
                fetcher = PackageFetcher(
                    sources, architecture=architecture,
                    prefer_label=LOCAL_ARCHIVE_LABEL)
                with fetcher:
                    with PackageUnpacker() as self.package_unpacker:
                        fetcher.ignore_packages(self.config.assume_installed)
                        self.packages = fetcher.fetch_packages(
                            self.packages,
                            download_content=self.config.include_debs)

                        if self.format.format_as_string == '3.0':
                            self.extract_files()
                        else:
                            self._old_format_extract_files()

                        self._add_packages_to_hwpack(local_packages)

                        out_name = self.out_name
                        if not out_name:
                            out_name = self.hwpack.filename()

                        manifest_name = os.path.splitext(out_name)[0]
                        if manifest_name.endswith('.tar'):
                            manifest_name = os.path.splitext(manifest_name)[0]
                        manifest_name += '.manifest.txt'

                        self._write_hwpack_and_manifest(out_name,
                                                        manifest_name)

                        cache_dir = fetcher.cache.tempdir
                        self._extract_build_info(cache_dir, out_name,
                                                 manifest_name)

    def _write_hwpack_and_manifest(self, out_name, manifest_name):
        """Write the real hwpack file and its manifest file.

        :param out_name: The name of the file to write.
        :type out_name: str
        :param manifest_name: The name of the manifest file.
        :type manifest_name: str
        """
        logger.debug("Writing hwpack file")
        with open(out_name, 'w') as f:
            self.hwpack.to_file(f)
            logger.info("Wrote %s" % out_name)

        logger.debug("Writing manifest file content")
        with open(manifest_name, 'w') as f:
            f.write(self.hwpack.manifest_text())

    def _old_format_extract_files(self):
        """Extract files for hwpack versions < 3.0."""
        bootloader_package = None
        if self.config.bootloader_file is not None:
            assert(self.config.bootloader_package is not None)
            bootloader_package = self.find_fetched_package(
                self.packages,
                self.config.bootloader_package)
            self.hwpack.metadata.u_boot = self.add_file_to_hwpack(
                bootloader_package,
                self.config.bootloader_file,
                self.hwpack.U_BOOT_DIR)

        spl_package = None
        if self.config.spl_file is not None:
            assert self.config.spl_package is not None
            spl_package = self.find_fetched_package(self.packages,
                                                    self.config.spl_package)
            self.hwpack.metadata.spl = self.add_file_to_hwpack(
                spl_package,
                self.config.spl_file,
                self.hwpack.SPL_DIR)

        # bootloader_package and spl_package can be identical
        if (bootloader_package is not None and
                bootloader_package in self.packages):
            self.packages.remove(bootloader_package)
        if (spl_package is not None and spl_package in self.packages):
            self.packages.remove(spl_package)

    def _add_packages_to_hwpack(self, local_packages):
        """Adds the packages to the hwpack.

        :param local_packages: The packages to add.
        :type local_packages: list
        """
        logger.debug("Adding packages to hwpack")
        self.hwpack.add_packages(self.packages)
        for local_package in local_packages:
            if local_package not in self.packages:
                logger.warning("Local package '%s' not included",
                               local_package.name)
        self.hwpack.add_dependency_package(self.config.packages)

    def _extract_build_info(self, cache_dir, out_name, manifest_name):
        """Extracts build-info from the packages.

        :param cache_dir: The cache directory where build-info should be
            located.
        :type cache_dir: str
        :param out_name: The name of the hwpack file.
        :type out_name: str
        :param manifest_name: The name of the manifest file.
        :type manifest_name: str
        """
        logger.debug("Extracting build-info")
        build_info_dir = os.path.join(cache_dir, 'build-info')
        build_info_available = 0
        for deb_pkg in self.packages:
            deb_pkg_file_path = deb_pkg.filepath
            # FIXME: test deb_pkg_dir to work around
            # https://bugs.launchpad.net/bugs/1067786
            deb_pkg_dir = os.path.dirname(deb_pkg_file_path)
            if deb_pkg_dir != cache_dir:
                continue
            if os.path.islink(deb_pkg_file_path):
                # Skip symlink-ed debian package file
                # e.g. fetched package with dummy information
                continue
            try:
                # Extract Build-Info attribute from debian control
                deb_control = DebFile(deb_pkg_file_path).control.debcontrol()
                build_info = deb_control.get('Build-Info')
            except ArError:
                # Skip invalid debian package file
                # e.g. fetched package with dummy information
                continue
            if build_info is not None:
                build_info_available += 1
                # Extract debian packages with build information
                env = os.environ
                env['LC_ALL'] = 'C'
                env['NO_PKG_MANGLE'] = '1'
                proc = cmd_runner.Popen(['dpkg-deb', '-x',
                                        deb_pkg_file_path, build_info_dir],
                                        env=env, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE)

                (stdoutdata, stderrdata) = proc.communicate()
                if proc.returncode:
                    raise ValueError('dpkg-deb extract failed!\n%s' %
                                     stderrdata)
                if stderrdata:
                    raise ValueError('dpkg-deb extract had warnings:\n%s' %
                                     stderrdata)

        self._concatenate_build_info(build_info_available, build_info_dir,
                                     out_name, manifest_name)

    def _concatenate_build_info(self, build_info_available, build_info_dir,
                                out_name, manifest_name):
        """Concatenates the build-info text if more than one is available.

        :param build_info_available: The number of available build-info.
        :type build_info_available: int
        :param build_info_dir: Where build-info files should be.
        :type build_info_dir: str
        :param out_name: The name of the hwpack file.
        :type out_name: str
        :param manifest_name: The name of the manifest file.
        :type manifest_name: str
        """
        logger.debug("Concatenating build-info files")
        dst_file = open('BUILD-INFO.txt', 'wb')
        if build_info_available > 0:
            build_info_path = (r'%s/usr/share/doc/*/BUILD-INFO.txt' %
                               build_info_dir)
            for src_file in iglob(build_info_path):
                with open(src_file, 'rb') as f:
                    dst_file.write('\nFiles-Pattern: %s\n' % out_name)
                    shutil.copyfileobj(f, dst_file)
            dst_file.write('\nFiles-Pattern: %s\nLicense-Type: open\n' %
                           manifest_name)
        else:
            dst_file.write('Format-Version: 0.1\n'
                           'Files-Pattern: %s, %s\n'
                           'License-Type: open\n' % (out_name, manifest_name))
        dst_file.close()
