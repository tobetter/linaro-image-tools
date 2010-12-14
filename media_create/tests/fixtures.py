import os
import shutil
import subprocess
import sys
import tempfile

from media_create import create_partitions
from media_create import cmd_runner


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
        self.tarball = os.path.join(self.dir, 'tarball.tar.gz')

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


class MockCmdRunnerPopen(object):
    """A mock for cmd_runner.Popen() which stores the args given to it."""
    args = None
    def __call__(self, args, **kwargs):
        self.args = args
        self.returncode = 0
        return self

    def wait(self):
        return self.returncode


class MockCmdRunnerPopenFixture(MockSomethingFixture):
    """A test fixture which mocks cmd_runner.do_run with the given mock.

    If no mock is given, a MockCmdRunnerPopen instance is used.
    """

    def __init__(self, mock=None):
        if mock is None:
            mock = MockCmdRunnerPopen()
        super(MockCmdRunnerPopenFixture, self).__init__(
            cmd_runner, 'Popen', mock)


class ChangeCurrentWorkingDirFixture(object):

    def __init__(self, dir):
        self.dir = dir
        self.orig_cwd = os.getcwd()

    def setUp(self):
        os.chdir(self.dir)

    def tearDown(self):
        os.chdir(self.orig_cwd)


class MockCallableWithPositionalArgs(object):
    """A callable mock which just stores the positional args given to it.

    Every time an instance of this is "called", it will append a tuple
    containing the positional arguments given to it to self.calls.
    """
    calls = None
    return_value = None
    def __call__(self, *args):
        if self.calls is None:
            self.calls = []
        self.calls.append(args)
        return self.return_value


class MockRunSfdiskCommandsFixture(MockSomethingFixture):

    def __init__(self):
        mock = MockCallableWithPositionalArgs()
        mock.return_value = ('', '')
        super(MockRunSfdiskCommandsFixture, self).__init__(
            create_partitions, 'run_sfdisk_commands', mock)


class StdoutToDevnullFixture(object):

    def __init__(self):
        self.orig_stdout = None

    def setUp(self):
        # Redirect stdout to /dev/null.
        self.orig_stdout = sys.stdout
        sys.stdout = open(os.devnull, 'w')

    def tearDown(self):
        sys.stdout = self.orig_stdout
