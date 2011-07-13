#!/usr/bin/env python
# Copyright (C) 2010, 2011 Linaro
#
# Author: James Tunnicliffe <james.tunnicliffe@linaro.org>
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

import wx
import wx.wizard
import wx.wizard as wiz
import sys
import re
import os
import linaro_image_tools.FetchImage as FetchImage
import string
import unittest
import operator
import Queue
import time
import datetime


def add_button(bind_to,
               sizer,
               label,
               style,
               select_event,
               hover_event,
               unhover_event):

    """Create a radio button with event bindings."""
    if(style != None):
        radio_button = wx.RadioButton(bind_to, label = label, style = style)
    else:
        radio_button = wx.RadioButton(bind_to, label = label)

    sizer.Add(radio_button, 0, wx.ALIGN_LEFT | wx.LEFT | wx.RIGHT | wx.TOP, 5)
    bind_to.Bind(wx.EVT_RADIOBUTTON, select_event, radio_button)
    wx.EVT_ENTER_WINDOW(radio_button, hover_event)
    wx.EVT_LEAVE_WINDOW(radio_button, unhover_event)

    return radio_button


class ReleaseOrSnapshotPage(wiz.PyWizardPage):
    """Ask the user if they want to use a release or a snapshot"""

    def __init__(self, parent, config):
        wiz.PyWizardPage.__init__(self, parent)
        self.config = config
        self.settings = self.config.settings
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.next = None
        self.prev = None

        self.sizer.Add(wx.StaticText(self, -1,
"""This Wizard will write an operating system of your choosing to
either a disk image or to an MMC card. First we need to know if
your priority is stability or the latest and greatest features."""))

        self.box1 = wx.BoxSizer(wx.VERTICAL)

        self.button_text = {'release':  "I would like to run stable, "
                                        "tested software.",
                            'snapshot': "I would like to run untested, but "
                                        "more up-to-date software."}

        add_button(self, self.box1, self.button_text['release'],
                   wx.RB_GROUP, self.event_radio_button_select, None, None)

        # Save the setting for the default selected value
        self.settings['release_or_snapshot'] = "release"

        add_button(self, self.box1, self.button_text['snapshot'], None,
                   self.event_radio_button_select, None, None)

        self.sizer.Add(self.box1, 0, wx.ALIGN_LEFT | wx.ALL, 5)

        self.SetSizerAndFit(self.sizer)
        self.sizer.Fit(self)
        self.Move((50, 50))

    def event_radio_button_select(self, event):
        self.radio_selected = event.GetEventObject().GetLabel()
        # The radio button can be release, snapshot or "latest snapshot"
        if(self.radio_selected == self.button_text['release']):
            self.settings['release_or_snapshot'] = "release"
        else:
            self.settings['release_or_snapshot'] = "snapshot"

    def SetNext(self, next):
        self.next = next

    def GetNext(self):
        return self.next


class AboutMyHardwarePage(wiz.WizardPageSimple):
    """Ask the user about their hardware. This only asks about the board, not
       any specific hardware packs because there can be multiple names for the
       same hardware pack or sometimes a hardware pack is only available in the
       releases or snapshots repository. We whittle down the choice as we go
       and the user can chose a hardare pack (if they don't like the default)
       under advanced options in the Linaro Media Create options
       page"""

    def __init__(self, parent, config, db, width):
        wiz.WizardPageSimple.__init__(self, parent)
        self.settings = config.settings
        self.db = db
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.box1 = wx.BoxSizer(wx.VERTICAL)
        self.box2 = wx.BoxSizer(wx.VERTICAL)

        header = wx.StaticText(self,
                               label = "Please select the hardware that you "
                                       "would like to build an image for from "
                                       "the following list")

        header.Wrap(width - 10)  # -10 because boarder below is 5 pixels wide

        #--- Hardware Combo Box ---
        # Make sure that the displayed release is the one set in settings if
        # no selection is made
        if "panda" in self.settings['choice']['hardware'].keys():
            default_hardware = "panda"
        else:
            default_hardware = self.settings['choice']['hardware'].keys()[-1]

        self.settings['hardware'] = default_hardware
        self.settings['compatable_hwpacks'] = (
                self.settings['choice']['hwpack'][self.settings['hardware']])
        
        self.cb_hardware = wx.ComboBox(self,
                            value =
                            self.settings['choice']['hardware'][default_hardware],
                            style = wx.CB_DROPDOWN | wx.CB_READONLY)

        self.Bind(wx.EVT_COMBOBOX,
                  self.event_combo_box_hardware,
                  self.cb_hardware)
        self.box1.Add(self.cb_hardware, 0,
                      wx.ALIGN_LEFT | wx.LEFT | wx.RIGHT | wx.TOP, 5)

        self.sizer.Add(header)
        self.sizer.Add(self.box1, 0, wx.ALIGN_LEFT | wx.ALL, 5)
        self.sizer.Add(self.box2, 0, wx.ALIGN_LEFT | wx.ALL, 5)
        self.SetSizerAndFit(self.sizer)
        self.sizer.Fit(self)
        self.Move((50, 50))

    def on_page_changing(self):
        self.update_hardware_box()

    def update_hardware_box(self):
        self.cb_hardware.Clear()

        sorted_hardware_names = sorted(self.settings['choice']['hardware']
                                                                  .iteritems(),
                                       key=operator.itemgetter(1))

        table = self.settings['release_or_snapshot'] + "_hwpacks"

        for device_name, human_readable_name in sorted_hardware_names:
            for hwpack in self.settings['choice']['hwpack'][device_name]:
                if self.db.hardware_is_available_in_table(table, hwpack):
                    self.cb_hardware.Append(human_readable_name, device_name)
                    break

    #--- Event(s) ---
    def event_combo_box_hardware(self, event):
        self.settings['hardware'] = (event
                                     .GetEventObject()
                                      .GetClientData(event.GetSelection())
                                       .encode('ascii'))

        self.settings['compatable_hwpacks'] = (
                self.settings['choice']['hwpack'][self.settings['hardware']])
    #--- END event(s) ---


