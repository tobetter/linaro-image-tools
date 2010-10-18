from StringIO import StringIO
import tarfile

from testtools import TestCase

from hwpack.hardwarepack import HardwarePack, Metadata
from hwpack.packages import get_packages_file
from hwpack.testing import DummyFetchedPackage, HardwarePackHasFile, Not


class MetadataTests(TestCase):

    def test_name(self):
        metadata = Metadata("ahwpack", "3", "armel")
        self.assertEqual("ahwpack", metadata.name)

    def test_version(self):
        metadata = Metadata("ahwpack", "3", "armel")
        self.assertEqual("3", metadata.version)

    def test_version_with_whitespace(self):
        self.assertRaises(
            AssertionError, Metadata, "ahwpack", "3 (with extras)", "armel")

    def test_architecture(self):
        metadata = Metadata("ahwpack", "3", "armel")
        self.assertEqual("armel", metadata.architecture)

    def test_default_origin_is_None(self):
        metadata = Metadata("ahwpack", "4", "armel")
        self.assertEqual(None, metadata.origin)

    def test_origin(self):
        metadata = Metadata("ahwpack", "4", "armel", origin="linaro")
        self.assertEqual("linaro", metadata.origin)

    def test_default_maintainer_is_None(self):
        metadata = Metadata("ahwpack", "4", "armel")
        self.assertEqual(None, metadata.maintainer)

    def test_maintainer(self):
        metadata = Metadata(
            "ahwpack", "4", "armel", maintainer="Some maintainer")
        self.assertEqual("Some maintainer", metadata.maintainer)

    def test_default_support_is_None(self):
        metadata = Metadata("ahwpack", "4", "armel")
        self.assertEqual(None, metadata.support)

    def test_support(self):
        metadata = Metadata("ahwpack", "4", "armel", support="supported")
        self.assertEqual("supported", metadata.support)

    def test_str(self):
        metadata = Metadata("ahwpack", "4", "armel")
        self.assertEqual(
            "NAME=ahwpack\nVERSION=4\nARCHITECTURE=armel\n", str(metadata))

    def test_str_with_origin(self):
        metadata = Metadata("ahwpack", "4", "armel", origin="linaro")
        self.assertEqual(
            "NAME=ahwpack\nVERSION=4\nARCHITECTURE=armel\nORIGIN=linaro\n",
            str(metadata))

    def test_str_with_maintainer(self):
        metadata = Metadata(
            "ahwpack", "4", "armel", maintainer="Some Maintainer")
        self.assertEqual(
            "NAME=ahwpack\nVERSION=4\nARCHITECTURE=armel\n"
            "MAINTAINER=Some Maintainer\n",
            str(metadata))

    def test_str_with_support(self):
        metadata = Metadata("ahwpack", "4", "armel", support="unsupported")
        self.assertEqual(
            "NAME=ahwpack\nVERSION=4\nARCHITECTURE=armel\n"
            "SUPPORT=unsupported\n",
            str(metadata))

    def test_from_config(self):
        class Config:
            name = "foo"
            origin = "linaro"
            maintainer = "someone"
            support = "supported"
        config = Config()
        metadata = Metadata.from_config(config, "2.0", "i386")
        self.assertEqual(config.name, metadata.name)
        self.assertEqual(config.origin, metadata.origin)
        self.assertEqual(config.maintainer, metadata.maintainer)
        self.assertEqual(config.support, metadata.support)
        self.assertEqual("2.0", metadata.version)
        self.assertEqual("i386", metadata.architecture)


