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
        hwpack.to_f(fileobj)
        fileobj.seek(0)
        tf = tarfile.open(mode="r:gz", fileobj=fileobj)
        self.addCleanup(tf.close)
        return tf

    def assertHasPath(self, tarball, path, **kwargs):
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
        self.assertThat(tarball, TarfileHasFile(path, **kwargs))

    def test_creates_FORMAT_file(self):
        hwpack = HardwarePack(self.metadata)
        tf = self.get_tarfile(hwpack)
        self.assertHasPath(tf, "FORMAT", content=hwpack.FORMAT+"\n")

    def test_creates_metadata_file(self):
        metadata = Metadata(
            "ahwpack", "4", origin="linaro",
            maintainer="Some Maintainer", support="unsupported")
        hwpack = HardwarePack(metadata)
        tf = self.get_tarfile(hwpack)
        self.assertHasPath(tf, "metadata", content=str(metadata))

    def test_creates_manifest_file(self):
        hwpack = HardwarePack(self.metadata)
        tf = self.get_tarfile(hwpack)
        self.assertHasPath(tf, "manifest")

    def test_manifest_file_empty_with_no_packages(self):
        hwpack = HardwarePack(self.metadata)
        tf = self.get_tarfile(hwpack)
        self.assertHasPath(tf, "manifest", content="")

    def test_creates_pkgs_dir(self):
        hwpack = HardwarePack(self.metadata)
        tf = self.get_tarfile(hwpack)
        self.assertHasPath(tf, "pkgs", type=tarfile.DIRTYPE)

    def test_creates_Packages_file(self):
        hwpack = HardwarePack(self.metadata)
        tf = self.get_tarfile(hwpack)
        self.assertHasPath(tf, "pkgs/Packages")

    def test_Packages_file_empty_with_no_packages(self):
        hwpack = HardwarePack(self.metadata)
        tf = self.get_tarfile(hwpack)
        self.assertHasPath(tf, "pkgs/Packages", content="")

    def test_creates_sources_list_dir(self):
        hwpack = HardwarePack(self.metadata)
        tf = self.get_tarfile(hwpack)
        self.assertHasPath(tf, "sources.list.d", type=tarfile.DIRTYPE)

    def test_creates_sources_list_gpg_dir(self):
        hwpack = HardwarePack(self.metadata)
        tf = self.get_tarfile(hwpack)
        self.assertHasPath(tf, "sources.list.d.gpg", type=tarfile.DIRTYPE)
