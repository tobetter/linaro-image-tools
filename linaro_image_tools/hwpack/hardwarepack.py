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

import time
import os

from linaro_image_tools.hwpack.better_tarfile import writeable_tarfile
from linaro_image_tools.hwpack.packages import (
    FetchedPackage,
    get_packages_file,
    PackageMaker,
    )
from linaro_image_tools.hwpack.hardwarepack_format import (
    HardwarePackFormatV1,
)


class Metadata(object):
    """Metadata for a hardware pack.

    This metadata is what is required and optional for the metadata file
    that ends up in the hardware pack.

    In addition str() can be used to create the contents of the metdata
    file for the hardware pack that this metadata file refers to.

    :ivar name: the name of the hardware pack.
    :type name: str
    :ivar version: the version of the hardware pack. It must not contain white
        spaces.
    :type version: str
    :ivar origin: the origin of the hardware pack, or None if the origin
        is not known.
    :type origin: str or None
    :ivar maintainer: the maintainer of the hardware pack, or None if
        not known.
    :type maintainer: str or None
    :ivar support: the support status of this hardware pack, or None if
         not know.
    :type support: str or None
    """

    def __init__(self, name, version, architecture, origin=None,
                 maintainer=None, support=None, format=HardwarePackFormatV1()):
        """Create the Metadata for a hardware pack.

        See the instance variables for a description of the arguments.
        """
        self.format = format
        self.name = name
        if ' ' in version:
            raise AssertionError(
                'Hardware pack version must not contain white '
                'spaces: "%s"' % version)
        self.version = version
        self.origin = origin
        self.maintainer = maintainer
        self.support = support
        self.architecture = architecture

    @classmethod
    def add_v2_config(self, serial_tty=None, kernel_addr=None, initrd_addr=None,
                      load_addr=None, dtb_file=None, wired_interfaces=[],
                      wireless_interfaces=[], partition_layout=None,
                      mmc_id=None, boot_min_size=None, root_min_size=None,
                      loader_min_size=None, vmlinuz=None, initrd=None,
                      dtb_addr=None, extra_boot_options=None,
                      boot_script=None, uboot_in_boot_part=None,
                      uboot_dd=None, spl_in_boot_part=None, spl_dd=None,
                      extra_serial_opts=None, loader_start=None,
                      snowball_startup_files_config=None,
                      samsung_bl1_start=None, samsung_bl1_len=None,
                      samsung_env_len=None, samsung_bl2_len=None):
        """Add fields that are specific to the new format.

        These fields are not present in earlier config files.
        """
        self.u_boot = None
        self.spl = None
        self.serial_tty = serial_tty
        self.kernel_addr = kernel_addr
        self.initrd_addr = initrd_addr
        self.load_addr = load_addr
        self.wired_interfaces = wired_interfaces
        self.wireless_interfaces = wireless_interfaces
        self.partition_layout = partition_layout
        self.mmc_id = mmc_id
        self.boot_min_size = boot_min_size
        self.root_min_size = root_min_size
        self.loader_min_size = loader_min_size
        self.loader_start = loader_start
        self.vmlinuz = vmlinuz
        self.initrd = initrd
        self.dtb_file = dtb_file
        self.dtb_addr = dtb_addr
        self.extra_boot_options = extra_boot_options
        self.boot_script = boot_script
        self.uboot_in_boot_part = uboot_in_boot_part
        self.uboot_dd = uboot_dd
        self.spl_in_boot_part = spl_in_boot_part
        self.spl_dd = spl_dd
        self.extra_serial_opts = extra_serial_opts
        self.snowball_startup_files_config = snowball_startup_files_config
        self.samsung_bl1_start = samsung_bl1_start
        self.samsung_bl1_len = samsung_bl1_len
        self.samsung_env_len = samsung_env_len
        self.samsung_bl2_len = samsung_bl2_len

    @classmethod
    def from_config(cls, config, version, architecture):
        """Create a Metadata from a Config object.

        As a Config will contain most of the information needed for a
        Metadata, we can provide this convenient way to construct one.

        Information that is not in the config has to be provided by
        the caller.

        :param config: the config to take values from.
        :type config: Config
        :param version: the version to record in the metadata.
        :type version: str
        :param architecture: the architecture that the hardware pack is
            targetting.
        :type architecture: str
        """
        metadata = cls(
            config.name, version, architecture, origin=config.origin,
            maintainer=config.maintainer, support=config.support,
            format=config.format)

        if config.format.has_v2_fields:
            metadata.add_v2_config(serial_tty=config.serial_tty,
                                   kernel_addr=config.kernel_addr,
                                   initrd_addr=config.initrd_addr,
                                   load_addr=config.load_addr,
                                   wired_interfaces=config.wired_interfaces,
                                   wireless_interfaces=config.wireless_interfaces,
                                   partition_layout=config.partition_layout,
                                   mmc_id=config.mmc_id,
                                   boot_min_size=config.boot_min_size,
                                   root_min_size=config.root_min_size,
                                   loader_min_size=config.loader_min_size,
                                   loader_start=config.loader_start,
                                   vmlinuz=config.vmlinuz,
                                   initrd=config.initrd,
                                   dtb_file=config.dtb_file,
                                   dtb_addr=config.dtb_addr,
                                   extra_boot_options=config.extra_boot_options,
                                   boot_script=config.boot_script,
                                   uboot_in_boot_part=config.uboot_in_boot_part,
                                   uboot_dd=config.uboot_dd,
                                   spl_in_boot_part=config.spl_in_boot_part,
                                   spl_dd=config.spl_dd,
                                   extra_serial_opts=config.extra_serial_opts,
                                   snowball_startup_files_config=config.snowball_startup_files_config,
                                   samsung_bl1_start=config.samsung_bl1_start,
                                   samsung_bl1_len=config.samsung_bl1_len,
                                   samsung_env_len=config.samsung_env_len,
                                   samsung_bl2_len=config.samsung_bl2_len)
        return metadata

    def __str__(self):
        """Get the contents of the metadata file."""
        metadata = "NAME=%s\n" % self.name
        metadata += "VERSION=%s\n" % self.version
        metadata += "ARCHITECTURE=%s\n" % self.architecture
        if self.origin is not None:
            metadata += "ORIGIN=%s\n" % self.origin
        if self.maintainer is not None:
            metadata += "MAINTAINER=%s\n" % self.maintainer
        if self.support is not None:
            metadata += "SUPPORT=%s\n" % self.support

        if not self.format.has_v2_fields:
            return metadata
            
        if self.u_boot is not None:
            metadata += "U_BOOT=%s\n" % self.u_boot
        if self.spl is not None:
            metadata += "SPL=%s\n" % self.spl
        if self.serial_tty is not None:
            metadata += "SERIAL_TTY=%s\n" % self.serial_tty
        if self.kernel_addr is not None:
            metadata += "KERNEL_ADDR=%s\n" % self.kernel_addr
        if self.initrd_addr is not None:
            metadata += "INITRD_ADDR=%s\n" % self.initrd_addr
        if self.load_addr is not None:
            metadata += "LOAD_ADDR=%s\n" % self.load_addr
        if self.dtb_addr is not None:
            metadata += "DTB_ADDR=%s\n" % self.dtb_addr
        if self.wired_interfaces != []:
            metadata += "WIRED_INTERFACES=%s\n" % " ".join(self.wired_interfaces)
        if self.wireless_interfaces != []:
            metadata += "WIRELESS_INTERFACES=%s\n" % " ".join(
                self.wireless_interfaces)
        if self.partition_layout is not None:
            metadata += "PARTITION_LAYOUT=%s\n" % self.partition_layout
        if self.mmc_id is not None:
            metadata += "MMC_ID=%s\n" % self.mmc_id
        if self.boot_min_size is not None:
            metadata += "BOOT_MIN_SIZE=%s\n" % self.boot_min_size
        if self.root_min_size is not None:
            metadata += "ROOT_MIN_SIZE=%s\n" % self.root_min_size
        if self.loader_min_size is not None:
            metadata += "LOADER_MIN_SIZE=%s\n" % self.loader_min_size
        if self.loader_start is not None:
            metadata += "LOADER_START=%s\n" % self.loader_start
        if self.vmlinuz is not None:
            metadata += "KERNEL_FILE=%s\n" % self.vmlinuz
        if self.initrd is not None:
            metadata += "INITRD_FILE=%s\n" % self.initrd
        if self.dtb_file is not None:
            metadata += "DTB_FILE=%s\n" % self.dtb_file
        if self.extra_boot_options is not None:
            metadata += "EXTRA_BOOT_OPTIONS=%s\n" % self.extra_boot_options
        if self.boot_script is not None:
            metadata += "BOOT_SCRIPT=%s\n" % self.boot_script
        if self.uboot_in_boot_part is not None:
            metadata += "U_BOOT_IN_BOOT_PART=%s\n" % self.uboot_in_boot_part
        if self.spl_in_boot_part is not None:
            metadata += "SPL_IN_BOOT_PART=%s\n" % self.spl_in_boot_part
        if self.uboot_dd is not None:
            metadata += "U_BOOT_DD=%s\n" % self.uboot_dd
        if self.spl_dd is not None:
            metadata += "SPL_BOOT_DD=%s\n" % self.spl_dd
        if self.extra_serial_opts is not None:
            metadata += "EXTRA_SERIAL_OPTIONS=%s\n" % self.extra_serial_opts
        if self.snowball_startup_files_config is not None:
            metadata += "SNOWBALL_STARTUP_FILES_CONFIG=%s\n" % self.snowball_startup_files_config
        if self.samsung_bl1_start is not None:
            metadata += "SAMSUNG_BL1_START=%s\n" % self.samsung_bl1_start
        if self.samsung_bl1_len is not None:
            metadata += "SAMSUNG_BL1_LEN=%s\n" % self.samsung_bl1_len
        if self.samsung_env_len is not None:
            metadata += "SAMSUNG_ENV_LEN=%s\n" % self.samsung_env_len
        if self.samsung_bl2_len is not None:
            metadata += "SAMSUNG_BL2_LEN=%s\n" % self.samsung_bl2_len

        return metadata


