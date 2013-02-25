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
import os
import re
import string
import yaml

from linaro_image_tools.hwpack.hardwarepack_format import (
    HardwarePackFormatV1,
    HardwarePackFormatV2,
    HardwarePackFormatV3,
)

from hwpack_fields import (
    ARCHITECTURES_FIELD,
    ARCHITECTURE_FIELD,
    ASSUME_INSTALLED_FIELD,
    BOARDS_FIELD,
    BOOTLOADERS_FIELD,
    BOOT_MIN_SIZE_FIELD,
    BOOT_SCRIPT_FIELD,
    COPY_FILES_FIELD,
    DD_FIELD,
    DTB_ADDR_FIELD,
    DTB_FILE_FIELD,
    DEFAULT_BOOTLOADER,
    DTB_FILES_FIELD,
    ENV_DD_FIELD,
    EXTRA_BOOT_OPTIONS_FIELD,
    EXTRA_SERIAL_OPTIONS_FIELD,
    FILE_FIELD,
    FORMAT_FIELD,
    INCLUDE_DEBS_FIELD,
    IN_BOOT_PART_FIELD,
    INITRD_ADDR_FIELD,
    INITRD_FILE_FIELD,
    KERNEL_ADDR_FIELD,
    KERNEL_FILE_FIELD,
    LOAD_ADDR_FIELD,
    LOADER_MIN_SIZE_FIELD,
    LOADER_START_FIELD,
    MAINTAINER_FIELD,
    MMC_ID_FIELD,
    NAME_FIELD,
    ORIGIN_FIELD,
    PACKAGE_FIELD,
    PACKAGES_FIELD,
    PARTITION_LAYOUT_FIELD,
    ROOT_MIN_SIZE_FIELD,
    SAMSUNG_BL1_LEN_FIELD,
    SAMSUNG_BL1_START_FIELD,
    SAMSUNG_BL2_LEN_FIELD,
    SAMSUNG_BL2_START_FIELD,
    SAMSUNG_ENV_LEN_FIELD,
    SAMSUNG_ENV_START_FIELD,
    SERIAL_TTY_FIELD,
    SNOWBALL_STARTUP_FILES_CONFIG_FIELD,
    SOURCES_FIELD,
    SPL_DD_FIELD,
    SPL_FILE_FIELD,
    SPL_IN_BOOT_PART_FIELD,
    SPL_PACKAGE_FIELD,
    SUPPORT_FIELD,
    WIRED_INTERFACES_FIELD,
    WIRELESS_INTERFACES_FIELD,
    DEFINED_PARTITION_LAYOUTS,
    VERSION_FIELD,
    hwpack_v3_layout,
)

import logging


class HwpackConfigError(Exception):
    pass


