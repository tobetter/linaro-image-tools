import unittest


def test_suite():
    module_names = [
        'linaro_image_tools.media_create.tests.test_media_create',
        'linaro_image_tools.media_create.tests.test_android_boards',
        ]
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromNames(module_names)
    return suite
