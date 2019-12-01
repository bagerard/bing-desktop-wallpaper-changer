#!/usr/bin/python
# -*- coding: utf-8 -*-

import locale
import os
import re
import sys
import traceback
import time
import fnmatch
import random
import argparse
import ctypes
import struct

# replace with the actual path to the bing-desktop-wallpaper-changer folder
path_to_Bing_Wallpapers = "/path/to/bing-desktop-wallpaper-changer"

import ctypes
import struct

try:  # try python 3 import
    from urllib.request import urlopen
    from urllib.request import urlretrieve
    from configparser import ConfigParser
except ImportError:  # fall back to python2
    from urllib import urlretrieve
    from urllib2 import urlopen
    from ConfigParser import ConfigParser

import xml.etree.ElementTree as ET
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Notify", "0.7")
from gi.repository import Gio
from gi.repository import Gtk
from gi.repository import Notify
from subprocess import check_output

BING_MARKETS = [
    u"ar-XA",
    u"bg-BG",
    u"cs-CZ",
    u"da-DK",
    u"de-AT",
    u"de-CH",
    u"de-DE",
    u"el-GR",
    u"en-AU",
    u"en-CA",
    u"en-GB",
    u"en-ID",
    u"en-IE",
    u"en-IN",
    u"en-MY",
    u"en-NZ",
    u"en-PH",
    u"en-SG",
    u"en-US",
    u"en-XA",
    u"en-ZA",
    u"es-AR",
    u"es-CL",
    u"es-ES",
    u"es-MX",
    u"es-US",
    u"es-XL",
    u"et-EE",
    u"fi-FI",
    u"fr-BE",
    u"fr-CA",
    u"fr-CH",
    u"fr-FR",
    u"he-IL",
    u"hr-HR",
    u"hu-HU",
    u"it-IT",
    u"ja-JP",
    u"ko-KR",
    u"lt-LT",
    u"lv-LV",
    u"nb-NO",
    u"nl-BE",
    u"nl-NL",
    u"pl-PL",
    u"pt-BR",
    u"pt-PT",
    u"ro-RO",
    u"ru-RU",
    u"sk-SK",
    u"sl-SL",
    u"sv-SE",
    u"th-TH",
    u"tr-TR",
    u"uk-UA",
    u"zh-CN",
    u"zh-HK",
    u"zh-TW",
]

config_file_skeleton = """[market]
# If you want to override the current Bing market dectection,
# set your preferred market here. For a list of markets, see
# https://msdn.microsoft.com/en-us/library/dd251064.aspx
area =
[directory]
# Download directory path. By default images are saved to
# /home/[user]/[Pictures]/BingWallpapers/
dir_path =
# Limit the size of the downloaded image directory
# Size should be specified in bytes. The minimum 
# limit is the size of 1 image (whatever size that image is)
# Set to negative value for unlimit. Default value is 100MiB
dir_max_size = 
"""


def uptime():
    libc = ctypes.CDLL("libc.so.6")
    buf = ctypes.create_string_buffer(4096)  # generous buffer to hold
    # struct sysinfo
    if libc.sysinfo(buf) != 0:
        print("failed")
        return -1

    uptime = struct.unpack_from("@l", buf.raw)[0]
    return uptime


# wait computer internet connection
if uptime() < 120:
    print("waiting for internet connection...")
    time.sleep(10)


def get_file_uri(filename):
    return "file://%s" % filename


def set_gsetting(schema, key, value):
    gsettings = Gio.Settings.new(schema)
    gsettings.set_string(key, value)
    gsettings.apply()


def change_background_gnome(filename):
    set_gsetting("org.gnome.desktop.background", "picture-uri", get_file_uri(filename))


def change_background_cinnamon(filename):
    set_gsetting(
        "org.cinnamon.desktop.background", "picture-uri", get_file_uri(filename)
    )


def _get_current_background_gnome_uri():
    gsettings = Gio.Settings.new("org.gnome.desktop.background")
    path = gsettings.get_string("picture-uri")
    return path[7:]


def _get_current_background_cinnamon_uri():
    gsettings = Gio.Settings.new("org.cinnamon.desktop.background")
    path = gsettings.get_string("picture-uri")
    return path[7:]


