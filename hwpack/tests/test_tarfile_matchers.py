from StringIO import StringIO
import tarfile

from testtools import TestCase

from hwpack.better_tarfile import writeable_tarfile, standard_tarfile
from hwpack.tarfile_matchers import (
    TarfileHasFile,
    TarfileMissingPathMismatch,
    TarfileWrongValueMismatch,
    )


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
        with writeable_tarfile(backing_file) as tf:
            tf.create_file_from_string("foo", "")
        with standard_tarfile(backing_file) as tf:
            matcher = TarfileHasFile("foo")
            self.assertIs(None, matcher.match(tf))

    def test_mismatches_missing_path(self):
        backing_file = StringIO()
        with standard_tarfile(backing_file) as tf:
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
        with writeable_tarfile(backing_file) as tf:
            tf.create_file_from_string("foo", "")
        with standard_tarfile(backing_file) as tf:
            matcher = TarfileHasFile("foo", type=tarfile.DIRTYPE)
            mismatch = matcher.match(tf)
            self.assertValueMismatch(
                mismatch, tf, "foo", "type", tarfile.DIRTYPE,
                tarfile.REGTYPE)

    def test_mismatches_wrong_size(self):
        backing_file = StringIO()
        with writeable_tarfile(backing_file) as tf:
            tf.create_file_from_string("foo", "")
        with standard_tarfile(backing_file) as tf:
            matcher = TarfileHasFile("foo", size=1235)
            mismatch = matcher.match(tf)
            self.assertValueMismatch(
                mismatch, tf, "foo", "size", 1235, 0)

    def test_mismatches_wrong_mtime(self):
        backing_file = StringIO()
        with writeable_tarfile(backing_file, default_mtime=12345) as tf:
            tf.create_file_from_string("foo", "")
        with standard_tarfile(backing_file) as tf:
            matcher = TarfileHasFile("foo", mtime=54321)
            mismatch = matcher.match(tf)
            self.assertValueMismatch(
                mismatch, tf, "foo", "mtime", 54321, 12345)

    def test_mismatches_wrong_mode(self):
        backing_file = StringIO()
        with writeable_tarfile(backing_file) as tf:
            tf.create_file_from_string("foo", "")
        with standard_tarfile(backing_file) as tf:
            matcher = TarfileHasFile("foo", mode=0000)
            mismatch = matcher.match(tf)
            self.assertValueMismatch(
                mismatch, tf, "foo", "mode", 0000, 0644)
