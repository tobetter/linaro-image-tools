from contextlib import contextmanager
from StringIO import StringIO
from tarfile import TarFile as StandardTarFile

from testtools import TestCase

from hwpack.better_tarfile import TarFile


@contextmanager
def writeable_tarfile(backing_file):
    tarfile = TarFile.open(mode="w", fileobj=backing_file)
    try:
        yield tarfile
    finally:
        tarfile.close()


@contextmanager
def standard_tarfile(backing_file, seek=True):
    if seek:
        backing_file.seek(0)
    tarfile = StandardTarFile.open(fileobj=backing_file)
    try:
        yield tarfile
    finally:
        tarfile.close()


class TarFileTests(TestCase):

    def test_creates_empty_tarfile(self):
        backing_file = StringIO()
        with writeable_tarfile(backing_file):
            pass
        with standard_tarfile(backing_file, seek=False) as tarfile:
            self.assertEqual([], tarfile.getnames())

    def test_add_file_from_string_adds_path(self):
        backing_file = StringIO()
        with writeable_tarfile(backing_file) as tarfile:
            tarfile.add_file_from_string("foo", "bar")
        with standard_tarfile(backing_file) as tarfile:
            self.assertEqual(["foo"], tarfile.getnames())

    def test_add_file_from_string_uses_content(self):
        backing_file = StringIO()
        with writeable_tarfile(backing_file) as tarfile:
            tarfile.add_file_from_string("foo", "bar")
        with standard_tarfile(backing_file) as tarfile:
            self.assertEqual("bar", tarfile.extractfile("foo").read())

    def test_add_file_from_string_sets_size(self):
        backing_file = StringIO()
        with writeable_tarfile(backing_file) as tarfile:
            tarfile.add_file_from_string("foo", "bar")
        with standard_tarfile(backing_file) as tarfile:
            self.assertEqual(3, tarfile.getmember("foo").size)

    def test_add_file_from_string_sets_mode(self):
        backing_file = StringIO()
        with writeable_tarfile(backing_file) as tarfile:
            tarfile.add_file_from_string("foo", "bar")
        with standard_tarfile(backing_file) as tarfile:
            self.assertEqual(0644, tarfile.getmember("foo").mode)
