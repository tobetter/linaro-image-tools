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

import os, sys, re
import linaro_image_tools.FetchImage as FetchImage
import logging

if __name__ == '__main__':
    
    file_handler = FetchImage.FileHandler()
    config = FetchImage.Config()
    
    # Unfortunately we need to do a bit of a hack here and look for some options before performing
    # a full options parse.
    clean_cache = (   "--clean-cache" in sys.argv[1:]
                   or "-x" in sys.argv[1:])
    
    force_download = (   "--force-download" in sys.argv[1:]
                      or "-d" in sys.argv[1:])
    
    # If the settings file and server index need updating, grab them
    file_handler.update_files_from_server(force_download)
    
    # Load settings YAML, which defines the parameters we ask for and acceptable responses from the user
    config.read_config(file_handler.settings_file)

    # Using the settings that the YAML defines as what we need for a build, generate a command line parser
    # and parse the command line
    config.parse_args(sys.argv[1:])

    if config.args['platform'] == "snapshot":
        config.args['release_or_snapshot'] = "snapshot"
    else:
        config.args['release_or_snapshot'] = "release"

    # Using the config we have, look up URLs to download data from in the server index
    db = FetchImage.DB(file_handler.index_file)

    image_url, hwpack_url = db.get_image_and_hwpack_urls(config.args)

    if(image_url and hwpack_url):
        file_handler.create_media(image_url, hwpack_url, config.args)
    else:
       logging.error("Unable to find files that match the parameters specified")