class SelectStableRelease(wiz.WizardPageSimple):
    """Ask the user which Linaro release they would like to run."""
    def __init__(self, parent, config, db, width):
        wiz.WizardPageSimple.__init__(self, parent)
        self.settings = config.settings
        self.db = db
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.wizard = parent

        header = wx.StaticText(self, label = "Please select the stable Linaro "
                                             "release you would like to use")

        header.Wrap(width - 10)  # -10 because boarder below is 5 pixels wide

        self.sizer.Add(header)
        self.box1 = wx.BoxSizer(wx.VERTICAL)

        platforms = []
        for key, value in self.settings['choice']['platform'].items():
            platforms.append(key)

        default_release = self.settings['UI']['translate'][platforms[-1]]
        self.cb_release = wx.ComboBox(self,
                                      value = default_release,
                                      style = wx.CB_DROPDOWN | wx.CB_READONLY)
        self.Bind(wx.EVT_COMBOBOX,
                  self.event_combo_box_release,
                  self.cb_release)

        if(default_release in self.settings['UI']['translate']):
            default_release = self.settings['UI']['translate'][default_release]
        self.settings['platform'] = (
                    self.settings['UI']['reverse-translate'][default_release])

        for item in platforms:
            if(item in self.settings['UI']['translate']):
                new_item = self.settings['UI']['translate'][item]
                item = new_item

            self.cb_release.Append(item, item.upper())

        self.cb_build = wx.ComboBox(self,
                                    style = wx.CB_DROPDOWN | wx.CB_READONLY)
        self.Bind(wx.EVT_COMBOBOX, self.event_combo_box_build, self.cb_build)

        self.box1.Add(self.cb_release, 0,
                      wx.ALIGN_LEFT | wx.LEFT | wx.RIGHT | wx.TOP, 5)
        self.box1.Add(self.cb_build,   0,
                      wx.ALIGN_LEFT | wx.LEFT | wx.RIGHT | wx.TOP, 5)
        self.sizer.Add(self.box1, 0, wx.ALIGN_LEFT | wx.ALL, 5)
        self.SetSizerAndFit(self.sizer)
        self.sizer.Fit(self)
        self.Move((50, 50))

    def update_build_box(self):
        """Depending on what hardware has been chosen, the OS list may be
        restricted. Filter out anything that is unavailable."""
        self.cb_build.Clear()

        builds = self.db.get_builds(self.settings['platform'])
        self.cb_build.SetValue("No build available")

        for build in builds:
            if( self.db.hardware_is_available_for_platform_build(
                                          self.settings['compatable_hwpacks'],
                                          self.settings['platform'],
                                          build)
                and self.db.build_is_available_for_platform_image(
                                "release_binaries",
                                self.settings['platform'],
                                self.settings['image'],
                                build)):

                self.cb_build.Append(build)
                self.cb_build.SetValue(build)
                self.settings['release_build'] = build

        available_hwpacks = (
            self.db.get_available_hwpacks_for_hardware_build_plaform(
                                          self.settings['compatable_hwpacks'],
                                          self.settings['platform'],
                                          self.settings['release_build']))

        if len(available_hwpacks):
            self.settings['hwpack'] = available_hwpacks[0]
            self.wizard.FindWindowById(wx.ID_FORWARD).Enable()
        else:
            self.wizard.FindWindowById(wx.ID_FORWARD).Disable()

    def update_release_and_build_boxes(self):
        """Depending on what hardware has been chosen, some builds may be
           unavailable..."""
        self.cb_release.Clear()

        default_release = None
        for platform, value in self.settings['choice']['platform'].items():
            if(self.db.hardware_is_available_for_platform(
                                          self.settings['compatable_hwpacks'],
                                          platform)
               and len(self.db.execute_return_list(
                               'select * from release_binaries '
                               'where platform == ? and image == ?',
                                (platform, self.settings['image'])))):

                if(platform in self.settings['UI']['translate']):
                    platform = self.settings['UI']['translate'][platform]

                self.cb_release.Append(platform, platform.upper())
                if not default_release or default_release < platform:
                    default_release = platform

        self.settings['platform'] = (
                    self.settings['UI']['reverse-translate'][default_release])
        self.cb_release.SetValue(default_release)
        self.update_build_box()

    #--- Event(s) ---
    def event_combo_box_release(self, evt):
        str = evt.GetString().encode('ascii').lower()
        if(str in self.settings['UI']['reverse-translate']):
            str = self.settings['UI']['reverse-translate'][str]
        self.settings['platform'] = str

        self.update_build_box()

    def event_combo_box_build(self, evt):
        self.settings['release_build'] = evt.GetString().encode('ascii')
    #--- END event(s) ---


class SelectSnapshot(wiz.WizardPageSimple):
    """Present the user with a calendar widget and a list of builds available
    on the selected date so they can chose a snapshot. Filter out days when
    their chosen hardware does not have an available build."""

    def __init__(self, parent, config, db, width):
        wiz.WizardPageSimple.__init__(self, parent)
        self.settings = config.settings
        self.db = db
        self.wizard = parent
        self.width = width
        self.sizer = wx.BoxSizer(wx.VERTICAL)

        header = wx.StaticText(self,
                               label = "Builds are created most days. First "
                                       "please select the day on which the "
                                       "build you would like to use was built,"
                                       " then, if there was more than one "
                                       "build that day you will be able to "
                                       "select the build number.")
        header.Wrap(width - 10)  # -10 because boarder below is 5 pixels wide

        box1 = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(header)

        # Set today as the default build date in settings
        # (matches the date picker)
        self.today = wx.DateTime()
        self.today.SetToCurrent()
        self.settings['build_date'] = self.today.FormatISODate().encode('ascii')

        dpc = wx.DatePickerCtrl(self, size = (120, -1),
                                style = wx.DP_DEFAULT)
        self.Bind(wx.EVT_DATE_CHANGED, self.on_date_changed, dpc)

        #--- Build number Combo Box ---
        # Make sure that the displayed build is the one set in settings if no
        # selection is made
        self.settings['build_number'] = 0
        self.update_build()
        self.cb_build = wx.ComboBox(self,
                                    style = wx.CB_DROPDOWN | wx.CB_READONLY)
        self.Bind(wx.EVT_COMBOBOX, self.event_combo_box_build, self.cb_build)

        #--- Layout ---
        # -- Combo boxes for hardware and image selection --

        grid2 = wx.FlexGridSizer(0, 2, 0, 0)
        grid2.Add(dpc, 0, wx.ALIGN_LEFT | wx.ALL, 5)
        grid2.Add(self.cb_build, 0, wx.ALIGN_LEFT | wx.ALL, 5)

        box1.Add(grid2, 0, wx.ALIGN_LEFT | wx.ALL, 5)

        self.sizer.Add(box1, 0, wx.ALIGN_LEFT | wx.ALL, 5)

        self.help_text = wx.StaticText(self)
        self.sizer.Add(self.help_text, 1, wx.EXPAND, 5)

        self.SetSizer(self.sizer)
        self.sizer.Fit(self)
        self.Move((50, 50))

    def update_platform(self):
        build_and_date = self.settings['snapshot_build'].split(":")

        if len(build_and_date) == 2:
            self.settings['platform'] = (
                    self.db.execute_return_list(
                            "select platform from snapshot_binaries "
                            "where date == ? and build == ?",
                            (build_and_date[0], build_and_date[1])))

            if len(self.settings['platform']) > 0:
                self.settings['platform'] = self.settings['platform'][0][0]

    def update_build(self):
        small_date = re.sub('-', '', self.settings['build_date'])
        self.settings['snapshot_build'] = (small_date
                                           + ":"
                                           + str(self.settings['build_number']))

    def fill_build_combo_box_for_date(self, date):
        """Every time a date is chosen, this function should be called. It will
        check to see if a compatible build is available. If there isn't, it
        will search for one and provide some help text to tell the user when
        compatable builds were built."""
        # Re-populate the build combo box

        self.cb_build.Clear()

        builds = self.db.get_binary_builds_on_day_from_db(
                                      self.settings['image'],
                                      date,
                                      self.settings['compatable_hwpacks'])

        if len(builds):
            max = 0
            for item in builds:
                #Always get a tuple, only interested in the first entry
                item = item[0]
                self.cb_build.Append(item, item.upper())

                if item > max:
                    max = item

            self.cb_build.SetValue(max)
            self.wizard.FindWindowById(wx.ID_FORWARD).Enable()
            self.help_text.SetLabel("")

        else:
            self.cb_build.SetValue("No builds available")
            future_date, past_date = self.db.get_next_prev_day_with_builds(
                                           self.settings['image'],
                                           date,
                                           self.settings['compatable_hwpacks'])

            help_text = None

            if future_date and past_date:
                help_text = ("There are no builds that match your "
                             "specifications available on the selected date. "
                             "The previous build was on " + past_date +
                             " and the next build was on " + future_date + ".")
            elif future_date:
                help_text = ("There are no builds that match your "
                             "specifications available on the selected date. "
                             "The next build was on " + future_date +
                             " and I couldn't find a past build (looked one "
                             "year back from the selected date).")
            elif past_date:
                help_text = ("There are no builds that match your "
                             "specifications available on the selected date. "
                             "The previous build was on " + past_date)
                if date != self.today.FormatISODate().encode('ascii'):
                    help_text += (" and I couldn't find a future build (I "
                                  "looked up to one year forward from the "
                                  "selected date).")
            else:
                help_text = ("I could not find any builds that match your "
                             "specifications close to the selected date (I "
                             "looked forward and back one year from the "
                             "selected date).")

            self.help_text.SetLabel(help_text)
            self.help_text.Wrap(self.width - 10)
            self.wizard.FindWindowById(wx.ID_FORWARD).Disable()

    #--- Event(s) ---
    def on_date_changed(self, evt):
        self.settings['build_date'] = evt.GetDate().FormatISODate().encode('ascii')
        self.fill_build_combo_box_for_date(self.settings['build_date'])
        self.update_build()

    def event_combo_box_build(self, evt):
        self.settings['build_number'] = evt.GetString().encode('ascii').lower()
        self.update_build()
    #--- END event(s) ---


