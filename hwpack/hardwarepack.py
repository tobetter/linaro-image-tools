import time

from hwpack.better_tarfile import writeable_tarfile
from hwpack.packages import (
    FetchedPackage,
    get_packages_file,
    PackageMaker,
    )


class Metadata(object):
    """Metadata for a hardware pack.

    This metadata is what is required and optional for the metadata file
    that ends up in the hardware pack.

    In addition str() can be used to create the contents of the metdata
    file for the hardware pack that this metadata file refers to.

    :ivar name: the name of the hardware pack.
    :type name: str
    :ivar version: the version of the hardware pack. It must not contain white
        spaces.
    :type version: str
    :ivar origin: the origin of the hardware pack, or None if the origin
        is not known.
    :type origin: str or None
    :ivar maintainer: the maintainer of the hardware pack, or None if
        not known.
    :type maintainer: str or None
    :ivar support: the support status of this hardware pack, or None if
         not know.
    :type support: str or None
    """

    def __init__(self, name, version, architecture, origin=None,
                 maintainer=None, support=None):
        """Create the Metadata for a hardware pack.

        See the instance variables for a description of the arguments.
        """
        self.name = name
        if ' ' in version:
            raise AssertionError(
                'Hardware pack version must not contain white '
                'spaces: "%s"' % version)
        self.version = version
        self.origin = origin
        self.maintainer = maintainer
        self.support = support
        self.architecture = architecture

    @classmethod
    def from_config(cls, config, version, architecture):
        """Create a Metadata from a Config object.

        As a Config will contain most of the information needed for a
        Metadata, we can provide this convenient way to construct one.

        Information that is not in the config has to be provided by
        the caller.

        :param config: the config to take values from.
        :type config: Config
        :param version: the version to record in the metadata.
        :type version: str
        :param architecture: the architecture that the hardware pack is
            targetting.
        :type architecture: str
        """
        return cls(
            config.name, version, architecture, origin=config.origin,
            maintainer=config.maintainer, support=config.support)

    def __str__(self):
        """Get the contents of the metadata file."""
        metadata = "NAME=%s\n" % self.name
        metadata += "VERSION=%s\n" % self.version
        metadata += "ARCHITECTURE=%s\n" % self.architecture
        if self.origin is not None:
            metadata += "ORIGIN=%s\n" % self.origin
        if self.maintainer is not None:
            metadata += "MAINTAINER=%s\n" % self.maintainer
        if self.support is not None:
            metadata += "SUPPORT=%s\n" % self.support
        return metadata


class HardwarePack(object):
    """The representation of a hardware pack.

    :ivar metadata: the metadata of this hardware pack.
    :type metadata: Metadata
    :ivar FORMAT: the format of hardware pack that should be created.
    :type FORMAT: str
    """

    # The format version cannot contain white spaces. 
    FORMAT = "2.0"
    FORMAT_FILENAME = "FORMAT"
    METADATA_FILENAME = "metadata"
    MANIFEST_FILENAME = "manifest"
    PACKAGES_DIRNAME = "pkgs"
    PACKAGES_FILENAME = "%s/Packages" % PACKAGES_DIRNAME
    SOURCES_LIST_DIRNAME = "sources.list.d"
    SOURCES_LIST_GPG_DIRNAME = "sources.list.d.gpg"

    def __init__(self, metadata):
        """Create a HardwarePack.

        :param metadata: the metadata to use.
        :type metadata: Metadata
        """
        self.metadata = metadata
        self.sources = {}
        self.packages = []

    def filename(self):
        """The filename that this hardware pack should have.

        Returns the filename that the hardware pack should have, according
        to the convention used.

        :return: the filename that should be used.
        :rtype: str
        """
        if self.metadata.support is None:
            support_suffix = ""
        else:
            support_suffix = "_%s" % self.metadata.support
        return "hwpack_%s_%s_%s%s.tar.gz" % (
            self.metadata.name, self.metadata.version,
            self.metadata.architecture, support_suffix)

    def add_apt_sources(self, sources):
        """Add APT sources to the hardware pack.

        Given a dict of names and the source lines this will add
        them to the hardware pack.

        The names should be an identifier for the source, and the
        source lines should be what is put in sources.list for that
        source, minus the "deb" part.

        If you pass an identifier that has already been passed to this
        method, then the previous value will be replaced with the new
        value.

        :param sources: the sources to use as a dict mapping identifiers
            to sources entries.
        :type sources: a dict mapping str to str
        """
        self.sources.update(sources)

    def add_packages(self, packages):
        """Add packages to the hardware pack.

        Given a list of packages this will add them to the hardware
        pack.

        :param packages: the packages to add
        :type packages: FetchedPackage
        """
        self.packages += packages

    def add_dependency_package(self, packages_spec):
        """Add a packge that depends on packages_spec to the hardware pack.

        The added package will share the name, version and architecture of the
        hardware pack itself.

        :param packages_spec: A list of apt package specifications,
            e.g. ``['foo', 'bar (>= 1.2)']``.
        """
        with PackageMaker() as maker:
            if packages_spec:
                relationships = {'Depends': ', '.join(packages_spec)}
            else:
                relationships = {}
            deb_file_path = maker.make_package(
                'hwpack-' + self.metadata.name, self.metadata.version,
                relationships, self.metadata.architecture)
            self.packages.append(FetchedPackage.from_deb(deb_file_path))

    def to_file(self, fileobj):
        """Write the hwpack to a file object.

        The full hardware pack will be written to the file object in
        gzip compressed tarball form as the spec requires.

        :param fileobj: the file object to write to.
        :type fileobj: a file-like object
        :return: None
        """
        kwargs = {}
        kwargs["default_uid"] = 1000
        kwargs["default_gid"] = 1000
        kwargs["default_uname"] = "user"
        kwargs["default_gname"] = "group"
        kwargs["default_mtime"] = time.time()
        with writeable_tarfile(fileobj, mode="w:gz", **kwargs) as tf:
            tf.create_file_from_string(
                self.FORMAT_FILENAME, self.FORMAT + "\n")
            tf.create_file_from_string(
                self.METADATA_FILENAME, str(self.metadata))
            tf.create_dir(self.PACKAGES_DIRNAME)
            manifest_content = ""
            for package in self.packages:
                if package.content is not None:
                    tf.create_file_from_string(
                        self.PACKAGES_DIRNAME + "/" + package.filename,
                        package.content.read())
                manifest_content += "%s=%s\n" % (
                    package.name, package.version)
            tf.create_file_from_string(
                self.MANIFEST_FILENAME, manifest_content)
            tf.create_file_from_string(
                self.PACKAGES_FILENAME,
                get_packages_file(
                    [p for p in self.packages if p.content is not None]))
            tf.create_dir(self.SOURCES_LIST_DIRNAME)
            for source_name, source_info in self.sources.items():
                tf.create_file_from_string(
                    self.SOURCES_LIST_DIRNAME + "/" + source_name + ".list",
                    "deb " + source_info + "\n")
            # TODO: include sources keys etc.
            tf.create_dir(self.SOURCES_LIST_GPG_DIRNAME)