def get_current_background_uri():
    source = Gio.SettingsSchemaSource.get_default()
    cinnamon_exists = source.lookup("org.cinnamon.desktop.background", True)
    if cinnamon_exists:
        current = _get_current_background_cinnamon_uri()
    else:
        current = _get_current_background_gnome_uri()
    return current


def change_screensaver(filename):
    set_gsetting("org.gnome.desktop.screensaver", "picture-uri", get_file_uri(filename))


def get_config_file():
    """
    Get the path to the program's config file.

    :return: Path to the program's config file.
    """
    config_dir = os.path.join(
        os.path.expanduser("~"), ".config", "bing-desktop-wallpaper-changer"
    )
    init_dir(config_dir)
    config_path = os.path.join(config_dir, "config.ini")
    if not os.path.isfile(config_path):
        with open(config_path, "w") as config_file:
            config_file.write(config_file_skeleton)
    return config_path


def get_market():
    """
    Get the desired Bing Market.

    In order of preference, this program will use:
    * Config value market.area from desktop_wallpaper_changer.ini
    * Default locale, in case that's a valid Bing market
    * Fallback value is 'en-US'.

    :return: Bing Market
    :rtype: str
    """
    config = ConfigParser()
    config.read(get_config_file())
    market_area_override = config.get("market", "area")
    if market_area_override:
        return market_area_override

    default_locale = locale.getdefaultlocale()[0]
    if default_locale in BING_MARKETS:
        return default_locale

    return "en-US"


def get_download_path():
    # By default images are saved to '/home/[user]/[Pictures]/BingWallpapers/'
    default_path = (
        check_output("xdg-user-dir PICTURES", shell=True).strip().decode("utf-8")
        + "/BingWallpapers"
    )

    try:
        config = ConfigParser()
        config.read(get_config_file())
        path = config.get("directory", "dir_path")

        return path or default_path
    except Exception:
        return default_path


def get_directory_limit():
    """
    Get the directory sized limit
    """
    config = ConfigParser()
    config.read(get_config_file())
    try:
        size = config.getint("directory", "dir_max_size")
        return size
    except Exception:
        return 100 * 1024 * 1024


def get_bing_xml():
    """
    Get BingXML file which contains the URL of the Bing Photo of the day.

    :return: URL with the Bing Photo of the day.
    """
    # idx = Number days previous the present day.
    # 0 means today, 1 means yesterday
    # n = Number of images previous the day given by idx
    # mkt = Bing Market Area, see get_valid_bing_markets.
    market = get_market()
    return (
        "https://www.bing.com/HPImageArchive.aspx?format=xml&idx=0&n=1&mkt=%s" % market
    )


def get_screen_resolution_str():
    """
    Get a regexp like string with your current screen resolution.

    :return: String with your current screen resolution.
    """
    sizes = [
        [800, [600]],
        [1024, [768]],
        [1280, [720, 768]],
        [1366, [768]],
        [1920, [1080, 1200]],
    ]
    sizes_mobile = [[768, [1024]], [720, [1280]], [768, [1280, 1366]], [1080, [1920]]]
    default_w = 1920
    default_h = 1080
    default_mobile_w = 1080
    default_mobile_h = 1920
    is_mobile = False
    window = Gtk.Window()
    screen = window.get_screen()
    nmons = screen.get_n_monitors()
    maxw = 0
    maxh = 0
    sizew = 0
    sizeh = 0
    if nmons == 1:
        maxw = screen.get_width()
        maxh = screen.get_height()
    else:
        for m in range(nmons):
            mg = screen.get_monitor_geometry(m)
            if mg.width > maxw or mg.height > maxw:
                maxw = mg.width
                maxh = mg.height
    if maxw > maxh:
        v_array = sizes
    else:
        v_array = sizes_mobile
        is_mobile = True
    for m in v_array:
        if maxw <= m[0]:
            sizew = m[0]
            sizeh = m[1][len(m[1]) - 1]
            for e in m[1]:
                if maxh <= e:
                    sizeh = e
                    break
            break

    if sizew == 0:
        if is_mobile:
            sizew = default_mobile_w
            sizeh = default_mobile_h
        else:
            sizew = default_w
            sizeh = default_h

    return r"%sx%s" % (sizew, sizeh)


def get_bing_image_metadata():
    """
    Get Bing wallpaper metadata.

    :return: XML tag object for the wallpaper image.
    """
    bing_xml_url = get_bing_xml()
    page = urlopen(bing_xml_url)

    bing_xml = ET.parse(page).getroot()

    # For extracting complete URL of the image
    images = bing_xml.findall("image")
    return images[0]


