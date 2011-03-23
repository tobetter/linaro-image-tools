from linaro_image_tools.hwpack.tests import test_suite as hwpack_suite
from linaro_image_tools.media_create.tests import (
    test_suite as media_create_suite,
    )


def test_suite():
    suite = hwpack_suite()
    suite.addTests(media_create_suite())
    return suite