class SelectOS(wiz.WizardPageSimple):
    """Ask the user which OS they would like to run. Filter out any choices
    that are unavailable due to previous choices."""
    def __init__(self, parent, config, db, width):
        wiz.WizardPageSimple.__init__(self, parent)
        self.settings = config.settings
        self.wizard = parent
        self.db = db
        self.width = width
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.settings['image'] = None

        header = wx.StaticText(self, label = "Please select the operating "
                                             "system you would like to run on "
                                             "your hardware.")
        header.Wrap(width - 10)  # -10 because boarder below is 5 pixels wide

        self.box1 = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(header)

        self.cb_image = wx.ComboBox(self,
                                    style = wx.CB_DROPDOWN | wx.CB_READONLY)
        self.Bind(wx.EVT_COMBOBOX, self.event_combo_box_os, self.cb_image)

        #--- Layout ---
        # -- Combo boxes for hardware and image selection --
        self.box1.Add(self.cb_image, 0, wx.ALIGN_LEFT | wx.ALL, 5)

        self.sizer.Add(self.box1, 0, wx.ALIGN_LEFT | wx.ALL, 5)

        self.help_text = wx.StaticText(self)
        self.sizer.Add(self.help_text, 1, wx.EXPAND, 5)

        self.SetSizer(self.sizer)
        self.sizer.Fit(self)
        self.Move((50, 50))

    def get_human_os_name(self, item):
        """Given an OS name from the database, return a human name (either
        translated from the YAML settings, or just prettified) and if it is a
        LEB OS or not"""

        item = re.sub("linaro-", "", item)  # Remove any linaro- decoration

        human_name = item

        if item in self.settings['UI']['descriptions']:
            human_name = self.settings['UI']['descriptions'][item]
        else:
            # Make human_name look nicer...
            human_name = string.capwords(item)

        leb_search = re.search("^LEB:\s*(.*)$", human_name)

        if leb_search:
            return leb_search.group(1), True

        return human_name, False

    def fill_os_list(self):
        """Filter the list of OS's from the config file based on the users
        preferences so all choices in the list are valid (i.e. their hardware
        is supported for the build they have chosen)."""

        # select unique image from snapshot_binaries/release_binaries to
        # generate list
        os_list = None
        if self.settings['release_or_snapshot'] == "release":
            os_list = self.db.get_os_list_from('release_binaries')
        else:
            os_list = self.db.get_os_list_from('snapshot_binaries')

        self.cb_image.Clear()

        printed_tag = None
        last_name = None
        current_image_setting_valid = False

        for state in ["LEB", "other"]:
            for item in os_list:
                if item == "old":
                    # Old is a directory that sometimes hangs around,
                    # but isn't one we want to display
                    continue

                # Save the original, untouched image name for use later.
                # We give it a more human name for display
                original = item
                item = re.sub("linaro-", "", item)

                os_hardware_combo_available = (
                            self.db.image_hardware_combo_available(
                                    self.settings['release_or_snapshot'],
                                    original,
                                    self.settings['compatable_hwpacks']))

                if os_hardware_combo_available:
                    human_name, is_LEB = self.get_human_os_name(item)

                    if item == self.settings['image']:
                        current_image_setting_valid = True

                    if state == "LEB" and is_LEB:

                        if printed_tag != state:
                            self.cb_image.Append(
                                            "- Linaro Supported Releases -")
                            printed_tag = state

                        self.cb_image.Append(human_name, original)

                        if self.settings['image'] == None:
                            self.settings['image'] = original

                    elif state != "LEB" and not is_LEB:
                        if printed_tag != state:
                            self.cb_image.Append(
                                            "- Community Supported Releases -")
                            printed_tag = state

                        self.cb_image.Append(human_name, original)

                    last_name = original

        if(    self.settings['image'] != None
           and current_image_setting_valid == False):
            # If we have an image setting, but it doesn't match the OS list, we
            # have switched OS list. It may be that adding/removing "linaro-"
            # from the name will get a match.

            if re.search("linaro-", self.settings['image']):
                test_name = re.sub("linaro-", "", self.settings['image'])
            else:
                test_name = "linaro-" + self.settings['image']

            if test_name in os_list:
                # Success! We have translated the name and can retain the
                # "old setting"
                self.settings['image'] = test_name
                current_image_setting_valid = True

        if(   self.settings['image'] == None
           or current_image_setting_valid == False):
            # This should only get hit if there are no LEBs available
            self.settings['image'] = last_name

        assert self.settings['image']

        # Make sure the visible selected value matches the saved setting
        self.cb_image.SetValue(
                            self.get_human_os_name(self.settings['image'])[0])

    #--- Event(s) ---
    def event_combo_box_os(self, evt):
        self.settings['image'] = self.cb_image.GetClientData(
                                                            evt.GetSelection())

        if self.settings['image']:  # Is None for items that aren't an OS
            self.wizard.FindWindowById(wx.ID_FORWARD).Enable()
            image = re.sub("linaro-", "", self.settings['image'])

            if image + "::long" in self.settings['UI']['descriptions']:
                self.help_text.SetLabel(self.settings['UI']
                                                     ['descriptions']
                                                     [image + "::long"])
            else:
                self.help_text.SetLabel("")

        else:  # Have selected help text
            self.wizard.FindWindowById(wx.ID_FORWARD).Disable()
            self.help_text.SetLabel("Please select an operating system to run "
                                    "on your chosen hardware.")

        self.help_text.Wrap(self.width - 10)
    #--- END event(s) ---


