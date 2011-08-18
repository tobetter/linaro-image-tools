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

import ConfigParser
import re
import string

from linaro_image_tools.hwpack.hardwarepack_format import (
    HardwarePackFormatV1,
    HardwarePackFormatV2,
    )

class HwpackConfigError(Exception):
    pass


class Config(object):
    """Encapsulation of a hwpack-create configuration."""

    MAIN_SECTION = "hwpack"
    NAME_KEY = "name"
    NAME_REGEX = r"[a-z0-9][a-z0-9+\-.]+$"
    INCLUDE_DEBS_KEY = "include-debs"
    SUPPORT_KEY = "support"
    SOURCES_ENTRY_KEY = "sources-entry"
    PACKAGES_KEY = "packages"
    PACKAGE_REGEX = NAME_REGEX
    PATH_REGEX = r"\w[\w+\-./_]+$"
    ORIGIN_KEY = "origin"
    MAINTAINER_KEY = "maintainer"
    ARCHITECTURES_KEY = "architectures"
    ASSUME_INSTALLED_KEY = "assume-installed"
    U_BOOT_PACKAGE_KEY = "u_boot_package"
    U_BOOT_FILE_KEY = "u_boot_file"
    SERIAL_TTY_KEY = "serial_tty"
    KERNEL_ADDR_KEY = "kernel_addr"
    INITRD_ADDR_KEY = "initrd_addr"
    LOAD_ADDR_KEY = "load_addr"
    DTB_ADDR_KEY = "dtb_addr"
    WIRED_INTERFACES_KEY = "wired_interfaces"
    WIRELESS_INTERFACES_KEY = "wireless_interfaces"
    PARTITION_LAYOUT_KEY = "partition_layout"
    MMC_ID_KEY = "mmc_id"
    FORMAT_KEY = "format"
    BOOT_MIN_SIZE_KEY = "boot_min_size"
    ROOT_MIN_SIZE_KEY = "root_min_size"
    LOADER_MIN_SIZE_KEY = "loader_min_size"
    X_LOADER_PACKAGE_KEY = "x_loader_package"
    X_LOADER_FILE_KEY = "x_loader_file"
    VMLINUZ_KEY = "kernel_file"
    INITRD_KEY = "initrd_file"
    DTB_FILE_KEY = "dtb_file"
    EXTRA_BOOT_OPTIONS_KEY = 'extra_boot_options'
    BOOT_SCRIPT_KEY = 'boot_script'
    UBOOT_IN_BOOT_PART_KEY = 'u_boot_in_boot_part'
    EXTRA_SERIAL_OPTS_KEY = 'extra_serial_options'

    DEFINED_PARTITION_LAYOUTS = [
        'bootfs16_rootfs',
        'bootfs_rootfs',
        #'reserved_bootfs_rootfs',
        ]


    def __init__(self, fp):
        """Create a Config.

        :param fp: a file-like object containing the configuration.
        """
        self.parser = ConfigParser.RawConfigParser()
        self.parser.readfp(fp)

    def validate(self):
        """Check that this configuration follows the schema.

        :raises HwpackConfigError: if it does not.
        """
        if not self.parser.has_section(self.MAIN_SECTION):
            raise HwpackConfigError("No [%s] section" % self.MAIN_SECTION)
        self._validate_format()
        self._validate_name()
        self._validate_include_debs()
        self._validate_support()
        self._validate_packages()
        self._validate_architectures()
        self._validate_assume_installed()

        if self.format.has_v2_fields:
            self._validate_u_boot_package()
            self._validate_u_boot_file()
            self._validate_serial_tty()
            self._validate_kernel_addr()
            self._validate_initrd_addr()
            self._validate_load_addr()
            self._validate_dtb_addr()
            self._validate_wired_interfaces()
            self._validate_wireless_interfaces()
            self._validate_partition_layout()
            self._validate_mmc_id()
            self._validate_boot_min_size()
            self._validate_root_min_size()
            self._validate_loader_min_size()
            self._validate_x_loader_package()
            self._validate_x_loader_file()
            self._validate_vmlinuz()
            self._validate_initrd()
            self._validate_dtb_file()
            self._validate_extra_boot_options()
            self._validate_boot_script()
            self._validate_uboot_in_boot_part()
            self._validate_extra_serial_opts()

        self._validate_sections()

    @property
    def format(self):
        """The format of the hardware pack. A subclass of HardwarePackFormat.
        """
        try:
            format_string = self.parser.get(self.MAIN_SECTION, self.FORMAT_KEY)
        except ConfigParser.NoOptionError:
            # Default to 1.0 to aviod breaking existing hwpack files.
            # When this code no longer supports 1.0, it effectively makes
            # explicitly specifying format in hwpack files mandatory.
            format_string = "1.0"
        
        if format_string == '1.0':
            return HardwarePackFormatV1()
        elif format_string == '2.0':
            return HardwarePackFormatV2()
        else:
            raise HwpackConfigError("Format version '%s' is not supported." % \
                                     format_string)

    @property
    def name(self):
        """The name of the hardware pack. A str."""
        return self.parser.get(self.MAIN_SECTION, self.NAME_KEY)

    @property
    def include_debs(self):
        """Whether the hardware pack should contain .debs. A bool."""
        try:
            if not self.parser.get(
                self.MAIN_SECTION, self.INCLUDE_DEBS_KEY):
                return True
            return self.parser.getboolean(
                self.MAIN_SECTION, self.INCLUDE_DEBS_KEY)
        except ConfigParser.NoOptionError:
            return True

    @property
    def uboot_in_boot_part(self):
        """Whether uboot binary should be put in the boot partition. A str."""
        return self.parser.get(self.MAIN_SECTION, self.UBOOT_IN_BOOT_PART_KEY)

    def _get_option_from_main_section(self, key):
        """Get the value from the main section for the given key.

        :param key: the key to return the value for.
        :type key: str.
        :return: the value for that key, or None if the key is not present
            or the value is empty.
        :rtype: str or None.
        """
        try:
            result = self.parser.get(self.MAIN_SECTION, key)
            if not result:
                return None
            return result
        except ConfigParser.NoOptionError:
            return None

    @property
    def serial_tty(self):
        """/dev device name of the serial console for this kernel 

        A str.
        """
        return self._get_option_from_main_section(self.SERIAL_TTY_KEY)

    @property
    def extra_boot_options(self):
        """Extra boot arg options.

        A str.
        """
        return self._get_option_from_main_section(self.EXTRA_BOOT_OPTIONS_KEY)

    @property
    def extra_serial_opts(self):
        """Extra serial options.

        A str.
        """
        return self._get_option_from_main_section(self.EXTRA_SERIAL_OPTS_KEY)

    @property
    def boot_script(self):
        """File name of the target boot script.

        A str.
        """
        return self._get_option_from_main_section(self.BOOT_SCRIPT_KEY)

    @property
    def kernel_addr(self):
        """address where u-boot should load the kernel 

        An int.
        """
        return self._get_option_from_main_section(self.KERNEL_ADDR_KEY)

    @property
    def initrd_addr(self):
        """address where u-boot should load the kernel 

        An int.
        """
        return self._get_option_from_main_section(self.INITRD_ADDR_KEY)

    @property
    def load_addr(self):
        """address for uImage generation

        An int.
        """
        return self._get_option_from_main_section(self.LOAD_ADDR_KEY)

    @property
    def dtb_addr(self):
        """address for dtb image generation

        An int.
        """
        return self._get_option_from_main_section(self.DTB_ADDR_KEY)

    @property
    def wired_interfaces(self):
        """The interfaces for wired networks

        A list of str.
        """
        return self._get_list_from_main_section(self.WIRED_INTERFACES_KEY)

    @property
    def wireless_interfaces(self):
        """The interfaces for wireless networks

        A list of str.
        """
        return self._get_list_from_main_section(self.WIRELESS_INTERFACES_KEY)

    @property
    def partition_layout(self):
        """bootfs16_rootfs, bootfs_rootfs and reserved_bootfs_rootfs; 
        controls what kind of SD card partition layout we should use when 
        writing images 

        A str.
        """
        return self._get_option_from_main_section(self.PARTITION_LAYOUT_KEY)

    @property
    def mmc_id(self):
        """which MMC drive contains the boot filesystem 

        An int.
        """
        return self._get_option_from_main_section(self.MMC_ID_KEY)

    @property
    def root_min_size(self):
        """Minimum size of the root partition, in MiB.

        An int.
        """
        return self._get_option_from_main_section(self.ROOT_MIN_SIZE_KEY)

    @property
    def boot_min_size(self):
        """Minimum size of the boot partition, in MiB.

        An int.
        """
        return self._get_option_from_main_section(self.BOOT_MIN_SIZE_KEY)

    @property
    def loader_min_size(self):
        """Minimum size of the optional loader partition, in MiB.

        An int.
        """
        return self._get_option_from_main_section(self.LOADER_MIN_SIZE_KEY)

    @property
    def origin(self):
        """The origin that should be recorded in the hwpack.

        A str or None if no origin should be recorded.
        """
        return self._get_option_from_main_section(self.ORIGIN_KEY)

    @property
    def maintainer(self):
        """The maintainer that should be recorded in the hwpack.

        A str or None if not maintainer should be recorded.
        """
        return self._get_option_from_main_section(self.MAINTAINER_KEY)

    @property
    def support(self):
        """The support level that should be recorded in the hwpack.

        A str or None if no support level should be recorded.
        """
        return self._get_option_from_main_section(self.SUPPORT_KEY)

    def _get_list_from_main_section(self, key):
        raw_values = self._get_option_from_main_section(key)
        if raw_values is None:
            return []
        values = re.split("\s+", raw_values)
        filtered_values = []
        for value in values:
            if value not in filtered_values:
                filtered_values.append(value)
        return filtered_values

    @property
    def packages(self):
        """The packages that should be contained in the hwpack.

        A list of str.
        """
        return self._get_list_from_main_section(self.PACKAGES_KEY)

    @property
    def u_boot_package(self):
        """The u-boot package that contains the u-boot bin.

        A str.
        """
        return self._get_option_from_main_section(self.U_BOOT_PACKAGE_KEY)

    @property
    def u_boot_file(self):
        """The u-boot bin file that will be unpacked from the u-boot package.

        A str.
        """
        return self._get_option_from_main_section(self.U_BOOT_FILE_KEY)

    @property
    def x_loader_package(self):
        """The x-loader package that contains the x-loader bin.

        A str.
        """
        return self._get_option_from_main_section(self.X_LOADER_PACKAGE_KEY)

    @property
    def x_loader_file(self):
        """The x-loader bin file that will be unpacked from the x-loader package.

        A str.
        """
        return self._get_option_from_main_section(self.X_LOADER_FILE_KEY)

    @property
    def vmlinuz(self):
        """The path to the vmlinuz kernel.

        A str.
        """
        return self._get_option_from_main_section(self.VMLINUZ_KEY)

    @property
    def initrd(self):
        """The path to initrd

        A str.
        """
        return self._get_option_from_main_section(self.INITRD_KEY)

    @property
    def dtb_file(self):
        """The path to the device tree binary.

        A str.
        """
        return self._get_option_from_main_section(self.DTB_FILE_KEY)

    @property
    def architectures(self):
        """The architectures to build the hwpack for.

        A list of str.
        """
        return self._get_list_from_main_section(self.ARCHITECTURES_KEY)

    @property
    def assume_installed(self):
        """The packages that the hwpack should assume as already installed.

        A list of str.
        """
        return self._get_list_from_main_section(self.ASSUME_INSTALLED_KEY)

    @property
    def sources(self):
        """The sources defined in the configuration.

        A dict mapping source identifiers to sources entries.
        """
        sources = {}
        sections = self.parser.sections()
        for section_name in sections:
            if section_name == self.MAIN_SECTION:
                continue
            sources[section_name] = self.parser.get(
                section_name, self.SOURCES_ENTRY_KEY)
        return sources

    def _validate_format(self):
        format = self.format
        if not format:
            raise HwpackConfigError("Empty value for format")
        if not format.is_supported:
            raise HwpackConfigError("Format version '%s' is not supported." % \
                                        format)

    def _assert_matches_pattern(self, regex, config_item, error_message):
            if re.match(regex, config_item) is None:
                raise HwpackConfigError(error_message)

    def _validate_name(self):
        try:
            name = self.name
            if not name:
                raise HwpackConfigError("Empty value for name")
            self._assert_matches_pattern(
                self.NAME_REGEX, name, "Invalid name: %s" % name)
        except ConfigParser.NoOptionError:
            raise HwpackConfigError(
                "No name in the [%s] section" % self.MAIN_SECTION)

    def _validate_u_boot_file(self):
        u_boot_file = self.u_boot_file
        if u_boot_file is not None:
            self._assert_matches_pattern(
                self.PATH_REGEX, u_boot_file, "Invalid path: %s" % u_boot_file)

    def _validate_x_loader_file(self):
        x_loader_file = self.x_loader_file
        if x_loader_file is not None:
            self._assert_matches_pattern(
                self.PATH_REGEX, x_loader_file, "Invalid path: %s" % \
                    x_loader_file)

    def _validate_vmlinuz(self):
        vmlinuz = self.vmlinuz
        if not vmlinuz:
            raise HwpackConfigError("No kernel_file in the [%s] section" % \
                                        self.MAIN_SECTION)
        self._assert_matches_pattern(
            self.PATH_REGEX, vmlinuz, "Invalid path: %s" % vmlinuz)

    def _validate_initrd(self):
        initrd = self.initrd
        if not initrd:
            raise HwpackConfigError("No initrd_file in the [%s] section" % \
                                        self.MAIN_SECTION)
        self._assert_matches_pattern(
            self.PATH_REGEX, initrd, "Invalid path: %s" % initrd)

    def _validate_dtb_file(self):
        dtb_file = self.dtb_file
        if dtb_file is not None:
            self._assert_matches_pattern(
                self.PATH_REGEX, dtb_file, "Invalid path: %s" % dtb_file)
        
    def _validate_extra_boot_options(self):
        # Optional and tricky to determine a valid pattern.
        pass

    def _validate_extra_serial_opts(self):
        # Optional and tricky to determine a valid pattern.
        pass

    def _validate_boot_script(self):
        boot_script = self.boot_script
        if not boot_script:
            raise HwpackConfigError(
                "No boot_script in the [%s] section" % \
                    self.MAIN_SECTION)
        else:
            self._assert_matches_pattern(
                self.PATH_REGEX, boot_script, "Invalid path: %s" % boot_script)

    def _validate_serial_tty(self):
        serial_tty = self.serial_tty
        if serial_tty is None:
            return
        if len(serial_tty) < 4 or serial_tty[:3] != 'tty':
            raise HwpackConfigError("Invalid serial tty: %s" % serial_tty)

    def _validate_addr(self, addr):
        return re.match(r"^0x[a-fA-F0-9]{8}$", addr)

    def _validate_kernel_addr(self):
        addr = self.kernel_addr
        if addr is None:
            return
        if not self._validate_addr(addr):
            raise HwpackConfigError("Invalid kernel address: %s" % addr)

    def _validate_initrd_addr(self):
        addr = self.initrd_addr
        if addr is None:
            return
        if not self._validate_addr(addr):
            raise HwpackConfigError("Invalid initrd address: %s" % addr)

    def _validate_load_addr(self):
        addr = self.load_addr
        if addr is None:
            return
        if not self._validate_addr(addr):
            raise HwpackConfigError("Invalid load address: %s" % addr)

    def _validate_dtb_addr(self):
        addr = self.dtb_addr
        if addr is None:
            return
        if not self._validate_addr(addr):
            raise HwpackConfigError("Invalid dtb address: %s" % addr)

    def _validate_wired_interfaces(self):
        pass

    def _validate_wireless_interfaces(self):
        pass

    def _validate_partition_layout(self):
        if self.partition_layout not in self.DEFINED_PARTITION_LAYOUTS:
            raise HwpackConfigError(
                "Undefined partition layout %s in the [%s] section. "
                "Valid partition layouts are %s."
                % (self.partition_layout, self.MAIN_SECTION,
                   ", ".join(self.DEFINED_PARTITION_LAYOUTS)))

    def _validate_mmc_id(self):
        mmc_id = self.mmc_id
        if mmc_id is None:
            return
        try:
            int(mmc_id)
        except:
            raise HwpackConfigError("Invalid mmc id %s" % (mmc_id))

    def _validate_root_min_size(self):
        root_min_size = self.root_min_size
        if root_min_size is None:
            return
        try:
            assert int(root_min_size) > 0
        except:
            raise HwpackConfigError(
                "Invalid root min size %s" % (root_min_size))

    def _validate_boot_min_size(self):
        boot_min_size = self.boot_min_size
        if boot_min_size is None:
            return
        try:
            assert int(boot_min_size) > 0
        except:
            raise HwpackConfigError(
                "Invalid boot min size %s" % (boot_min_size))

    def _validate_loader_min_size(self):
        loader_min_size = self.loader_min_size
        if loader_min_size is None:
            return
        try:
            assert int(loader_min_size) > 0
        except:
            raise HwpackConfigError(
                "Invalid loader min size %s" % (loader_min_size))

    def _validate_include_debs(self):
        try:
            self.include_debs
        except ValueError:
            raise HwpackConfigError(
                "Invalid value for include-debs: %s"
                % self.parser.get("hwpack", "include-debs"))

    def _validate_uboot_in_boot_part(self):
        uboot_in_boot_part = self.uboot_in_boot_part
        if string.lower(uboot_in_boot_part) not in ['yes', 'no']:
            raise HwpackConfigError(
                "Invalid value for u_boot_in_boot_part: %s"
                % self.parser.get("hwpack", "u_boot_in_boot_part"))

    def _validate_support(self):
        support = self.support
        if support not in (None, "supported", "unsupported"):
            raise HwpackConfigError(
                "Invalid value for support: %s" % support)

    def _validate_packages(self):
        packages = self.packages
        if not packages:
            raise HwpackConfigError(
                "No %s in the [%s] section"
                % (self.PACKAGES_KEY, self.MAIN_SECTION))
        for package in packages:
            self._assert_matches_pattern(
                self.PACKAGE_REGEX, package, "Invalid value in %s in the " \
                    "[%s] section: %s" % (self.PACKAGES_KEY, self.MAIN_SECTION,
                                          package))

    def _validate_u_boot_package(self):
        u_boot_package = self.u_boot_package
        if u_boot_package is not None:
            self._assert_matches_pattern(
                self.PACKAGE_REGEX, u_boot_package, "Invalid value in %s in " \
                    "the [%s] section: %s" % (self.U_BOOT_PACKAGE_KEY,
                                              self.MAIN_SECTION, u_boot_package))

    def _validate_x_loader_package(self):
        x_loader_package = self.x_loader_package
        if x_loader_package is not None:
            self._assert_matches_pattern(
                self.PACKAGE_REGEX, x_loader_package, "Invalid value in %s in " \
                    "the [%s] section: %s" % (self.X_LOADER_PACKAGE_KEY,
                                              self.MAIN_SECTION,
                                              x_loader_package))

    def _validate_architectures(self):
        architectures = self.architectures
        if not architectures:
            raise HwpackConfigError(
                "No %s in the [%s] section"
                % (self.ARCHITECTURES_KEY, self.MAIN_SECTION))

    def _validate_assume_installed(self):
        assume_installed = self.assume_installed
        for package in assume_installed:
            self._assert_matches_pattern(
                self.PACKAGE_REGEX, package, "Invalid value in %s in the " \
                    "[%s] section: %s" % (self.ASSUME_INSTALLED_KEY,
                                          self.MAIN_SECTION, package))

    def _validate_section_sources_entry(self, section_name):
        try:
            sources_entry = self.parser.get(
                section_name, self.SOURCES_ENTRY_KEY)
            if not sources_entry:
                raise HwpackConfigError(
                    "The %s in the [%s] section is missing the URI"
                    % (self.SOURCES_ENTRY_KEY, section_name))
            if len(sources_entry.split(" ", 1)) < 2:
                raise HwpackConfigError(
                    "The %s in the [%s] section is missing the distribution"
                    % (self.SOURCES_ENTRY_KEY, section_name))
            if sources_entry.startswith("deb"):
                raise HwpackConfigError(
                    "The %s in the [%s] section shouldn't start with 'deb'"
                    % (self.SOURCES_ENTRY_KEY, section_name))
        except ConfigParser.NoOptionError:
            raise HwpackConfigError(
                "No %s in the [%s] section"
                % (self.SOURCES_ENTRY_KEY, section_name))

    def _validate_section(self, section_name):
        self._validate_section_sources_entry(section_name)

    def _validate_sections(self):
        sections = self.parser.sections()
        found = False
        for section_name in sections:
            if section_name == self.MAIN_SECTION:
                continue
            self._validate_section(section_name)
            found = True
        if not found:
            raise HwpackConfigError(
                "No sections other than [%s]" % self.MAIN_SECTION)
