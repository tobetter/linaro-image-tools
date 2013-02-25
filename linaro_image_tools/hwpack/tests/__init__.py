# Copyright (C) 2010, 2011, 2012 Linaro
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

import unittest


def test_suite():
    module_names = [
        'linaro_image_tools.hwpack.tests.test_better_tarfile',
        'linaro_image_tools.hwpack.tests.test_builder',
        'linaro_image_tools.hwpack.tests.test_config',
        'linaro_image_tools.hwpack.tests.test_config_v3',
        'linaro_image_tools.hwpack.tests.test_hardwarepack',
        'linaro_image_tools.hwpack.tests.test_hwpack_converter',
        'linaro_image_tools.hwpack.tests.test_hwpack_reader',
        'linaro_image_tools.hwpack.tests.test_packages',
        'linaro_image_tools.hwpack.tests.test_script',
        'linaro_image_tools.hwpack.tests.test_tarfile_matchers',
        'linaro_image_tools.hwpack.tests.test_testing',
    ]
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromNames(module_names)
    return suite
