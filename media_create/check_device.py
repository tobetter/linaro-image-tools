import re
import sys

import dbus


def _get_devices():
    bus = dbus.SystemBus()
    udisks = dbus.Interface(
        bus.get_object("org.freedesktop.UDisks", "/org/freedesktop/UDisks"),
        'org.freedesktop.UDisks')
    return udisks.get_dbus_method('EnumerateDevices')()


def _get_dbus_properties(prop, device, path):
    return device.Get(
        path, prop, dbus_interface='org.freedesktop.DBus.Properties')


def _find_device(device_to_find):
    bus = dbus.SystemBus()
    devices = _get_devices()
    for path in devices:
        device = bus.get_object("org.freedesktop.UDisks", path)
        device_file = _get_dbus_properties('DeviceFile', device, path)
        if device_file == device_to_find:
            return True
    return False


def _print_partitions():
    bus = dbus.SystemBus()
    devices = _get_devices()
    for path in devices:
        device = bus.get_object("org.freedesktop.UDisks", path)
        if _get_dbus_properties('DeviceIsPartition', device, path):
            print path
            print _get_dbus_properties('device-mount-paths', device, path)
            print _get_dbus_properties('partition-size', device, path)
            print "="*60


def _print_mounted_devices():
    mount_file = '/etc/mtab'
    try:
        with open(mount_file) as f:
            for line in f:
                if re.match('/dev/', line) is not None:
                    sys.stdout.write(line)
    except IOError:
        print 'IOError: cannot read %s' % mount_file


def _print_device_info():
    print '\nDevice partitions:'
    _print_partitions()
    print '\nMounted devices:'
    _print_mounted_devices()
    print


def _select_device(device):
    resp = raw_input('Are you 100% sure, on selecting [%s] (y/n)? ' % device)
    if resp.lower() != 'y':
        return False
    return True


def check_device(device):
    """Checks that a selected device exists.

    :param device: The selected device.
    :return: True if the device exist and is selected, else False.
    """

    if _find_device(device):
        print '\nI see...'
        _print_device_info()
        return _select_device(device)
    else:
        print '\nAre you sure? I do not see [%s].' % device
        print 'Here is what I see...'
        _print_device_info()
        return False


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print 'usage: ' + sys.argv[0] + ' <DEVICE>'
        sys.exit(2)

    device_selected = check_device(sys.argv[1])
    if device_selected:
        sys.exit(0)
    else:
        sys.exit(1)
