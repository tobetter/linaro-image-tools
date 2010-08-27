import ConfigParser

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
        raise HwpackConfigError("No name in the [hwpack] section")
