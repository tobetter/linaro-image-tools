import ConfigParser
import logging
import os
import os.path
import re

# This is the main section of an INI-style hwpack config file.
MAIN_SECTION = 'hwpack'
# This, if has multiple values, should be converted into the proper structure.
ARCHITECTURES_KEY = 'architectures'
BOOTLOADERS_KEY = ['', '', '', '']
# The suffix for the new file
NEW_FILE_SUFFIX = '.yaml'
# How many spaces should be used for indentation.
INDENT_STEP = 1
# Regular expression to convert for Yes/No values into Boolean.
YES_REGEX = '[Yy]es'
NO_REGEX = '[Nn]o'

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
                                self.parse_architectures_string(value)
                                continue
                            self.hwpack[key] = value
                else:
                    # Here we have only sources sections.
                    for _, value in parser.items(section):
                        if value is not None:
                            self.sources[section] = value

    def parse_architectures_string(self, string):
        """Parse the string containing the architectures and store them in
        the list.
        """
        self.architectures.extend(string.split(" "))

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
        """Readable representation of the converted hwpack."""
        converted = ''
        if self.hwpack:
            converted += create_yaml_dictionary(self.hwpack)
        if self.architectures:
            converted += create_yaml_sequence(self.architectures,
                                                    'architectures')
        if self.sources:
            converted += create_yaml_dictionary(self.sources, 'sources')
        return converted


def create_yaml_sequence(sequence, name, indent=0):
    """Creates a YAML-string that describes a list (sequence).

    :param sequence: The list to be converted into YAML format.
    :param name: The name to be given to the created list.
    :param indent: A positive integer to calculate the indentation level.
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
                            {'indentation': indentation, 'value': item})
    return yaml_sequence


def create_yaml_dictionary(dictionary, name=None, indent=0):
    """Creates a YAML-string that describes a dictionary (mapping of mappings).

    :param dictionary: The dictionary to be converted into YAML format.
    :param name: The name to be given to the created dictionary.
    :param indent: A positive integer to calculate the indentation level.
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
    :param indent: A positive integer to calculate the indentation level."""
    if key is None or value is None:
        raise HwpackConverterException("Name or value cannot be empty.")
    if indent < 0:
        raise HwpackConverterException("Indentation value has to be positive.")
    # Convert 'Yes' and 'No' values into boolean.
    if re.match(YES_REGEX, value):
        value = True
    elif re.match(NO_REGEX, value):
        value = False
    yaml_string = ''
    indentation = _calculate_indent(indent)
    yaml_string += ("%(indentation)s%(key)s: %(value)s\n" %
                    {'indentation': indentation, 'key': key,
                        'value': str(value)})
    return yaml_string


def _calculate_indent(indent):
    """Create the string used for indenting the YAML structures."""
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
