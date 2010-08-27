import ConfigParser
import re

class HwpackConfigError(Exception):
    pass


class Config(object):
    """Encapsulation of a hwpack-create configuration."""

    def __init__(self, fp):
        """Create a Config.

        :param fp: a file-like object containing the configuration.
        """
        self.parser = ConfigParser.RawConfigParser()
        self.parser.readfp(fp)

    def validate(self):
        if not self.parser.has_section("hwpack"):
            raise HwpackConfigError("No [hwpack] section")
        try:
            name = self.parser.get("hwpack", "name")
            if re.match("[a-z0-9][a-z0-9+0.]+", name) is None:
                raise HwpackConfigError("Invalid name: %s" % name)
        except ConfigParser.NoOptionError:
            raise HwpackConfigError("No name in the [hwpack] section")
