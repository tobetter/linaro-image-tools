import ConfigParser
import re

class HwpackConfigError(Exception):
    pass


class Config(object):
    """Encapsulation of a hwpack-create configuration."""

    MAIN_SECTION = "hwpack"
    NAME_KEY = "name"
    NAME_REGEX = "[a-z0-9][a-z0-9+0.]+"
    INCLUDE_DEBS_KEY = "include-debs"

    def __init__(self, fp):
        """Create a Config.

        :param fp: a file-like object containing the configuration.
        """
        self.parser = ConfigParser.RawConfigParser()
        self.parser.readfp(fp)

    def validate(self):
        if not self.parser.has_section(self.MAIN_SECTION):
            raise HwpackConfigError("No [%s] section" % self.MAIN_SECTION)
        try:
            name = self.parser.get(self.MAIN_SECTION, self.NAME_KEY)
            if re.match(self.NAME_REGEX, name) is None:
                raise HwpackConfigError("Invalid name: %s" % name)
        except ConfigParser.NoOptionError:
            raise HwpackConfigError(
                "No name in the [%s] section" % self.MAIN_SECTION)
        try:
            name = self.parser.getboolean(
                self.MAIN_SECTION, self.INCLUDE_DEBS_KEY)
        except ConfigParser.NoOptionError:
            pass
        except ValueError:
            raise HwpackConfigError(
                "Invalid value for include-debs: %s"
                % self.parser.get("hwpack", "include-debs"))
