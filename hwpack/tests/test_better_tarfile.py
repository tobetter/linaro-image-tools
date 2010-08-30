from contextlib import contextmanager
from StringIO import StringIO
import tarfile
from tarfile import TarFile as StandardTarFile

from testtools import TestCase

from hwpack.better_tarfile import TarFile


@contextmanager
def writeable_tarfile(backing_file, **kwargs):
    tf = TarFile.open(mode="w", fileobj=backing_file, **kwargs)
    try:
        yield tf
    finally:
        tf.close()


@contextmanager
def standard_tarfile(backing_file, seek=True):
    if seek:
        backing_file.seek(0)
    tf = StandardTarFile.open(fileobj=backing_file)
    try:
        yield tf
    finally:
        tf.close()


class TarFileTests(TestCase):

    def test_creates_empty_tarfile(self):
        backing_file = StringIO()
        with writeable_tarfile(backing_file):
            pass
        with standard_tarfile(backing_file, seek=False) as tf:
            self.assertEqual([], tf.getnames())

    def test_add_file_from_string_adds_path(self):
        backing_file = StringIO()
        with writeable_tarfile(backing_file) as tf:
            tf.add_file_from_string("foo", "bar")
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(["foo"], tf.getnames())

    def test_add_file_from_string_uses_content(self):
        backing_file = StringIO()
        with writeable_tarfile(backing_file) as tf:
            tf.add_file_from_string("foo", "bar")
        with standard_tarfile(backing_file) as tf:
            self.assertEqual("bar", tf.extractfile("foo").read())

    def test_add_file_from_string_sets_size(self):
        backing_file = StringIO()
        with writeable_tarfile(backing_file) as tf:
            tf.add_file_from_string("foo", "bar")
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(3, tf.getmember("foo").size)

    def test_add_file_from_string_sets_mode(self):
        backing_file = StringIO()
        with writeable_tarfile(backing_file) as tf:
            tf.add_file_from_string("foo", "bar")
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(0644, tf.getmember("foo").mode)

    def test_add_file_from_string_sets_type(self):
        backing_file = StringIO()
        with writeable_tarfile(backing_file) as tf:
            tf.add_file_from_string("foo", "bar")
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(tarfile.REGTYPE, tf.getmember("foo").type)

    def test_add_file_from_string_sets_linkname(self):
        backing_file = StringIO()
        with writeable_tarfile(backing_file) as tf:
            tf.add_file_from_string("foo", "bar")
        with standard_tarfile(backing_file) as tf:
            self.assertEqual('', tf.getmember("foo").linkname)

    def test_add_file_uses_default_mtime(self):
        now = 126793
        backing_file = StringIO()
        with writeable_tarfile(backing_file, default_mtime=now) as tf:
            tf.add_file_from_string("foo", "bar")
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(now, tf.getmember("foo").mtime)

    def test_add_file_uses_default_uid(self):
        uid = 1259
        backing_file = StringIO()
        with writeable_tarfile(backing_file, default_uid=uid) as tf:
            tf.add_file_from_string("foo", "bar")
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(uid, tf.getmember("foo").uid)