class HardwarePackTests(TestCase):

    def setUp(self):
        super(HardwarePackTests, self).setUp()
        self.metadata = Metadata("ahwpack", "4", "armel")

    def test_format_is_1_0(self):
        hwpack = HardwarePack(self.metadata)
        self.assertEqual("1.0", hwpack.FORMAT)

    def test_filename(self):
        hwpack = HardwarePack(self.metadata)
        self.assertEqual("hwpack_ahwpack_4_armel.tar.gz", hwpack.filename())

    def test_filename_with_support(self):
        metadata = Metadata("ahwpack", "4", "armel", support="supported")
        hwpack = HardwarePack(metadata)
        self.assertEqual(
            "hwpack_ahwpack_4_armel_supported.tar.gz", hwpack.filename())

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
            "ahwpack", "4", "armel", origin="linaro",
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

    def test_manifest_contains_package_info(self):
        package1 = DummyFetchedPackage("foo", "1.1")
        package2 = DummyFetchedPackage("bar", "1.2")
        hwpack = HardwarePack(self.metadata)
        hwpack.add_packages([package1, package2])
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf,
            HardwarePackHasFile("manifest", content="foo=1.1\nbar=1.2\n"))

    def test_creates_pkgs_dir(self):
        hwpack = HardwarePack(self.metadata)
        tf = self.get_tarfile(hwpack)
        self.assertThat(tf, HardwarePackHasFile("pkgs", type=tarfile.DIRTYPE))

    def test_adds_packages(self):
        package = DummyFetchedPackage("foo", "1.1")
        hwpack = HardwarePack(self.metadata)
        hwpack.add_packages([package])
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf,
            HardwarePackHasFile("pkgs/%s" % package.filename,
                content=package.content.read()))

    def test_adds_multiple_packages_at_once(self):
        package1 = DummyFetchedPackage("foo", "1.1")
        package2 = DummyFetchedPackage("bar", "1.1")
        hwpack = HardwarePack(self.metadata)
        hwpack.add_packages([package1, package2])
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf,
            HardwarePackHasFile("pkgs/%s" % package1.filename,
                content=package1.content.read()))
        self.assertThat(
            tf,
            HardwarePackHasFile("pkgs/%s" % package2.filename,
                content=package2.content.read()))

    def test_adds_multiple_in_multiple_steps(self):
        package1 = DummyFetchedPackage("foo", "1.1")
        package2 = DummyFetchedPackage("bar", "1.1")
        hwpack = HardwarePack(self.metadata)
        hwpack.add_packages([package1])
        hwpack.add_packages([package2])
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf,
            HardwarePackHasFile("pkgs/%s" % package1.filename,
                content=package1.content.read()))
        self.assertThat(
            tf,
            HardwarePackHasFile("pkgs/%s" % package2.filename,
                content=package2.content.read()))

    def test_add_packages_without_content_leaves_out_debs(self):
        package1 = DummyFetchedPackage("foo", "1.1", no_content=True)
        hwpack = HardwarePack(self.metadata)
        hwpack.add_packages([package1])
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf,
            Not(HardwarePackHasFile("pkgs/%s" % package1.filename)))

    def test_creates_Packages_file(self):
        hwpack = HardwarePack(self.metadata)
        tf = self.get_tarfile(hwpack)
        self.assertThat(tf, HardwarePackHasFile("pkgs/Packages"))

    def test_Packages_file_empty_with_no_packages(self):
        hwpack = HardwarePack(self.metadata)
        tf = self.get_tarfile(hwpack)
        self.assertThat(tf, HardwarePackHasFile("pkgs/Packages", content=""))

    def test_Packages_file_correct_contents_with_packages(self):
        package1 = DummyFetchedPackage("foo", "1.1")
        package2 = DummyFetchedPackage("bar", "1.1")
        hwpack = HardwarePack(self.metadata)
        hwpack.add_packages([package1, package2])
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf,
            HardwarePackHasFile(
                "pkgs/Packages",
                content=get_packages_file([package1, package2])))

    def test_Packages_file_empty_with_no_deb_content(self):
        package1 = DummyFetchedPackage("foo", "1.1", no_content=True)
        package2 = DummyFetchedPackage("bar", "1.1", no_content=True)
        hwpack = HardwarePack(self.metadata)
        hwpack.add_packages([package1, package2])
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf,
            HardwarePackHasFile("pkgs/Packages", content=""))

    def test_Packages_file_correct_content_with_some_deb_content(self):
        package1 = DummyFetchedPackage("foo", "1.1", no_content=True)
        package2 = DummyFetchedPackage("bar", "1.1")
        hwpack = HardwarePack(self.metadata)
        hwpack.add_packages([package1, package2])
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf,
            HardwarePackHasFile(
                "pkgs/Packages",
                content=get_packages_file([package2])))

    def test_creates_sources_list_dir(self):
        hwpack = HardwarePack(self.metadata)
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf, HardwarePackHasFile("sources.list.d", type=tarfile.DIRTYPE))

    def test_adds_sources_list_file(self):
        hwpack = HardwarePack(self.metadata)
        source = 'http://example.org/ ubuntu'
        hwpack.add_apt_sources({'ubuntu': source})
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf, HardwarePackHasFile("sources.list.d/ubuntu.list",
                content="deb " + source + "\n"))

    def test_adds_multiple_sources_list_files(self):
        hwpack = HardwarePack(self.metadata)
        source1 = 'http://example.org/ ubuntu main universe'
        source2 = 'http://example.org/ linaro'
        hwpack.add_apt_sources({'ubuntu': source1, 'linaro': source2})
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf, HardwarePackHasFile("sources.list.d/ubuntu.list",
                content="deb " + source1 + "\n"))
        self.assertThat(
            tf, HardwarePackHasFile("sources.list.d/linaro.list",
                content="deb " + source2 + "\n"))

    def test_overwrites_sources_list_file(self):
        hwpack = HardwarePack(self.metadata)
        old_source = 'http://example.org/ ubuntu'
        hwpack.add_apt_sources({'ubuntu': old_source})
        new_source = 'http://example.org/ ubuntu main universe'
        hwpack.add_apt_sources({'ubuntu': new_source})
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf, HardwarePackHasFile("sources.list.d/ubuntu.list",
                content="deb " + new_source + "\n"))

    def test_creates_sources_list_gpg_dir(self):
        hwpack = HardwarePack(self.metadata)
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf,
            HardwarePackHasFile("sources.list.d.gpg", type=tarfile.DIRTYPE))
