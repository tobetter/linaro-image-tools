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
from operator import attrgetter
import re
import string
import yaml

from linaro_image_tools.hwpack.hardwarepack_format import (
    HardwarePackFormatV1,
    HardwarePackFormatV2,
    HardwarePackFormatV3,
    )


class HwpackConfigError(Exception):
    pass


class Config(object):
    """Encapsulation of a hwpack-create configuration."""
    translate_v2_to_v3 = {}

    MAIN_SECTION = "hwpack"
    NAME_KEY = "name"
    NAME_REGEX = r"[a-z0-9][a-z0-9+\-.]+$"
    INCLUDE_DEBS_KEY = "include-debs"
    SUPPORT_KEY = "support"
    SOURCES_ENTRY_KEY = "sources-entry"
    PACKAGES_KEY = "packages"
    PACKAGE_REGEX = NAME_REGEX
    PATH_REGEX = r"\w[\w+\-./_]+$"
    GLOB_REGEX = r"[\w+\-./_\*]+$"
    ORIGIN_KEY = "origin"
    MAINTAINER_KEY = "maintainer"
    ARCHITECTURES_KEY = "architectures"
    ASSUME_INSTALLED_KEY = "assume-installed"
    U_BOOT_PACKAGE_KEY = "u_boot_package"
    translate_v2_to_v3[U_BOOT_PACKAGE_KEY] = "package"
    U_BOOT_FILE_KEY = "u_boot_file"
    translate_v2_to_v3[U_BOOT_FILE_KEY] = "file"
    SPL_FILE_KEY = "spl_file"
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
    LOADER_START_KEY = "loader_start"
    SPL_PACKAGE_KEY = "spl_package"
    VMLINUZ_KEY = "kernel_file"
    INITRD_KEY = "initrd_file"
    DTB_FILE_KEY = "dtb_file"
    EXTRA_BOOT_OPTIONS_KEY = 'extra_boot_options'
    BOOT_SCRIPT_KEY = 'boot_script'
    UBOOT_IN_BOOT_PART_KEY = 'u_boot_in_boot_part'
    translate_v2_to_v3[UBOOT_IN_BOOT_PART_KEY] = "in_boot_part"
    UBOOT_DD_KEY = 'u_boot_dd'
    translate_v2_to_v3[UBOOT_DD_KEY] = "dd"
    SPL_IN_BOOT_PART_KEY = 'spl_in_boot_part'
    SPL_DD_KEY = 'spl_dd'
    ENV_DD_KEY = 'env_dd'
    EXTRA_SERIAL_OPTS_KEY = 'extra_serial_options'
    SNOWBALL_STARTUP_FILES_CONFIG_KEY = 'snowball_startup_files_config'
    SAMSUNG_BL1_START_KEY = 'samsung_bl1_start'
    SAMSUNG_BL1_LEN_KEY = 'samsung_bl1_len'
    SAMSUNG_ENV_LEN_KEY = 'samsung_env_len'
    SAMSUNG_BL2_LEN_KEY = 'samsung_bl2_len'

    DEFINED_PARTITION_LAYOUTS = [
        'bootfs16_rootfs',
        'bootfs_rootfs',
        'reserved_bootfs_rootfs',
        ]

    def __init__(self, fp, bootloader=None, board=None):
        """Create a Config.

        :param fp: a file-like object containing the configuration.
        """
        obfuscated_e = None
        try:
            self.parser = ConfigParser.RawConfigParser()
            self.parser.readfp(fp)
        except ConfigParser.Error, e:
            obfuscated_e = re.sub(r"([^ ]https://).+?(@)", r"\1***\2", str(e))

        if obfuscated_e:
            try:
                fp.seek(0)
                self.parser = yaml.safe_load(fp)
                self.set_board(board)
                self.set_bootloader(bootloader)
            except yaml.YAMLError, e:
                obfuscated_e = re.sub(r"([^ ]https://).+?(@)",
                                      r"\1***\2", str(e))
            else:
                obfuscated_e = None

        if obfuscated_e:
            raise ConfigParser.Error(obfuscated_e)

    def set_bootloader(self, bootloader):
        if not bootloader:
            # Auto-detect bootloader. If there is a single bootloader specified
            # then use it, else, error.
            bootloaders = self.bootloaders
            if isinstance(bootloaders, dict):
                # We have a list of bootloaders in the expected format
                bootloaders = bootloaders.keys()
                if len(bootloaders) == 1:
                    bootloader = bootloaders[0]

        self.bootloader = bootloader

    def set_board(self, board):
        self.board = board

    def validate(self):
        """Check that this configuration follows the schema.

        :raises HwpackConfigError: if it does not.
        """
        if isinstance(self.parser, ConfigParser.RawConfigParser):
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
            self._validate_boot_min_size()
            self._validate_root_min_size()
            self._validate_loader_min_size()
            self._validate_loader_start()
            self._validate_spl_package()
            self._validate_spl_file()
            self._validate_vmlinuz()
            self._validate_initrd()
            self._validate_dtb_file()
            self._validate_mmc_id()
            self._validate_extra_boot_options()
            self._validate_boot_script()
            self._validate_uboot_in_boot_part()
            self._validate_uboot_dd()
            self._validate_spl_in_boot_part()
            self._validate_spl_dd()
            self._validate_env_dd()
            self._validate_extra_serial_opts()
            self._validate_snowball_startup_files_config()
            self._validate_samsung_bl1_start()
            self._validate_samsung_bl1_len()
            self._validate_samsung_env_len()
            self._validate_samsung_bl2_len()

        self._validate_sources()

    @property
    def format(self):
        """The format of the hardware pack. A subclass of HardwarePackFormat.
        """
        if isinstance(self.parser, ConfigParser.RawConfigParser):
            try:
                format_string = self.parser.get(self.MAIN_SECTION,
                                                self.FORMAT_KEY)
            except (ConfigParser.NoOptionError, ConfigParser.NoSectionError):
                # Default to 1.0 to aviod breaking existing hwpack files.
                # When this code no longer supports 1.0, it effectively makes
                # explicitly specifying format in hwpack files mandatory.
                format_string = "1.0"
        else:
            format_string = self.parser.get(self.FORMAT_KEY)

        if format_string == '1.0':
            return HardwarePackFormatV1()
        elif format_string == '2.0':
            return HardwarePackFormatV2()
        elif format_string == 3.0 or format_string == '3.0':
            return HardwarePackFormatV3()
        else:
            raise HwpackConfigError("Format version '%s' is not supported." %
                                        format_string)

    @property
    def name(self):
        """The name of the hardware pack. A str."""
        return self._get_option(self.NAME_KEY)

    @property
    def include_debs(self):
        """Whether the hardware pack should contain .debs. A bool."""
        try:
            if self._get_option(self.INCLUDE_DEBS_KEY) == None:
                return True
            try:
                return self._get_option_bool(self.INCLUDE_DEBS_KEY)
            except ValueError as e:
                raise HwpackConfigError("Invalid value for include-debs: %s" %
                                        e)
        except ConfigParser.NoOptionError:
            return True

    @property
    def bootloaders(self):
        return self._get_option('bootloaders')

    @property
    def uboot_in_boot_part(self):
        """Whether uboot binary should be put in the boot partition. A str."""
        return self._get_bootloader_option(self.UBOOT_IN_BOOT_PART_KEY)

    @property
    def uboot_dd(self):
        """If the uboot binary should be dd:d to the boot partition
        this field specifies the offset. An int."""
        return self._get_bootloader_option(self.UBOOT_DD_KEY)

    @property
    def spl_in_boot_part(self):
        """Whether spl binary should be put in the boot partition. A str."""
        return self._get_bootloader_option(self.SPL_IN_BOOT_PART_KEY)

    @property
    def spl_dd(self):
        """If the spl binary should be dd:d to the boot partition
        this field specifies the offset. An int."""
        return self._get_bootloader_option(self.SPL_DD_KEY)

    @property
    def env_dd(self):
        """If the env should be dd:d to the boot partition. 'Yes' or 'No'."""
        return self._get_bootloader_option(self.ENV_DD_KEY)

    def _get_option_bool(self, key):
        """Gets a boolean value from the key."""
        if self.format.format_as_string == '3.0':
            value = self._get_option(key, convert_to="disable")
            if isinstance(value, bool):
                return value
            else:
                raise ValueError(value)
        else:
            try:
                return self.parser.getboolean(self.MAIN_SECTION, key)
            except ConfigParser.NoOptionError:
                return None

    def _get_bootloader_option(self, key, join_list_with=False,
                               convert_to=None):
        """Get an option inside the current bootloader section/"""
        if self._is_v3:
            if not self.bootloader:
                raise ValueError("bootloader not set.")
            if not isinstance(key, list):
                keys = [key]
            keys = ['bootloaders', self.bootloader] + keys
        else:
            keys = key

        return self._get_option(keys, join_list_with, convert_to)

    def _yes_no(self, value):
        """Convert value, treated as boolean, to string "yes" or "no"."""
        if value:
            return "yes"
        else:
            return "no"

    def _addr(self, value):
        """Convert value to 8 character hex string"""
        return "0x%08x" % value

    def _v2_key_to_v3(self, key):
        """Convert V2 key to a V3 key"""
        if key in self.translate_v2_to_v3:
            key = self.translate_v2_to_v3[key]
        return key

    def _get_v3_option(self, keys):
        """Find value in config dictionary based on supplied list (keys)."""
        result = self.parser
        for key in keys:
            key = self._v2_key_to_v3(key)
            try:
                result = result.get(key)
                if result == None:  # False is a valid boolean value...
                    return None
            except ConfigParser.NoOptionError:
                return None
        return result

    def get_option(self, name):
        """Return the value of an attribute by name.

        Used when you can't use a property.
        """
        return attrgetter(name)(self)

    def _get_option(self, key, join_list_with=False, convert_to=None):
        """Return value for the given key. Precedence to board specific values.

        :param key: the key to return the value for.
        :type key: str.
        :param join_list_with: Used to convert lists to strings.
        :type join_list_with: str
        :param convert_to: Used to convert stored value to another type.
        :type convert_to: type or function.
        :return: the value for that key, or None if the key is not present
            or the value is empty.
        :rtype: str or None.
        """
        if self.format.format_as_string == "3.0":
            if not isinstance(key, list):
                keys = [key]
            else:
                keys = key

            result = None  # Just mark result as not set yet...

            # If board is set, search board specific keys first
            if self.board:
                result = self._get_v3_option(["boards", self.board] + keys)

            # If a board specific value isn't found, look for a global one
            if result == None:
                result = self._get_v3_option(keys)

            # If no value is found, bail early (return None)
            if result == None:
                return None

            # <v3 compatibility: Lists of items can be converted to strings
            if join_list_with and isinstance(result, list):
                result = join_list_with.join(result)

            # <v3 compatibility:
            # To aid code that is trying to keep the format of results the
            # same as before, we have some type conversions. By default
            # booleans are "yes" or "no", integers are converted to
            # strings.
            if not convert_to:
                if isinstance(result, int):
                    if isinstance(result, bool):
                        convert_to = self._yes_no
                    else:
                        convert_to = str

            if convert_to and convert_to != "disable":
                if isinstance(result, list):
                    new_list = []
                    for item in result:
                        new_list = convert_to(item)
                    result = new_list
                else:
                    result = convert_to(result)

            return result
        else:
            try:
                result = self.parser.get(self.MAIN_SECTION, key)
                if not result:
                    return None
                return result
            except (ConfigParser.NoOptionError, ConfigParser.NoSectionError):
                return None

    @property
    def serial_tty(self):
        """/dev device name of the serial console for this kernel

        A str.
        """
        return self._get_option(self.SERIAL_TTY_KEY)

    @property
    def extra_boot_options(self):
        """Extra boot arg options.

        A str.
        """
        return self._get_bootloader_option(self.EXTRA_BOOT_OPTIONS_KEY,
                                           join_list_with=" ")

    @property
    def extra_serial_opts(self):
        """Extra serial options.

        A str.
        """
        return self._get_option(self.EXTRA_SERIAL_OPTS_KEY, join_list_with=" ")

    @property
    def boot_script(self):
        """File name of the target boot script.

        A str.
        """
        return self._get_option(self.BOOT_SCRIPT_KEY)

    @property
    def snowball_startup_files_config(self):
        """File name of the snowball startfiles config file.

        A str.
        """
        return self._get_option(self.SNOWBALL_STARTUP_FILES_CONFIG_KEY)

    @property
    def kernel_addr(self):
        """address where u-boot should load the kernel

        An int.
        """
        return self._get_option(self.KERNEL_ADDR_KEY, convert_to=self._addr)

    @property
    def initrd_addr(self):
        """address where u-boot should load the kernel

        An int.
        """
        return self._get_option(self.INITRD_ADDR_KEY, convert_to=self._addr)

    @property
    def load_addr(self):
        """address for uImage generation

        An int.
        """
        return self._get_option(self.LOAD_ADDR_KEY, convert_to=self._addr)

    @property
    def dtb_addr(self):
        """address for dtb image generation

        An int.
        """
        return self._get_option(self.DTB_ADDR_KEY, convert_to=self._addr)

    @property
    def wired_interfaces(self):
        """The interfaces for wired networks

        A list of str.
        """
        return self._get_list(self.WIRED_INTERFACES_KEY)

    @property
    def wireless_interfaces(self):
        """The interfaces for wireless networks

        A list of str.
        """
        return self._get_list(self.WIRELESS_INTERFACES_KEY)

    @property
    def partition_layout(self):
        """bootfs16_rootfs, bootfs_rootfs and reserved_bootfs_rootfs;
        controls what kind of SD card partition layout we should use when
        writing images

        A str.
        """
        return self._get_option(self.PARTITION_LAYOUT_KEY, join_list_with=" ")

    @property
    def mmc_id(self):
        """which MMC drive contains the boot filesystem

        An int.
        """
        return self._get_option(self.MMC_ID_KEY)

    @property
    def root_min_size(self):
        """Minimum size of the root partition, in MiB.

        An int.
        """
        return self._get_option(self.ROOT_MIN_SIZE_KEY)

    @property
    def boot_min_size(self):
        """Minimum size of the boot partition, in MiB.

        An int.
        """
        return self._get_option(self.BOOT_MIN_SIZE_KEY)

    @property
    def loader_min_size(self):
        """Minimum size of the optional loader partition, in MiB.

        An int.
        """
        return self._get_option(self.LOADER_MIN_SIZE_KEY)

    @property
    def loader_start(self):
        """Start of loader partition. If left out, defaults to 1.

        An int.
        """
        return self._get_option(self.LOADER_START_KEY)

    @property
    def origin(self):
        """The origin that should be recorded in the hwpack.

        A str or None if no origin should be recorded.
        """
        return self._get_option(self.ORIGIN_KEY)

    @property
    def maintainer(self):
        """The maintainer that should be recorded in the hwpack.

        A str or None if not maintainer should be recorded.
        """
        return self._get_option(self.MAINTAINER_KEY)

    @property
    def support(self):
        """The support level that should be recorded in the hwpack.

        A str or None if no support level should be recorded.
        """
        return self._get_option(self.SUPPORT_KEY)

    def _get_list(self, key):
        values = self._get_option(key)
        if values is None:
            return []

        if not isinstance(values, list):
            values = re.split("\s+", values)

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
        return self._get_list(self.PACKAGES_KEY)

    @property
    def u_boot_package(self):
        """The u-boot package that contains the u-boot bin.

        A str.
        """
        return self._get_bootloader_option(self.U_BOOT_PACKAGE_KEY)

    @property
    def u_boot_file(self):
        """The u-boot bin file that will be unpacked from the u-boot package.

        A str.
        """
        return self._get_bootloader_option(self.U_BOOT_FILE_KEY)

    @property
    def spl_file(self):
        """The spl bin file that will be unpacked from the u-boot package.

        A str.
        """
        return self._get_bootloader_option(self.SPL_FILE_KEY)

    @property
    def spl_package(self):
        """The spl package that contains the spl bin.

        A str.
        """
        return self._get_bootloader_option(self.SPL_PACKAGE_KEY)

    @property
    def vmlinuz(self):
        """The path to the vmlinuz kernel.

        A str.
        """
        return self._get_option(self.VMLINUZ_KEY)

    @property
    def initrd(self):
        """The path to initrd

        A str.
        """
        return self._get_option(self.INITRD_KEY)

    @property
    def dtb_file(self):
        """The path to the device tree binary.

        A str.
        """
        return self._get_option(self.DTB_FILE_KEY)

    @property
    def samsung_bl1_start(self):
        """BL1 start offset for Samsung boards.

        A str.
        """
        return self._get_option(self.SAMSUNG_BL1_START_KEY)

    @property
    def samsung_bl1_len(self):
        """BL1 length for Samsung boards.

        A str.
        """
        return self._get_option(self.SAMSUNG_BL1_LEN_KEY)

    @property
    def samsung_env_len(self):
        """Env length for Samsung boards.

        A str.
        """
        return self._get_option(self.SAMSUNG_ENV_LEN_KEY)

    @property
    def samsung_bl2_len(self):
        """BL2 length for Samsung boards.

        A str.
        """
        return self._get_option(self.SAMSUNG_BL2_LEN_KEY)

    @property
    def architectures(self):
        """The architectures to build the hwpack for.

        A list of str.
        """
        return self._get_list(self.ARCHITECTURES_KEY)

    @property
    def assume_installed(self):
        """The packages that the hwpack should assume as already installed.

        A list of str.
        """
        return self._get_list(self.ASSUME_INSTALLED_KEY)

    @property
    def sources(self):
        """The sources defined in the configuration.

        A dict mapping source identifiers to sources entries.
        """
        if self._is_v3:
            sources = self.parser.get("sources")
        else:
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

    def _validate_spl_file(self):
        spl_file = self.spl_file
        if spl_file is not None:
            self._assert_matches_pattern(
                self.PATH_REGEX, spl_file, "Invalid path: %s" % spl_file)

    def _validate_vmlinuz(self):
        vmlinuz = self.vmlinuz
        if not vmlinuz:
            raise HwpackConfigError(self._not_found_message("kernel_file"))
        self._assert_matches_pattern(
            self.GLOB_REGEX, vmlinuz, "Invalid path: %s" % vmlinuz)

    def _validate_initrd(self):
        initrd = self.initrd
        if not initrd:
            raise HwpackConfigError(self._not_found_message("initrd_file"))
        self._assert_matches_pattern(
            self.GLOB_REGEX, initrd, "Invalid path: %s" % initrd)

    def _not_found_message(self, thing, v2_section=None):
        if self._is_v3:
            return "No " + thing + " found in the metadata"
        else:
            if not v2_section:
                v2_section = self.MAIN_SECTION
            return "No " + thing + " in the [" + v2_section + "] section"

    def _validate_dtb_file(self):
        dtb_file = self.dtb_file
        if dtb_file is not None:
            self._assert_matches_pattern(
                self.GLOB_REGEX, dtb_file, "Invalid path: %s" % dtb_file)

    def _validate_extra_boot_options(self):
        # Optional and tricky to determine a valid pattern.
        pass

    def _validate_extra_serial_opts(self):
        # Optional and tricky to determine a valid pattern.
        pass

    def _validate_boot_script(self):
        boot_script = self.boot_script
        if not boot_script:
            return
        else:
            self._assert_matches_pattern(
                self.PATH_REGEX, boot_script, "Invalid path: %s" % boot_script)

    def _validate_snowball_startup_files_config(self):
        snowball_startup_files_config = self.snowball_startup_files_config
        if snowball_startup_files_config is not None:
            self._assert_matches_pattern(
                self.PATH_REGEX, snowball_startup_files_config,
                "Invalid path: %s" % snowball_startup_files_config)

    def _validate_serial_tty(self):
        serial_tty = self.serial_tty
        if serial_tty is None:
            return
        if len(serial_tty) < 4 or serial_tty[:3] != 'tty':
            raise HwpackConfigError("Invalid serial tty: %s" % serial_tty)

    def _validate_addr(self, key):
        """Validate the address for the given key.
        Assumptions:
            1. key name is of the form name_addr
            2. property name matches key name

        Currently these assumptions are met and it seems reasonable to place
        these restrictions on future code.
        """
        name = re.sub("_addr", "", key)

        try:
            addr = attrgetter(key)(self)
        except TypeError:
            raise HwpackConfigError("Invalid %s address: %s" %
                                    (name, self._get_option(key)))

        if addr == None:
            return

        if not re.match(r"^0x[a-fA-F0-9]{8}$", addr):
            raise HwpackConfigError("Invalid %s address: %s" % (name, addr))

    def _validate_kernel_addr(self):
        self._validate_addr(self.KERNEL_ADDR_KEY)

    def _validate_initrd_addr(self):
        self._validate_addr(self.INITRD_ADDR_KEY)

    def _validate_load_addr(self):
        self._validate_addr(self.LOAD_ADDR_KEY)

    def _validate_dtb_addr(self):
        self._validate_addr(self.DTB_ADDR_KEY)

    def _validate_wired_interfaces(self):
        pass

    def _validate_wireless_interfaces(self):
        pass

    def _validate_partition_layout(self):
        if self.partition_layout not in self.DEFINED_PARTITION_LAYOUTS:
            if self._is_v3:
                message = ("Undefined partition layout %s. "
                           "Valid partition layouts are %s." %
                           (self.partition_layout,
                            ", ".join(self.DEFINED_PARTITION_LAYOUTS)))
            else:
                message = ("Undefined partition layout %s in the [%s] section."
                           " Valid partition layouts are %s." %
                           (self.partition_layout, self.MAIN_SECTION,
                            ", ".join(self.DEFINED_PARTITION_LAYOUTS)))

            raise HwpackConfigError(message)

    def _validate_mmc_id(self):
        mmc_id = self.mmc_id
        if not mmc_id:
            raise HwpackConfigError(
                "No mmc_id in the [%s] section" % \
                    self.MAIN_SECTION)
        else:
            self._assert_matches_pattern(
                r"[0-9]:[0-9]", mmc_id, "Invalid mmc_id %s" % mmc_id)

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

    def _validate_loader_start(self):
        loader_start = self.loader_start
        if loader_start is None:
            return
        try:
            assert int(loader_start) > 0
        except:
            raise HwpackConfigError(
                "Invalid loader start %s" % (loader_start))

    def _validate_include_debs(self):
        try:
            self.include_debs
        except ValueError:
            raise HwpackConfigError(
                "Invalid value for include-debs: %s"
                % self.include_debs)

    @property
    def _is_v3(self):
        """Checks if format is 3.0."""
        return self.format.format_as_string == '3.0'

    def _validate_bool(self, value):
        """Checks if a value is boolean or not, represented by "yes" or "no".
        """
        if not isinstance(value, str):
            return False
        return string.lower(value) in ['yes', 'no']

    def _validate_uboot_in_boot_part(self):
        if not self._validate_bool(self.uboot_in_boot_part):
            raise HwpackConfigError(
                "Invalid value for u_boot_in_boot_part: %s"
                % self.uboot_in_boot_part)

    def _validate_spl_in_boot_part(self):
        spl_in_boot_part = self.spl_in_boot_part
        if spl_in_boot_part is None:
            return
        if string.lower(spl_in_boot_part) not in ['yes', 'no']:
            raise HwpackConfigError(
                "Invalid value for spl_in_boot_part: %s"
                % self.spl_in_boot_part)

    def _validate_env_dd(self):
        env_dd = self.env_dd
        if env_dd is None:
            return
        if string.lower(env_dd) not in ['yes', 'no']:
            raise HwpackConfigError(
                "Invalid value for env_dd: %s"
                % self.env_dd)

    def _validate_uboot_dd(self):
        uboot_dd = self.uboot_dd
        if uboot_dd is None:
            return
        try:
            assert int(uboot_dd) > 0
        except:
            raise HwpackConfigError(
                "Invalid uboot_dd %s" % (uboot_dd))

    def _validate_spl_dd(self):
        spl_dd = self.spl_dd
        if spl_dd is None:
            return
        try:
            assert int(spl_dd) > 0
        except:
            raise HwpackConfigError(
                "Invalid spl_dd %s" % (spl_dd))

    def _validate_support(self):
        support = self.support
        if support not in (None, "supported", "unsupported"):
            raise HwpackConfigError(
                "Invalid value for support: %s" % support)

    def _invalid_package_message(self, package_name, section_name, value):
        if self._is_v3:
            message = ("Invalid value in %s in the metadata: %s" %
                       (package_name, value))
        else:
            message = ("Invalid value in %s in the [%s] section: %s" %
                       (package_name, section_name, value))
        return message

    def _validate_packages(self):
        packages = self.packages
        if not packages:
            raise HwpackConfigError(self._not_found_message(self.PACKAGES_KEY))
        for package in packages:
            self._assert_matches_pattern(
                self.PACKAGE_REGEX, package,
                self._invalid_package_message(
                    self.PACKAGES_KEY, self.MAIN_SECTION, package))

    def _validate_u_boot_package(self):
        u_boot_package = self.u_boot_package
        if u_boot_package is not None:
            self._assert_matches_pattern(
                self.PACKAGE_REGEX, u_boot_package,
                self._invalid_package_message(
                    self.U_BOOT_PACKAGE_KEY, self.MAIN_SECTION,
                    u_boot_package))

    def _validate_spl_package(self):
        spl_package = self.spl_package
        if spl_package is not None:
            self._assert_matches_pattern(
                self.PACKAGE_REGEX, spl_package,
                self._invalid_package_message(self.SPL_PACKAGE_KEY,
                                              self.MAIN_SECTION,
                                              spl_package))

    def _validate_samsung_bl1_start(self):
        samsung_bl1_start = self.samsung_bl1_start
        if samsung_bl1_start is None:
            return
        try:
            assert int(samsung_bl1_start) > 0
        except:
            raise HwpackConfigError(
                "Invalid samsung_bl1_start %s" % (samsung_bl1_start))

    def _validate_samsung_bl1_len(self):
        samsung_bl1_len = self.samsung_bl1_len
        if samsung_bl1_len is None:
            return
        try:
            assert int(samsung_bl1_len) > 0
        except:
            raise HwpackConfigError(
                "Invalid samsung_bl1_len %s" % (samsung_bl1_len))

    def _validate_samsung_env_len(self):
        samsung_env_len = self.samsung_env_len
        if samsung_env_len is None:
            return
        try:
            assert int(samsung_env_len) > 0
        except:
            raise HwpackConfigError(
                "Invalid samsung_env_len %s" % (samsung_env_len))

    def _validate_samsung_bl2_len(self):
        samsung_bl2_len = self.samsung_bl2_len
        if samsung_bl2_len is None:
            return
        try:
            assert int(samsung_bl2_len) > 0
        except:
            raise HwpackConfigError(
                "Invalid samsung_bl2_len %s" % (samsung_bl2_len))

    def _validate_architectures(self):
        architectures = self.architectures
        if not architectures:
            raise HwpackConfigError(
                self._not_found_message(self.ARCHITECTURES_KEY))

    def _validate_assume_installed(self):
        assume_installed = self.assume_installed
        for package in assume_installed:
            self._assert_matches_pattern(
                self.PACKAGE_REGEX, package,
                self._invalid_package_message(self.ASSUME_INSTALLED_KEY,
                                              self.MAIN_SECTION, package))

    def _message_start(self, key, section_name):
        if self._is_v3:
            message = "The %s, %s " % (key, section_name)
        else:
            message = "The %s in the [%s] section " % (key, section_name)
        return message

    def _validate_source(self, section_name):
        if self._is_v3:
            sources_entry = self._get_option(["sources"] + [section_name])
        else:
            try:
                sources_entry = self.parser.get(
                    section_name, self.SOURCES_ENTRY_KEY)
            except ConfigParser.NoOptionError:
                raise HwpackConfigError(
                    "No %s in the [%s] section"
                    % (self.SOURCES_ENTRY_KEY, section_name))

        if not sources_entry:
            raise HwpackConfigError(
                self._message_start(self.SOURCES_ENTRY_KEY, section_name) +
                "is missing the URI")
        if len(sources_entry.split(" ", 1)) < 2:
            raise HwpackConfigError(
                self._message_start(self.SOURCES_ENTRY_KEY, section_name) +
                "is missing the distribution")
        if sources_entry.startswith("deb"):
            raise HwpackConfigError(
                self._message_start(self.SOURCES_ENTRY_KEY, section_name) +
                "shouldn't start with 'deb'")

    def _validate_sources(self):
        if self._is_v3:
            source_dict = self.parser.get("sources")
            if not source_dict:
                return
            if isinstance(source_dict, dict):
                sources = source_dict.keys()
            else:
                raise HwpackConfigError(
                    "The %s in the [%s] section is missing the URI"
                    % (self.SOURCES_ENTRY_KEY, source_dict))
        else:
            sources = self.parser.sections()
        found = False
        for source_name in sources:
            if source_name == self.MAIN_SECTION:
                continue
            self._validate_source(source_name)
            found = True
        if not found:
            raise HwpackConfigError(
                "No sections other than [%s]" % self.MAIN_SECTION)
