import os
from StringIO import StringIO
import textwrap

from testtools import TestCase

from hwpack.packages import (
    FetchedPackage,
    get_packages_file,
    PackageFetcher,
    )
from hwpack.testing import (
    AptSourceFixture,
    DummyFetchedPackage,
    TestCaseWithFixtures,
    )


class GetPackagesFileTests(TestCase):

    def test_single_stanza(self):
        package = DummyFetchedPackage("foo", "1.1", architecture="armel")
        self.assertEqual(textwrap.dedent("""\
            Package: foo
            Version: 1.1
            Filename: %(filename)s
            Size: %(size)d
            Architecture: armel
            MD5sum: %(md5)s
            \n""" % {
                'filename': package.filename,
                'size': package.size,
                'md5': package.md5,
            }), get_packages_file([package]))

    def test_two_stanzas(self):
        package1 = DummyFetchedPackage("foo", "1.1")
        package2 = DummyFetchedPackage("bar", "1.2")
        self.assertEqual(
            get_packages_file([package1]) + get_packages_file([package2]),
            get_packages_file([package1, package2]))

    def test_with_depends(self):
        package = DummyFetchedPackage("foo", "1.1", depends="bar | baz")
        self.assertEqual(textwrap.dedent("""\
            Package: foo
            Version: 1.1
            Filename: %(filename)s
            Size: %(size)d
            Architecture: all
            Depends: bar | baz
            MD5sum: %(md5)s
            \n""" % {
                'filename': package.filename,
                'size': package.size,
                'md5': package.md5,
            }), get_packages_file([package]))


