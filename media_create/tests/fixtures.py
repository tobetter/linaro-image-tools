import os
import shutil
import subprocess
import tempfile


class CreateTempDirFixture(object):

    def __init__(self):
        self.tempdir = None

    def setUp(self):
        self.tempdir = tempfile.mkdtemp()

    def tearDown(self):
        if os.path.exists(self.tempdir):
            shutil.rmtree(self.tempdir)

    def get_temp_dir(self):
        return self.tempdir


class CreateTarballFixture(object):

    def __init__(self, dir):
        self.dir = dir
        self.tarball = os.path.join(self.dir + 'tarball.tar.gz')

    def setUp(self):
        # Create gzipped tar archive.
        args = ['tar', '-czf', self.tarball, self.dir]
        proc = subprocess.Popen(args)
        proc.wait()

    def tearDown(self):
        if os.path.exists(self.tarball):
            os.remove(self.tarball)

    def get_tarball(self):
        return self.tarball


class MockSomethingFixture(object):
    """A fixture which mocks something on the given object.

    Replaces attr_name on obj with the given mock, undoing that upon
    tearDown().
    """

    def __init__(self, obj, attr_name, mock):
        self.obj = obj
        self.attr_name = attr_name
        self.mock = mock
        self.orig_attr = getattr(obj, attr_name)

    def setUp(self):
        setattr(self.obj, self.attr_name, self.mock)

    def tearDown(self):
        setattr(self.obj, self.attr_name, self.orig_attr)
