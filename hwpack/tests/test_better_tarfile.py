from StringIO import StringIO
import tarfile

from testtools import TestCase

from hwpack.better_tarfile import writeable_tarfile, standard_tarfile


class TarFileTests(TestCase):

    def test_creates_empty_tarfile(self):
        backing_file = StringIO()
        with writeable_tarfile(backing_file):
            pass
        with standard_tarfile(backing_file, seek=False) as tf:
            self.assertEqual([], tf.getnames())

    def test_create_file_from_string_adds_path(self):
        backing_file = StringIO()
        with writeable_tarfile(backing_file) as tf:
            tf.create_file_from_string("foo", "bar")
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(["foo"], tf.getnames())

    def test_create_file_from_string_uses_content(self):
        backing_file = StringIO()
        with writeable_tarfile(backing_file) as tf:
            tf.create_file_from_string("foo", "bar")
        with standard_tarfile(backing_file) as tf:
            self.assertEqual("bar", tf.extractfile("foo").read())

    def test_create_file_from_string_sets_size(self):
        backing_file = StringIO()
        with writeable_tarfile(backing_file) as tf:
            tf.create_file_from_string("foo", "bar")
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(3, tf.getmember("foo").size)

    def test_create_file_from_string_sets_mode(self):
        backing_file = StringIO()
        with writeable_tarfile(backing_file) as tf:
            tf.create_file_from_string("foo", "bar")
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(0644, tf.getmember("foo").mode)

    def test_create_file_from_string_sets_type(self):
        backing_file = StringIO()
        with writeable_tarfile(backing_file) as tf:
            tf.create_file_from_string("foo", "bar")
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(tarfile.REGTYPE, tf.getmember("foo").type)

    def test_create_file_from_string_sets_linkname(self):
        backing_file = StringIO()
        with writeable_tarfile(backing_file) as tf:
            tf.create_file_from_string("foo", "bar")
        with standard_tarfile(backing_file) as tf:
            self.assertEqual('', tf.getmember("foo").linkname)

    def test_create_file_uses_default_mtime(self):
        now = 126793
        backing_file = StringIO()
        with writeable_tarfile(backing_file, default_mtime=now) as tf:
            tf.create_file_from_string("foo", "bar")
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(now, tf.getmember("foo").mtime)

    def test_create_file_uses_default_uid(self):
        uid = 1259
        backing_file = StringIO()
        with writeable_tarfile(backing_file, default_uid=uid) as tf:
            tf.create_file_from_string("foo", "bar")
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(uid, tf.getmember("foo").uid)

    def test_create_file_uses_default_gid(self):
        gid = 2259
        backing_file = StringIO()
        with writeable_tarfile(backing_file, default_gid=gid) as tf:
            tf.create_file_from_string("foo", "bar")
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(gid, tf.getmember("foo").gid)

    def test_create_file_uses_default_uname(self):
        uname = "someperson"
        backing_file = StringIO()
        with writeable_tarfile(backing_file, default_uname=uname) as tf:
            tf.create_file_from_string("foo", "bar")
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(uname, tf.getmember("foo").uname)

    def test_create_file_uses_default_gname(self):
        gname = "somegroup"
        backing_file = StringIO()
        with writeable_tarfile(backing_file, default_gname=gname) as tf:
            tf.create_file_from_string("foo", "bar")
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(gname, tf.getmember("foo").gname)

    def test_create_dir_adds_path(self):
        backing_file = StringIO()
        with writeable_tarfile(backing_file) as tf:
            tf.create_dir("foo")
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(["foo"], tf.getnames())

    def test_create_dir_sets_name(self):
        backing_file = StringIO()
        with writeable_tarfile(backing_file) as tf:
            tf.create_dir("foo")
        with standard_tarfile(backing_file) as tf:
            self.assertEqual("foo", tf.getmember("foo").name)

    def test_create_dir_sets_type(self):
        backing_file = StringIO()
        with writeable_tarfile(backing_file) as tf:
            tf.create_dir("foo")
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(tarfile.DIRTYPE, tf.getmember("foo").type)

    def test_create_dir_sets_size(self):
        backing_file = StringIO()
        with writeable_tarfile(backing_file) as tf:
            tf.create_dir("foo")
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(0, tf.getmember("foo").size)

    def test_create_dir_sets_mode(self):
        backing_file = StringIO()
        with writeable_tarfile(backing_file) as tf:
            tf.create_dir("foo")
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(0755, tf.getmember("foo").mode)

    def test_create_dir_sets_linkname(self):
        backing_file = StringIO()
        with writeable_tarfile(backing_file) as tf:
            tf.create_dir("foo")
        with standard_tarfile(backing_file) as tf:
            self.assertEqual('', tf.getmember("foo").linkname)

    def test_create_dir_uses_default_mtime(self):
        now = 126793
        backing_file = StringIO()
        with writeable_tarfile(backing_file, default_mtime=now) as tf:
            tf.create_dir("foo")
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(now, tf.getmember("foo").mtime)

    def test_create_dir_uses_default_uid(self):
        uid = 1259
        backing_file = StringIO()
        with writeable_tarfile(backing_file, default_uid=uid) as tf:
            tf.create_dir("foo")
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(uid, tf.getmember("foo").uid)

    def test_create_dir_uses_default_gid(self):
        gid = 2259
        backing_file = StringIO()
        with writeable_tarfile(backing_file, default_gid=gid) as tf:
            tf.create_dir("foo")
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(gid, tf.getmember("foo").gid)

    def test_create_dir_uses_default_uname(self):
        uname = "someperson"
        backing_file = StringIO()
        with writeable_tarfile(backing_file, default_uname=uname) as tf:
            tf.create_dir("foo")
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(uname, tf.getmember("foo").uname)

    def test_create_dir_uses_default_gname(self):
        gname = "somegroup"
        backing_file = StringIO()
        with writeable_tarfile(backing_file, default_gname=gname) as tf:
            tf.create_dir("foo")
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(gname, tf.getmember("foo").gname)
