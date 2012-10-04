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
import tempfile
import os
import shutil
from glob import iglob

from debian.debfile import DebFile

from linaro_image_tools import cmd_runner

from linaro_image_tools.hwpack.config import Config
from linaro_image_tools.hwpack.hardwarepack import HardwarePack, Metadata
from linaro_image_tools.hwpack.packages import (
    FetchedPackage,
    LocalArchiveMaker,
    PackageFetcher,
    )

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


class PackageUnpacker(object):
    def __enter__(self):
        self.tempdir = tempfile.mkdtemp()
        return self

    def __exit__(self, type, value, traceback):
        if self.tempdir is not None and os.path.exists(self.tempdir):
            shutil.rmtree(self.tempdir)

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
        p = cmd_runner.run(["tar", "-C", unpack_dir, "-xf", "-"],
                           stdin=subprocess.PIPE)
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
            raise AssertionError("Package '%s' was not fetched." % \
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
            dest_path = os.path.join(base_dest_path,
                            os.path.dirname(self.config.bootloader_file))
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
                self.config.set_board(None)
                self.config.set_bootloader(bootloader)
                function()

        if self.config.boards is not None:
            for board in self.config.boards:
                if self.config.bootloaders is not None:
                    for bootloader in self.config.bootloaders:
                        self.config.set_board(board)
                        self.config.set_bootloader(bootloader)
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

                        # On a v3 hwpack, all the values we need to check are
                        # in the bootloaders and boards section, so we loop
                        # through both of them changing what is necessary.

                        if self.config.format.format_as_string == '3.0':
                            self.extract_files()
                        else:
                            bootloader_package = None
                            if self.config.bootloader_file is not None:
                                assert(self.config.bootloader_package
                                       is not None)
                                bootloader_package = self.find_fetched_package(
                                    self.packages,
                                    self.config.bootloader_package)
                                self.hwpack.metadata.u_boot = \
                                    self.add_file_to_hwpack(
                                        bootloader_package,
                                        self.config.bootloader_file,
                                        self.hwpack.U_BOOT_DIR)

                            spl_package = None
                            if self.config.spl_file is not None:
                                assert self.config.spl_package is not None
                                spl_package = self.find_fetched_package(
                                    self.packages,
                                    self.config.spl_package)
                                self.hwpack.metadata.spl = \
                                    self.add_file_to_hwpack(
                                        spl_package,
                                        self.config.spl_file,
                                        self.hwpack.SPL_DIR)

                            # bootloader_package and spl_package can be
                            # identical
                            if (bootloader_package is not None and
                                bootloader_package in self.packages):
                                self.packages.remove(bootloader_package)
                            if (spl_package is not None and
                                spl_package in self.packages):
                                self.packages.remove(spl_package)

                        logger.debug("Adding packages to hwpack")
                        self.hwpack.add_packages(self.packages)
                        for local_package in local_packages:
                            if local_package not in self.packages:
                                logger.warning(
                                    "Local package '%s' not included",
                                    local_package.name)
                        self.hwpack.add_dependency_package(
                                self.config.packages)
                        out_name = self.out_name
                        if not out_name:
                            out_name = self.hwpack.filename()
                        with open(out_name, 'w') as f:
                            self.hwpack.to_file(f)
                            logger.info("Wrote %s" % out_name)
                        manifest_name = os.path.splitext(out_name)[0]
                        if manifest_name.endswith('.tar'):
                            manifest_name = os.path.splitext(manifest_name)[0]
                        manifest_name += '.manifest.txt'
                        with open(manifest_name, 'w') as f:
                            f.write(self.hwpack.manifest_text())

                        logger.debug("Extracting build-info")
                        build_info_dir = os.path.join(fetcher.cache.tempdir,
                                                      'build-info')
                        build_info_available = 0
                        for deb_pkg in self.packages:
                            # Extract Build-Info attribute from debian control
                            deb_pkg_file_path = deb_pkg.filepath
                            deb_control = \
                                DebFile(deb_pkg_file_path).control.debcontrol()
                            build_info = deb_control.get('Build-Info')
                            if build_info is not None:
                                build_info_available += 1
                                # Extract debian packages with build
                                # information
                                env = os.environ
                                env['LC_ALL'] = 'C'
                                env['NO_PKG_MANGLE'] = '1'
                                proc = cmd_runner.Popen(['dpkg-deb', '-x',
                                       deb_pkg_file_path, build_info_dir],
                                       env=env, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
                                (stdoutdata, stderrdata) = proc.communicate()
                                if proc.returncode:
                                    raise ValueError('dpkg-deb extract failed!'
                                        '\n%s' % stderrdata)
                                if stderrdata:
                                    raise ValueError('dpkg-deb extract had '
                                        'warnings:\n%s' % stderrdata)

                        # Concatenate BUILD-INFO.txt files
                        if build_info_available > 0:
                            dst_file = open('BUILD-INFO.txt', 'wb')
                            build_info_path = \
                                r'%s/usr/share/doc/*/BUILD-INFO.txt' % \
                                build_info_dir
                            for src_file in iglob(build_info_path):
                                with open(src_file, 'rb') as f:
                                    dst_file.write('Files-Pattern: %s\n' % \
                                                   out_name)
                                    shutil.copyfileobj(f, dst_file)
                            dst_file.close()
