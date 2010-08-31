from hwpack.better_tarfile import writeable_tarfile


class Metadata(object):

    def __init__(self, name, version, origin=None, maintainer=None,
                 support=None):
        self.name = name
        self.version = version
        self.origin = origin
        self.maintainer = maintainer
        self.support = support

    def __str__(self):
        metadata = "NAME=%s\n" % self.name
        metadata += "VERSION=%s\n" % self.version
        if self.origin is not None:
            metadata += "ORIGIN=%s\n" % self.origin
        if self.maintainer is not None:
            metadata += "MAINTAINER=%s\n" % self.maintainer
        if self.support is not None:
            metadata += "SUPPORT=%s\n" % self.support
        return metadata


class HardwarePack(object):

    FORMAT = "1.0"
    FORMAT_FILENAME = "FORMAT"
    METADATA_FILENAME = "metadata"
    MANIFEST_FILENAME = "manifest"
    PACKAGES_DIRNAME = "pkgs"
    PACKAGES_FILENAME = "%s/Packages" % PACKAGES_DIRNAME
    SOURCES_LIST_DIRNAME = "sources.list.d"
    SOURCES_LIST_GPG_DIRNAME = "sources.list.d.gpg"

    def __init__(self, metadata):
        self.metadata = metadata

    def filename(self):
        if self.metadata.support is None:
            support_suffix = ""
        else:
            support_suffix = "_%s" % self.metadata.support
        return "hwpack_%s_%s%s.tar.gz" % (
            self.metadata.name, self.metadata.version, support_suffix)

    def to_f(self, fileobj):
        kwargs = {}
        kwargs["default_uid"] = 1000
        kwargs["default_gid"] = 1000
        kwargs["default_uname"] = "user"
        kwargs["default_gname"] = "group"
        with writeable_tarfile(fileobj, mode="w:gz", **kwargs) as tf:
            tf.create_file_from_string(
                self.FORMAT_FILENAME, self.FORMAT + "\n")
            tf.create_file_from_string(
                self.METADATA_FILENAME, str(self.metadata))
            tf.create_file_from_string(self.MANIFEST_FILENAME, "")
            tf.create_dir(self.PACKAGES_DIRNAME)
            tf.create_file_from_string(self.PACKAGES_FILENAME, "")
            tf.create_dir(self.SOURCES_LIST_DIRNAME)
            tf.create_dir(self.SOURCES_LIST_GPG_DIRNAME)
