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
    SUPPORT_KEY = "support"
    SOURCES_ENTRY_KEY = "sources-entry"
    PACKAGES_KEY = "packages"
    PACKAGE_REGEX = NAME_REGEX

    def __init__(self, fp):
        """Create a Config.

        :param fp: a file-like object containing the configuration.
        """
        self.parser = ConfigParser.RawConfigParser()
        self.parser.readfp(fp)

    def _validate_name(self):
        try:
            name = self.parser.get(self.MAIN_SECTION, self.NAME_KEY)
            if not name:
                raise HwpackConfigError("Empty value for name")
            if re.match(self.NAME_REGEX, name) is None:
                raise HwpackConfigError("Invalid name: %s" % name)
        except ConfigParser.NoOptionError:
            raise HwpackConfigError(
                "No name in the [%s] section" % self.MAIN_SECTION)

    def _validate_include_debs(self):
        try:
            self.parser.getboolean(self.MAIN_SECTION, self.INCLUDE_DEBS_KEY)
        except ConfigParser.NoOptionError:
            pass
        except ValueError:
            raise HwpackConfigError(
                "Invalid value for include-debs: %s"
                % self.parser.get("hwpack", "include-debs"))

    def _validate_support(self):
        try:
            support = self.parser.get(self.MAIN_SECTION, self.SUPPORT_KEY)
            if support not in ("supported", "unsupported"):
                raise HwpackConfigError(
                    "Invalid value for support: %s" % support)
        except ConfigParser.NoOptionError:
            pass

    def _validate_section(self, section_name):
        try:
            sources_entry = self.parser.get(
                section_name, self.SOURCES_ENTRY_KEY)
            if not sources_entry:
                raise HwpackConfigError(
                    "The %s in the [%s] section is missing the URI"
                    % (self.SOURCES_ENTRY_KEY, section_name))
            if len(sources_entry.split(" ", 1)) < 2:
                raise HwpackConfigError(
                    "The %s in the [%s] section is missing the distribution"
                    % (self.SOURCES_ENTRY_KEY, section_name))
            if sources_entry.startswith("deb"):
                raise HwpackConfigError(
                    "The %s in the [%s] section shouldn't start with 'deb'"
                    % (self.SOURCES_ENTRY_KEY, section_name))
        except ConfigParser.NoOptionError:
            raise HwpackConfigError(
                "No %s in the [%s] section"
                % (self.SOURCES_ENTRY_KEY, section_name))
        try:
            packages = self.parser.get(section_name, self.PACKAGES_KEY)
            if not packages:
                raise HwpackConfigError(
                    "The %s in the [%s] section is empty"
                    % (self.PACKAGES_KEY, section_name))
            for package in packages.split(" "):
                if not package:
                    continue
                if re.match(self.PACKAGE_REGEX, package) is None:
                    raise HwpackConfigError(
                        "Invalid value in %s in the [%s] section: %s"
                        % (self.PACKAGES_KEY, section_name, package))
        except ConfigParser.NoOptionError:
            raise HwpackConfigError(
                "No %s in the [%s] section"
                % (self.PACKAGES_KEY, section_name))

    def _validate_sections(self):
        sections = self.parser.sections()
        found = False
        for section_name in sections:
            if section_name == self.MAIN_SECTION:
                continue
            self._validate_section(section_name)
            found = True
        if not found:
            raise HwpackConfigError(
                "No sections other than [%s]" % self.MAIN_SECTION)

    def validate(self):
        """Check that this configuration follows the schema.

        :raises HwpackConfigError: if it does not.
        """
        if not self.parser.has_section(self.MAIN_SECTION):
            raise HwpackConfigError("No [%s] section" % self.MAIN_SECTION)
        self._validate_name()
        self._validate_include_debs()
        self._validate_support()
        self._validate_sections()
