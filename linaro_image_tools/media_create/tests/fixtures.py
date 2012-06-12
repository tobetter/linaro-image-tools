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
import subprocess

from linaro_image_tools.media_create import partitions

from linaro_image_tools.tests.fixtures import MockSomethingFixture


class CreateTarballFixture(object):

    def __init__(self, basedir, reldir='tarball', filename='tarball.tar.gz'):
        self.basedir = basedir
        self.reldir = reldir
        self.tarball = os.path.join(self.basedir, filename)

    def setUp(self):
        # Create gzipped tar archive.
        os.mkdir(os.path.join(self.basedir, self.reldir))
        args = ['tar', '-C', self.basedir, '-czf', self.tarball, self.reldir]
        proc = subprocess.Popen(args)
        proc.wait()

    def tearDown(self):
        if os.path.exists(self.tarball):
            os.remove(self.tarball)
        dir = os.path.join(self.basedir, self.reldir)
        if os.path.exists(dir):
            os.rmdir(dir)

    def get_tarball(self):
        return self.tarball


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
