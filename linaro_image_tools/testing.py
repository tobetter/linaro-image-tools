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

import os
import tempfile

from testtools import TestCase


class TestCaseWithFixtures(TestCase):
    """A TestCase with the ability to easily add 'fixtures'.

    A fixture is an object which can be created and cleaned up, and
    this test case knows how to manage them to ensure that they will
    always be cleaned up at the end of the test.
    """

    def useFixture(self, fixture):
        """Make use of a fixture, ensuring that it will be cleaned up.

        Given a fixture, this method will run the `setUp` method of
        the fixture, and ensure that its `tearDown` method will be
        called at the end of the test, regardless of success or failure.

        :param fixture: the fixture to use.
        :type fixture: an object with setUp and tearDown methods.
        :return: the fixture that was passed in.
        """
        self.addCleanup(fixture.tearDown)
        fixture.setUp()
        return fixture

    def createTempFileAsFixture(self, prefix='tmp', dir=None):
        """Create a temp file and make sure it is removed on tearDown.

        :return: The filename of the file created.
        """
        _, filename = tempfile.mkstemp(prefix=prefix, dir=dir)
        self.addCleanup(os.unlink, filename)
        return filename
