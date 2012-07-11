import yaml
import ConfigParser
import re

# This is the entry line for all hwpack versions < 3.
HWPACK_MAIN_SECTION = '[hwpack]'
MAIN_SECTION = "hwpack"


class AbstractHwpackParserError(Exception):
    """General error class for hwpack parsers."""


class AbstractHwpackParser(object):
    """Abstract version of a parser class for hwpack."""
    def parse(self):
        raise NotImplementedError("This must be implemented.")

    def get(self, key):
        raise NotImplementedError("This must be implemented.")


class HwpackParser(object):
    def __init__(self, fp):
        """Initialize the abstraction for the parser.

        :param fp: The file pointer of the file to process.
        """
        self.fp = fp

    def _get_parser(self):
        """Retrieves the correct parser based on the config file in the
        class constructor.

        If the config file has no extension, it is suppose to be an INI style
        configuration file.
        """
        parser = None
        # Remove spaces and newlines.
        first_line = self.fp.readline().strip()
        # Rewind the file.
        self.fp.seek(0)
        if first_line == HWPACK_MAIN_SECTION:
            parser = CfgParser(self.fp)
        else:
            parser = YamlParser(self.fp)
        return parser

    @property
    def parser(self):
        return self._get_parser()


class YamlParser(AbstractHwpackParser):
    """Class that represents a Yaml parser."""
    def __init__(self, fp):
        """Initialize the class.

        :param fp: The file pointer of the file to parse."""
        self.fp = fp
        self.parsed = None

    def parse(self):
        """Read and parse the data from the file.

        :return A Python object representing the YAML document read.
        """
        try:
            self.parsed = yaml.load(self.fp)
        except yaml.scanner.ScannerError, e:
            raise AbstractHwpackParserError(e)

        return self.parsed

    def get(self, key):

        return self.parsed.get(key)


class CfgParser(AbstractHwpackParser):
    """Class that represents a RawConfigParser from ConfigParser."""
    def __init__(self, fp):
        """Initialize the class.

        :param fp: the file pointer of the file to parse"""
        self.fp = fp
        self.parser = ConfigParser.RawConfigParser()
        try:
            self.parser.readfp(self.fp)
        except ConfigParser.Error, e:
            obfuscated_e = re.sub(r"([^ ]https://).+?(@)", r"\1***\2", str(e))
            raise AbstractHwpackParserError(obfuscated_e)

    def parse(self):
        """Read the configuration data from the file.
        """
        try:
            self.parser.readfp(self.fp)
        except ConfigParser.Error, e:
            obfuscated_e = re.sub(r"([^ ]https://).+?(@)", r"\1***\2", str(e))
            raise AbstractHwpackParserError(obfuscated_e)

    def get(self, key):
        return self.parser.get(MAIN_SECTION, key)
