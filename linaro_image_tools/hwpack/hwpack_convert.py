import ConfigParser
import logging
import os
import os.path
import re

# This is the main section of an INI-style hwpack config file.
MAIN_SECTION = 'hwpack'
# This, if has multiple values, should be converted into the proper structure.
ARCHITECTURES_KEY = 'architectures'
# The extra boot options field.
EXTRA_BOOT_OPTIONS_KEY = 'extra_boot_options'
# The extra_serial_options key.
EXTRA_SERIAL_OPTIONS_KEY = 'extra_serial_options'
# The sources key.
SOURCES_KEY = 'sources'
# The packages key.
PACKAGES_KEY = 'packages'
# The format key.
FORMAT_KEY = 'format'
# The suffix for the new file
NEW_FILE_SUFFIX = '.yaml'
# How many spaces should be used for indentation.
INDENT_STEP = 1
# Regular expression to convert for Yes/No values into Boolean.
YES_REGEX = '[Yy]es'
NO_REGEX = '[Nn]o'
# The default format number.
DEFAULT_FORMAT = '3.0'
# Old INI style u_boot keys name, and new YAML ones.
U_BOOT_PACKAGE_KEY = "u_boot_package"
U_BOOT_FILE_KEY = "u_boot_file"
UBOOT_IN_BOOT_PART_KEY = 'u_boot_in_boot_part'
UBOOT_DD_KEY = 'u_boot_dd'
PACKAGE_KEY = "package"
FILE_KEY = "file"
IN_BOOT_PART_KEY = "in_boot_part"
DD_KEY = "dd"
# All the u_boot defined keys in a list.
UBOOT_KEYS = [U_BOOT_PACKAGE_KEY, U_BOOT_FILE_KEY, UBOOT_IN_BOOT_PART_KEY,
                UBOOT_DD_KEY]

# The name of the bootloaders section.
BOOTLOADERS_FIELD = 'bootloaders'
# The default bootloader for the bootloaders section.
DEFAULT_BOOTLOADER = 'u_boot'
# Network interfaces.
WIRED_INTERFACES_KEY = 'wired_interfaces'
WIRELESS_INTERFACES_KEY = 'wireless_interfaces'

logger = logging.getLogger("linaro_hwpack_converter")


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
                            if key == ARCHITECTURES_KEY:
                                self.parse_list_string(self.architectures,
                                                        value)
                                continue
                            elif key == EXTRA_BOOT_OPTIONS_KEY:
                                self.parse_list_string(self.extra_boot_options,
                                                        value)
                                continue
                            elif key == EXTRA_SERIAL_OPTIONS_KEY:
                                self.parse_list_string(
                                                    self.extra_serial_options,
                                                    value)
                                continue
                            elif key == WIRED_INTERFACES_KEY:
                                self.parse_list_string(self.wired_interfaces,
                                                        value)
                                continue
                            elif key == WIRELESS_INTERFACES_KEY:
                                self.parse_list_string(
                                                    self.wireless_interfaces,
                                                    value)
                                continue
                            elif key == FORMAT_KEY:
                                value = DEFAULT_FORMAT
                            elif key == PACKAGES_KEY:
                                self.parse_list_string(self.packages, value)
                                continue
                            elif key in UBOOT_KEYS:
                                self._set_bootloaders(key, value)
                                continue
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
        if key == U_BOOT_PACKAGE_KEY:
            self.bootloaders[PACKAGE_KEY] = value
        elif key == U_BOOT_FILE_KEY:
            self.bootloaders[FILE_KEY] = value
        elif key == UBOOT_IN_BOOT_PART_KEY:
            self.bootloaders[IN_BOOT_PART_KEY] = value
        elif key == UBOOT_DD_KEY:
            self.bootloaders[DD_KEY] = value

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
                                                ARCHITECTURES_KEY)
        if self.extra_boot_options:
            converted += create_yaml_sequence(self.extra_boot_options,
                                                EXTRA_BOOT_OPTIONS_KEY)
        if self.extra_serial_options:
            converted += create_yaml_sequence(self.extra_serial_options,
                                                EXTRA_SERIAL_OPTIONS_KEY)
        if self.packages:
            converted += create_yaml_sequence(self.packages, PACKAGES_KEY)
        if self.wired_interfaces:
            converted += create_yaml_sequence(self.wired_interfaces,
                                                WIRED_INTERFACES_KEY)
        if self.wireless_interfaces:
            converted += create_yaml_sequence(self.wireless_interfaces,
                                                WIRELESS_INTERFACES_KEY)
        if self.sources:
            converted += create_yaml_dictionary(self.sources, SOURCES_KEY)
        if self.bootloaders:
            converted += BOOTLOADERS_FIELD + ":\n"
            # We default to u_boot as the bootloader.
            converted += create_yaml_dictionary(self.bootloaders,
                                                DEFAULT_BOOTLOADER, indent=1)
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
    """Creates a YAML-string that describes a dictionary (mapping of mappings).

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
    """Creates a normal YAML-format string of the type KEY: VALUE.

    :param key: The name of the key.
    :param value: The value to assign to the key.
    :param indent: A positive integer to calculate the indentation level.
    :return A YAML-string of the key:value type.
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
