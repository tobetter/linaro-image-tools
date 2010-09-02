from StringIO import StringIO
import tarfile

from testtools import TestCase

from hwpack.hardwarepack import HardwarePack, Metadata
from hwpack.tarfile_matchers import TarfileHasFile


class MetadataTests(TestCase):

    def test_name(self):
        metadata = Metadata("ahwpack", "3")
        self.assertEqual("ahwpack", metadata.name)

    def test_version(self):
        metadata = Metadata("ahwpack", "3")
        self.assertEqual("3", metadata.version)

    def test_default_origin_is_None(self):
        metadata = Metadata("ahwpack", "4")
        self.assertEqual(None, metadata.origin)

    def test_origin(self):
        metadata = Metadata("ahwpack", "4", origin="linaro")
        self.assertEqual("linaro", metadata.origin)

    def test_default_maintainer_is_None(self):
        metadata = Metadata("ahwpack", "4")
        self.assertEqual(None, metadata.maintainer)

    def test_maintainer(self):
        metadata = Metadata("ahwpack", "4", maintainer="Some maintainer")
        self.assertEqual("Some maintainer", metadata.maintainer)

    def test_default_support_is_None(self):
        metadata = Metadata("ahwpack", "4")
        self.assertEqual(None, metadata.support)

    def test_support(self):
        metadata = Metadata("ahwpack", "4", support="supported")
        self.assertEqual("supported", metadata.support)

    def test_str(self):
        metadata = Metadata("ahwpack", "4")
        self.assertEqual("NAME=ahwpack\nVERSION=4\n", str(metadata))

    def test_str_with_origin(self):
        metadata = Metadata("ahwpack", "4", origin="linaro")
        self.assertEqual(
            "NAME=ahwpack\nVERSION=4\nORIGIN=linaro\n", str(metadata))

    def test_str_with_maintainer(self):
        metadata = Metadata("ahwpack", "4", maintainer="Some Maintainer")
        self.assertEqual(
            "NAME=ahwpack\nVERSION=4\nMAINTAINER=Some Maintainer\n",
            str(metadata))

    def test_str_with_support(self):
        metadata = Metadata("ahwpack", "4", support="unsupported")
        self.assertEqual(
            "NAME=ahwpack\nVERSION=4\nSUPPORT=unsupported\n", str(metadata))


class HardwarePackHasFile(TarfileHasFile):
    """A subclass of TarfileHasFile specific to hardware packs.

    We default to a set of attributes expected for files in a hardware
    pack.
    """

    def __init__(self, path, **kwargs):
        """Create a HardwarePackHasFile matcher.

        The kwargs are the keyword arguments taken by TarfileHasFile.
        If they are not given then defaults will be checked:
            - The type should be a regular file
            - If the content is given then the size will be checked
                to ensure it indicates the length of the content
                correctly.
            - the mode is appropriate for the type. If the type is
                regular file this is 0644, otherwise if it is
                a directory then it is 0755.
            - the linkname should be the empty string.
            - the uid and gid should be 1000
            - the uname and gname should be "user" and "group"
                respectively.

        :param path: the path that should be present.
        :type path: str
        """
        kwargs.setdefault("type", tarfile.REGTYPE)
        if "content" in kwargs:
            kwargs.setdefault("size", len(kwargs["content"]))
        if kwargs["type"] == tarfile.DIRTYPE:
            kwargs.setdefault("mode", 0755)
        else:
            kwargs.setdefault("mode", 0644)
        kwargs.setdefault("linkname", "")
        kwargs.setdefault("uid", 1000)
        kwargs.setdefault("gid", 1000)
        kwargs.setdefault("uname", "user")
        kwargs.setdefault("gname", "group")
        # TODO: mtime checking
        super(HardwarePackHasFile, self).__init__(path, **kwargs)


class HardwarePackTests(TestCase):

    def setUp(self):
        super(HardwarePackTests, self).setUp()
        self.metadata = Metadata("ahwpack", 4)

    def test_format_is_1_0(self):
        hwpack = HardwarePack(self.metadata)
        self.assertEqual("1.0", hwpack.FORMAT)

    def test_filename(self):
        hwpack = HardwarePack(self.metadata)
        self.assertEqual("hwpack_ahwpack_4.tar.gz", hwpack.filename())

    def test_filename_with_support(self):
        metadata = Metadata("ahwpack", "4", support="supported")
        hwpack = HardwarePack(metadata)
        self.assertEqual(
            "hwpack_ahwpack_4_supported.tar.gz", hwpack.filename())

    def get_tarfile(self, hwpack):
        fileobj = StringIO()
        hwpack.to_file(fileobj)
        fileobj.seek(0)
        tf = tarfile.open(mode="r:gz", fileobj=fileobj)
        self.addCleanup(tf.close)
        return tf

    def test_creates_FORMAT_file(self):
        hwpack = HardwarePack(self.metadata)
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf,
            HardwarePackHasFile("FORMAT", content=hwpack.FORMAT+"\n"))

    def test_creates_metadata_file(self):
        metadata = Metadata(
            "ahwpack", "4", origin="linaro",
            maintainer="Some Maintainer", support="unsupported")
        hwpack = HardwarePack(metadata)
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf, HardwarePackHasFile("metadata", content=str(metadata)))

    def test_creates_manifest_file(self):
        hwpack = HardwarePack(self.metadata)
        tf = self.get_tarfile(hwpack)
        self.assertThat(tf, HardwarePackHasFile("manifest"))

    def test_manifest_file_empty_with_no_packages(self):
        hwpack = HardwarePack(self.metadata)
        tf = self.get_tarfile(hwpack)
        self.assertThat(tf, HardwarePackHasFile("manifest", content=""))

    def test_creates_pkgs_dir(self):
        hwpack = HardwarePack(self.metadata)
        tf = self.get_tarfile(hwpack)
        self.assertThat(tf, HardwarePackHasFile("pkgs", type=tarfile.DIRTYPE))

    def test_creates_Packages_file(self):
        hwpack = HardwarePack(self.metadata)
        tf = self.get_tarfile(hwpack)
        self.assertThat(tf, HardwarePackHasFile("pkgs/Packages"))

    def test_Packages_file_empty_with_no_packages(self):
        hwpack = HardwarePack(self.metadata)
        tf = self.get_tarfile(hwpack)
        self.assertThat(tf, HardwarePackHasFile("pkgs/Packages", content=""))

    def test_creates_sources_list_dir(self):
        hwpack = HardwarePack(self.metadata)
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf, HardwarePackHasFile("sources.list.d", type=tarfile.DIRTYPE))

    def test_creates_sources_list_gpg_dir(self):
        hwpack = HardwarePack(self.metadata)
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf,
            HardwarePackHasFile("sources.list.d.gpg", type=tarfile.DIRTYPE))
