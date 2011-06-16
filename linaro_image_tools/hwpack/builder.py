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

from linaro_image_tools import cmd_runner

from linaro_image_tools.hwpack.config import Config
from linaro_image_tools.hwpack.hardwarepack import HardwarePack, Metadata
from linaro_image_tools.hwpack.packages import (
    FetchedPackage,
    LocalArchiveMaker,
    PackageFetcher,
    )


logger = logging.getLogger(__name__)


LOCAL_ARCHIVE_LABEL='hwpack-local'


class ConfigFileMissing(Exception):

    def __init__(self, filename):
        self.filename = filename
        super(ConfigFileMissing, self).__init__(
            "No such config file: '%s'" % self.filename)


class PackageUnpacker:
    def __enter__(self):
        self.tempdir = tempfile.mkdtemp()
        return self

    def __exit__(self, type, value, traceback):
        if self.tempdir is not None and os.path.exists(self.tempdir):
            shutil.rmtree(self.tempdir)
            pass

    def unpack_package(self, package_file_name):
        p = cmd_runner.run(["tar", "--wildcards", "-C", self.tempdir, "-xf", "-"],
                           stdin=subprocess.PIPE)
        cmd_runner.run(["dpkg", "--fsys-tarfile", package_file_name],
                       stdout=p.stdin).communicate()
        p.communicate()

    def add_file_from_package(self, package, file, target_dir, target_hwpack):
        self.unpack_package(package)
        temp_file = os.path.join(self.tempdir, file)
        assert os.path.exists(temp_file), "The file '%s' was " \
            "not found in the package '%s'." % (file, package)
            
        logger.debug("Unpacked %s from package %s." % (temp_file, package))
        target_hwpack.add_file(target_dir, temp_file)
        return os.path.join(target_dir, os.path.basename(temp_file))


class HardwarePackBuilder(object):

    def __init__(self, config_path, version, local_debs):
        try:
            with open(config_path) as fp:
                self.config = Config(fp)
        except IOError, e:
            if e.errno == errno.ENOENT:
                raise ConfigFileMissing(config_path)
            raise
        self.config.validate()
        self.format = self.config.format
        self.version = version
        self.local_debs = local_debs

    def put_uboot_in_hwpack(self, packages, fetcher, file_in_package, hwpack):
        u_boot_package = None
        for package in packages:
            if package.name == self.config.u_boot_package:
                u_boot_package = package
                break
            else:
                raise Exception(
                    "U-boot package %s was not fetched." % \
                        self.config.u_boot_package)
        packages.remove(u_boot_package)
        u_boot_package_path = os.path.join(fetcher.cache.tempdir,
                                           u_boot_package.filepath)
        return file_in_package.add_file_from_package(
            u_boot_package_path, self.config.u_boot_file,
            hwpack.U_BOOT_DIR, hwpack)

    def build(self):
        for architecture in self.config.architectures:
            logger.info("Building for %s" % architecture)
            metadata = Metadata.from_config(
                self.config, self.version, architecture)
            hwpack = HardwarePack(metadata, self.format)
            sources = self.config.sources
            with LocalArchiveMaker() as local_archive_maker:
                hwpack.add_apt_sources(sources)
                sources = sources.values()
                packages = self.config.packages[:]
                if self.config.u_boot_package is not None:
                    packages.append(self.config.u_boot_package)
                local_packages = [
                    FetchedPackage.from_deb(deb)
                    for deb in self.local_debs]
                sources.append(
                    local_archive_maker.sources_entry_for_debs(
                        local_packages, LOCAL_ARCHIVE_LABEL))
                packages.extend([lp.name for lp in local_packages])
                logger.info("Fetching packages")
                fetcher = PackageFetcher(
                    sources, architecture=architecture,
                    prefer_label=LOCAL_ARCHIVE_LABEL)
                with fetcher, PackageUnpacker() as file_in_package:
                    fetcher.ignore_packages(self.config.assume_installed)
                    packages = fetcher.fetch_packages(
                        packages, download_content=self.config.include_debs)

                    if self.config.u_boot_package is not None:
                        hwpack.metadata.u_boot = self.put_uboot_in_hwpack(
                            packages, fetcher, file_in_package, hwpack)

                    logger.debug("Adding packages to hwpack")
                    hwpack.add_packages(packages)
                    for local_package in local_packages:
                        if local_package not in packages:
                            logger.warning(
                                "Local package '%s' not included",
                                local_package.name)
                    hwpack.add_dependency_package(self.config.packages)
                    with open(hwpack.filename(), 'w') as f:
                        hwpack.to_file(f)
                        logger.info("Wrote %s" % hwpack.filename())
                    with open(hwpack.filename('.manifest.txt'), 'w') as f:
                        f.write(hwpack.manifest_text())
