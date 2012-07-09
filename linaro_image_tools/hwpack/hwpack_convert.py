import ConfigParser
import logging
import os
import os.path

# This is the main section of an INI-style hwpack config file.
MAIN_SECTION = 'hwpack'
# This, if has multiple values, should be converted into the proper structure.
ARCHITECTURES_KEY = 'architectures'
# The suffix for the new file
NEW_FILE_SUFFIX = '.yaml'

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
    def __init__(self, input_file, output_file):
        """Initializie the class."""
        self.input_file = input_file
        self.output_file = output_file

        self.parser = ConfigParser.RawConfigParser()
        # Where we store the list of sources.
        self.sources = {}
        # Where we store all the information of the hwpack config file
        # In this case we have one board per hwpack config file.
        self.hwpack = {}
        # List of supported architectures.
        self.architectures = []

    def _parse(self):
        """Parses the config file and stores its values."""
        with open(self.input_file, 'r') as fp:
            self.parser.readfp(fp)

        # Iterate through all the file sections.
        for section in self.parser.sections():
            if section == MAIN_SECTION:
                for key, value in self.parser.items(section):
                    if value is not None:
                        if key == ARCHITECTURES_KEY:
                            self.parse_architectures_string(value)
                            continue
                        self.hwpack[key] = value
            else:
                for _, value in self.parser.items(section):
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
            for key, value in self.hwpack.iteritems():
                # Convert 'Yes' and 'No' values into boolean.
                if value == 'Yes':
                    value = True
                elif value == 'No':
                    value = False
                converted += "%s: %s\n" % (key, value)
        if self.architectures:
            converted += 'architectures:\n'
            for arch in self.architectures:
                converted += ' - %s\n' % arch
        if self.sources:
            converted += "sources:\n"
            for key, value in self.sources.iteritems():
                # Keep the heading white-space, we need it to define nesting.
                converted += " %s: %s\n" % (key, value)
        return converted


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
