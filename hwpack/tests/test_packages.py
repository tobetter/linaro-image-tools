import hashlib
import os
import shutil
import tempfile

from testtools import TestCase

from hwpack.packages import PackageFetcher


class Package(object):

    def __init__(self, name, version, architecture="all"):
        self.name = name
        self.version = version
        self.architecture = architecture

    @property
    def filename(self):
        return "%s_%s_%s.deb" % (self.name, self.version, self.architecture)

    @property
    def content(self):
        return "Content of %s" % self.filename


class AptSource(object):

    def __init__(self, packages):
        self.packages = packages

    def setUp(self):
        self.rootdir = tempfile.mkdtemp(prefix="hwpack-apt-source-")
        for package in self.packages:
            with open(
                os.path.join(self.rootdir, package.filename), 'wb') as f:
                f.write(package.content)
        with open(os.path.join(self.rootdir, "Packages"), 'wb') as f:
            for package in self.packages:
                f.write('Package: %s\n' % package.name)
                f.write('Version: %s\n' % package.version)
                f.write('Filename: %s\n' % package.filename)
                f.write('Size: %d\n' % len(package.content))
                f.write('Architecture: %s\n' % package.architecture)
                md5sum = hashlib.md5()
                md5sum.update(package.content)
                f.write('MD5sum: %s\n' % md5sum.hexdigest())
                f.write('\n')

    def tearDown(self):
        if os.path.exists(self.rootdir):
            shutil.rmtree(self.rootdir)

    @property
    def sources_entry(self):
        return "file:" + os.path.abspath(self.rootdir) +" ./"


class PackageFetcherTests(TestCase):

    def useFixture(self, fixture):
        self.addCleanup(fixture.tearDown)
        fixture.setUp()
        return fixture

    def test_fetch_packages_not_found_because_no_sources(self):
        fetcher = PackageFetcher([])
        self.addCleanup(fetcher.cleanup)
        self.assertRaises(KeyError, fetcher.fetch_packages, ["nothere"])

    def test_fetch_packages_not_found_because_not_in_sources(self):
        available_package = Package("foo", "1.0")
        source = self.useFixture(AptSource([available_package]))
        fetcher = PackageFetcher([source.sources_entry])
        self.addCleanup(fetcher.cleanup)
        self.assertRaises(KeyError, fetcher.fetch_packages, ["nothere"])

    def test_fetch_packages_not_found_one_of_two_missing(self):
        available_package = Package("foo", "1.0")
        source = self.useFixture(AptSource([available_package]))
        fetcher = PackageFetcher([source.sources_entry])
        self.addCleanup(fetcher.cleanup)
        self.assertRaises(
            KeyError, fetcher.fetch_packages, ["foo", "nothere"])

    def test_fetch_packges_fetches_no_packages(self):
        available_package = Package("foo", "1.0")
        source = self.useFixture(AptSource([available_package]))
        fetcher = PackageFetcher([source.sources_entry])
        self.addCleanup(fetcher.cleanup)
        self.assertEqual(0, len(fetcher.fetch_packages([])))

    def test_fetch_packges_fetches_single_package(self):
        available_package = Package("foo", "1.0")
        source = self.useFixture(AptSource([available_package]))
        fetcher = PackageFetcher([source.sources_entry])
        self.addCleanup(fetcher.cleanup)
        self.assertEqual(1, len(fetcher.fetch_packages(["foo"])))

    def test_fetch_packges_fetches_correct_filename(self):
        available_package = Package("foo", "1.0")
        source = self.useFixture(AptSource([available_package]))
        fetcher = PackageFetcher([source.sources_entry])
        self.addCleanup(fetcher.cleanup)
        self.assertEqual(
            [available_package.filename],
            fetcher.fetch_packages(["foo"]).keys())

    def test_fetch_packges_fetches_correct_contents(self):
        available_package = Package("foo", "1.0")
        source = self.useFixture(AptSource([available_package]))
        fetcher = PackageFetcher([source.sources_entry])
        self.addCleanup(fetcher.cleanup)
        self.assertEqual(
            available_package.content,
            fetcher.fetch_packages(
                ["foo"])[available_package.filename].read())

    def test_fetch_packges_fetches_multiple_packages(self):
        available_packages = [Package("bar", 1.0), Package("foo", "1.0")]
        source = self.useFixture(AptSource(available_packages))
        fetcher = PackageFetcher([source.sources_entry])
        self.addCleanup(fetcher.cleanup)
        self.assertEqual(2, len(fetcher.fetch_packages(["foo", "bar"])))

    def test_fetch_packges_fetches_multiple_packages_correctly(self):
        available_packages = [Package("bar", 1.0), Package("foo", "1.0")]
        source = self.useFixture(AptSource(available_packages))
        fetcher = PackageFetcher([source.sources_entry])
        self.addCleanup(fetcher.cleanup)
        fetched_contents = fetcher.fetch_packages(["foo", "bar"])
        self.assertEqual(
            dict([(p.filename, p.content) for p in available_packages]),
            dict([(fn, fetched_contents[fn].read())
                for fn in fetched_contents]))
