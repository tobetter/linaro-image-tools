import os
import tarfile
import tempfile
from testtools import TestCase

from linaro_image_tools.hwpack.builder import HardwarePackBuilder


class TestLinaroHwpackCreate(TestCase):

    def __init__(self, *args, **kwargs):
        super(self.__class__, self).__init__(*args, **kwargs)
        self.basedir = os.path.dirname(__file__)

    def test_global_and_board_bootloader(self):
        local_debs = ["mock-base_1.0_all.deb", "mock-u-boot1_1.0_all.deb",
                      "mock-u-boot2_1.0_all.deb"]
        local_debs = [self.basedir + "/data/pkgs/" + f for f in local_debs]
        fd, filename = tempfile.mkstemp(prefix="hwpack-test-")
        builder = HardwarePackBuilder(
            self.basedir + "/data/test.hwpack.conf", "3.0", local_debs,
            out_name=filename)
        builder.build()
        tar = tarfile.open(filename)
        assert tar.getmember("u_boot/u-boot.img")
        assert tar.getmember("u_boot/copyright")
        assert tar.getmember("u_boot-board1/u-boot.img")
        f = tar.extractfile("u_boot/u-boot.img")
        assert "#1" in f.read()
        f = tar.extractfile("u_boot/copyright")
        assert "#1" in f.read()
        f = tar.extractfile("u_boot-board1/u-boot.img")
        assert "#2" in f.read()
        os.remove(filename)
