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
    ORIGIN_KEY = "origin"
    MAINTAINER_KEY = "maintainer"

    def __init__(self, fp):
        """Create a Config.

        :param fp: a file-like object containing the configuration.
        """
        self.parser = ConfigParser.RawConfigParser()
        self.parser.readfp(fp)

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

    @property
    def name(self):
        return self.parser.get(self.MAIN_SECTION, self.NAME_KEY)

    @property
    def include_debs(self):
        try:
            if not self.parser.get(
                self.MAIN_SECTION, self.INCLUDE_DEBS_KEY):
                return True
            return self.parser.getboolean(
                self.MAIN_SECTION, self.INCLUDE_DEBS_KEY)
        except ConfigParser.NoOptionError:
            return True

    def _get_main_option(self, key):
        return self.parser.get(self.MAIN_SECTION, key)

    @property
    def origin(self):
        try:
            origin = self._get_main_option(self.ORIGIN_KEY)
            if not origin:
                return None
            return origin
        except ConfigParser.NoOptionError:
            return None

    @property
    def maintainer(self):
        try:
            maintainer = self._get_main_option(self.MAINTAINER_KEY)
            if not maintainer:
                return None
            return maintainer
        except ConfigParser.NoOptionError:
            return None

    @property
    def support(self):
        try:
            support = self._get_main_option(self.SUPPORT_KEY)
            if not support:
                return None
            return support
        except ConfigParser.NoOptionError:
            return None

    def _validate_name(self):
        try:
            name = self.name
            if not name:
                raise HwpackConfigError("Empty value for name")
            if re.match(self.NAME_REGEX, name) is None:
                raise HwpackConfigError("Invalid name: %s" % name)
        except ConfigParser.NoOptionError:
            raise HwpackConfigError(
                "No name in the [%s] section" % self.MAIN_SECTION)

    def _validate_include_debs(self):
        try:
            self.include_debs
        except ValueError:
            raise HwpackConfigError(
                "Invalid value for include-debs: %s"
                % self.parser.get("hwpack", "include-debs"))

    def _validate_support(self):
        support = self.support
        if support not in (None, "supported", "unsupported"):
            raise HwpackConfigError(
                "Invalid value for support: %s" % support)

    def _validate_section_sources_entry(self, section_name):
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

    def _validate_section_packages(self, section_name):
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

    def _validate_section(self, section_name):
        self._validate_section_sources_entry(section_name)
        self._validate_section_packages(section_name)

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
