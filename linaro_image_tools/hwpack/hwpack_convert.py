# Copyright (C) 2010, 2011, 2012 Linaro
#
# Author: Milo Casagrande <milo.casagrande@linaro.org>
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
import logging
import os
import os.path
import re
import yaml

from hwpack_fields import (
    ARCHITECTURES_FIELD,
    ASSUME_INSTALLED_FIELD,
    BOOTLOADERS_FIELD,
    EXTRA_BOOT_OPTIONS_FIELD,
    EXTRA_SERIAL_OPTIONS_FIELD,
    SOURCES_FIELD,
    FORMAT_FIELD,
    PACKAGES_FIELD,
    PACKAGE_FIELD,
    FILE_FIELD,
    IN_BOOT_PART_FIELD,
    DD_FIELD,
    DTB_FILE_FIELD,
    DTB_FILES_FIELD,
    ENV_DD_FIELD,
    SPL_IN_BOOT_PART_FIELD,
    SPL_DD_FIELD,
    SPL_PACKAGE_FIELD,
    SPL_FILE_FIELD,
    WIRED_INTERFACES_FIELD,
    WIRELESS_INTERFACES_FIELD,
    INCLUDE_DEBS_FIELD,
)

# This is the main section of an INI-style hwpack config file.
MAIN_SECTION = 'hwpack'
# The suffix for the new file
NEW_FILE_SUFFIX = '.yaml'
# How many spaces should be used for indentation.
INDENT_STEP = 1
# Regular expression to convert from Yes/No values into Boolean.
YES_REGEX = '[Yy]es'
NO_REGEX = '[Nn]o'
# The default format number.
DEFAULT_FORMAT = '3.0'
# Old INI style u_boot keys name.
UBOOT_PACKAGE_KEY = "u_boot_package"
UBOOT_FILE_KEY = "u_boot_file"
UBOOT_IN_BOOT_PART_KEY = 'u_boot_in_boot_part'
UBOOT_DD_KEY = 'u_boot_dd'
# All the u_boot defined keys in a list.
UBOOT_KEYS = [UBOOT_PACKAGE_KEY, UBOOT_FILE_KEY, UBOOT_IN_BOOT_PART_KEY,
              UBOOT_DD_KEY]

# Old field, the only one with a dash: since the format is new, convert it.
ASSUME_INSTALLED_OLD = 'assume-installed'
INCLUDE_DEBS_OLD = 'include-debs'

# The default bootloader for the bootloaders section.
DEFAULT_BOOTLOADER = 'u_boot'

# All the SPL keys
SPL_KEYS = [SPL_IN_BOOT_PART_FIELD, SPL_DD_FIELD, SPL_PACKAGE_FIELD,
            SPL_FILE_FIELD, ENV_DD_FIELD]

# The default name used for renaming dtb file
DEFAULT_DTB_NAME = 'board.dtb'

logger = logging.getLogger(__name__)


class HwpackConverterException(Exception):
    """General exception class for the converter."""


