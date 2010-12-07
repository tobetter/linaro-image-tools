from testtools import TestCase
from testtools.matchers import (
    Equals,
    NotEquals,)
from hwpack.testing import (
    DummyFetchedPackage,
    MatchesAsPackagesFile,
    MatchesPackage,
    MatchesStructure,
    MatchesSetwise,
    parse_packages_file_content,
    )
from hwpack.packages import (
    get_packages_file,
    )

class TestMatchesStructure(TestCase):

    class SimpleClass:
        def __init__(self, x):
            self.x = x

    def test_matches(self):
        self.assertThat(
            self.SimpleClass(1), MatchesStructure(x=Equals(1)))

    def test_mismatch(self):
        self.assertRaises(
            AssertionError, self.assertThat, self.SimpleClass(1),
            MatchesStructure(x=NotEquals(1)))

    def test_fromExample(self):
        self.assertThat(
            self.SimpleClass(1),
            MatchesStructure.fromExample(self.SimpleClass(1), 'x'))

    def test_update(self):
        self.assertThat(
            self.SimpleClass(1),
            MatchesStructure(x=NotEquals(1)).update(x=Equals(1)))

    def test_update_none(self):
        self.assertThat(
            self.SimpleClass(1),
            MatchesStructure(x=Equals(1), y=NotEquals(42)).update(
                y=None))


class TestMatchesPackage(TestCase):

    def test_simple(self):
        observed = DummyFetchedPackage("foo", "1.1", architecture="armel")
        expected = DummyFetchedPackage("foo", "1.1", architecture="armel")
        self.assertThat(
            observed, MatchesPackage(expected))

    def test_mismatch(self):
        observed = DummyFetchedPackage("foo", "1.1", depends="bar")
        expected = DummyFetchedPackage("foo", "1.1", depends="baz")
        self.assertRaises(AssertionError, self.assertThat, observed,
            MatchesPackage(expected))

    def test_skip_one_attribute(self):
        observed = DummyFetchedPackage("foo", "1.1", depends="bar")
        expected = DummyFetchedPackage("foo", "1.1", depends="baz")
        self.assertThat(
            observed,
            MatchesPackage(expected).update(depends=None))


class TestMatchesSetwise(TestCase):

    def test_matches(self):
        self.assertThat(
            [2, 1], MatchesSetwise(Equals(1), Equals(2)))

    def test_mismatches(self):
        self.assertRaises(AssertionError, self.assertThat,
            [2, 3], MatchesSetwise(Equals(1), Equals(2)))

class TestParsePackagesFileContent(TestCase):

    def test_one(self):
        observed = DummyFetchedPackage("foo", "1.1")
        packages_content = get_packages_file([observed])
        parsed = parse_packages_file_content(packages_content)
        self.assertThat(len(parsed), Equals(1))
        self.assertThat(parsed[0], MatchesPackage(observed))

    def test_several(self):
        observed1 = DummyFetchedPackage("foo", "1.1")
        observed2 = DummyFetchedPackage("bar", "1.2")
        observed3 = DummyFetchedPackage("baz", "1.5")
        packages_content = get_packages_file(
            [observed1, observed2, observed3])
        parsed = parse_packages_file_content(packages_content)
        self.assertThat(parsed, MatchesSetwise(
            MatchesPackage(observed3),
            MatchesPackage(observed2),
            MatchesPackage(observed1)))


class TestMatchesAsPackagesFile(TestCase):

    def test_one(self):
        observed = DummyFetchedPackage("foo", "1.1")
        packages_content = get_packages_file([observed])
        self.assertThat(
            packages_content,
            MatchesAsPackagesFile(
                MatchesPackage(observed)))

    def test_ignore_one_md5(self):
        # This is what I actually care about: being able to specify that a
        # packages file matches a set of packages, ignoring just a few
        # details on just one package.
        observed1 = DummyFetchedPackage("foo", "1.1")
        observed2 = DummyFetchedPackage("bar", "1.2")
        observed3 = DummyFetchedPackage("baz", "1.5")
        packages_content = get_packages_file(
            [observed1, observed2, observed3])
        oldmd5 = observed3.md5
        observed3._content = ''.join(reversed(observed3._content_str()))
        self.assertNotEqual(oldmd5, observed3.md5)
        self.assertThat(packages_content, MatchesAsPackagesFile(
            MatchesPackage(observed1),
            MatchesPackage(observed2),
            MatchesPackage(observed3).update(md5=None)))
