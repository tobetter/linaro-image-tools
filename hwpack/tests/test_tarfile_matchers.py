from StringIO import StringIO
import tarfile

from testtools import TestCase

from hwpack.better_tarfile import writeable_tarfile, standard_tarfile
from hwpack.tarfile_matchers import (
    TarfileHasFile,
    TarfileMissingPathMismatch,
    TarfileWrongTypeMismatch,
    )


class TarfileMissingPathMismatchTests(TestCase):

    def test_describe(self):
        mismatch = TarfileMissingPathMismatch("foo", "bar")
        self.assertEqual('"foo" has no path "bar"', mismatch.describe())


class TarfileWrongTypeMismatchTests(TestCase):

    def test_describe(self):
        mismatch = TarfileWrongTypeMismatch("foo", "bar", 1, 2)
        self.assertEqual(
            'The path "bar" in "foo" has type 2, not type 1',
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

    def test_mismatches_wrong_type(self):
        backing_file = StringIO()
        with writeable_tarfile(backing_file) as tf:
            tf.create_file_from_string("foo", "")
        with standard_tarfile(backing_file) as tf:
            matcher = TarfileHasFile("foo", type=tarfile.DIRTYPE)
            self.assertIsInstance(
                matcher.match(tf), TarfileWrongTypeMismatch)
