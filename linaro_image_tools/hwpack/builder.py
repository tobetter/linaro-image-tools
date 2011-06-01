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

    def unpack_package(self, package, wanted_path):
        package_file_name = 'testing/pkgs/u-boot-linaro-s5pv310_2011.03-0samsung6_armel.deb'
        
        tempdir = tempfile.mkdtemp()
        # XXX atexit remove tempdir
        p = cmd_runner.run(["tar", "--wildcards", "-C", tempdir, "-xf", "-"],
                           stdin=subprocess.PIPE)
        cmd_runner.run(["dpkg", "--fsys-tarfile", package_file_name],
                       stdout=p.stdin).communicate()
        p.communicate()
        
        unpacked_files = []
        for root, _, files in os.walk(tempdir + wanted_path):
            unpacked_files.extend(os.path.join(root, file) for file in files)

        return unpacked_files

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
                with fetcher:
                    fetcher.ignore_packages(self.config.assume_installed)
                    packages = fetcher.fetch_packages(
                        packages, download_content=self.config.include_debs)

                    u_boot_package = None
                    for package in packages:
                        # XXX This probably can be done with python list magic?
                        if package.name == self.config.u_boot_package:
                            u_boot_package = package
                    packages.remove(u_boot_package)
                    u_boot_files = self.unpack_package(u_boot_package,
                                                       '/usr/lib/u-boot/')
                    logger.debug("Unpacked %d files from u-boot package %s." % \
                                     (len(u_boot_files), u_boot_package.name))
                    hwpack.add_files(hwpack.U_BOOT_DIR, u_boot_files)

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