class LMC_settings(wiz.WizardPageSimple):
    """Present the user with, intially, the choice of writing the file system
    they are going to have created to a file, or directly to a device. Ask
    which file/device to write to.

    If writing to a device, the user is asked to tick a box saying that they
    understand that the device they have chosen will be erased.

    If the user ticks the advanced box, more options are shown."""

    def __init__(self, parent, config, db, width):
        wiz.WizardPageSimple.__init__(self, parent)
        self.settings = config.settings
        self.wizard = parent
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.yes_use_mmc = False
        self.db = db

        self.settings['path_selected'] = ""

        header = wx.StaticText(self,
                               label = "Media Creation Settings\n\n"
                               "Please select if you would like to write the "
                               "file system I am about to create to a memory "
                               "card, or to a file on the local file system.")
        header.Wrap(width - 10)  # -10 because boarder below is 5 pixels wide

        #--- Build some widgets ---
        #-- Target file system --
        file_systems = ["ext3", "ext4", "btrfs", "ext2"]
        default_target = file_systems[0]
        self.settings['rootfs'] = default_target
        cb_rootfs = wx.ComboBox(self,
                                value = default_target,
                                style = wx.CB_DROPDOWN | wx.CB_READONLY)

        for item in file_systems:
            cb_rootfs.Append(item, item.upper())

        self.Bind(wx.EVT_COMBOBOX, self.event_combo_box_rootfs, cb_rootfs)

        #-- Image size spinner
        self.image_size_spinner = wx.SpinCtrl(self, -1, "")
        self.Bind(wx.EVT_SPINCTRL,
                  self.event_image_size,
                  self.image_size_spinner)

        #-- Swap size spinner
        self.swap_size_spinner = wx.SpinCtrl(self, -1, "")
        self.Bind(wx.EVT_SPINCTRL,
                  self.event_swap_size,
                  self.swap_size_spinner)

        #--- Layout ---
        self.sizer.Add(header, 0, wx.ALIGN_LEFT | wx.ALL, 5)
        box1 = wx.BoxSizer(wx.VERTICAL)
        file_dev_grid = wx.FlexGridSizer(0, 2, 0, 0)
        box1.Add(file_dev_grid, 0, wx.EXPAND)
        grid1 = wx.FlexGridSizer(0, 2, 0, 0)

        # self.settings['write_to_file_or_device'] should match the first
        # button below...
        self.settings['write_to_file_or_device'] = "file"
        add_button(self,
                   file_dev_grid,
                   "Write to file",
                   wx.RB_GROUP,
                   self.event_radio_button_select,
                   None, None)

        add_button(self,
                   file_dev_grid,
                   "Write to device",
                   None,
                   self.event_radio_button_select,
                   None, None)

        self.help_text_values = {"device": "Please select a device to write "
                                           "the file system to:",
                                 "file":   "Please select a file to write the "
                                           "file system to:"}

        self.help_text = wx.StaticText(
                             self,
                             label =
                             self.help_text_values[
                                   self.settings['write_to_file_or_device']])
        self.help_text.Wrap(width - 10)

        #-- File/dev picker --
        file_browse_button = wx.Button(self, -1, "Browse")
        file_browse_grid   = wx.FlexGridSizer(0, 2, 0, 0)
        self.file_path_and_name = wx.TextCtrl(self, -1, "", size=(300, -1))

        file_browse_grid.Add(self.file_path_and_name, 0, wx.EXPAND)
        file_browse_grid.Add(file_browse_button, 0, wx.EXPAND)

        self.Bind(wx.EVT_BUTTON,
                  self.event_open_file_control,
                  file_browse_button)

        self.Bind(wx.EVT_TEXT,
                  self.event_file_path_and_name,
                  self.file_path_and_name)

        box1.Add(self.help_text, 0, wx.ALIGN_LEFT | wx.ALL, 5)

        box1.Add(file_browse_grid, 0, wx.EXPAND)

        cb1 = wx.CheckBox(self, -1, "Show advanced options")
        self.Bind(wx.EVT_CHECKBOX, self.event_show_advanced_options, cb1)
        box1.Add(cb1)

        #-- Combo boxes for hardware and image selection --
        optional_settings_box_title = wx.StaticBox(
                                                self,
                                                label = " Optional Settings ")

        self.optional_settings_box = wx.StaticBoxSizer(
                                                optional_settings_box_title,
                                                wx.VERTICAL)

        self.box2 = wx.BoxSizer(wx.VERTICAL)

        self.box2.AddWindow(self.optional_settings_box,
                            0,
                            border=2,
                            flag=wx.ALL | wx.EXPAND)

        grid1.Add(cb_rootfs, 0, wx.ALIGN_LEFT | wx.LEFT | wx.RIGHT | wx.TOP, 5)

        grid1.Add(wx.StaticText(self,
                                label = "The root file system of the image"),
                                0,
                                wx.ALIGN_LEFT | wx.LEFT | wx.RIGHT | wx.TOP,
                                5)

        # We want to sub-devide the cell, to add another grid sizer...
        file_size_grid = wx.FlexGridSizer(0, 2, 0, 0)

        grid1.Add(file_size_grid,
                  0,
                  wx.ALIGN_LEFT | wx.LEFT | wx.RIGHT | wx.TOP)

        # Add a spinner that allows us to type/click a numerical value (defined above)
        file_size_grid.Add(self.image_size_spinner,
                           0,
                           wx.ALIGN_LEFT | wx.LEFT | wx.RIGHT | wx.TOP,
                           5)

        # Add a choice of MB or GB for size input
        units = ["GB", "MB"]
        self.size_unit = units[0]  # Set the default unit
        unit_choice = wx.Choice(self, -1, (100, 50), choices = units)
        self.Bind(wx.EVT_CHOICE, self.event_chose_unit, unit_choice)
        file_size_grid.Add(unit_choice, 0, wx.ALIGN_RIGHT | wx.TOP, 5)

        # Back out of the extra grid, add some help text
        grid1.Add(wx.StaticText(
                            self,
                            label = "Writing to file only: Image file size"),
                            0,
                            wx.ALIGN_LEFT | wx.LEFT | wx.RIGHT | wx.TOP,
                            5)

        # The swap size (MB only)
        grid1.Add(self.swap_size_spinner,
                  0,
                  wx.ALIGN_LEFT | wx.LEFT | wx.RIGHT | wx.TOP,
                  5)

        grid1.Add(wx.StaticText(self, label = "Swap file size in MB"),
                  0,
                  wx.ALIGN_LEFT | wx.LEFT | wx.RIGHT | wx.TOP,
                  5)

        self.cb_hwpacks = wx.ComboBox(
                                self,
                                value = self.settings['compatable_hwpacks'][0],
                                style = wx.CB_DROPDOWN | wx.CB_READONLY)

        self.Bind(wx.EVT_COMBOBOX,
                  self.event_combo_box_hwpack,
                  self.cb_hwpacks)

        grid1.Add(self.cb_hwpacks,
                  0,
                  wx.ALIGN_LEFT | wx.LEFT | wx.RIGHT | wx.TOP,
                  5)

        grid1.Add(wx.StaticText(self, label = "Compatible hardware packs"),
                  0,
                  wx.ALIGN_LEFT | wx.LEFT | wx.RIGHT | wx.TOP,
                  5)

        self.optional_settings_box.Add(grid1, 0, wx.ALIGN_LEFT | wx.ALL, 5)

        confirm_mmc_usage_title = wx.StaticBox(self, label = " Are you sure? ")

        self.confirm_mmc_usage_box = wx.StaticBoxSizer(confirm_mmc_usage_title,
                                                       wx.VERTICAL)
        cb2 = wx.CheckBox(
                        self,
                        -1,
                        "Yes, erase and use the device I have selected above.")

        self.Bind(wx.EVT_CHECKBOX, self.event_use_mmc_tickbox, cb2)
        self.confirm_mmc_usage_box.Add(cb2)

        self.box3 = wx.BoxSizer(wx.VERTICAL)
        self.box3.AddWindow(self.confirm_mmc_usage_box,
                            0,
                            border=2,
                            flag=wx.ALL | wx.EXPAND)

        self.sizer.Add(box1, 0, wx.ALIGN_LEFT | wx.ALL, 0)
        self.sizer.Add(self.box2, 0, wx.ALIGN_LEFT | wx.ALL, 0)
        self.sizer.Add(self.box3, 0, wx.ALIGN_LEFT | wx.ALL, 0)
        self.SetSizer(self.sizer)
        self.sizer.Fit(self)
        self.Move((50, 50))

    def on_activate(self):
        self.update_forward_active_and_mmc_confirm_box_visible()
        self.set_hwpacks_for_hardware()

    def set_hwpacks_for_hardware(self):
        self.cb_hwpacks.Clear()

        if self.settings['release_or_snapshot'] == "snapshot":
            self.settings['build'] = self.settings['snapshot_build']

            date_and_build = self.settings['build'].split(":")

            compatable_hwpacks = (
                self.db.get_available_hwpacks_for_hardware_snapshot_build(
                                        self.settings['compatable_hwpacks'],
                                        self.settings['platform'],
                                        date_and_build[0],
                                        date_and_build[1]))
        else:
            self.settings['build'] = self.settings['release_build']
            compatable_hwpacks = (
                self.db.get_available_hwpacks_for_hardware_build_plaform(
                                        self.settings['compatable_hwpacks'],
                                        self.settings['platform'],
                                        self.settings['build']))

        for hwpack in compatable_hwpacks:
            self.cb_hwpacks.Append(hwpack)

        self.cb_hwpacks.SetStringSelection(compatable_hwpacks[0])
        self.settings['hwpack'] = compatable_hwpacks[0]

    def update_forward_active_and_mmc_confirm_box_visible(self):
        if(    self.settings['path_selected']
           and self.settings['path_selected'] != ""):

            if (   self.settings['write_to_file_or_device'] == "file"
                or self.settings['write_to_file_or_device'] == "device"
                   and self.yes_use_mmc):
                self.wizard.FindWindowById(wx.ID_FORWARD).Enable()
            else:
                self.wizard.FindWindowById(wx.ID_FORWARD).Disable()
        else:
            self.wizard.FindWindowById(wx.ID_FORWARD).Disable()

        if self.settings['write_to_file_or_device'] == "device":
            self.box3.Show(self.confirm_mmc_usage_box, True)
        else:
            self.box3.Hide(self.confirm_mmc_usage_box, True)

    # --- Event Handlers ---
    def event_open_file_control(self, event):
        if self.settings['write_to_file_or_device'] == "file":

            dlg = wx.FileDialog(self,
                                message="Save file as ...",
                                defaultDir=os.getcwd(),
                                defaultFile="",
                                style=wx.SAVE)

        elif self.settings['write_to_file_or_device'] == "device":
            dlg = wx.FileDialog(self,
                                message="Choose a device",
                                defaultDir=os.getcwd(),
                                defaultFile="",
                                style=wx.OPEN | wx.CHANGE_DIR)

        if dlg.ShowModal() == wx.ID_OK:
            self.settings['path_selected'] = dlg.GetPaths()[0]
            self.file_path_and_name.SetValue(self.settings['path_selected'])

        dlg.Destroy()
        self.update_forward_active_and_mmc_confirm_box_visible()

    def event_file_path_and_name(self, event):
        self.settings['path_selected'] = event.GetString()
        self.update_forward_active_and_mmc_confirm_box_visible()

    def event_combo_box_hwpack(self, event):
        self.settings['hwpack'] = event.GetString().encode('ascii')

    def event_combo_box_rootfs(self, evt):
        self.settings['rootfs'] = evt.GetString().encode('ascii').lower()

    def event_radio_button_select(self, event):
        """Search the label of the button that has been selected to work out
        what we are writing to."""
        setting_search = re.search(
                            "write to (\w+)",
                            event
                             .GetEventObject()
                              .GetLabel()
                               .encode('ascii')
                                .lower())

        assert setting_search

        self.settings['write_to_file_or_device'] = setting_search.group(1)

        self.help_text.SetLabel(
               self.help_text_values[self.settings['write_to_file_or_device']])

        self.update_forward_active_and_mmc_confirm_box_visible()

    def event_show_advanced_options(self, event):
        if event.IsChecked():
            self.box2.Show(self.optional_settings_box, True)
        else:
            self.box2.Hide(self.optional_settings_box, True)

    def event_pick_file_path(self, evt):
        self.settings['path_selected'] = os.path.abspath(evt.GetPath())
        self.update_forward_active_and_mmc_confirm_box_visible()

    def update_image_size_setting(self):
        if(self.image_size_spinner.GetValue() > 0):
            self.settings['image_size'] = (str(self.image_size_spinner
                                                                 .GetValue())
                                           + self.size_unit[0])
        else:
            self.settings['image_size'] = None

    def event_image_size(self, event):
        self.update_image_size_setting()

    def event_chose_unit(self, event):
        self.size_unit = event.GetString()
        self.update_image_size_setting()

    def event_swap_size(self, event):
        self.settings['swap_file'] = str(self.image_size_spinner.GetValue())

    def event_use_mmc_tickbox(self, event):
        self.yes_use_mmc = event.IsChecked()
        self.update_forward_active_and_mmc_confirm_box_visible()


