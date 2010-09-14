import ConfigParser
import re


class HwpackConfigError(Exception):
    pass


class Config(object):
    """Encapsulation of a hwpack-create configuration."""

    MAIN_SECTION = "hwpack"
    NAME_KEY = "name"
    NAME_REGEX = "[a-z0-9][a-z0-9+\-.]+$"
    INCLUDE_DEBS_KEY = "include-debs"
    SUPPORT_KEY = "support"
    SOURCES_ENTRY_KEY = "sources-entry"
    PACKAGES_KEY = "packages"
    PACKAGE_REGEX = NAME_REGEX
    ORIGIN_KEY = "origin"
    MAINTAINER_KEY = "maintainer"
    ARCHITECTURES_KEY = "architectures"
    ASSUME_INSTALLED_KEY = "assume-installed"

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
        self._validate_packages()
        self._validate_architectures()
        self._validate_assume_installed()
        self._validate_sections()

    @property
    def name(self):
        """The name of the hardware pack. A str."""
        return self.parser.get(self.MAIN_SECTION, self.NAME_KEY)

    @property
    def include_debs(self):
        """Whether the hardware pack should contain .debs. A bool."""
        try:
            if not self.parser.get(
                self.MAIN_SECTION, self.INCLUDE_DEBS_KEY):
                return True
            return self.parser.getboolean(
                self.MAIN_SECTION, self.INCLUDE_DEBS_KEY)
        except ConfigParser.NoOptionError:
            return True

    def _get_option_from_main_section(self, key):
        """Get the value from the main section for the given key.

        :param key: the key to return the value for.
        :type key: str.
        :return: the value for that key, or None if the key is not present
            or the value is empty.
        :rtype: str or None.
        """
        try:
            result = self.parser.get(self.MAIN_SECTION, key)
            if not result:
                return None
            return result
        except ConfigParser.NoOptionError:
            return None

    @property
    def origin(self):
        """The origin that should be recorded in the hwpack.

        A str or None if no origin should be recorded.
        """
        return self._get_option_from_main_section(self.ORIGIN_KEY)

    @property
    def maintainer(self):
        """The maintainer that should be recorded in the hwpack.

        A str or None if not maintainer should be recorded.
        """
        return self._get_option_from_main_section(self.MAINTAINER_KEY)

    @property
    def support(self):
        """The support level that should be recorded in the hwpack.

        A str or None if no support level should be recorded.
        """
        return self._get_option_from_main_section(self.SUPPORT_KEY)

    def _get_list_from_main_section(self, key):
        raw_values = self._get_option_from_main_section(key)
        if raw_values is None:
            return []
        values = re.split("\s+", raw_values)
        filtered_values = []
        for value in values:
            if value not in filtered_values:
                filtered_values.append(value)
        return filtered_values

    @property
    def packages(self):
        """The packages that should be contained in the hwpack.

        A list of str.
        """
        return self._get_list_from_main_section(self.PACKAGES_KEY)

    @property
    def architectures(self):
        """The architectures to build the hwpack for.

        A list of str.
        """
        return self._get_list_from_main_section(self.ARCHITECTURES_KEY)

    @property
    def assume_installed(self):
        """The packages that the hwpack should assume as already installed.

        A list of str.
        """
        return self._get_list_from_main_section(self.ASSUME_INSTALLED_KEY)

    @property
    def sources(self):
        """The sources defined in the configuration.

        A dict mapping source identifiers to sources entries.
        """
        sources = {}
        sections = self.parser.sections()
        found = False
        for section_name in sections:
            if section_name == self.MAIN_SECTION:
                continue
            sources[section_name] = self.parser.get(
                section_name, self.SOURCES_ENTRY_KEY)
        return sources

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

    def _validate_packages(self):
        packages = self.packages
        if not packages:
            raise HwpackConfigError(
                "No %s in the [%s] section"
                % (self.PACKAGES_KEY, self.MAIN_SECTION))
        for package in packages:
            if re.match(self.PACKAGE_REGEX, package) is None:
                raise HwpackConfigError(
                    "Invalid value in %s in the [%s] section: %s"
                    % (self.PACKAGES_KEY, self.MAIN_SECTION, package))

    def _validate_architectures(self):
        architectures = self.architectures
        if not architectures:
            raise HwpackConfigError(
                "No %s in the [%s] section"
                % (self.ARCHITECTURES_KEY, self.MAIN_SECTION))

    def _validate_assume_installed(self):
        assume_installed = self.assume_installed
        for package in assume_installed:
            if re.match(self.PACKAGE_REGEX, package) is None:
                raise HwpackConfigError(
                    "Invalid value in %s in the [%s] section: %s"
                    % (self.ASSUME_INSTALLED_KEY, self.MAIN_SECTION,
                        package))

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

    def _validate_section(self, section_name):
        self._validate_section_sources_entry(section_name)

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
