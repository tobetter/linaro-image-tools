from testtools import TestCase
from testtools.matchers import (
    Equals,
    NotEquals,)
from hwpack.testing import (
    DummyFetchedPackage,
    MatchesPackage,
    MatchesStructure,
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
            observed, MatchesPackage.fromPackage(expected))

    def test_mismatch(self):
        observed = DummyFetchedPackage("foo", "1.1", depends="bar")
        expected = DummyFetchedPackage("foo", "1.1", depends="baz")
        self.assertRaises(AssertionError, self.assertThat, observed,
            MatchesPackage.fromPackage(expected))

    def test_skip_one_attribute(self):
        observed = DummyFetchedPackage("foo", "1.1", depends="bar")
        expected = DummyFetchedPackage("foo", "1.1", depends="baz")
        self.assertThat(
            observed,
            MatchesPackage.fromPackage(expected).update(depends=None))
