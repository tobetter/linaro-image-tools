from contextlib import contextmanager
import hashlib
import os
import shutil
import tempfile
from StringIO import StringIO
import tarfile

from testtools import TestCase

from hwpack.better_tarfile import writeable_tarfile


@contextmanager
def test_tarfile(contents=[], **kwargs):
    """Create a tarfile with the given contents, then re-open it for reading.

    This context manager creates a tarfile with the given contents, then
    reopens it for reading and yields it for use in a with block. When
    the block ends the tarfile will be closed.

    The contents can be specified as a list of tuples of (path, contents),
    where if the path ends with '/' it is considered to be a directory and
    the contents ignored.

    :param contents: the contents to put in the tarball, defaults to the
        empty list.
    :type contents: a list of tuples of (str, str)
    :param kwargs: keyword arguments for the better_tarfile.TarFile
        constructor.
    """
    backing_file = StringIO()
    with writeable_tarfile(backing_file, **kwargs) as tf:
        for path, content in contents:
            if path[-1] == "/":
                tf.create_dir(path)
            else:
                tf.create_file_from_string(path, content)
    if contents:
        backing_file.seek(0)
    tf = tarfile.TarFile.open(mode="r", fileobj=backing_file)
    try:
        yield tf
    finally:
        tf.close()


class Package(object):

    def __init__(self, name, version, architecture="all"):
        self.name = name
        self.version = version
        self.architecture = architecture

    @property
    def filename(self):
        return "%s_%s_%s.deb" % (self.name, self.version, self.architecture)

    @property
    def content(self):
        return "Content of %s" % self.filename


class AptSource(object):

    def __init__(self, packages):
        self.packages = packages

    def setUp(self):
        self.rootdir = tempfile.mkdtemp(prefix="hwpack-apt-source-")
        for package in self.packages:
            with open(
                os.path.join(self.rootdir, package.filename), 'wb') as f:
                f.write(package.content)
        with open(os.path.join(self.rootdir, "Packages"), 'wb') as f:
            for package in self.packages:
                f.write('Package: %s\n' % package.name)
                f.write('Version: %s\n' % package.version)
                f.write('Filename: %s\n' % package.filename)
                f.write('Size: %d\n' % len(package.content))
                f.write('Architecture: %s\n' % package.architecture)
                md5sum = hashlib.md5()
                md5sum.update(package.content)
                f.write('MD5sum: %s\n' % md5sum.hexdigest())
                f.write('\n')

    def tearDown(self):
        if os.path.exists(self.rootdir):
            shutil.rmtree(self.rootdir)

    @property
    def sources_entry(self):
        return "file:" + os.path.abspath(self.rootdir) +" ./"


class TestCaseWithFixtures(TestCase):

    def useFixture(self, fixture):
        self.addCleanup(fixture.tearDown)
        fixture.setUp()
        return fixture