class Config(object):
    """Encapsulation of a hwpack-create configuration."""
    translate_v2_to_v3 = {}
    translate_v2_metadata = {}

    MAIN_SECTION = "hwpack"
    NAME_REGEX = r"[a-z0-9][a-z0-9+\-.]+$"
    SOURCES_ENTRY_KEY = "sources-entry"
    PACKAGE_REGEX = NAME_REGEX
    PATH_REGEX = r"\w[\w+\-./_]+$"
    GLOB_REGEX = r"[\w+\-./_\*]+$"
    INCLUDE_DEBS_KEY = "include-debs"
    translate_v2_to_v3[INCLUDE_DEBS_KEY] = INCLUDE_DEBS_FIELD
    translate_v2_metadata[ARCHITECTURES_FIELD] = "ARCHITECTURE"
    ASSUME_INSTALLED_KEY = "assume-installed"
    translate_v2_to_v3[ASSUME_INSTALLED_KEY] = ASSUME_INSTALLED_FIELD
    BOOTLOADER_PACKAGE_KEY = "u_boot_package"
    translate_v2_to_v3[BOOTLOADER_PACKAGE_KEY] = PACKAGE_FIELD
    BOOTLOADER_FILE_KEY = "u_boot_file"
    translate_v2_to_v3[BOOTLOADER_FILE_KEY] = FILE_FIELD
    translate_v2_metadata[BOOTLOADER_FILE_KEY] = "U_BOOT"
    SPL_FILE_KEY = "spl_file"
    translate_v2_metadata[SPL_FILE_KEY] = "SPL"
    BOOTLOADER_IN_BOOT_PART_KEY = 'u_boot_in_boot_part'
    translate_v2_to_v3[BOOTLOADER_IN_BOOT_PART_KEY] = IN_BOOT_PART_FIELD
    BOOTLOADER_DD_KEY = 'u_boot_dd'
    translate_v2_to_v3[BOOTLOADER_DD_KEY] = DD_FIELD
    last_used_keys = []
    board = None

    def __init__(self, fp, bootloader=None, board=None,
                 allow_unset_bootloader=False):
        """Create a Config.

        :param fp: a file-like object containing the configuration.
        :param allow_unset_bootloader: Bool. If you have more than 1 bootloader
          in the config object and don't set which one to use, accessing
          bootloader related parameters will throw an exception. By setting
          this None will be returned instead.
        """
        # This Config class is used in two places:
        # 1. Generating hardware packs
        # 2. Combining a hardware pack with an OS image to create a bootable
        #    disk image.
        #
        # In both cases we are providing a file format independant interface
        # to configuration data to the rest of Linaro Image Tools.
        #
        # In case 1 we want all information to be put in the hardware pack and
        # there is no possibility of picking a booloader (all bootloaders are
        # put in the hardware pack and one is picked later). In this case we
        # don't want to trip up other code by throwing an exception when a
        # bootloader dependant parameter is queried so we return None. In
        # reality this information isn't used, but sometimes gets queried by
        # tests. This flag allows us to keep things simple.
        #
        # In case 2 we may have multiple bootloaders specified, but only one
        # can be used by the OS image so we need to pick one. If a bootloader
        # isn't specified we want to throw an error when a choice would make a
        # difference to what is returned when querying the object.
        #
        # self.allow_unset_bootloader allows for both modes of operation.
        self.logger = logging.getLogger('linaro_image_tools')
        self.allow_unset_bootloader = allow_unset_bootloader
        self.board = board
        self._bootloader = bootloader

        obfuscated_e = None
        obfuscated_yaml_e = ""
        try:
            self.parser = ConfigParser.RawConfigParser()
            self.parser.readfp(fp)
        except ConfigParser.Error, e:
            obfuscated_e = re.sub(r"([^ ]https://).+?(@)", r"\1***\2", str(e))

        if obfuscated_e:
            # obfuscated_e being set indicates that something went wrong.
            # It could be that the input is in fact YAML. Try the YAML
            # parser.
            try:
                fp.seek(0)
                self.parser = yaml.safe_load(fp)
            except yaml.YAMLError, e:
                obfuscated_yaml_e = re.sub(r"([^ ]https://).+?(@)",
                                           r"\1***\2", str(e))
            else:
                # If YAML parsed OK, we don't have an error.
                obfuscated_e = None

        if obfuscated_e:
            # If INI parsing from ConfigParser or YAML parsing failed,
            # print both error messages.
            msg = ("Failed to parse hardware pack configuration. Tried to "
                   "parse as both INI and YAML. INI parsing error:\n" +
                   obfuscated_e + "\n" +
                   "YAML parser error:\n" +
                   obfuscated_yaml_e)
            raise ConfigParser.Error(msg)

    def _get_bootloader(self):
        """Returns the bootloader associated with this config.

        If bootloader is None / empty and there is only one bootloader
        available, use that."""
        bootloader = self._bootloader
        if not bootloader:
            # Auto-detect bootloader. If there is a single bootloader specified
            # then use it, else, error.
            bootloaders = self.bootloaders
            if isinstance(bootloaders, dict):
                # We have a list of bootloaders in the expected format
                bootloaders = bootloaders.keys()
                bootloader = bootloaders[0]
                if len(bootloaders) > 1:
                    # We have more than one bootloader, use 'u_boot'.
                    if DEFAULT_BOOTLOADER in bootloaders:
                        bootloader = DEFAULT_BOOTLOADER
                        self.logger.warning('WARNING: no bootloader specified '
                                            'on the command line. Defaulting '
                                            'to \'%s\'.' % DEFAULT_BOOTLOADER)
                        self.logger.warning('WARNING: specify another '
                                            'bootloader if this is not the '
                                            'correct one to use.')
                    else:
                        self.logger.warning('Default bootloader \'%s\' not '
                                            'found. Will try to use \'%s\'. '
                                            'instead.' % (DEFAULT_BOOTLOADER,
                                                          bootloader))
            # bootloader is None: since we are here, set it so we do not
            # have to go through all the config retrieval again.
            self._bootloader = bootloader
        return bootloader

    def _set_bootloader(self, value):
        """Set bootloader used to look up configuration in bootloader section.
        """
        self._bootloader = value

    bootloader = property(_get_bootloader, _set_bootloader)

    def get_bootloader_list(self):
        if isinstance(self.bootloaders, dict):
            # We have a list of bootloaders in the expected format
            return self.bootloaders.keys()
        return []

    def validate_bootloader_fields(self):
        self._validate_bootloader_package()
        self._validate_bootloader_file()
        self._validate_spl_package()
        self._validate_spl_file()
        self._validate_bootloader_file_in_boot_part()
        self._validate_bootloader_dd()
        self._validate_spl_in_boot_part()
        self._validate_spl_dd()
        self._validate_env_dd()

    def validate(self):
        """Check that this configuration follows the schema.

        :raises HwpackConfigError: if it does not.
        """
        if isinstance(self.parser, ConfigParser.RawConfigParser):
            if not self.parser.has_section(self.MAIN_SECTION):
                raise HwpackConfigError("No [%s] section" % self.MAIN_SECTION)
        self._validate_keys()
        self._validate_format()
        self._validate_name()
        self._validate_include_debs()
        self._validate_support()
        self._validate_packages()
        self._validate_architectures()
        self._validate_assume_installed()

        if self.format.has_v2_fields:
            # Check config for all bootloaders if one isn't specified.
            if not self.bootloader and self._is_v3:
                for bootloader in self.get_bootloader_list():
                    self.bootloader = bootloader
                    self.validate_bootloader_fields()
            else:
                self.validate_bootloader_fields()

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
            self._validate_vmlinuz()
            self._validate_initrd()
            self._validate_dtb_file()
            self._validate_dtb_files()
            self._validate_mmc_id()
            self._validate_extra_boot_options()
            self._validate_boot_script()
            self._validate_extra_serial_options()
            self._validate_snowball_startup_files_config()
            self._validate_samsung_bl1_start()
            self._validate_samsung_bl1_len()
            self._validate_samsung_env_start()
            self._validate_samsung_env_len()
            self._validate_samsung_bl2_start()
            self._validate_samsung_bl2_len()

        self._validate_sources()

    @property
    def format(self):
        """The format of the hardware pack. A subclass of HardwarePackFormat.
        """
        if isinstance(self.parser, ConfigParser.RawConfigParser):
            try:
                format_string = self.parser.get(self.MAIN_SECTION,
                                                FORMAT_FIELD)
            except (ConfigParser.NoOptionError, ConfigParser.NoSectionError):
                # Default to 1.0 to aviod breaking existing hwpack files.
                # When this code no longer supports 1.0, it effectively makes
                # explicitly specifying format in hwpack files mandatory.
                format_string = "1.0"
        else:
            format_string = self.parser.get(FORMAT_FIELD)

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
        return self._get_option(NAME_FIELD)

    @property
    def version(self):
        return self._get_option(VERSION_FIELD)

    @property
    def include_debs(self):
        """Whether the hardware pack should contain .debs. A bool."""
        try:
            if self._get_option(self.INCLUDE_DEBS_KEY) is None:
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
        """Bootloaders available in the hardware pack"""
        return self._get_option(BOOTLOADERS_FIELD)

    @property
    def boards(self):
        """Multiple boards available in the hardware pack."""
        return self._get_option(BOARDS_FIELD)

    @property
    def bootloader_file_in_boot_part(self):
        """Whether uboot binary should be put in the boot partition. A str."""
        return self._get_bootloader_option(self.BOOTLOADER_IN_BOOT_PART_KEY)

    @property
    def bootloader_dd(self):
        """If the uboot binary should be dd:d to the boot partition
        this field specifies the offset. An int."""
        return self._get_bootloader_option(self.BOOTLOADER_DD_KEY)

    @property
    def spl_in_boot_part(self):
        """Whether spl binary should be put in the boot partition. A str."""
        return self._get_bootloader_option(SPL_IN_BOOT_PART_FIELD)

    @property
    def bootloader_copy_files(self):
        """Extra files to copy to boot partition.

        This can be stored in several formats. We always present in a common
        one: {source_package: [{source_file_path: dest_file_path}].
        dest_file_path (in the above example) is always absolute.
        """
        #copy_files:
        #  source_package:
        #   - source_file_path : dest_file_path
        #   - source_file_without_explicit_destination
        #copy_files:
        # - file1
        # - file2: dest_path
        #
        # Note that the list of files is always that - a list.

        copy_files = self._get_bootloader_option(COPY_FILES_FIELD)

        if copy_files is None:
            return None

        if not isinstance(copy_files, dict):
            copy_files = {self.bootloader_package: copy_files}

        for package in copy_files:
            new_list = []
            for value in copy_files[package]:
                if not isinstance(value, dict):
                    dest_path = "/boot"
                    source_path = value
                else:
                    if len(value.keys()) > 1:
                        raise HwpackConfigError("copy_files entry found with"
                                                "more than one destination")
                    source_path = value.keys()[0]
                    dest_path = value[source_path]

                if not dest_path.startswith("/boot"):
                    # Target path should be relative, or start with /boot - we
                    # don't support to copying to anywhere other than /boot.
                    if dest_path[0] == "/":
                        raise HwpackConfigError(
                            "copy_files destinations must"
                            "be relative to /boot or start with /boot.")
                    dest_path = os.path.join("/boot", dest_path)

                new_list.append({source_path: dest_path})
            copy_files[package] = new_list

        return copy_files

    @property
    def spl_dd(self):
        """If the spl binary should be dd:d to the boot partition
        this field specifies the offset. An int."""
        return self._get_bootloader_option(SPL_DD_FIELD)

    @property
    def env_dd(self):
        """If the env should be dd:d to the boot partition. 'Yes' or 'No'."""
        return self._get_bootloader_option(ENV_DD_FIELD)

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
        """Get an option inside the current bootloader section."""
        if self._is_v3:
            if not self.bootloader:
                if self.allow_unset_bootloader:
                    return None
                raise ValueError("bootloader not set.")
            if not isinstance(key, list):
                keys = [key]
            keys = [BOOTLOADERS_FIELD, self.bootloader] + keys
        else:
            keys = key

        return self._get_option(keys, join_list_with, convert_to)

    def _bool_to_string(self, value):
        """Convert value, treated as boolean, to string "yes" or "no"."""
        if value:
            return "yes"
        else:
            return "no"

    def _hex_addrress(self, value):
        """Convert value to 8 character hex string"""
        converted_value = value
        if not isinstance(value, str):
            converted_value = "0x%08x" % value
        return converted_value

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
            if result is not None:
                result = result.get(key, None)
        self.last_used_keys = keys
        return result

    def get_last_used_keys(self):
        """Used so you can work out which boards + boot loader was used.

        Configuration data is stored in a dictionary. This returns a list of
        keys used to traverse into the dictionary the last time an item was
        looked up.

        This can be used to see where a bit of information came from - we
        store data that may be indexed differently depending on which board
        and bootloader are set.
        """
        return self.last_used_keys

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
                result = self._get_v3_option([BOARDS_FIELD, self.board] + keys)

            # If a board specific value isn't found, look for a global one
            if result is None:
                result = self._get_v3_option(keys)

            # If no value is found, bail early (return None)
            if result is None:
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
                        convert_to = self._bool_to_string
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
        else:
            try:
                result = self.parser.get(self.MAIN_SECTION, key)
            except (ConfigParser.NoOptionError, ConfigParser.NoSectionError):
                # May be trying to read a metadata file, which has uppercase
                # keys, some of which need translating to different strings...
                if key in self.translate_v2_metadata:
                    key = self.translate_v2_metadata[key]
                else:
                    key = key.upper()
                try:
                    result = self.parser.get(self.MAIN_SECTION, key)
                except (ConfigParser.NoOptionError,
                        ConfigParser.NoSectionError):
                    result = None
            if not result:
                result = None

        return result

    @property
    def serial_tty(self):
        """/dev device name of the serial console for this kernel

        A str.
        """
        return self._get_option(SERIAL_TTY_FIELD)

    @property
    def extra_boot_options(self):
        """Extra boot arg options.

        A str.
        """
        return self._get_bootloader_option(EXTRA_BOOT_OPTIONS_FIELD,
                                           join_list_with=" ")

    @property
    def extra_serial_options(self):
        """Extra serial options.

        A str.
        """
        return self._get_option(EXTRA_SERIAL_OPTIONS_FIELD, join_list_with=" ")

    @property
    def boot_script(self):
        """File name of the target boot script.

        A str.
        """
        return self._get_option(BOOT_SCRIPT_FIELD)

    @property
    def snowball_startup_files_config(self):
        """File name of the snowball startfiles config file.

        A str.
        """
        return self._get_option(SNOWBALL_STARTUP_FILES_CONFIG_FIELD)

    @property
    def kernel_addr(self):
        """address where u-boot should load the kernel

        An int.
        """
        return self._get_option(KERNEL_ADDR_FIELD,
                                convert_to=self._hex_addrress)

    @property
    def initrd_addr(self):
        """address where u-boot should load the kernel

        An int.
        """
        return self._get_option(INITRD_ADDR_FIELD,
                                convert_to=self._hex_addrress)

    @property
    def load_addr(self):
        """address for uImage generation

        An int.
        """
        return self._get_option(LOAD_ADDR_FIELD, convert_to=self._hex_addrress)

    @property
    def dtb_addr(self):
        """address for dtb image generation

        An int.
        """
        return self._get_option(DTB_ADDR_FIELD, convert_to=self._hex_addrress)

    @property
    def wired_interfaces(self):
        """The interfaces for wired networks

        A list of str.
        """
        return self._get_list(WIRED_INTERFACES_FIELD)

    @property
    def wireless_interfaces(self):
        """The interfaces for wireless networks

        A list of str.
        """
        return self._get_list(WIRELESS_INTERFACES_FIELD)

    @property
    def partition_layout(self):
        """bootfs16_rootfs, bootfs_rootfs and reserved_bootfs_rootfs;
        controls what kind of SD card partition layout we should use when
        writing images

        A str.
        """
        return self._get_option(PARTITION_LAYOUT_FIELD, join_list_with=" ")

    @property
    def mmc_id(self):
        """which MMC drive contains the boot filesystem

        An int.
        """
        return self._get_option(MMC_ID_FIELD)

    @property
    def root_min_size(self):
        """Minimum size of the root partition, in MiB.

        An int.
        """
        return self._get_option(ROOT_MIN_SIZE_FIELD)

    @property
    def boot_min_size(self):
        """Minimum size of the boot partition, in MiB.

        An int.
        """
        return self._get_option(BOOT_MIN_SIZE_FIELD)

    @property
    def loader_min_size(self):
        """Minimum size of the optional loader partition, in MiB.

        An int.
        """
        return self._get_option(LOADER_MIN_SIZE_FIELD)

    @property
    def loader_start(self):
        """Start of loader partition. If left out, defaults to 1.

        An int.
        """
        return self._get_option(LOADER_START_FIELD)

    @property
    def origin(self):
        """The origin that should be recorded in the hwpack.

        A str or None if no origin should be recorded.
        """
        return self._get_option(ORIGIN_FIELD)

    @property
    def maintainer(self):
        """The maintainer that should be recorded in the hwpack.

        A str or None if not maintainer should be recorded.
        """
        return self._get_option(MAINTAINER_FIELD)

    @property
    def support(self):
        """The support level that should be recorded in the hwpack.

        A str or None if no support level should be recorded.
        """
        return self._get_option(SUPPORT_FIELD)

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
        return self._get_list(PACKAGES_FIELD)

    @property
    def bootloader_package(self):
        """The u-boot package that contains the u-boot bin.

        A str.
        """
        return self._get_bootloader_option(self.BOOTLOADER_PACKAGE_KEY)

    @property
    def bootloader_file(self):
        """The u-boot bin file that will be unpacked from the u-boot package.

        A str.
        """
        return self._get_bootloader_option(self.BOOTLOADER_FILE_KEY)

    @property
    def spl_file(self):
        """The spl bin file that will be unpacked from the u-boot package.

        A str.
        """
        return self._get_bootloader_option(SPL_FILE_FIELD)

    @property
    def spl_package(self):
        """The spl package that contains the spl bin.

        A str.
        """
        return self._get_bootloader_option(SPL_PACKAGE_FIELD)

    @property
    def vmlinuz(self):
        """The path to the vmlinuz kernel.

        A str.
        """
        return self._get_option(KERNEL_FILE_FIELD)

    @property
    def initrd(self):
        """The path to initrd

        A str.
        """
        return self._get_option(INITRD_FILE_FIELD)

    @property
    def dtb_file(self):
        """The path to the device tree binary.

        A str.
        """
        return self._get_option(DTB_FILE_FIELD)

    @property
    def dtb_files(self):
        """
        The list of dtb files.
        :return: A list of dtb files
        """
        return self._get_option(DTB_FILES_FIELD)

    @property
    def samsung_bl1_start(self):
        """BL1 start offset for Samsung boards.

        A str.
        """
        return self._get_option(SAMSUNG_BL1_START_FIELD)

    @property
    def samsung_bl1_len(self):
        """BL1 length for Samsung boards.

        A str.
        """
        return self._get_option(SAMSUNG_BL1_LEN_FIELD)

    @property
    def samsung_env_start(self):
        """Env start offset for Samsung boards.

        A str.
        """
        return self._get_option(SAMSUNG_ENV_START_FIELD)

    @property
    def samsung_env_len(self):
        """Env length for Samsung boards.

        A str.
        """
        return self._get_option(SAMSUNG_ENV_LEN_FIELD)

    @property
    def samsung_bl2_start(self):
        """BL2 start offset for Samsung boards.

        A str.
        """
        return self._get_option(SAMSUNG_BL2_START_FIELD)

    @property
    def samsung_bl2_len(self):
        """BL2 length for Samsung boards.

        A str.
        """
        return self._get_option(SAMSUNG_BL2_LEN_FIELD)

    @property
    def architectures(self):
        """The architectures to build the hwpack for.

        A list of str.
        """
        return self._get_list(ARCHITECTURES_FIELD)

    @property
    def architecture(self):
        """The architectures to build the hwpack for.

        A list of str.
        """
        return self._get_option(ARCHITECTURE_FIELD)

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
            sources = self.parser.get(SOURCES_FIELD)
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
            raise HwpackConfigError("Format version '%s' is not supported." %
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

    def _validate_bootloader_file(self):
        bootloader_file = self.bootloader_file
        if bootloader_file is not None:
            self._assert_matches_pattern(
                self.PATH_REGEX, bootloader_file,
                "Invalid path: %s" % bootloader_file)

    def _validate_spl_file(self):
        spl_file = self.spl_file
        if spl_file is not None:
            self._assert_matches_pattern(
                self.PATH_REGEX, spl_file, "Invalid path: %s" % spl_file)

    def _validate_vmlinuz(self):
        vmlinuz = self.vmlinuz
        if not vmlinuz:
            raise HwpackConfigError(self._not_found_message(KERNEL_FILE_FIELD))
        self._assert_matches_pattern(
            self.GLOB_REGEX, vmlinuz, "Invalid path: %s" % vmlinuz)

    def _validate_initrd(self):
        initrd = self.initrd
        if not initrd:
            raise HwpackConfigError(self._not_found_message(INITRD_FILE_FIELD))
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
        self._check_single_dtb_file(self.dtb_file)

    def _validate_dtb_files(self):
        dtb_files = self.dtb_files
        if dtb_files:
            for dtb_file in dtb_files:
                for _, src in dtb_file.iteritems():
                    self._check_single_dtb_file(src)

    def _check_single_dtb_file(self, dtb_file):
        if dtb_file is not None:
            self._assert_matches_pattern(
                self.GLOB_REGEX, dtb_file, "Invalid path: %s" % dtb_file)

    def _validate_extra_boot_options(self):
        # Optional and tricky to determine a valid pattern.
        pass

    def _validate_extra_serial_options(self):
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

        if addr is None:
            return

        if not re.match(r"^0x[a-fA-F0-9]{8}$", addr):
            raise HwpackConfigError("Invalid %s address: %s" % (name, addr))

    def _validate_kernel_addr(self):
        self._validate_addr(KERNEL_ADDR_FIELD)

    def _validate_initrd_addr(self):
        self._validate_addr(INITRD_ADDR_FIELD)

    def _validate_load_addr(self):
        self._validate_addr(LOAD_ADDR_FIELD)

    def _validate_dtb_addr(self):
        self._validate_addr(DTB_ADDR_FIELD)

    def _validate_wired_interfaces(self):
        pass

    def _validate_wireless_interfaces(self):
        pass

    def _validate_partition_layout(self):
        if self.partition_layout not in DEFINED_PARTITION_LAYOUTS:
            if self._is_v3:
                message = ("Undefined partition layout %s. "
                           "Valid partition layouts are %s." %
                           (self.partition_layout,
                            ", ".join(DEFINED_PARTITION_LAYOUTS)))
            else:
                message = ("Undefined partition layout %s in the [%s] section."
                           " Valid partition layouts are %s." %
                           (self.partition_layout, self.MAIN_SECTION,
                            ", ".join(DEFINED_PARTITION_LAYOUTS)))

            raise HwpackConfigError(message)

    def _validate_mmc_id(self):
        mmc_id = self.mmc_id
        if not mmc_id:
            raise HwpackConfigError(
                "No mmc_id in the [%s] section" %
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

    def _validate_bootloader_file_in_boot_part(self):
        if not self._validate_bool(self.bootloader_file_in_boot_part):
            if self._is_v3:
                name = "bootloader"
            else:
                name = "u_boot"
            raise HwpackConfigError(
                "Invalid value for %s_in_boot_part: %s"
                % (name, self.bootloader_file_in_boot_part))

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

    def _validate_bootloader_dd(self):
        bootloader_dd = self.bootloader_dd
        if bootloader_dd is None:
            return
        try:
            assert int(bootloader_dd) > 0
        except:
            if self._is_v3:
                name = "bootloader"
            else:
                name = "u_boot"

            raise HwpackConfigError(
                "Invalid %s_dd %s" % (name, bootloader_dd))

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
            raise HwpackConfigError(self._not_found_message(PACKAGES_FIELD))
        for package in packages:
            self._assert_matches_pattern(
                self.PACKAGE_REGEX, package,
                self._invalid_package_message(
                    PACKAGES_FIELD, self.MAIN_SECTION, package))

    def _validate_bootloader_package(self):
        bootloader_package = self.bootloader_package
        if bootloader_package is not None:
            self._assert_matches_pattern(
                self.PACKAGE_REGEX, bootloader_package,
                self._invalid_package_message(
                    self.BOOTLOADER_PACKAGE_KEY, self.MAIN_SECTION,
                    bootloader_package))

    def _validate_spl_package(self):
        spl_package = self.spl_package
        if spl_package is not None:
            self._assert_matches_pattern(
                self.PACKAGE_REGEX, spl_package,
                self._invalid_package_message(SPL_PACKAGE_FIELD,
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

    def _validate_samsung_env_start(self):
        samsung_env_start = self.samsung_env_start
        if samsung_env_start is None:
            return
        try:
            assert int(samsung_env_start) > 0
        except:
            raise HwpackConfigError(
                "Invalid samsung_env_start %s" % (samsung_env_start))

    def _validate_samsung_env_len(self):
        samsung_env_len = self.samsung_env_len
        if samsung_env_len is None:
            return
        try:
            assert int(samsung_env_len) > 0
        except:
            raise HwpackConfigError(
                "Invalid samsung_env_len %s" % (samsung_env_len))

    def _validate_samsung_bl2_start(self):
        samsung_bl2_start = self.samsung_bl2_start
        if samsung_bl2_start is None:
            return
        try:
            assert int(samsung_bl2_start) > 0
        except:
            raise HwpackConfigError(
                "Invalid samsung_bl2_start %s" % (samsung_bl2_start))

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
                self._not_found_message(ARCHITECTURES_FIELD))

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
            sources_entry = self._get_option([SOURCES_FIELD] + [section_name])
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
            source_dict = self.parser.get(SOURCES_FIELD)
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

    def _validate_keys(self):
        """Check the dictionary created by the YAML parser for unknown keys"""

        if not self._is_v3:
            # We don't check V1 or V2 configurations in this way
            return

        self._validate_keys_layout = hwpack_v3_layout
        self._do_validate_keys_prefix = []
        self._do_validate_keys(self._validate_keys_layout, self.parser)

    def _do_validate_keys_push_prefix(self, prefix):
        self._do_validate_keys_prefix.append(prefix)
        prefix = ": ".join(self._do_validate_keys_prefix)[2:]
        if prefix:
            prefix += ": "
        return prefix

    def _do_validate_keys(self, expected, config, prefix=""):
        prefix = self._do_validate_keys_push_prefix(prefix)

        if not isinstance(config, dict):
            raise HwpackConfigError("Invalid structure in metadata. Expected "
                                    "key: value pairs, found: '%s'" %
                                    (prefix + str(config)))

        for key in config.keys():
            # If expected == {"*": {...}} then we can accept any key
            if("*" in expected and expected.keys() == ["*"] and
               isinstance(expected["*"], dict)):
                # Have found a sub-dictionary to check. Recurse.
                self._do_validate_keys(expected["*"], config[key], key)
                continue

            # Check to see if the key is valid
            if key not in expected:
                raise HwpackConfigError("Unknown key in metadata: '%s'" %
                                        (prefix + str(key)))

            # Have a valid key. If it should point to a dictionary, recurse
            if expected[key]:
                if isinstance(expected[key], dict):
                    # Have found a sub-dictionary to check. Recurse.
                    self._do_validate_keys(expected[key], config[key], key)
                    continue

            if expected[key] == "root":
                config = config[key]
                prefix = self._do_validate_keys_push_prefix(key)

                for key in config.keys():
                    self._do_validate_keys(self._validate_keys_layout,
                                           config[key], key)

                self._do_validate_keys_prefix.pop()

        self._do_validate_keys_prefix.pop()
