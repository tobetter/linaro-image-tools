import ConfigParser
import logging
import os
import os.path
import re

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
    ENV_DD_FIELD,
    SPL_IN_BOOT_PART_FIELD,
    SPL_DD_FIELD,
    SPL_PACKAGE_FIELD,
    SPL_FILE_FIELD,
    WIRED_INTERFACES_FIELD,
    WIRELESS_INTERFACES_FIELD,
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

# The default bootloader for the bootloaders section.
DEFAULT_BOOTLOADER = 'u_boot'

# All the SPL keys
SPL_KEYS = [SPL_IN_BOOT_PART_FIELD, SPL_DD_FIELD, SPL_PACKAGE_FIELD,
            SPL_FILE_FIELD, ENV_DD_FIELD]

logger = logging.getLogger("linaro_hwpack_converter")


class HwpackConverterException(Exception):
    """General exception class for the converter."""


class HwpackConverter(object):
    """Simple and basic class that converts an INI-style format file into the
    new YAML format.

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
                            if key == ARCHITECTURES_FIELD:
                                self.parse_list_string(self.architectures,
                                                        value)
                                continue
                            elif key == EXTRA_BOOT_OPTIONS_FIELD:
                                self.parse_list_string(self.extra_boot_options,
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
                            # Convert an old key into the new one.
                            elif key == ASSUME_INSTALLED_OLD:
                                key = ASSUME_INSTALLED_FIELD
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
            converted += create_yaml_dictionary(self.hwpack)
        if self.architectures:
            converted += create_yaml_sequence(self.architectures,
                                                ARCHITECTURES_FIELD)
        if self.extra_serial_options:
            converted += create_yaml_sequence(self.extra_serial_options,
                                                EXTRA_SERIAL_OPTIONS_FIELD)
        if self.packages:
            converted += create_yaml_sequence(self.packages, PACKAGES_FIELD)
        if self.wired_interfaces:
            converted += create_yaml_sequence(self.wired_interfaces,
                                                WIRED_INTERFACES_FIELD)
        if self.wireless_interfaces:
            converted += create_yaml_sequence(self.wireless_interfaces,
                                                WIRELESS_INTERFACES_FIELD)
        if self.sources:
            converted += create_yaml_dictionary(self.sources, SOURCES_FIELD)
        if self.bootloaders or self.extra_boot_options or self.spl:
            converted += create_yaml_entry(BOOTLOADERS_FIELD)
            # We default to u_boot as the bootloader.
            converted += create_yaml_entry(DEFAULT_BOOTLOADER, indent=1)
            if self.bootloaders:
                converted += create_yaml_dictionary(self.bootloaders,
                                                    indent=2)
            if self.extra_boot_options:
                converted += create_yaml_sequence(self.extra_boot_options,
                                                    EXTRA_BOOT_OPTIONS_FIELD,
                                                    indent=2)
            if self.spl:
                converted += create_yaml_dictionary(self.spl, indent=2)
        return converted


def create_yaml_sequence(sequence, name, indent=0):
    """Creates a YAML-string that describes a list (sequence).

    :param sequence: The list to be converted into YAML format.
    :param name: The name to be given to the created list.
    :param indent: A positive integer to calculate the indentation level.
    :return A YAML-string representing a sequence.
    """
    if not isinstance(sequence, list):
        raise HwpackConverterException("The value passed is not of type "
                                        "'list'.")
    if name is None or name.strip() == "":
        raise HwpackConverterException("The name of a sequence cannot be "
                                        "empty or None.")
    indentation = _calculate_indent(indent)
    yaml_sequence = ("%(indentation)s%(name)s:\n" %
                        {'indentation': indentation, 'name': name})
    indentation = _calculate_indent(indent + INDENT_STEP)
    for item in sequence:
        yaml_sequence += ("%(indentation)s- %(value)s\n" %
                            {'indentation': indentation, 'value': str(item)})
    return yaml_sequence


def create_yaml_dictionary(dictionary, name=None, indent=0):
    """Creates a string that describes a dictionary in YAML
    (mapping of mappings).

    :param dictionary: The dictionary to be converted into YAML format.
    :param name: The name to be given to the created dictionary.
    :param indent: A positive integer to calculate the indentation level.
    :return A YAML-string represeting a dictionary.
    """
    if not isinstance(dictionary, dict):
        raise HwpackConverterException("The value passed is not of type "
                                        "'dict'.")
    if name is not None and name.strip() == "":
        raise HwpackConverterException("The name of a dictionary cannot "
                                        "be empty.")
    if indent < 0:
        raise HwpackConverterException("Indentation value has to be positive.")
    yaml_dictionary = ""
    if name is not None:
        indentation = _calculate_indent(indent)
        yaml_dictionary += ("%(indentation)s%(name)s:\n" %
                            {'indentation': indentation, 'name': name})
        indent += INDENT_STEP

    for key, value in dictionary.iteritems():
        yaml_dictionary += create_yaml_string(key, value, indent)
    return yaml_dictionary


def create_yaml_string(key, value, indent=0):
    """Creates a normal YAML-format string of the type 'KEY: VALUE'.

    :param key: The name of the key.
    :param value: The value to assign to the key.
    :param indent: A positive integer to calculate the indentation level.
                    Defaults to zero.
    :return A YAML-string of the 'key: value' type.
    """
    if key is None or value is None:
        raise HwpackConverterException("Name or value cannot be empty.")
    if indent < 0:
        raise HwpackConverterException("Indentation value has to be positive.")
    value = str(value)
    # Convert 'Yes' and 'No' values into boolean.
    if re.match(YES_REGEX, value):
        value = True
    elif re.match(NO_REGEX, value):
        value = False
    yaml_string = ''
    indentation = _calculate_indent(indent)
    yaml_string += ("%(indentation)s%(key)s: %(value)s\n" %
                    {'indentation': indentation, 'key': key,
                        'value': value})
    return yaml_string


def create_yaml_entry(name, indent=0):
    """Create a simple entry in a YAML format, like 'name:'.

    :param name: The name of the entry.
    :param indent: A positive integer to calculate the indentation level.
                    Defaults to zero.
    :return A string.
    """
    if not name:
        raise HwpackConverterException("Name cannot be None or empty.")
    if indent < 0:
        raise HwpackConverterException("Indentation value has to be positive.")

    indentation = _calculate_indent(indent)
    yaml_string = ("%s%s:\n" % (indentation, name))
    return yaml_string


def create_yaml_string_from_list(name, sequence, indent=0):
    """Create a YAML key:value entry where value is a space separated strings
    starting from a list.

    :param name: The name of the entry.
    :param sequence: The sequence to concatanate.
    :param indent: A positive integer to calculate the indentation leve.
                    Defaults to zero.
    :return A string.
    """
    if not isinstance(sequence, list):
        raise HwpackConverterException("The value passed is not of type "
                                        "'list''")
    if not name:
        raise HwpackConverterException("Name cannot be None or empty.")
    if indent < 0:
        raise HwpackConverterException("Indentation value has to be positive.")
    indentation = _calculate_indent(indent)
    space_separate_string = " ".join(sequence)
    yaml_string = ("%s%s: %s\n" % (indentation, name, space_separate_string))
    return yaml_string


def recurse_dictionary(dictionary, indent=0, convert=False):
    """Recursively create a string that describes a dictionary in YAML starting
    from a dictionary containing other dictionaries or other entries.

    :param dictionary: The dictionary that will be recursively converted.
    :param indent: A positive integer to calculate the indentation level.
                    Defaults to zero.
    :param convert: If a list contained in the dictionary should be converted
                    into a space separated strng. Defaults to False.
    :return A string.
    """
    metadata = ''
    for key, value in dictionary.iteritems():
        if isinstance(value, dict):
            metadata += create_yaml_entry(key, indent)
            metadata += recurse_dictionary(value, indent + INDENT_STEP,
                                            convert)
        elif isinstance(value, list):
            if convert:
                # We default into creating a space separate list
                metadata += create_yaml_string_from_list(key, value, indent)
            else:
                metadata += create_yaml_sequence(key, value, indent)
        else:
            metadata += create_yaml_string(key, value, indent)
    return metadata


def _calculate_indent(indent):
    """Create the string used for indenting the YAML structures.

    :return A string with the correct spaces for indentation.
    """
    indented_string = ''
    for i in range(indent):
        indented_string += ' '
    return indented_string


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
