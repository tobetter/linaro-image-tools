from StringIO import StringIO
from tarfile import TarFile as StandardTarFile

from testtools import TestCase

from hwpack.better_tarfile import TarFile


class TarFileTests(TestCase):

    def test_creates_empty_tarfile(self):
        backing_file = StringIO()
        tarfile = TarFile.open(mode="w", fileobj=backing_file)
        tarfile.close()
        tarfile = StandardTarFile.open(fileobj=backing_file)
        self.assertEqual([], tarfile.getnames())

    def test_add_file_from_string_adds_path(self):
        backing_file = StringIO()
        tarfile = TarFile.open(mode="w", fileobj=backing_file)
        try:
            tarfile.add_file_from_string("foo", "bar")
        finally:
            tarfile.close()
        backing_file.seek(0)
        tarfile = StandardTarFile.open(fileobj=backing_file)
        self.assertEqual(["foo"], tarfile.getnames())
