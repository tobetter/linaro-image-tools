import sys

from parted import (
    Device,
    Disk,
    )


def calculate_partition_size_and_offset(device):
    """Return the size and offset of the boot and root partitions.

    Both the size and offset are in sectors.

    :param device: A string containing the path to the device.
    :return: A 4-tuple containing the offset and size of the boot partition
        followed by the offset and size of the root partition.
    """
    disk = Disk(Device(device))
    vfat_partition = None
    for partition in disk.partitions:
        if 'boot' in partition.getFlagsAsString():
            geometry = partition.geometry
            vfat_offset = geometry.start * 512
            vfat_size = geometry.length * 512
            vfat_partition = partition

    assert vfat_partition is not None, (
        "Couldn't find boot partition on %s" % device)
    linux_partition = vfat_partition.nextPartition()
    geometry = linux_partition.geometry
    linux_offset = geometry.start * 512
    linux_size = geometry.length * 512
    return vfat_size, vfat_offset, linux_size, linux_offset


if __name__ == "__main__":
    vsize, voffset, rsize, roffset = calculate_partition_size_and_offset(
        sys.argv[1])
    # These values need to be assigned to shell variables in our script, so we
    # make its job easier by printing something it can pass on to eval.
    print "VFATSIZE=%s VFATOFFSET=%s ROOTSIZE=%s ROOTOFFSET=%s" % (
        vsize, voffset, rsize, roffset)
