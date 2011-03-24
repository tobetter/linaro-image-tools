import unittest

from linaro_image_tools.hwpack.tests import test_suite as hwpack_suite
from linaro_image_tools.media_create.tests import (
    test_suite as media_create_suite,
    )

def test_suite():
    module_names = [
        'linaro_image_tools.tests.test_utils',
        ]
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromNames(module_names)
    suite.addTests(hwpack_suite())
    suite.addTests(media_create_suite())
    return suite

