from StringIO import StringIO
import tarfile

from testtools import TestCase

from hwpack.tarfile_matchers import (
    TarfileHasFile,
    TarfileMissingPathMismatch,
    TarfileWrongValueMismatch,
    )
from hwpack.testing import test_tarfile


class TarfileMissingPathMismatchTests(TestCase):

    def test_describe(self):
        mismatch = TarfileMissingPathMismatch("foo", "bar")
        self.assertEqual('"foo" has no path "bar"', mismatch.describe())


class TarfileWrongTypeMismatchTests(TestCase):

    def test_describe(self):
        mismatch = TarfileWrongValueMismatch("type", "foo", "bar", 1, 2)
        self.assertEqual(
            'The path "bar" in "foo" has type 2, expected 1',
            mismatch.describe())


class TarfileHasFileTests(TestCase):

    def test_str(self):
        matcher = TarfileHasFile("foo")
        self.assertEqual('tarfile has file "foo"', str(matcher))

    def test_matches(self):
        backing_file = StringIO()
        with test_tarfile(contents=[("foo", "")]) as tf:
            matcher = TarfileHasFile("foo")
            self.assertIs(None, matcher.match(tf))

    def test_mismatches_missing_path(self):
        backing_file = StringIO()
        with test_tarfile() as tf:
            matcher = TarfileHasFile("foo")
            self.assertIsInstance(
                matcher.match(tf), TarfileMissingPathMismatch)

    def assertValueMismatch(self, mismatch, tarball, path, attribute,
                            expected, actual):
        self.assertIsInstance(mismatch, TarfileWrongValueMismatch)
        self.assertEqual(attribute, mismatch.attribute)
        self.assertEqual(tarball, mismatch.tarball)
        self.assertEqual(path, mismatch.path)
        self.assertEqual(actual, mismatch.actual)
        self.assertEqual(expected, mismatch.expected)

    def test_mismatches_wrong_type(self):
        backing_file = StringIO()
        with test_tarfile(contents=[("foo", "")]) as tf:
            matcher = TarfileHasFile("foo", type=tarfile.DIRTYPE)
            mismatch = matcher.match(tf)
            self.assertValueMismatch(
                mismatch, tf, "foo", "type", tarfile.DIRTYPE,
                tarfile.REGTYPE)

    def test_mismatches_wrong_size(self):
        backing_file = StringIO()
        with test_tarfile(contents=[("foo", "")]) as tf:
            matcher = TarfileHasFile("foo", size=1235)
            mismatch = matcher.match(tf)
            self.assertValueMismatch(
                mismatch, tf, "foo", "size", 1235, 0)

    def test_mismatches_wrong_mtime(self):
        backing_file = StringIO()
        with test_tarfile(contents=[("foo", "")], default_mtime=12345) as tf:
            matcher = TarfileHasFile("foo", mtime=54321)
            mismatch = matcher.match(tf)
            self.assertValueMismatch(
                mismatch, tf, "foo", "mtime", 54321, 12345)

    def test_mismatches_wrong_mode(self):
        backing_file = StringIO()
        with test_tarfile(contents=[("foo", "")]) as tf:
            matcher = TarfileHasFile("foo", mode=0000)
            mismatch = matcher.match(tf)
            self.assertValueMismatch(
                mismatch, tf, "foo", "mode", 0000, 0644)

    def test_mismatches_wrong_linkname(self):
        backing_file = StringIO()
        with test_tarfile(contents=[("foo", "")]) as tf:
            matcher = TarfileHasFile("foo", linkname="somelink")
            mismatch = matcher.match(tf)
            self.assertValueMismatch(
                mismatch, tf, "foo", "linkname", "somelink", "")

    def test_mismatches_wrong_uid(self):
        backing_file = StringIO()
        with test_tarfile(contents=[("foo", "")], default_uid=100) as tf:
            matcher = TarfileHasFile("foo", uid=99)
            mismatch = matcher.match(tf)
            self.assertValueMismatch(
                mismatch, tf, "foo", "uid", 99, 100)

    def test_mismatches_wrong_gid(self):
        backing_file = StringIO()
        with test_tarfile(contents=[("foo", "")], default_gid=100) as tf:
            matcher = TarfileHasFile("foo", gid=99)
            mismatch = matcher.match(tf)
            self.assertValueMismatch(
                mismatch, tf, "foo", "gid", 99, 100)

    def test_mismatches_wrong_uname(self):
        backing_file = StringIO()
        with test_tarfile(
            contents=[("foo", "")], default_uname="someuser") as tf:
            matcher = TarfileHasFile("foo", uname="otheruser")
            mismatch = matcher.match(tf)
            self.assertValueMismatch(
                mismatch, tf, "foo", "uname", "otheruser", "someuser")

    def test_mismatches_wrong_gname(self):
        backing_file = StringIO()
        with test_tarfile(
            contents=[("foo", "")], default_gname="somegroup") as tf:
            matcher = TarfileHasFile("foo", gname="othergroup")
            mismatch = matcher.match(tf)
            self.assertValueMismatch(
                mismatch, tf, "foo", "gname", "othergroup", "somegroup")

    def test_mismatches_wrong_content(self):
        backing_file = StringIO()
        with test_tarfile(contents=[("foo", "somecontent")]) as tf:
            matcher = TarfileHasFile("foo", content="othercontent")
            mismatch = matcher.match(tf)
            self.assertValueMismatch(
                mismatch, tf, "foo", "content", "othercontent", "somecontent")