class FetchedPackageTests(TestCase):

    def test_attributes(self):
        package = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", StringIO("xxxx"), 4, "aaaa",
            "armel")
        self.assertEqual("foo", package.name)
        self.assertEqual("1.1", package.version)
        self.assertEqual("foo_1.1.deb", package.filename)
        self.assertEqual("xxxx", package.content.read())
        self.assertEqual(4, package.size)
        self.assertEqual("aaaa", package.md5)
        self.assertEqual("armel", package.architecture)

    def test_equal(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", StringIO("xxxx"), 4, "aaaa", "armel")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", StringIO("xxxx"), 4, "aaaa", "armel")
        self.assertEqual(package1, package2)

    def test_not_equal_different_name(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", StringIO("xxxx"), 4, "aaaa", "armel")
        package2 = FetchedPackage(
            "bar", "1.1", "foo_1.1.deb", StringIO("xxxx"), 4, "aaaa", "armel")
        self.assertNotEqual(package1, package2)

    def test_not_equal_different_version(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", StringIO("xxxx"), 4, "aaaa", "armel")
        package2 = FetchedPackage(
            "foo", "1.2", "foo_1.1.deb", StringIO("xxxx"), 4, "aaaa", "armel")
        self.assertNotEqual(package1, package2)

    def test_not_equal_different_filename(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", StringIO("xxxx"), 4, "aaaa", "armel")
        package2 = FetchedPackage(
            "foo", "1.1", "afoo_1.1.deb", StringIO("xxxx"), 4, "aaaa", "armel")
        self.assertNotEqual(package1, package2)

    def test_not_equal_different_content(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", StringIO("xxxx"), 4, "aaaa", "armel")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", StringIO("yyyy"), 4, "aaaa", "armel")
        self.assertNotEqual(package1, package2)

    def test_not_equal_different_size(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", StringIO("xxxx"), 4, "aaaa", "armel")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", StringIO("xxxx"), 5, "aaaa", "armel")
        self.assertNotEqual(package1, package2)

    def test_not_equal_different_md5(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", StringIO("xxxx"), 4, "aaaa", "armel")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", StringIO("xxxx"), 4, "bbbb", "armel")
        self.assertNotEqual(package1, package2)

    def test_not_equal_different_architecture(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", StringIO("xxxx"), 4, "aaaa", "armel")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", StringIO("xxxx"), 4, "aaaa", "i386")
        self.assertNotEqual(package1, package2)

    def test_equal_hash_equal(self):
        package1 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", StringIO("xxxx"), 4, "aaaa", "armel")
        package2 = FetchedPackage(
            "foo", "1.1", "foo_1.1.deb", StringIO("xxxx"), 4, "aaaa", "armel")
        self.assertEqual(hash(package1), hash(package2))


class PackageFetcherTests(TestCaseWithFixtures):

    def test_cleanup_removes_tempdir(self):
        fetcher = PackageFetcher([])
        fetcher.prepare()
        tempdir = fetcher.tempdir
        fetcher.cleanup()
        self.assertFalse(os.path.exists(tempdir))

    def test_cleanup_ignores_missing_tempdir(self):
        fetcher = PackageFetcher([])
        fetcher.prepare()
        tempdir = fetcher.tempdir
        fetcher.cleanup()
        # Check that there is no problem removing it again
        fetcher.cleanup()

    def test_cleanup_before_prepare(self):
        fetcher = PackageFetcher([])
        # Check that there is no problem cleaning up before we start
        fetcher.cleanup()

    def test_prepare_creates_tempdir(self):
        fetcher = PackageFetcher([])
        self.addCleanup(fetcher.cleanup)
        fetcher.prepare()
        self.assertTrue(os.path.isdir(fetcher.tempdir))

    def test_prepare_creates_var_lib_dpkg_status_file(self):
        fetcher = PackageFetcher([])
        self.addCleanup(fetcher.cleanup)
        fetcher.prepare()
        self.assertEqual(
            '',
            open(os.path.join(
                fetcher.tempdir, "var", "lib", "dpkg", "status")).read())

    def test_prepare_creates_var_cache_apt_archives_partial_dir(self):
        fetcher = PackageFetcher([])
        self.addCleanup(fetcher.cleanup)
        fetcher.prepare()
        self.assertTrue(
            os.path.isdir(os.path.join(
                fetcher.tempdir, "var", "cache", "apt", "archives",
                "partial")))

    def test_prepare_creates_var_lib_apt_lists_partial_dir(self):
        fetcher = PackageFetcher([])
        self.addCleanup(fetcher.cleanup)
        fetcher.prepare()
        self.assertTrue(
            os.path.isdir(os.path.join(
                fetcher.tempdir, "var", "lib", "apt", "lists", "partial")))

    def test_prepare_creates_etc_apt_sources_list_file(self):
        source1 = self.useFixture(AptSourceFixture([]))
        source2 = self.useFixture(AptSourceFixture([]))
        fetcher = PackageFetcher(
            [source1.sources_entry, source2.sources_entry])
        self.addCleanup(fetcher.cleanup)
        fetcher.prepare()
        self.assertEqual(
            "deb %s\ndeb %s\n" % (
                source1.sources_entry, source2.sources_entry),
            open(os.path.join(
                fetcher.tempdir, "etc", "apt", "sources.list")).read())

    def test_prepare_with_arch_creates_etc_apt_apt_conf(self):
        fetcher = PackageFetcher([], architecture="arch")
        self.addCleanup(fetcher.cleanup)
        fetcher.prepare()
        self.assertEqual(
            'Apt {\nArchitecture "arch";\n}\n',
            open(os.path.join(
                fetcher.tempdir, "etc", "apt", "apt.conf")).read())

    def test_context_manager(self):
        # A smoketest that PackageFetcher can be used as a context
        # manager
        with PackageFetcher([]) as fetcher:
            tempdir = fetcher.tempdir
            self.assertTrue(os.path.isdir(tempdir))
        self.assertFalse(os.path.exists(tempdir))

    def get_fetcher(self, sources, architecture=None):
        fetcher = PackageFetcher(
            [s.sources_entry for s in sources], architecture=architecture)
        self.addCleanup(fetcher.cleanup)
        fetcher.prepare()
        return fetcher

    def test_fetch_packages_not_found_because_no_sources(self):
        fetcher = self.get_fetcher([])
        self.assertRaises(KeyError, fetcher.fetch_packages, ["nothere"])

    def test_fetch_packages_not_found_because_not_in_sources(self):
        available_package = DummyFetchedPackage("foo", "1.0")
        source = self.useFixture(AptSourceFixture([available_package]))
        fetcher = self.get_fetcher([source])
        self.assertRaises(KeyError, fetcher.fetch_packages, ["nothere"])

    def test_fetch_packages_not_found_one_of_two_missing(self):
        available_package = DummyFetchedPackage("foo", "1.0")
        source = self.useFixture(AptSourceFixture([available_package]))
        fetcher = self.get_fetcher([source])
        self.assertRaises(
            KeyError, fetcher.fetch_packages, ["foo", "nothere"])

    def test_fetch_packages_fetches_no_packages(self):
        available_package = DummyFetchedPackage("foo", "1.0")
        source = self.useFixture(AptSourceFixture([available_package]))
        fetcher = self.get_fetcher([source])
        self.assertEqual(0, len(fetcher.fetch_packages([])))

    def test_fetch_packages_fetches_single_package(self):
        available_package = DummyFetchedPackage("foo", "1.0")
        source = self.useFixture(AptSourceFixture([available_package]))
        fetcher = self.get_fetcher([source])
        self.assertEqual(1, len(fetcher.fetch_packages(["foo"])))

    def test_fetch_packages_fetches_correct_package(self):
        available_package = DummyFetchedPackage("foo", "1.0")
        source = self.useFixture(AptSourceFixture([available_package]))
        fetcher = self.get_fetcher([source])
        self.assertEqual(
            available_package, fetcher.fetch_packages(["foo"])[0])

    def test_fetch_packages_fetches_multiple_packages(self):
        available_packages = [
            DummyFetchedPackage("bar", "1.0"),
            DummyFetchedPackage("foo", "1.0"),
        ]
        source = self.useFixture(AptSourceFixture(available_packages))
        fetcher = self.get_fetcher([source])
        self.assertEqual(2, len(fetcher.fetch_packages(["foo", "bar"])))

    def test_fetch_packages_fetches_multiple_packages_correctly(self):
        available_packages = [
            DummyFetchedPackage("foo", "1.0"),
            DummyFetchedPackage("bar", "1.0"),
        ]
        source = self.useFixture(AptSourceFixture(available_packages))
        fetcher = self.get_fetcher([source])
        fetched = fetcher.fetch_packages(["foo", "bar"])
        self.assertEqual(available_packages[0], fetched[0])
        self.assertEqual(available_packages[1], fetched[1])

    def test_fetch_packages_fetches_newest(self):
        available_packages = [
            DummyFetchedPackage("bar", "1.0"),
            DummyFetchedPackage("bar", "1.1"),
        ]
        source = self.useFixture(AptSourceFixture(available_packages))
        fetcher = self.get_fetcher([source])
        fetched = fetcher.fetch_packages(["bar"])
        self.assertEqual(available_packages[1], fetched[0])

    def test_fetch_packages_fetches_newest_from_multiple_sources(self):
        old_source_packages = [DummyFetchedPackage("bar", "1.0")]
        new_source_packages = [DummyFetchedPackage("bar", "1.1")]
        old_source = self.useFixture(AptSourceFixture(old_source_packages))
        new_source = self.useFixture(AptSourceFixture(new_source_packages))
        fetcher = self.get_fetcher([old_source, new_source])
        fetched = fetcher.fetch_packages(["bar"])
        self.assertEqual(new_source_packages[0], fetched[0])

    def test_fetch_package_records_correct_architecture(self):
        available_package = DummyFetchedPackage(
            "foo", "1.0", architecture="nonexistant")
        source = self.useFixture(AptSourceFixture([available_package]))
        fetcher = self.get_fetcher([source], architecture="nonexistant")
        self.assertEqual(
            "nonexistant", fetcher.fetch_packages(["foo"])[0].architecture)

    def test_fetch_package_fetches_from_correct_architecture(self):
        wanted_package = DummyFetchedPackage(
            "foo", "1.0", architecture="arch1")
        unwanted_package = DummyFetchedPackage(
            "foo", "1.1", architecture="arch2")
        source = self.useFixture(
            AptSourceFixture([wanted_package, unwanted_package]))
        fetcher = self.get_fetcher([source], architecture="arch1")
        self.assertEqual(
            wanted_package, fetcher.fetch_packages(["foo"])[0])
