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
# along with Linaro Image Tools.  If not, see <http://www.gnu.org/licenses/>.

import glob

import dbus

from linaro_image_tools.media_create import partitions


def _get_system_bus_and_udisks_iface():
    """Return the system bus and the UDisks interface.

    :return: System bus and UDisks inteface tuple.
    """
    bus = dbus.SystemBus()
    udisks = dbus.Interface(
        bus.get_object("org.freedesktop.UDisks", "/org/freedesktop/UDisks"),
        'org.freedesktop.UDisks')

    return (bus, udisks)


def _get_dbus_property(prop, device, path):
    """ Return a named property for a specific device.

    :param prop: Named property.
    :param device: Device object.
    :param path: Device path.
    :return: Device property.
    """
    return device.Get(
        path, prop, dbus_interface='org.freedesktop.DBus.Properties')


def _does_device_exist(path):
    """Checks if the provided path is an existing device.

    :param path: Disk device path.
    :return: True if the device exist, else False.
    """
    bus, udisks = _get_system_bus_and_udisks_iface()
    try:
        udisks.get_dbus_method('FindDeviceByDeviceFile')(path)
    except dbus.exceptions.DBusException:
        # TODO: Check that this exception isn't hiding other errors.
        return False

    return True


def _print_devices():
    """Print disk devices found on the system."""
    bus, udisks = _get_system_bus_and_udisks_iface()
    print '%-16s %-16s %s' % ('Device', 'Mount point', 'Size')
    devices = udisks.get_dbus_method('EnumerateDevices')()
    devices.sort()
    for path in devices:
        device = bus.get_object("org.freedesktop.UDisks", path)
        device_file = _get_dbus_property('DeviceFile', device, path)

        mount_paths = _get_dbus_property('device-mount-paths', device, path)
        mount_point = ''.join(b for b in mount_paths)
        if mount_point == '':
            mount_point = 'none'

        if _get_dbus_property('DeviceIsPartition', device, path):
            part_size = _get_dbus_property('partition-size', device, path)
            print '%-16s %-16s %dMB' % (
                device_file, mount_point, part_size / 1024 ** 2)
        else:
            device_size = _get_dbus_property('device-size', device, path)
            print '%-16s %-16s %dMB' % (
                device_file, mount_point, device_size / 1024 ** 2)


def _select_device(device):
    """Ask the user to confirm the selected device.

    :param device: Device path.
    :return: True if the user confirms the selection, else False.
    """
    resp = raw_input('Are you 100%% sure, on selecting [%s] (y/n)? ' % device)
    if resp.lower() != 'y':
        return False
    return True


def _ensure_device_partitions_not_mounted(device):
    """Ensure all partitions of the given device are not mounted."""
    # Use '%s?*' as we only want the device files representing
    # partitions and not the one representing the device itself.
    for part in glob.glob('%s?*' % device):
        partitions.ensure_partition_is_not_mounted(part)


def confirm_device_selection_and_ensure_it_is_ready(
        device,
        yes_to_mmc_selection=False):
    """Confirm this is the device to use and ensure it's ready.

    If the device exists, the user is asked to confirm that this is the
    device to use. Upon confirmation we ensure all partitions of the device
    are umounted.

    :param device: The path to the device.
    :return: True if the device exist and is selected, else False.
    """
    if _does_device_exist(device):
        print '\nI see...'
        _print_devices()
        if yes_to_mmc_selection or _select_device(device):
            _ensure_device_partitions_not_mounted(device)
            return True
    else:
        print '\nAre you sure? I do not see [%s].' % device
        print 'Here is what I see...'
        _print_devices()
    return False