class HwpackConverter(object):
    """Simple and basic class that converts an INI-style format file into the
    new YAML format.

    The old format number is maintained.

    :param input_file: the input file to parse, has to be an INI-style file.
    :param output_file: where to write the new file, if not given, the name
                        of the input file will be used adding the 'yaml'
                        suffix.
    """
    def __init__(self, input_file=None, output_file=None):
        """Initializie the class."""
        self.input_file = input_file
        self.output_file = output_file

        # Where we store the list of sources.
        self.sources = {}
        # Where we store all the information of the hwpack config file
        # In this case we have one board per hwpack config file.
        self.hwpack = {}
        # List of supported architectures.
        self.architectures = []
        # Where we hold bootloaders info
        self.bootloaders = {}
        # List to store extra boot options.
        self.extra_boot_options = []
        # The list of packages.
        self.packages = []
        # List of the extra_serial_options.
        self.extra_serial_options = []
        # Lists for network interfaces.
        self.wired_interfaces = []
        self.wireless_interfaces = []
        # SPL entries
        self.spl = {}
        # The list of packages that should be installed.
        self.assume_installed = []
        # The dtb_files section
        self.dtb_files = []

    def _parse(self):
        """Parses the config file and stores its values."""
        if self.input_file is not None:
            parser = ConfigParser.RawConfigParser()
            with open(self.input_file, 'r') as fp:
                parser.readfp(fp)

            # Iterate through all the file sections.
            for section in parser.sections():
                if section == MAIN_SECTION:
                    for key, value in parser.items(section):
                        if value is not None:
                            if re.match("[Yy]es", value):
                                value = True
                            elif re.match("[Nn]o", value):
                                value = False
                            if key == ARCHITECTURES_FIELD:
                                self.parse_list_string(
                                    self.architectures,
                                    value)
                                continue
                            elif key == EXTRA_BOOT_OPTIONS_FIELD:
                                self.parse_list_string(
                                    self.extra_boot_options,
                                    value)
                                continue
                            elif key == EXTRA_SERIAL_OPTIONS_FIELD:
                                self.parse_list_string(
                                    self.extra_serial_options,
                                    value)
                                continue
                            elif key == WIRED_INTERFACES_FIELD:
                                self.parse_list_string(self.wired_interfaces,
                                                       value)
                                continue
                            elif key == WIRELESS_INTERFACES_FIELD:
                                self.parse_list_string(
                                    self.wireless_interfaces,
                                    value)
                                continue
                            elif key in SPL_KEYS:
                                self.spl[key] = value
                                continue
                            elif key == FORMAT_FIELD:
                                value = DEFAULT_FORMAT
                            elif key == PACKAGES_FIELD:
                                self.parse_list_string(self.packages, value)
                                continue
                            elif key in UBOOT_KEYS:
                                self._set_bootloaders(key, value)
                                continue
                            # Create list.
                            elif key == ASSUME_INSTALLED_OLD:
                                self.parse_list_string(
                                    self.assume_installed,
                                    value)
                                continue
                            elif key == DTB_FILE_FIELD:
                                self.dtb_files.append({DEFAULT_DTB_NAME:
                                                       value})
                                continue
                            elif key == INCLUDE_DEBS_OLD:
                                key = INCLUDE_DEBS_FIELD
                            self.hwpack[key] = value
                else:
                    # Here we have only sources sections.
                    for _, value in parser.items(section):
                        if value is not None:
                            self.sources[section] = value

    def _set_bootloaders(self, key, value):
        """Sets the bootloaders dictionary of a new YAML file. Converts from
        the old INI keys name into the new ones.

        :param key: The key of the bootloader.
        :param value: The key value."""
        if key == UBOOT_PACKAGE_KEY:
            self.bootloaders[PACKAGE_FIELD] = value
        elif key == UBOOT_FILE_KEY:
            self.bootloaders[FILE_FIELD] = value
        elif key == UBOOT_IN_BOOT_PART_KEY:
            self.bootloaders[IN_BOOT_PART_FIELD] = value
        elif key == UBOOT_DD_KEY:
            self.bootloaders[DD_FIELD] = value

    def parse_list_string(self, store, string, split=" "):
        """Parses a string of listed values, and stores the single splitted
        value in the provided list.

        :param store: The list where to store the values.
        :param string: The string that should be splitted.
        :param split: The separator to use, defaults to empty space.
        """
        if not isinstance(store, list):
            raise HwpackConverterException("Can use this method only with "
                                           "list.")
        store.extend(string.split(" "))

    def _to_file(self):
        """Writes the converted hwpack to file."""
        with open(self.output_file, 'w') as fp:
            fp.write(str(self))

    def convert(self):
        """Converts the input file into the output file with the new format.
        """
        self._parse()
        self._to_file()

    def __str__(self):
        """Readable representation of the converted hwpack.

        :return A YAML-string representation of the hwpack configuration.
        """
        converted = ''
        if self.hwpack:
            converted += dump(self.hwpack)
        if self.architectures:
            archs = {ARCHITECTURES_FIELD: self.architectures}
            converted += dump(archs)
        if self.assume_installed:
            installed = {ASSUME_INSTALLED_FIELD: self.assume_installed}
            converted += dump(installed)
        if self.extra_serial_options:
            serial_options = {EXTRA_SERIAL_OPTIONS_FIELD:
                              self.extra_serial_options}
            converted += dump(serial_options)
        if self.packages:
            packages = {PACKAGES_FIELD: self.packages}
            converted += dump(packages)
        if self.wired_interfaces:
            wired = {WIRED_INTERFACES_FIELD: self.wired_interfaces}
            converted += dump(wired)
        if self.wireless_interfaces:
            converted += dump(self.wireless_interfaces)
        if self.sources:
            sources = {SOURCES_FIELD: self.sources}
            converted += dump(sources)
        if self.dtb_files:
            dtb = {DTB_FILES_FIELD: self.dtb_files}
            converted += dump(dtb)
        if self.bootloaders or self.extra_boot_options or self.spl:
            # The bootloaders section in the new YAML file is a dictionary
            # containing a dictionary which can contains also other
            # dictionaries. In this case we only have list and normal values.
            nested_value = {}
            if self.bootloaders:
                for key, value in self.bootloaders.iteritems():
                    nested_value[key] = value
            if self.extra_boot_options:
                nested_value[EXTRA_BOOT_OPTIONS_FIELD] = \
                    self.extra_boot_options
            if self.spl:
                for key, value in self.spl.iteritems():
                    nested_value[key] = value
            default_bootloader = {DEFAULT_BOOTLOADER: nested_value}
            bootloaders = {BOOTLOADERS_FIELD: default_bootloader}
            converted += dump(bootloaders)
        return converted


def dump(python_object):
    """Serialize a Python object in a YAML string format.

    :param python_object: The object to serialize.
    """
    return yaml.dump(python_object, default_flow_style=False)


def check_and_validate_args(args):
    """Assures that the args passed are valid.

    :param args: the args as defined in linaro-hwpack-convert.
    """
    input_file = args.CONFIG_FILE
    output_file = args.out
    if not os.path.exists(input_file) or not os.path.isfile(input_file):
        raise HwpackConverterException("The configuration file '%s' is not a "
                                       "regular file." % input_file)
    if output_file is not None:
        if os.path.exists(output_file) or os.path.isdir(output_file):
            raise HwpackConverterException("The output file name provided "
                                           "'%s' already exists, or is a "
                                           "directory." % output_file)
        elif not os.path.isabs(output_file):
            # If we output file is just a name, write it in the current dir.
            output_file = os.path.join(os.getcwd(), output_file)
    else:
        output_file = input_file + NEW_FILE_SUFFIX
    return (input_file, output_file)
