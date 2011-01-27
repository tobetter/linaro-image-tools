import os
import shutil
import subprocess
import tempfile

from linaro_media_create import partitions
from linaro_media_create import cmd_runner


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
    calls = None
    # A variable that is set to False in __call__() and only set back to True
    # when wait() is called, to indicate that tht subprocess has finished. Is
    # used in tests to make sure all callsites wait for their child.
    child_finished = True

    def __call__(self, cmd, *args, **kwargs):
        self.child_finished = False
        if self.calls is None:
            self.calls = []
        if isinstance(cmd, basestring):
            all_args = [cmd]
        else:
            all_args = cmd
        all_args.extend(args)
        self.calls.append(all_args)
        self.returncode = 0
        return self

    def communicate(self, input=None):
        self.wait()
        return '', ''

    def wait(self):
        self.child_finished = True
        return self.returncode

    @property
    def commands_executed(self):
        return [' '.join(args) for args in self.calls]


class MockCmdRunnerPopenFixture(MockSomethingFixture):
    """A test fixture which mocks cmd_runner.do_run with the given mock.

    If no mock is given, a MockCmdRunnerPopen instance is used.
    """

    def __init__(self):
        super(MockCmdRunnerPopenFixture, self).__init__(
            cmd_runner, 'Popen', MockCmdRunnerPopen())

    def tearDown(self):
        super(MockCmdRunnerPopenFixture, self).tearDown()
        if not self.mock.child_finished:
            raise AssertionError(
                "You should call wait() or communicate() to ensure "
                "the subprocess is finished before proceeding.")


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
            partitions, 'run_sfdisk_commands', mock)