class RunLMC(wiz.WizardPageSimple):
    """Present the user with some information about their choices and a button
    to start linaro-media-create. The linaro-media-create process is started in
    a new thread and important events are communicated back to the UI through a
    queue."""

    def __init__(self, parent, config, db, width):
        wiz.WizardPageSimple.__init__(self, parent)
        self.settings = config.settings
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.db = db
        self.width = width
        self.wizard = parent

        header = wx.StaticText(self, label = """Installing...""")
        header.Wrap(width - 10)  # -10 because boarder below is 5 pixels wide

        self.sizer.Add(header)
        self.box1 = wx.BoxSizer(wx.VERTICAL)

        # We expect to print 4 lines of information, reserve space using blank
        # lines.
        self.settings_summary_text = wx.StaticText(self, label = "\n\n\n\n")
        self.settings_summary_text.Wrap(width - 10)

        self.box1.Add(self.settings_summary_text, 0, wx.ALIGN_LEFT | wx.ALL, 5)

        self.start_button = wx.Button(self, 10, "Start", (20, 20))
        self.Bind(wx.EVT_BUTTON, self.start_lmc, self.start_button)

        self.start_button.SetToolTipString("Start creating an image, using the"
                                           "above settings.")

        self.start_button.SetSize(self.start_button.GetBestSize())
        self.box1.Add(self.start_button, 0, wx.ALIGN_LEFT | wx.ALL, 5)

        self.download_guage = wx.Gauge(self, -1, 1000, size=(self.width*2/3,25))

        self.status_grid = wx.FlexGridSizer(0, 2)

        self.status_grid.Add(wx.StaticText(self, label="Downloading files"),
                             0,
                             wx.ALIGN_LEFT | wx.LEFT | wx.RIGHT | wx.TOP,
                             5)

        self.downloading_files_status = wx.StaticText(self, label="")
        
        self.status_grid.Add(self.downloading_files_status,
                             0,
                             wx.ALIGN_LEFT | wx.LEFT | wx.RIGHT | wx.TOP,
                             5)

        self.status_grid.Add(self.download_guage,
                             0,
                             wx.ALIGN_LEFT | wx.LEFT | wx.RIGHT | wx.TOP,
                             5)

        self.downloading_files_info = wx.StaticText(self, label="")
        
        self.status_grid.Add(self.downloading_files_info,
                             0,
                             wx.ALIGN_LEFT | wx.LEFT | wx.RIGHT | wx.TOP,
                             5)

        self.status_grid.Add(wx.StaticText(self, label="Unpacking downloads"),
                             0,
                             wx.ALIGN_LEFT | wx.LEFT | wx.RIGHT | wx.TOP,
                             5)

        self.unpacking_files_status = wx.StaticText(self, label="")

        self.status_grid.Add(self.unpacking_files_status,
                             0,
                             wx.ALIGN_LEFT | wx.LEFT | wx.RIGHT | wx.TOP,
                             5)

        self.status_grid.Add(wx.StaticText(self, label="Installing packages"),
                             0,
                             wx.ALIGN_LEFT | wx.LEFT | wx.RIGHT | wx.TOP,
                             5)

        self.installing_packages_status = wx.StaticText(self, label="")

        self.status_grid.Add(self.installing_packages_status,
                             0,
                             wx.ALIGN_LEFT | wx.LEFT | wx.RIGHT | wx.TOP,
                             5)

        self.status_grid.Add(wx.StaticText(self, label="Create file system"),
                             0,
                             wx.ALIGN_LEFT | wx.LEFT | wx.RIGHT | wx.TOP,
                             5)

        self.create_file_system_status = wx.StaticText(self, label="")

        self.status_grid.Add(self.create_file_system_status,
                             0,
                             wx.ALIGN_LEFT | wx.LEFT | wx.RIGHT | wx.TOP,
                             5)

        self.status_grid.Add(wx.StaticText(self, label="Populate file system"),
                             0,
                             wx.ALIGN_LEFT | wx.LEFT | wx.RIGHT | wx.TOP,
                             5)

        self.populate_file_system_status = wx.StaticText(self, label="")

        self.status_grid.Add(self.populate_file_system_status,
                             0,
                             wx.ALIGN_LEFT | wx.LEFT | wx.RIGHT | wx.TOP,
                             5)

        self.sizer.Add(self.box1, 0, wx.ALIGN_LEFT | wx.ALL, 5)
        self.sizer.Add(self.status_grid, 0, wx.ALIGN_LEFT | wx.ALL, 5)
        self.SetSizerAndFit(self.sizer)
        self.sizer.Fit(self)
        self.Move((50, 50))

    def on_activate(self):
        """Called just before the page is displayed to update the text based on
        the users preferences."""

        # The build is stored in different forms depending on if we are using a
        # release or snapshot but from here on in it is a common value
        if self.settings['release_or_snapshot'] == "snapshot":
            self.settings['build'] = self.settings['snapshot_build']
        else:
            self.settings['build'] = self.settings['release_build']

        settings_summary = ("Press start to create an image with the "
                            "following settings:\n")
        settings_summary += "Operating System: " + self.settings['image'] + "\n"
        settings_summary += "Hardware: " + self.settings['hardware'] + "\n"

        # Assumption is that a file may be in a long path, we don't know how
        # big the font is and we don't want to allow the path to run off the
        # end of the line, so if a file is chosen, just show the file name.
        # Devices are (probably) /dev/some_short_name and the user really needs
        # to check them, so we show the whole thing.
        path = self.settings['path_selected']
        if self.settings['write_to_file_or_device'] == "file":
            path = self.settings['path_selected'].split(os.sep)[-1]

        settings_summary += (  "Writing image to "
                             + self.settings['write_to_file_or_device']
                             + " " 
                             + path)

        self.settings_summary_text.SetLabel(settings_summary)
        self.settings_summary_text.Wrap(self.width - 10)

    def start_lmc(self, event):
        """Start a thread that runs linaro-media-create and a timer, which
        checks for UI updates every 100ms"""

        if self.settings['write_to_file_or_device'] == "file":
            self.settings['image_file'] = self.settings['path_selected']
        elif self.settings['write_to_file_or_device'] == "device":
            self.settings['mmc'] = self.settings['path_selected']
        else:
            assert False, ("self.config.settings['write_to_file_or_device'] "
                           "was an unexpected value"
                           + self.settings['write_to_file_or_device'])

        image_url, hwpack_url = self.db.get_image_and_hwpack_urls(self.settings)

        # Currently the UI is blocked when LMC is running, so grey out the
        # buttons to indicate to the user that they won't work!
        self.wizard.FindWindowById(wx.ID_BACKWARD).Disable()
        self.wizard.FindWindowById(wx.ID_CANCEL).Disable()

        if(image_url and hwpack_url):

            self.file_handler = FetchImage.FileHandler()

            self.timer = wx.Timer(self)
            self.Bind(wx.EVT_TIMER, self.timer_ping, self.timer)
            self.timer.Start(milliseconds=100, oneShot=True)

            tools_dir = os.path.dirname(__file__)
            if tools_dir == '':
                tools_dir = None

            self.start_button.Disable()
            self.event_queue = Queue.Queue()
            self.lmc_thread = self.file_handler.LinaroMediaCreate(
                                                    image_url,
                                                    hwpack_url,
                                                    self.file_handler,
                                                    self.event_queue,
                                                    self.settings,
                                                    tools_dir)
            self.lmc_thread.start()
        else:
            print >> sys.stderr, ("Unable to find files that match the"
                                  "parameters specified")

    def timer_ping(self, event):
        """During start_lmc a timer is started to poll for events from
        linaro-media-create every 100ms. This is the function which is called
        to do that polling."""

        while not self.event_queue.empty():
            event = self.event_queue.get()

            if event[0] == "start":
                self.event_start(event[1])

            elif event[0] == "end":
                self.event_end(event[1])

            elif event == "terminate":
                # Process complete. Enable next button.
                self.wizard.FindWindowById(wx.ID_FORWARD).Enable()
                self.populate_file_system_status.SetLabel("Done")
                return # Even if queue isn't empty, stop processing it

            elif event[0] == "update":
                self.event_update(event[1], event[2], event[3])

            else:
                print >> sys.stderr, "timer_ping: Unhandled event", event

        self.timer.Start(milliseconds=50, oneShot=True)

    def unsigned_packages_query(self, package_list):
        message = ('In order to continue, I need to install some unsigned'
                   'packages into the image. Is this OK? The packages are:'
                   '\n\n' + package_list)

        dlg = wx.MessageDialog(self,
                               message,
                               'Install Unsigned Packages Into Image?',
                               wx.YES_NO | wx.NO_DEFAULT)

        choice = dlg.ShowModal()
        dlg.Destroy()

        return choice == wx.ID_YES

    #--- Event(s) ---
    def event_start(self, event):
        if event == "download OS":
            self.downloading_files_status.SetLabel("Downloading OS")
        elif event == "download hwpack":
            self.downloading_files_status.SetLabel("Downloading Hardware Pack")
        elif event == "unpack":
            self.unpacking_files_status.SetLabel("Running")
        elif event == "installing packages":
            self.installing_packages_status.SetLabel("Running")

        elif re.search('^unverified_packages:', event):
            # Get rid of event ID and whitespace invariance
            packages = " ".join(event.split()[1:])
            install_unsigned_packages = self.unsigned_packages_query(packages)

            if install_unsigned_packages == False:
                self.file_handler.kill_create_media()
                sys.exit(1)
            else:
                self.lmc_thread.send_to_create_process("y")

        elif event == "create file system":
            self.create_file_system_status.SetLabel("Running")
        elif event == "populate file system":
            self.populate_file_system_status.SetLabel("Running")
        else:
            print "Unhandled start event:", event

    def event_end(self, event):
        if event == "download OS":
            self.downloading_files_status.SetLabel("Done (1/2)")
        elif event == "download hwpack":
            self.downloading_files_status.SetLabel("Done")
        elif event == "unpack":
            self.unpacking_files_status.SetLabel("Done")
        elif event == "installing packages":
            self.installing_packages_status.SetLabel("Done")
        elif event == "create file system":
            self.create_file_system_status.SetLabel("Done")
        elif event == "populate file system":
            self.populate_file_system_status.SetLabel("Done")
        else:
            print "Unhhandled end event:", event

    def event_update(self, task, update_type, value):
        if task == "download":
            if update_type == "name":
                self.downloading_files_status.SetLabel("Downloading")
                self.old_time = time.time()
                self.old_bytes_downloaded = 0

            elif update_type == "progress":
                self.total_bytes_downloaded += value
                percent_complete = (  float(self.total_bytes_downloaded)
                                    / float(self.total_bytes_to_download))
                #self.downloading_files_info.SetLabel("{0:.1%}".format(
                #                                            percent_complete))

                time_difference = time.time() - self.old_time
                
                if time_difference > 1.0:
                    self.old_time = time.time()
                    
                    # More than a second has passed since we calculated data
                    # rate
                    speed = (  float(  self.total_bytes_downloaded
                                     - self.old_bytes_downloaded)
                             / time_difference)
                    
                    self.old_bytes_downloaded = self.total_bytes_downloaded
                    
                    self.speeds.append(speed)
                    
                    average_speed = 0
                    speeds_accumulated = 0
                    for speed in reversed(self.speeds):
                        average_speed += speed
                        speeds_accumulated += 1
                        
                        if speeds_accumulated == 6:
                            break # do rolling average of 6 seconds

                    average_speed /= speeds_accumulated

                    time_remaining = (  (  self.total_bytes_to_download
                                         - self.total_bytes_downloaded)
                                      / speed)

                    pretty_time = str(datetime.timedelta(seconds=
                                                         int(time_remaining)))

                    # Following table assumes we don't get past TBps internet
                    # connections soon :-)
                    units = ["Bps", "kBps", "MBps", "GBps", "TBps"]
                    units_index = 0
                    while speed > 1024:
                        speed /= 1024
                        units_index += 1

                    info = "Downloading at {0:.1f} {1}".format(
                                                         speed,
                                                         units[units_index])
                    
                    self.downloading_files_status.SetLabel(info)
                    
                    info = "{0} remaining".format(
                                                         pretty_time)
                    
                    self.downloading_files_info.SetLabel(info)

                self.download_guage.SetValue(  1000
                                             * self.total_bytes_downloaded
                                             / self.total_bytes_to_download)

            elif update_type == "total bytes":
                self.total_bytes_to_download = value
                self.total_bytes_downloaded = 0
                self.speeds = [] # keep an array of speeds used to calculate
                # the estimated time remaining - by not just using the
                # current speed we can stop the ETA bouncing around too much.

    def event_combo_box_release(self, evt):
        pass

    def event_combo_box_build(self, evt):
        pass
    #--- END event(s) ---


