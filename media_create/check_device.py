import sys

import dbus


def _get_udisks_if():
    bus = dbus.SystemBus()
    udisks = dbus.Interface(
        bus.get_object("org.freedesktop.UDisks", "/org/freedesktop/UDisks"),
        'org.freedesktop.UDisks')

    return (bus, udisks)


def _get_dbus_property(prop, device, path):
    return device.Get(
        path, prop, dbus_interface='org.freedesktop.DBus.Properties')


def _find_device(path):
    bus, udisks = _get_udisks_if()
    try:
        udisks.get_dbus_method('FindDeviceByDeviceFile')(path)
    except dbus.exceptions.DBusException:
        return False

    return True


def _print_devices():
    bus, udisks = _get_udisks_if()
    print '%-16s %-16s %s' % ('Device', 'Mount point', 'Size')
    devices = udisks.get_dbus_method('EnumerateDevices')()
    for path in devices:
        device = bus.get_object("org.freedesktop.UDisks", path)
        device_file =  _get_dbus_property('DeviceFile', device, path)
        
        mount_paths = _get_dbus_property('device-mount-paths', device, path)
        mount_point = ''.join(b for b in mount_paths)
        if mount_point == '':
            mount_point = 'none'
        
        if _get_dbus_property('DeviceIsPartition', device, path):
            part_size = _get_dbus_property('partition-size', device, path)
            print '%-16s %-16s %dMB' % (
                device_file, mount_point, part_size / 1024**2)
        else:
            device_size = _get_dbus_property('device-size', device, path)
            print '%-16s %-16s %dMB' % (
                device_file, mount_point, part_size / 1024**2)


def _select_device(device):
    resp = raw_input('Are you 100% sure, on selecting [%s] (y/n)? ' % device)
    if resp.lower() != 'y':
        return False
    return True


def check_device(path):
    """Checks that a selected device exists.

    If the device exist, the user is asked to confirm that this is the
    device to use.

    :param path: Device path.
    :return: True if the device exist and is selected, else False.

    """

    if _find_device(path):
        print '\nI see...'
        _print_devices()
        return _select_device(path)
    else:
        print '\nAre you sure? I do not see [%s].' % path
        print 'Here is what I see...'
        _print_devices()
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
