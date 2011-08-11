# Copyright (C) 2010, 2011 Linaro
#
# Author: James Tunnicliffe <james.tunnicliffe@linaro.org>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
import inspect
import os
import wx
from linaro_image_tools.testing import TestCaseWithFixtures
import re
import linaro_image_tools.fetch_image as fetch_image


class TestURLLookupFunctions(TestCaseWithFixtures):

    def setUp(self):
        # We use local files for testing, so get paths sorted.
        this_file = os.path.abspath(inspect.getfile(inspect.currentframe()))
        this_dir = os.path.dirname(this_file)
        yaml_file_location = os.path.join(this_dir, "../"
                                          "fetch_image_settings.yaml")
        sample_db_location = os.path.join(this_dir, "test_server_index.sqlite")
        self.file_handler   = fetch_image.FileHandler()
        self.config         = fetch_image.FetchImageConfig()
        self.config.settings["force_download"] = False

        # Load settings YAML, which defines the parameters we ask for and
        # acceptable responses from the user
        self.config.read_config(yaml_file_location)

        # Using the config we have, look up URLs to download data from in the
        # server index
        self.db = fetch_image.DB(sample_db_location)

        super(TestURLLookupFunctions, self).setUp()

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
                                             self.db.get_image_and_hwpack_urls(
                                                      self.settings))
                                    self.assertTrue(image_url)
                                    self.assertTrue(hwpack_url)
