# Copyright (C) 2010, 2011 Linaro
#
# Author: James Westby <james.westby@linaro.org>
#
# This file is part of Linaro Image Tools.
#
# Linaro Image Tools is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# Linaro Image Tools is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Linaro Image Tools; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
# USA.

import doctest
import re
from StringIO import StringIO
import sys

from testtools import TestCase
from testtools.matchers import (
    Annotate,
    Equals,
    Mismatch,
    NotEquals,
)
from linaro_image_tools.hwpack.testing import (
    DummyFetchedPackage,
    EachOf,
    MatchesAsPackagesFile,
    MatchesPackage,
    MatchesPackageRelationshipList,
    MatchesStructure,
    MatchesSetwise,
    parse_packages_file_content,
)
from linaro_image_tools.hwpack.packages import (
    get_packages_file,
)


def run_doctest(obj, name):
    p = doctest.DocTestParser()
    t = p.get_doctest(
        obj.__doc__, sys.modules[obj.__module__].__dict__, name, '', 0)
    r = doctest.DocTestRunner()
    output = StringIO()
    r.run(t, out=output.write)
    return r.failures, output.getvalue()


class TestEachOf(TestCase):

    def test_docstring(self):
        failure_count, output = run_doctest(EachOf, "EachOf")
        if failure_count:
            self.fail("Doctest failed with %s" % output)


class TestMatchesPackageRelationshipList(TestCase):

    def test_docstring(self):
        failure_count, output = run_doctest(
            MatchesPackageRelationshipList, "MatchesPackageRelationshipList")
        if failure_count:
            self.fail("Doctest failed with %s" % output)


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


class MatchesRegex(object):

    def __init__(self, pattern, flags=0):
        self.pattern = pattern
        self.flags = flags

    def match(self, value):
        if not re.match(self.pattern, value, self.flags):
            return Mismatch("%r did not match %r" % (self.pattern, value))


class TestMatchesSetwise(TestCase):

    def assertMismatchWithDescriptionMatching(self, value, matcher,
                                              description_matcher):
        mismatch = matcher.match(value)
        if mismatch is None:
            self.fail("%s matched %s" % (matcher, value))
        actual_description = mismatch.describe()
        self.assertThat(
            actual_description,
            Annotate(
                "%s matching %s" % (matcher, value),
                description_matcher))

    def test_matches(self):
        self.assertIs(
            None, MatchesSetwise(Equals(1), Equals(2)).match([2, 1]))

    def test_mismatches(self):
        self.assertMismatchWithDescriptionMatching(
            [2, 3], MatchesSetwise(Equals(1), Equals(2)),
            MatchesRegex('.*There was 1 mismatch$', re.S))

    def test_too_many_matchers(self):
        self.assertMismatchWithDescriptionMatching(
            [2, 3], MatchesSetwise(Equals(1), Equals(2), Equals(3)),
            Equals('There was 1 matcher left over: Equals(1)'))

    def test_too_many_values(self):
        self.assertMismatchWithDescriptionMatching(
            [1, 2, 3], MatchesSetwise(Equals(1), Equals(2)),
            Equals('There was 1 value left over: [3]'))

    def test_two_too_many_matchers(self):
        self.assertMismatchWithDescriptionMatching(
            [3], MatchesSetwise(Equals(1), Equals(2), Equals(3)),
            MatchesRegex(
                'There were 2 matchers left over: Equals\([12]\), '
                'Equals\([12]\)'))

    def test_two_too_many_values(self):
        self.assertMismatchWithDescriptionMatching(
            [1, 2, 3, 4], MatchesSetwise(Equals(1), Equals(2)),
            MatchesRegex(
                'There were 2 values left over: \[[34], [34]\]'))

    def test_mismatch_and_too_many_matchers(self):
        self.assertMismatchWithDescriptionMatching(
            [2, 3], MatchesSetwise(Equals(0), Equals(1), Equals(2)),
            MatchesRegex(
                '.*There was 1 mismatch and 1 extra matcher: Equals\([01]\)',
                re.S))

    def test_mismatch_and_too_many_values(self):
        self.assertMismatchWithDescriptionMatching(
            [2, 3, 4], MatchesSetwise(Equals(1), Equals(2)),
            MatchesRegex(
                '.*There was 1 mismatch and 1 extra value: \[[34]\]',
                re.S))

    def test_mismatch_and_two_too_many_matchers(self):
        self.assertMismatchWithDescriptionMatching(
            [3, 4], MatchesSetwise(
                Equals(0), Equals(1), Equals(2), Equals(3)),
            MatchesRegex(
                '.*There was 1 mismatch and 2 extra matchers: '
                'Equals\([012]\), Equals\([012]\)', re.S))

    def test_mismatch_and_two_too_many_values(self):
        self.assertMismatchWithDescriptionMatching(
            [2, 3, 4, 5], MatchesSetwise(Equals(1), Equals(2)),
            MatchesRegex(
                '.*There was 1 mismatch and 2 extra values: \[[145], [145]\]',
                re.S))


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
