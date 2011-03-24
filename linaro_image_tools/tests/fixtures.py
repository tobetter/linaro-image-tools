# Copyright (C) 2010, 2011 Linaro
#
# Author: Guilherme Salgado <guilherme.salgado@linaro.org>
#
# This file is part of Linaro Image Tools.
#
# Linaro Image Tools is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Linaro Image Tools is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import shutil
import subprocess
import tempfile

from linaro_image_tools import cmd_runner

from linaro_image_tools.media_create import partitions


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