class TestDriveWizard(wx.wizard.Wizard):
    def __init__(self, title):
        wx.wizard.Wizard.__init__(self, None, -1, title, wx.NullBitmap)
        self.Bind(wx.wizard.EVT_WIZARD_PAGE_CHANGING, self.on_page_changing)
        self.done_startup = False

    def on_page_changing(self, evt):
        'Executed before the page changes.'

        if self.done_startup == False:
            self.pages['lmc_settings'].box2.Hide(
                            self.pages['lmc_settings'].optional_settings_box,
                            True)

            self.pages['lmc_settings'].box3.Hide(
                            self.pages['lmc_settings'].confirm_mmc_usage_box,
                            True)

            self.done_startup = True

        page = evt.GetPage()

        if evt.GetDirection():  # If going forwards...
            # Always enable back button if going forwards
            self.wizard.FindWindowById(wx.ID_BACKWARD).Enable()

            # If going from a select snapshot or select release page, record
            # which we were on so the back button of the next page works
            if(self.config.settings['release_or_snapshot'] == "release"):
                self.pages['select_os'].SetNext(self.pages['select_release'])
                self.pages['select_release'].SetPrev(self.pages['select_os'])

                self.pages['select_release'].SetNext(self.pages['lmc_settings'])
                self.pages['lmc_settings'].SetPrev(self.pages['select_release'])
            else:
                self.pages['select_os'].SetNext(self.pages['select_snapshot'])
                self.pages['select_snapshot'].SetPrev(self.pages['select_os'])

                if(page == self.pages['select_os']):
                    self.pages['select_snapshot'].fill_build_combo_box_for_date(
                                            self.config.settings['build_date'])

                self.pages['select_snapshot'].SetNext(self.pages['lmc_settings'])
                self.pages['lmc_settings'].SetPrev(self.pages['select_snapshot'])

            if page == self.pages['hardware_details']:
                self.pages['select_os'].fill_os_list()

            if page == self.pages['release_or_snapshot']:
                self.pages['hardware_details'].on_page_changing()

            # If about to move into the release selection, make sure the list
            # is populated only with releases that are valid with our current
            # selection
            if(    page == self.pages['select_os']
               and self.config.settings['release_or_snapshot'] == "release"):
                self.pages['select_release'].update_release_and_build_boxes()

            if page == self.pages['select_snapshot']:
                # Execute when exiting page
                self.pages['select_snapshot'].update_platform()

            if(   page == self.pages['select_snapshot']
               or page == self.pages['select_release']):
                self.pages['lmc_settings'].on_activate()

            if page == self.pages['lmc_settings']:
                # Forward stays disabled until LMC has finished running
                self.wizard.FindWindowById(wx.ID_FORWARD).Disable()
                self.pages['run_lmc'].on_activate()

        else:  # Always enable the forward button if reversing into a page
            self.wizard.FindWindowById(wx.ID_FORWARD).Enable()

    def go(self, first_page):
        file_handler = FetchImage.FileHandler()
        self.config = FetchImage.FetchImageConfig()
        self.config.settings["force_download"] = False
        self.config.settings['compatable_hwpacks'] = ['foo']

        # If the settings file and server index need updating, grab them
        file_handler.update_files_from_server()

        # Load settings YAML, which defines the parameters we ask for and
        # acceptable responses from the user
        self.config.read_config(file_handler.settings_file)

        # Using the config we have, look up URLs to download data from in
        # the server index
        db = FetchImage.DB(file_handler.index_file)

        # Create the wizard and the pages
        self.wizard = wiz.Wizard(self, -1, "Linaro Media Builder")

        self.pages = {}
        self.pages['release_or_snapshot'] = ReleaseOrSnapshotPage(self.wizard,
                                                                  self.config)
        self.wizard.FitToPage(self.pages['release_or_snapshot'])
        (width, height) = self.wizard.GetSize()

        self.pages['hardware_details']  = AboutMyHardwarePage(self.wizard,
                                                              self.config,
                                                              db,
                                                              width)

        self.pages['select_release']    = SelectStableRelease(self.wizard,
                                                              self.config,
                                                              db,
                                                              width)

        self.pages['select_snapshot']   = SelectSnapshot(self.wizard,
                                                         self.config,
                                                         db,
                                                         width)

        self.pages['select_os']         = SelectOS(self.wizard,
                                                   self.config,
                                                   db,
                                                   width)

        self.pages['lmc_settings']      = LMC_settings(self.wizard,
                                                       self.config,
                                                       db,
                                                       width)

        self.pages['run_lmc']           = RunLMC(self.wizard,
                                                 self.config,
                                                 db,
                                                 width)

        self.pages['release_or_snapshot'].SetNext(
                                            self.pages['hardware_details'])

        self.pages['hardware_details'].SetPrev(
                                            self.pages['release_or_snapshot'])

        self.pages['hardware_details'].SetNext(self.pages['select_os'])
        self.pages['select_os'].SetPrev(self.pages['hardware_details'])
        # Select OS goes to select build, which is customised for
        # releases or snapshots
        self.pages['lmc_settings'].SetNext(self.pages['run_lmc'])
        self.pages['run_lmc'].SetPrev(self.pages['lmc_settings'])

        for (name, page) in self.pages.items():
            self.wizard.GetPageAreaSizer().Add(page)

        self.wizard.RunWizard(self.pages['release_or_snapshot'])


