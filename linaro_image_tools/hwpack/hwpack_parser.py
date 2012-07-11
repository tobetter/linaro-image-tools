import yaml
import ConfigParser
import re

YAML_SUFFIX = 'yaml'


class AbstractHwpackParserError(Exception):
    """General error class for hwpack parsers."""


class AbstractHwpackParser(object):
    """Abstract version of a parser class for hwpack."""
    def parse(self):
        raise NotImplementedError("This must be implemented.")

    def get(self, option, section):
        raise NotImplementedError("This must be implemented.")


class HwpackParser(object):
    def __init__(self, fp):
        """"""
        self.fp = fp
        self.file_name = fp.name

    def _get_parser(self):
        """Retrieves the correct parser based on the config file in the
        class constructor.

        If the config file has no extension, it is suppose to be an INI style
        configuration file.
        """
        parser = None
        if self.file_name.endswith(YAML_SUFFIX):
            parser = YamlParser(self.fp)
        else:
            parser = CfgParser(self.fp)
        return parser

    @property
    def parser(self):
        return self._get_parser()


class YamlParser(AbstractHwpackParser):
    """Class that represents a Yaml parser."""
    def __init__(self, fp):
        """Initialize the class.

        :param fp: the file pointer of the file to parse"""
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

    def get(self, option, section=None):
        return self.parsed.get(option)


class CfgParser(AbstractHwpackParser):
    """Class that represents a RawConfigParser from ConfigParser."""
    def __init__(self, fp):
        """Initialize the class.

        :param fp: the file pointer of the file to parse"""
        self.fp = fp
        self.parser = ConfigParser.RawConfigParser()

    def parse(self):
        """Read and parse the configuration data from the file.

        :return
        """
        try:
            return self.parser.readfp(self.fp)
        except ConfigParser.Error, e:
            obfuscated_e = re.sub(r"([^ ]https://).+?(@)", r"\1***\2", str(e))
            raise AbstractHwpackParserError(obfuscated_e)

    def get(self, option, section):
        return self.parser.get(section, option)
