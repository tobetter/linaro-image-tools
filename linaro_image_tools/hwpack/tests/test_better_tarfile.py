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

from contextlib import contextmanager
from StringIO import StringIO
import tarfile

from testtools import TestCase

from linaro_image_tools.hwpack.better_tarfile import writeable_tarfile


@contextmanager
def standard_tarfile(backing_file, mode="r", seek=True):
    """A context manager to open a stdlib tarfile.

    :param backing_file: the file object to take the tarfile
        contents from.
    :param mode: the mode to open the tarfile with.
    :param seek: whether to seek the backing file to 0 before
        opening.
    """
    if seek:
        backing_file.seek(0)
    tf = tarfile.TarFile.open(mode=mode, fileobj=backing_file)
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

    def create_simple_tarball(self, contents, **kwargs):
        backing_file = StringIO()
        with writeable_tarfile(backing_file, **kwargs) as tf:
            for path, content in contents:
                if path[-1] == '/':
                    tf.create_dir(path)
                else:
                    tf.create_file_from_string(path, content)
        return backing_file

    def test_create_file_from_string_adds_path(self):
        backing_file = self.create_simple_tarball([("foo", "bar")])
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(["foo"], tf.getnames())

    def test_create_file_from_string_uses_content(self):
        backing_file = self.create_simple_tarball([("foo", "bar")])
        with standard_tarfile(backing_file) as tf:
            self.assertEqual("bar", tf.extractfile("foo").read())

    def test_create_file_from_string_sets_size(self):
        backing_file = self.create_simple_tarball([("foo", "bar")])
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(3, tf.getmember("foo").size)

    def test_create_file_from_string_sets_mode(self):
        backing_file = self.create_simple_tarball([("foo", "bar")])
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(0644, tf.getmember("foo").mode)

    def test_create_file_from_string_sets_type(self):
        backing_file = self.create_simple_tarball([("foo", "bar")])
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(tarfile.REGTYPE, tf.getmember("foo").type)

    def test_create_file_from_string_sets_linkname(self):
        backing_file = self.create_simple_tarball([("foo", "bar")])
        with standard_tarfile(backing_file) as tf:
            self.assertEqual('', tf.getmember("foo").linkname)

    def test_create_file_uses_default_mtime(self):
        now = 126793
        backing_file = self.create_simple_tarball(
            [("foo", "bar")], default_mtime=now)
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(now, tf.getmember("foo").mtime)

    def test_create_file_uses_default_uid(self):
        uid = 1259
        backing_file = self.create_simple_tarball(
            [("foo", "bar")], default_uid=uid)
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(uid, tf.getmember("foo").uid)

    def test_create_file_uses_default_gid(self):
        gid = 2259
        backing_file = self.create_simple_tarball(
            [("foo", "bar")], default_gid=gid)
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(gid, tf.getmember("foo").gid)

    def test_create_file_uses_default_uname(self):
        uname = "someperson"
        backing_file = self.create_simple_tarball(
            [("foo", "bar")], default_uname=uname)
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(uname, tf.getmember("foo").uname)

    def test_create_file_uses_default_gname(self):
        gname = "somegroup"
        backing_file = self.create_simple_tarball(
            [("foo", "bar")], default_gname=gname)
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(gname, tf.getmember("foo").gname)

    def test_create_dir_adds_path(self):
        backing_file = self.create_simple_tarball([("foo/", "")])
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(["foo"], tf.getnames())

    def test_create_dir_sets_name(self):
        backing_file = self.create_simple_tarball([("foo/", "")])
        with standard_tarfile(backing_file) as tf:
            self.assertEqual("foo", tf.getmember("foo").name)

    def test_create_dir_sets_type(self):
        backing_file = self.create_simple_tarball([("foo/", "")])
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(tarfile.DIRTYPE, tf.getmember("foo").type)

    def test_create_dir_sets_size(self):
        backing_file = self.create_simple_tarball([("foo/", "")])
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(0, tf.getmember("foo").size)

    def test_create_dir_sets_mode(self):
        backing_file = self.create_simple_tarball([("foo/", "")])
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(0755, tf.getmember("foo").mode)

    def test_create_dir_sets_linkname(self):
        backing_file = self.create_simple_tarball([("foo/", "")])
        with standard_tarfile(backing_file) as tf:
            self.assertEqual('', tf.getmember("foo").linkname)

    def test_create_dir_uses_default_mtime(self):
        now = 126793
        backing_file = self.create_simple_tarball(
            [("foo/", "")], default_mtime=now)
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(now, tf.getmember("foo").mtime)

    def test_create_dir_uses_default_uid(self):
        uid = 1259
        backing_file = self.create_simple_tarball(
            [("foo/", "")], default_uid=uid)
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(uid, tf.getmember("foo").uid)

    def test_create_dir_uses_default_gid(self):
        gid = 2259
        backing_file = self.create_simple_tarball(
            [("foo/", "")], default_gid=gid)
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(gid, tf.getmember("foo").gid)

    def test_create_dir_uses_default_uname(self):
        uname = "someperson"
        backing_file = self.create_simple_tarball(
            [("foo/", "")], default_uname=uname)
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(uname, tf.getmember("foo").uname)

    def test_create_dir_uses_default_gname(self):
        gname = "somegroup"
        backing_file = self.create_simple_tarball(
            [("foo/", "")], default_gname=gname)
        with standard_tarfile(backing_file) as tf:
            self.assertEqual(gname, tf.getmember("foo").gname)