def run(start_page = None):
    """Wrapper around the full wizard. Is encapsulated in its own function to
       allow a restart to be performed, as described in __main___, easily"""
    app = wx.PySimpleApp()  # Start the application
    #logging.basicConfig(level=logging.INFO)
    w = TestDriveWizard('Simple Wizard')
    return w.go(start_page)


class TestURLLookupFunctions(unittest.TestCase):

    def setUp(self):
        self.file_handler   = FetchImage.FileHandler()
        self.file_handler.update_files_from_server()
        self.config         = FetchImage.FetchImageConfig()
        self.config.settings["force_download"] = False

        # Load settings YAML, which defines the parameters we ask for and
        # acceptable responses from the user
        self.config.read_config(self.file_handler.settings_file)

        # Using the config we have, look up URLs to download data from in the
        # server index
        self.db = FetchImage.DB(self.file_handler.index_file)

    def test_url_lookup(self):
        self.settings = self.config.settings
        self.settings['release_or_snapshot'] = "snapshot"

        #--- Test first with a snapshot build lookup ---
        # -- Fix a build date --
        # We only need to look up a single snapshot date. Start with today and
        # go with the day in the DB, build 0
        today = wx.DateTime()
        today.SetToCurrent()

        # -- Don't iterate through platforms for snapshot --

        # -- Select hardware --
        for self.settings['hardware'] in (
                                   self.settings['choice']['hardware'].keys()):

            compatable_hwpacks = self.settings['choice']['hwpack'][
                                                    self.settings['hardware']]

            future_date, past_date = self.db.get_next_prev_day_with_builds(
                                        "linaro-alip",
                                        today.FormatISODate().encode('ascii'),
                                        compatable_hwpacks)

            if past_date == None:
                # Some hardware packs are not available in the snapshot repo,
                # so just skip if they aren't
                continue

            builds = self.db.get_binary_builds_on_day_from_db(
                                                        "linaro-alip",
                                                        past_date,
                                                        compatable_hwpacks)

            self.assertTrue(len(builds))
            # If the above assert fails, either the DB is empty, or
            # db.get_binary_builds_on_day_from_db failed

            small_date = re.sub('-', '', past_date)
            self.settings['build'] = small_date + ":" + "0"

            # -- Iterate through hardware packs --
            for self.settings['hwpack'] in compatable_hwpacks:

                # If hardware pack is available...
                if(self.settings['hwpack']
                    in self.db.get_hwpacks('snapshot_hwpacks')):

                    # -- Iterate through images
                    os_list = self.db.get_os_list_from('snapshot_binaries')

                    for self.settings['image'] in os_list:
                        if re.search('old', self.settings['image']):
                            # Directories with old in the name are of no
                            # interest to us
                            continue

                        # -- Check build which matches these parameters
                        #    (builds that don't match are excluded in UI) --
                        if(    len(self.db.execute_return_list(
                                    'select * from snapshot_hwpacks '
                                    'where hardware == ? '
                                    'and date == ? '
                                    'and build == ?',
                                    (self.settings['hwpack'],
                                     small_date,
                                     "0")))
                           and len(self.db.execute_return_list(
                                    'select * from snapshot_binaries '
                                    'where image == ? '
                                    'and date == ? '
                                    'and build == ?',
                                    (self.settings['image'],
                                     small_date,
                                     "0")))):

                            # - Run the function under test! -
                            image_url, hwpack_url = (
                              self.db.get_image_and_hwpack_urls(self.settings))

                            self.assertTrue(image_url)
                            self.assertTrue(hwpack_url)

        #--- Now test release build lookup ---
        self.settings['release_or_snapshot'] = "release"
        # -- Select hardware --
        for self.settings['hardware'] in (
                                    self.settings['choice']['hardware'].keys()):
            compatable_hwpacks = (
                  self.settings['choice']['hwpack'][self.settings['hardware']])

            # -- Iterate through hardware packs --
            for self.settings['hwpack'] in compatable_hwpacks:

                # If hardware pack is available...
                if(self.settings['hwpack']
                    in self.db.get_hwpacks('release_hwpacks')):

                    # -- Iterate through images
                    os_list = self.db.get_os_list_from('release_binaries')

                    for self.settings['image'] in os_list:
                        if re.search('old', self.settings['image']):
                            # Directories with old in the name are of no
                            # interest to us
                            continue

                        for platform, ignore in (
                                  self.settings['choice']['platform'].items()):
                            self.settings['platform'] = platform

                            # -- Iterate through available builds --
                            builds = self.db.get_builds(
                                                    self.settings['platform'],
                                                    self.settings['image'])

                            for build in builds:
                                self.settings['build'] = build

                                # -- Check build which matches these parameters
                                #(builds that don't match are excluded in UI)--
                                if(    len(self.db.execute_return_list(
                                            'select * from release_hwpacks '
                                            'where platform == ? '
                                            'and hardware == ? '
                                            'and build == ?',
                                            (self.settings['platform'],
                                             self.settings['hwpack'],
                                             self.settings['build'])))
                                   and len(self.db.execute_return_list(
                                            'select * from release_binaries '
                                            'where platform == ? '
                                            'and image == ? '
                                            'and build == ?',
                                            (self.settings['platform'],
                                             self.settings['image'],
                                             self.settings['build'])))):

                                    # - Run the function under test! -
                                    image_url, hwpack_url = (
                                        self.db.get_image_and_hwpack_urls(self.settings))
                                    self.assertTrue(image_url)
                                    self.assertTrue(hwpack_url)

if __name__ == '__main__':
    run()
