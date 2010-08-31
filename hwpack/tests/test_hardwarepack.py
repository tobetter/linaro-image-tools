from StringIO import StringIO
import tarfile

from testtools import TestCase

from hwpack.hardwarepack import HardwarePack
from hwpack.tarfile_matchers import TarfileHasFile


class HardwarePackTests(TestCase):

    def test_format_is_1_0(self):
        hwpack = HardwarePack("ahwpack", "3")
        self.assertEqual("1.0", hwpack.FORMAT)

    def test_name(self):
        hwpack = HardwarePack("ahwpack", "4")
        self.assertEqual("ahwpack", hwpack.name)

    def test_version(self):
        hwpack = HardwarePack("ahwpack", "4")
        self.assertEqual("4", hwpack.version)

    def test_default_origin_is_None(self):
        hwpack = HardwarePack("ahwpack", "4")
        self.assertEqual(None, hwpack.origin)

    def test_origin(self):
        hwpack = HardwarePack("ahwpack", "4", origin="linaro")
        self.assertEqual("linaro", hwpack.origin)

    def test_default_maintainer_is_None(self):
        hwpack = HardwarePack("ahwpack", "4")
        self.assertEqual(None, hwpack.maintainer)

    def test_maintainer(self):
        hwpack = HardwarePack("ahwpack", "4", maintainer="Some maintainer")
        self.assertEqual("Some maintainer", hwpack.maintainer)

    def test_default_support_is_None(self):
        hwpack = HardwarePack("ahwpack", "4")
        self.assertEqual(None, hwpack.support)

    def test_support(self):
        hwpack = HardwarePack("ahwpack", "4", support="supported")
        self.assertEqual("supported", hwpack.support)

    def test_filename(self):
        hwpack = HardwarePack("ahwpack", "4")
        self.assertEqual("hwpack_ahwpack_4.tar.gz", hwpack.filename())

    def test_filename_with_support(self):
        hwpack = HardwarePack("ahwpack", "4", support="supported")
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
        self.assertThat(tarball, TarfileHasFile(path, **kwargs))

    def test_creates_FORMAT_file(self):
        hwpack = HardwarePack("ahwpack", "4")
        tf = self.get_tarfile(hwpack)
        self.assertHasPath(tf, "FORMAT", content=hwpack.FORMAT+"\n")

    def test_creates_metadata_file(self):
        hwpack = HardwarePack("ahwpack", "4")
        tf = self.get_tarfile(hwpack)
        self.assertHasPath(tf, "metadata")

    def test_metadata_contains_name(self):
        hwpack = HardwarePack("ahwpack", "4")
        tf = self.get_tarfile(hwpack)
        self.assertIn("Name: ahwpack\n", tf.extractfile("metadata").read())

    def test_metadata_contains_version(self):
        hwpack = HardwarePack("ahwpack", "4")
        tf = self.get_tarfile(hwpack)
        self.assertIn("Version: 4\n", tf.extractfile("metadata").read())

    def test_metadata_contains_no_origin_if_not_given(self):
        hwpack = HardwarePack("ahwpack", "4")
        tf = self.get_tarfile(hwpack)
        self.assertNotIn("Origin", tf.extractfile("metadata").read())

    def test_metadata_contains_origin_if_given(self):
        hwpack = HardwarePack("ahwpack", "4", origin="linaro")
        tf = self.get_tarfile(hwpack)
        self.assertIn("Origin: linaro\n", tf.extractfile("metadata").read())

    def test_metadata_contains_no_maintainer_if_not_given(self):
        hwpack = HardwarePack("ahwpack", "4")
        tf = self.get_tarfile(hwpack)
        self.assertNotIn("Maintainer", tf.extractfile("metadata").read())

    def test_metadata_contains_maintainer_if_given(self):
        hwpack = HardwarePack("ahwpack", "4", maintainer="Some Maintainer")
        tf = self.get_tarfile(hwpack)
        self.assertIn(
            "Maintainer: Some Maintainer\n",
            tf.extractfile("metadata").read())

    def test_metadata_contains_no_support_if_not_given(self):
        hwpack = HardwarePack("ahwpack", "4")
        tf = self.get_tarfile(hwpack)
        self.assertNotIn("Support", tf.extractfile("metadata").read())

    def test_metadata_contains_support_if_given(self):
        hwpack = HardwarePack("ahwpack", "4", support="unsupported")
        tf = self.get_tarfile(hwpack)
        self.assertIn(
            "Support: unsupported\n", tf.extractfile("metadata").read())

    def test_creates_manifest_file(self):
        hwpack = HardwarePack("ahwpack", "4")
        tf = self.get_tarfile(hwpack)
        self.assertHasPath(tf, "manifest")

    def test_manifest_file_empty_with_no_packages(self):
        hwpack = HardwarePack("ahwpack", "4")
        tf = self.get_tarfile(hwpack)
        self.assertHasPath(tf, "manifest", content="")

    def test_creates_pkgs_dir(self):
        hwpack = HardwarePack("ahwpack", "4")
        tf = self.get_tarfile(hwpack)
        self.assertHasPath(tf, "pkgs", type=tarfile.DIRTYPE)

    def test_creates_Packages_file(self):
        hwpack = HardwarePack("ahwpack", "4")
        tf = self.get_tarfile(hwpack)
        self.assertHasPath(tf, "pkgs/Packages")

    def test_Packages_file_empty_with_no_packages(self):
        hwpack = HardwarePack("ahwpack", "4")
        tf = self.get_tarfile(hwpack)
        self.assertHasPath(tf, "pkgs/Packages", content="")

    def test_creates_sources_list_dir(self):
        hwpack = HardwarePack("ahwpack", "4")
        tf = self.get_tarfile(hwpack)
        self.assertHasPath(tf, "sources.list.d", type=tarfile.DIRTYPE)

    def test_creates_sources_list_gpg_dir(self):
        hwpack = HardwarePack("ahwpack", "4")
        tf = self.get_tarfile(hwpack)
        self.assertHasPath(tf, "sources.list.d.gpg", type=tarfile.DIRTYPE)