class HardwarePack(object):
    """The representation of a hardware pack.

    :ivar metadata: the metadata of this hardware pack.
    :type metadata: Metadata
    :ivar FORMAT: the format of hardware pack that should be created.
    :type FORMAT: str
    """

    FORMAT_FILENAME = "FORMAT"
    METADATA_FILENAME = "metadata"
    MANIFEST_FILENAME = "manifest"
    PACKAGES_DIRNAME = "pkgs"
    PACKAGES_FILENAME = "%s/Packages" % PACKAGES_DIRNAME
    SOURCES_LIST_DIRNAME = "sources.list.d"
    SOURCES_LIST_GPG_DIRNAME = "sources.list.d.gpg"
    U_BOOT_DIR = "u-boot"
    SPL_DIR = "spl"

    def __init__(self, metadata):
        """Create a HardwarePack.

        :param metadata: the metadata to use.
        :type metadata: Metadata
        """
        self.metadata = metadata
        self.sources = {}
        self.packages = []
        self.format = metadata.format
        self.files = []

    def filename(self, extension=".tar.gz"):
        """The filename that this hardware pack should have.

        Returns the filename that the hardware pack should have, according
        to the convention used.

        :return: the filename that should be used.
        :rtype: str
        """
        if self.metadata.support is None:
            support_suffix = ""
        else:
            support_suffix = "_%s" % self.metadata.support
        return "hwpack_%s_%s_%s%s%s" % (
            self.metadata.name, self.metadata.version,
            self.metadata.architecture, support_suffix, extension)

    def add_apt_sources(self, sources):
        """Add APT sources to the hardware pack.

        Given a dict of names and the source lines this will add
        them to the hardware pack.

        The names should be an identifier for the source, and the
        source lines should be what is put in sources.list for that
        source, minus the "deb" part.

        If you pass an identifier that has already been passed to this
        method, then the previous value will be replaced with the new
        value.

        :param sources: the sources to use as a dict mapping identifiers
            to sources entries.
        :type sources: a dict mapping str to str
        """
        self.sources.update(sources)

    def add_packages(self, packages):
        """Add packages to the hardware pack.

        Given a list of packages this will add them to the hardware
        pack.

        :param packages: the packages to add
        :type packages: FetchedPackage
        """
        self.packages += packages

    def add_dependency_package(self, packages_spec):
        """Add a packge that depends on packages_spec to the hardware pack.

        :param packages_spec: A list of apt package specifications,
            e.g. ``['foo', 'bar (>= 1.2)']``.
        """
        with PackageMaker() as maker:
            dep_package_name = 'hwpack-' + self.metadata.name
            relationships = {}
            if packages_spec:
                relationships = {'Depends': ', '.join(packages_spec)}
            deb_file_path = maker.make_package(
                dep_package_name, self.metadata.version,
                relationships, self.metadata.architecture)
            self.packages.append(FetchedPackage.from_deb(deb_file_path))

    def add_file(self, dir, file):
        target_file = os.path.join(dir, os.path.basename(file))
        self.files.append((file, target_file))
        return target_file

    def manifest_text(self):
        manifest_content = ""
        for package in self.packages:
            manifest_content += "%s=%s\n" % (
                package.name, package.version)
        return manifest_content

    def to_file(self, fileobj):
        """Write the hwpack to a file object.

        The full hardware pack will be written to the file object in
        gzip compressed tarball form as the spec requires.

        :param fileobj: the file object to write to.
        :type fileobj: a file-like object
        :return: None
        """
        kwargs = {}
        kwargs["default_uid"] = 1000
        kwargs["default_gid"] = 1000
        kwargs["default_uname"] = "user"
        kwargs["default_gname"] = "group"
        kwargs["default_mtime"] = time.time()
        with writeable_tarfile(fileobj, mode="w:gz", **kwargs) as tf:
            tf.create_file_from_string(
                self.FORMAT_FILENAME, "%s\n" % self.format)
            tf.create_file_from_string(
                self.METADATA_FILENAME, str(self.metadata))
            for fs_file_name, arc_file_name in self.files:
                tf.add(fs_file_name, arcname=arc_file_name)
            tf.create_dir(self.PACKAGES_DIRNAME)
            for package in self.packages:
                if package.content is not None:
                    tf.create_file_from_string(
                        self.PACKAGES_DIRNAME + "/" + package.filename,
                        package.content.read())
            tf.create_file_from_string(
                self.MANIFEST_FILENAME, self.manifest_text())
            tf.create_file_from_string(
                self.PACKAGES_FILENAME,
                get_packages_file(
                    [p for p in self.packages if p.content is not None]))
            tf.create_dir(self.SOURCES_LIST_DIRNAME)
            for source_name, source_info in self.sources.items():
                tf.create_file_from_string(
                    self.SOURCES_LIST_DIRNAME + "/" + source_name + ".list",
                    "deb " + source_info + "\n")
            # TODO: include sources keys etc.
            tf.create_dir(self.SOURCES_LIST_GPG_DIRNAME)