def get_image_url(metadata):
    """
    Get an appropriate Wallpaper URL based on your screen resolution.

    :param metadata: XML tag object with image metadata.
    :return: URL with Bing Wallpaper image.
    """
    base_image = metadata.find("url").text
    # Replace image resolution with the correct resolution
    # from your main monitor
    screen_size = get_screen_resolution_str()
    correct_resolution_image = re.sub(r"\d+x\d+", screen_size, base_image)
    return "https://www.bing.com" + correct_resolution_image


def init_dir(path):
    """Create directory if it doesn't exist."""
    if not os.path.exists(path):
        os.makedirs(path)


def p2_dirscan(path):
    files = list()
    size = 0

    for e in os.listdir(path):
        entry = path + "/" + e
        if os.path.isfile(entry) and os.path.splitext(entry)[1] == ".jpg":
            s = os.path.getsize(entry)
            files.append((entry, s))
            size = size + s
    files = sorted(files)
    return files, size


def check_limit():
    download_path = get_download_path()
    (files, size) = p2_dirscan(download_path)
    max_size = get_directory_limit()
    while max_size > 0 and size > max_size and len(files) > 1:
        os.remove(files[0][0])
        size = size - files[0][1]
        del files[0]


def get_random_downloaded_image(download_path):
    """Return a random image from a local directory"""
    files = fnmatch.filter(os.listdir(download_path), "*.jpg")
    if not files:
        return None
    picked_file = random.choice(files)
    image_desc = ""
    return os.path.join(download_path, picked_file), image_desc


def fetch_latest_bing_image(download_path):
    image_metadata = get_bing_image_metadata()
    image_name = image_metadata.find("startdate").text + ".jpg"
    image_url = get_image_url(image_metadata)

    image_desc = image_metadata.find("copyright").text.encode("utf-8")
    image_path = os.path.join(download_path, image_name)
    if os.path.isfile(image_path):
        print("Image already exists in directory")
    else:
        print("Downloading `{}` to {}...".format(image_name, image_path))
        urlretrieve(image_url, image_path)
        text = str(image_name) + " -- " + str(image_desc) + "\n"
        with open(download_path + "/image-details.txt", "a+") as myfile:
            print("updating details in image-details.txt")
            myfile.write(text)

    return image_path, image_desc


def get_image_description(download_path, image_path):
    image_name = os.path.basename(image_path)
    with open(download_path + "/image-details.txt", "r") as myfile:
        for line in myfile:
            line = line.decode("utf-8")
            if image_name in line:
                return line.split("-- ", 1)[1]


def set_image_as_background(image_path):
    if not os.path.isfile(image_path):
        raise Exception("Image not found {}".format(image_path))

    image_already_set = os.path.samefile(get_current_background_uri(), image_path)
    if image_already_set:
        print("Image already set as wallpaper")
    else:
        try:
            change_background_gnome(image_path)
        except:
            change_background_cinnamon(image_path)
    change_screensaver(image_path)


def main(switch_wp=False):
    app_name = "Bing Desktop Wallpaper"
    Notify.init(app_name)

    download_path = get_download_path()
    init_dir(download_path)

    exit_status = 0
    summary = ""
    body = ""
    try:
        if switch_wp:
            image_path, image_desc = get_random_downloaded_image(download_path)
        else:
            image_path, image_desc = fetch_latest_bing_image(download_path)

        image_desc = get_image_description(download_path, image_path)
        set_image_as_background(image_path)
        check_limit()
        body = image_desc
    except Exception as err:
        traceback.print_exc()
        summary = "Error executing %s" % app_name
        body = err
        exit_status = 1

    os.chdir(path_to_Bing_Wallpapers)
    icon = os.path.abspath("icon.svg")
    print(summary, unicode(body))
    app_notification = Notify.Notification.new(summary, unicode(body))
    app_notification.show()
    sys.exit(exit_status)


parser = argparse.ArgumentParser(description="Set latest Bingwallpaper as wallpaper")
parser.add_argument(
    "--switch",
    dest="switch",
    action="store_true",
    help="change image by taking one from the local image directory",
)
if __name__ == "__main__":
    results = parser.parse_args()
    switch_wp = results.switch
    main(switch_wp=switch_wp)
