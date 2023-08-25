#!/usr/bin/env python3
"""
NOT1MM Logger
"""
# pylint: disable=unused-import, c-extension-no-member, no-member, invalid-name, too-many-lines, no-name-in-module
# pylint: disable=logging-fstring-interpolation

import datetime as dt
import importlib
import locale
import logging
import os
import pkgutil
import platform
import re
import socket
import subprocess
import sys
import threading
import uuid
from datetime import datetime
from json import JSONDecodeError, dumps, loads
from pathlib import Path
from shutil import copyfile

import notctyparser
import psutil
import sounddevice as sd
import soundfile as sf
from PyQt5 import QtCore, QtGui, QtWidgets, uic
from PyQt5.QtCore import QDir, QPoint, QRect, QSize, Qt
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtWidgets import QFileDialog

from not1mm.lib.about import About
from not1mm.lib.cat_interface import CAT
from not1mm.lib.cwinterface import CW
from not1mm.lib.database import DataBase
from not1mm.lib.edit_macro import EditMacro
from not1mm.lib.edit_opon import OpOn
from not1mm.lib.edit_station import EditStation
from not1mm.lib.ham_utility import (
    bearing,
    bearing_with_latlon,
    calculate_wpx_prefix,
    distance,
    distance_with_latlon,
    get_logged_band,
    getband,
    reciprocol,
    fakefreq,
)
from not1mm.lib.lookup import HamDBlookup, HamQTH, QRZlookup
from not1mm.lib.multicast import Multicast
from not1mm.lib.n1mm import N1MM
from not1mm.lib.new_contest import NewContest
from not1mm.lib.super_check_partial import SCP
from not1mm.lib.select_contest import SelectContest
from not1mm.lib.settings import Settings
from not1mm.lib.version import __version__
from not1mm.lib.versiontest import VersionTest

loader = pkgutil.get_loader("not1mm")
WORKING_PATH = os.path.dirname(loader.get_filename())

DATA_PATH = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
DATA_PATH += "/not1mm"

try:
    os.mkdir(DATA_PATH)
except FileExistsError:
    ...

CONFIG_PATH = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
CONFIG_PATH += "/not1mm"

try:
    os.mkdir(CONFIG_PATH)
except FileExistsError:
    ...


CTYFILE = {}

with open(WORKING_PATH + "/data/cty.json", "rt", encoding="utf-8") as c_file:
    CTYFILE = loads(c_file.read())

poll_time = datetime.now()


def check_process(name: str) -> bool:
    """Checks to see if the name of the program is in the active process list.

    Parameters
    ----------
    name : str

    Returns
    -------
    Bool
    """
    for proc in psutil.process_iter():
        if len(proc.cmdline()) == 2:
            if name in proc.cmdline()[1]:
                return True
    return False


class MainWindow(QtWidgets.QMainWindow):
    """
    The main window
    """

    pref_ref = {
        "sounddevice": "default",
        "useqrz": False,
        "lookupusername": "username",
        "lookuppassword": "password",
        "run_state": True,
        "command_buttons": False,
        "cw_macros": True,
        "bands_modes": True,
        "window_height": 200,
        "window_width": 600,
        "window_x": 120,
        "window_y": 120,
        "current_database": "ham.db",
        "contest": "",
        "multicast_group": "239.1.1.1",
        "multicast_port": 2239,
        "interface_ip": "0.0.0.0",
        "send_n1mm_packets": False,
        "n1mm_station_name": "20M CW Tent",
        "n1mm_operator": "Bernie",
        "n1mm_radioport": "127.0.0.1:12060",
        "n1mm_contactport": "127.0.0.1:12060",
        "n1mm_lookupport": "127.0.0.1:12060",
        "n1mm_scoreport": "127.0.0.1:12060",
        "usehamdb": False,
        "usehamqth": False,
        "cloudlog": False,
        "cloudlogapi": "",
        "cloudlogurl": "",
        "CAT_ip": "127.0.0.1",
        "userigctld": False,
        "useflrig": False,
        "cwip": "127.0.0.1",
        "cwport": 6789,
        "cwtype": 0,
        "useserver": False,
        "CAT_port": 4532,
        "cluster_server": "dxc.nc7j.com",
        "cluster_port": 7373,
        "cluster_filter": "Set DX Filter SpotterCont=NA",
        "cluster_mode": "OPEN",
    }
    appstarted = False
    contact = {}
    contest = None
    contest_settings = {}
    pref = None
    station = {}
    current_op = ""
    current_mode = ""
    current_band = ""
    default_rst = "59"
    cw = None
    look_up = None
    run_state = False
    fkeys = {}
    about_dialog = None
    qrz_dialog = None
    settings_dialog = None
    edit_macro_dialog = None
    contest_dialog = None
    configuration_dialog = None
    opon_dialog = None
    dbname = DATA_PATH + "/ham.db"
    radio_state = {}
    rig_control = None
    multicast_group = None
    multicast_port = None
    interface_ip = None
    rig_control = None
    worked_list = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        logger.info("MainWindow: __init__")
        data_path = WORKING_PATH + "/data/main.ui"
        uic.loadUi(data_path, self)
        self.leftdot.hide()
        self.rightdot.hide()
        self.n1mm = N1MM()
        self.mscp = SCP(WORKING_PATH)
        self.next_field = self.other_2
        self.dupe_indicator.hide()
        self.cw_speed.valueChanged.connect(self.cwspeed_spinbox_changed)

        self.actionCW_Macros.triggered.connect(self.cw_macros_state_changed)
        self.actionCommand_Buttons.triggered.connect(self.command_buttons_state_change)
        self.actionLog_Window.triggered.connect(self.launch_log_window)
        self.actionBandmap.triggered.connect(self.launch_bandmap_window)
        self.actionCheck_Window.triggered.connect(self.launch_check_window)
        self.actionVFO.triggered.connect(self.launch_vfo)
        self.actionRecalculate_Mults.triggered.connect(self.recalculate_mults)

        self.actionGenerate_Cabrillo.triggered.connect(self.generate_cabrillo)
        self.actionGenerate_ADIF.triggered.connect(self.generate_adif)

        self.actionConfiguration_Settings.triggered.connect(
            self.edit_configuration_settings
        )
        self.actionStationSettings.triggered.connect(self.edit_station_settings)

        self.actionNew_Contest.triggered.connect(self.new_contest_dialog)
        self.actionOpen_Contest.triggered.connect(self.open_contest)
        self.actionEdit_Current_Contest.triggered.connect(self.edit_contest)

        self.actionNew_Database.triggered.connect(self.new_database)
        self.actionOpen_Database.triggered.connect(self.open_database)

        self.actionEdit_Macros.triggered.connect(self.edit_cw_macros)

        self.actionAbout.triggered.connect(self.show_about_dialog)
        self.actionHotKeys.triggered.connect(self.show_key_help)
        self.actionHelp.triggered.connect(self.show_help_dialog)
        self.actionUpdate_CTY.triggered.connect(self.check_for_new_cty)
        self.actionUpdate_MASTER_SCP.triggered.connect(self.update_masterscp)
        self.actionQuit.triggered.connect(self.quit_app)

        self.radioButton_run.clicked.connect(self.run_sp_buttons_clicked)
        self.radioButton_sp.clicked.connect(self.run_sp_buttons_clicked)
        self.score.setText("0")
        self.callsign.textEdited.connect(self.callsign_changed)
        self.callsign.returnPressed.connect(self.save_contact)
        self.sent.returnPressed.connect(self.save_contact)
        self.receive.returnPressed.connect(self.save_contact)
        self.other_1.returnPressed.connect(self.save_contact)
        self.other_1.textEdited.connect(self.other_1_changed)
        self.other_2.returnPressed.connect(self.save_contact)
        self.other_2.textEdited.connect(self.other_2_changed)

        self.sent.setText("59")
        self.receive.setText("59")
        icon_path = WORKING_PATH + "/data/"
        self.greendot = QtGui.QPixmap(icon_path + "greendot.png")
        self.reddot = QtGui.QPixmap(icon_path + "reddot.png")
        self.leftdot.setPixmap(self.greendot)
        self.rightdot.setPixmap(self.reddot)

        self.F1.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.F1.customContextMenuRequested.connect(self.edit_F1)
        self.F1.clicked.connect(self.sendf1)
        self.F2.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.F2.customContextMenuRequested.connect(self.edit_F2)
        self.F2.clicked.connect(self.sendf2)
        self.F3.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.F3.customContextMenuRequested.connect(self.edit_F3)
        self.F3.clicked.connect(self.sendf3)
        self.F4.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.F4.customContextMenuRequested.connect(self.edit_F4)
        self.F4.clicked.connect(self.sendf4)
        self.F5.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.F5.customContextMenuRequested.connect(self.edit_F5)
        self.F5.clicked.connect(self.sendf5)
        self.F6.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.F6.customContextMenuRequested.connect(self.edit_F6)
        self.F6.clicked.connect(self.sendf6)
        self.F7.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.F7.customContextMenuRequested.connect(self.edit_F7)
        self.F7.clicked.connect(self.sendf7)
        self.F8.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.F8.customContextMenuRequested.connect(self.edit_F8)
        self.F8.clicked.connect(self.sendf8)
        self.F9.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.F9.customContextMenuRequested.connect(self.edit_F9)
        self.F9.clicked.connect(self.sendf9)
        self.F10.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.F10.customContextMenuRequested.connect(self.edit_F10)
        self.F10.clicked.connect(self.sendf10)
        self.F11.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.F11.customContextMenuRequested.connect(self.edit_F11)
        self.F11.clicked.connect(self.sendf11)
        self.F12.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.F12.customContextMenuRequested.connect(self.edit_F12)
        self.F12.clicked.connect(self.sendf12)

        self.cw_band_160.mousePressEvent = self.click_160_cw
        self.cw_band_80.mousePressEvent = self.click_80_cw
        self.cw_band_40.mousePressEvent = self.click_40_cw
        self.cw_band_20.mousePressEvent = self.click_20_cw
        self.cw_band_15.mousePressEvent = self.click_15_cw
        self.cw_band_10.mousePressEvent = self.click_10_cw

        self.ssb_band_160.mousePressEvent = self.click_160_ssb
        self.ssb_band_80.mousePressEvent = self.click_80_ssb
        self.ssb_band_40.mousePressEvent = self.click_40_ssb
        self.ssb_band_20.mousePressEvent = self.click_20_ssb
        self.ssb_band_15.mousePressEvent = self.click_15_ssb
        self.ssb_band_10.mousePressEvent = self.click_10_ssb

        self.rtty_band_160.mousePressEvent = self.click_160_rtty
        self.rtty_band_80.mousePressEvent = self.click_80_rtty
        self.rtty_band_40.mousePressEvent = self.click_40_rtty
        self.rtty_band_20.mousePressEvent = self.click_20_rtty
        self.rtty_band_15.mousePressEvent = self.click_15_rtty
        self.rtty_band_10.mousePressEvent = self.click_10_rtty

        self.readpreferences()
        self.dbname = DATA_PATH + "/" + self.pref.get("current_database", "ham.db")
        self.database = DataBase(self.dbname, WORKING_PATH)
        self.station = self.database.fetch_station()
        if self.station is None:
            self.station = {}
            self.edit_station_settings()
            self.station = self.database.fetch_station()
            if self.station is None:
                self.station = {}
        self.contact = self.database.empty_contact
        self.current_op = self.station.get("Call", "")
        self.make_op_dir()
        self.read_cw_macros()
        self.clearinputs()

        self.band_indicators_cw = {
            "160": self.cw_band_160,
            "80": self.cw_band_80,
            "40": self.cw_band_40,
            "20": self.cw_band_20,
            "15": self.cw_band_15,
            "10": self.cw_band_10,
        }

        self.band_indicators_ssb = {
            "160": self.ssb_band_160,
            "80": self.ssb_band_80,
            "40": self.ssb_band_40,
            "20": self.ssb_band_20,
            "15": self.ssb_band_15,
            "10": self.ssb_band_10,
        }

        self.band_indicators_rtty = {
            "160": self.rtty_band_160,
            "80": self.rtty_band_80,
            "40": self.rtty_band_40,
            "20": self.rtty_band_20,
            "15": self.rtty_band_15,
            "10": self.rtty_band_10,
        }

        self.all_mode_indicators = {
            "CW": self.band_indicators_cw,
            "SSB": self.band_indicators_ssb,
            "RTTY": self.band_indicators_rtty,
        }

        if self.pref.get("contest"):
            self.load_contest()

        if VersionTest(__version__).test():
            self.show_message_box(
                "There is a newer version of not1mm available.\n"
                "You can udate to the current version by using:\npip install -U not1mm"
            )

    def click_160_cw(self, _event):
        """Handle clicked on label"""
        self.change_to_band_and_mode(160, "CW")

    def click_80_cw(self, _event):
        """doc"""
        self.change_to_band_and_mode(80, "CW")

    def click_40_cw(self, _event):
        """doc"""
        self.change_to_band_and_mode(40, "CW")

    def click_20_cw(self, _event):
        """doc"""
        self.change_to_band_and_mode(20, "CW")

    def click_15_cw(self, _event):
        """doc"""
        self.change_to_band_and_mode(15, "CW")

    def click_10_cw(self, _event):
        """doc"""
        self.change_to_band_and_mode(10, "CW")

    def click_160_ssb(self, _event):
        """doc"""
        self.change_to_band_and_mode(160, "SSB")

    def click_80_ssb(self, _event):
        """doc"""
        self.change_to_band_and_mode(80, "SSB")

    def click_40_ssb(self, _event):
        """doc"""
        self.change_to_band_and_mode(40, "SSB")

    def click_20_ssb(self, _event):
        """doc"""
        self.change_to_band_and_mode(20, "SSB")

    def click_15_ssb(self, _event):
        """doc"""
        self.change_to_band_and_mode(15, "SSB")

    def click_10_ssb(self, _event):
        """doc"""
        self.change_to_band_and_mode(10, "SSB")

    def click_160_rtty(self, _event):
        """doc"""
        self.change_to_band_and_mode(160, "RTTY")

    def click_80_rtty(self, _event):
        """doc"""
        self.change_to_band_and_mode(80, "RTTY")

    def click_40_rtty(self, _event):
        """doc"""
        self.change_to_band_and_mode(40, "RTTY")

    def click_20_rtty(self, _event):
        """doc"""
        self.change_to_band_and_mode(20, "RTTY")

    def click_15_rtty(self, _event):
        """doc"""
        self.change_to_band_and_mode(15, "RTTY")

    def click_10_rtty(self, _event):
        """doc"""
        self.change_to_band_and_mode(10, "RTTY")

    def change_to_band_and_mode(self, band, mode):
        """doc"""
        if mode in ["CW", "SSB", "RTTY"]:
            freq = fakefreq(str(band), mode)
            self.change_freq(freq)
            self.change_mode(mode)

    def quit_app(self):
        """doc"""
        cmd = {}
        cmd["cmd"] = "HALT"
        cmd["station"] = platform.node()
        self.multicast_interface.send_as_json(cmd)
        app.quit()

    @staticmethod
    def check_process(name: str) -> bool:
        """checks to see if program of name is in the active process list"""
        for proc in psutil.process_iter():
            if bool(re.match(name, proc.name().lower())):
                return True
        return False

    def show_message_box(self, message: str) -> None:
        """doc"""
        message_box = QtWidgets.QMessageBox()
        message_box.setIcon(QtWidgets.QMessageBox.Information)
        message_box.setText(message)
        message_box.setWindowTitle("Information")
        message_box.setStandardButtons(QtWidgets.QMessageBox.Ok)
        _ = message_box.exec_()

    def show_about_dialog(self):
        """Show about dialog"""
        self.about_dialog = About(WORKING_PATH)
        self.about_dialog.donors.setSource(
            QtCore.QUrl.fromLocalFile(WORKING_PATH + "/data/donors.html")
        )
        self.about_dialog.open()

    def show_help_dialog(self):
        """Show about dialog"""
        self.about_dialog = About(WORKING_PATH)
        self.about_dialog.setWindowTitle("Help")
        self.about_dialog.setGeometry(0, 0, 800, 600)
        self.about_dialog.donors.setSource(
            QtCore.QUrl.fromLocalFile(WORKING_PATH + "/data/not1mm.html")
        )
        self.about_dialog.open()

    def update_masterscp(self) -> None:
        """Update the MASTER.SCP file."""
        if self.mscp.update_masterscp():
            self.show_message_box("MASTER.SCP file updated.")
            return
        self.show_message_box("MASTER.SCP could not be updated.")

    def edit_configuration_settings(self):
        """Configuration Settings was clicked"""
        self.configuration_dialog = Settings(WORKING_PATH, CONFIG_PATH, self.pref)
        self.configuration_dialog.usehamdb_radioButton.hide()
        self.configuration_dialog.show()
        self.configuration_dialog.accepted.connect(self.edit_configuration_return)

    def edit_configuration_return(self):
        """Returns here when configuration dialog closed with okay."""
        self.configuration_dialog.save_changes()
        self.write_preference()
        logger.debug("%s", f"{self.pref}")
        self.readpreferences()

    def new_database(self):
        """Create new database."""
        filename = self.filepicker("new")
        if filename:
            if filename[-3:] != ".db":
                filename += ".db"
            self.pref["current_database"] = filename.split("/")[-1:][0]
            self.write_preference()
            self.dbname = DATA_PATH + "/" + self.pref.get("current_database", "ham.db")
            self.database = DataBase(self.dbname, WORKING_PATH)
            self.contact = self.database.empty_contact
            self.station = self.database.fetch_station()
            if self.station is None:
                self.station = {}
            self.current_op = self.station.get("Call", "")
            self.make_op_dir()
            cmd = {}
            cmd["cmd"] = "NEWDB"
            cmd["station"] = platform.node()
            self.multicast_interface.send_as_json(cmd)
            self.clearinputs()
            self.edit_station_settings()

    def open_database(self):
        """Open existing database."""
        filename = self.filepicker("open")
        if filename:
            self.pref["current_database"] = filename.split("/")[-1:][0]
            self.write_preference()
            self.dbname = DATA_PATH + "/" + self.pref.get("current_database", "ham.db")
            self.database = DataBase(self.dbname, WORKING_PATH)
            self.contact = self.database.empty_contact
            self.station = self.database.fetch_station()
            if self.station is None:
                self.station = {}
            if self.station.get("Call", "") == "":
                self.edit_station_settings()
            self.current_op = self.station.get("Call", "")
            self.make_op_dir()
            cmd = {}
            cmd["cmd"] = "NEWDB"
            cmd["station"] = platform.node()
            self.multicast_interface.send_as_json(cmd)
            self.clearinputs()

    def new_contest(self):
        """Create new contest in existing database."""

    def open_contest(self):
        """Switch to a different existing contest in existing database."""
        logger.debug("Open Contest selected")
        contests = self.database.fetch_all_contests()
        logger.debug("%s", f"{contests}")

        if contests:
            self.contest_dialog = SelectContest(WORKING_PATH)
            self.contest_dialog.contest_list.setRowCount(0)
            self.contest_dialog.contest_list.setColumnCount(4)
            self.contest_dialog.contest_list.verticalHeader().setVisible(False)
            self.contest_dialog.contest_list.setColumnWidth(1, 200)
            self.contest_dialog.contest_list.setColumnWidth(2, 200)
            self.contest_dialog.contest_list.setHorizontalHeaderItem(
                0, QtWidgets.QTableWidgetItem("Contest Nr")
            )
            self.contest_dialog.contest_list.setHorizontalHeaderItem(
                1, QtWidgets.QTableWidgetItem("Contest Name")
            )
            self.contest_dialog.contest_list.setHorizontalHeaderItem(
                2, QtWidgets.QTableWidgetItem("Contest Start")
            )
            self.contest_dialog.contest_list.setHorizontalHeaderItem(
                3, QtWidgets.QTableWidgetItem("Not UIsed")
            )
            self.contest_dialog.contest_list.setColumnHidden(0, True)
            self.contest_dialog.contest_list.setColumnHidden(3, True)
            self.contest_dialog.accepted.connect(self.open_contest_return)
            for contest in contests:
                number_of_rows = self.contest_dialog.contest_list.rowCount()
                self.contest_dialog.contest_list.insertRow(number_of_rows)
                contest_id = str(contest.get("ContestID", 1))
                contest_name = contest.get("ContestName", 1)
                start_date = contest.get("StartDate", 1)
                self.contest_dialog.contest_list.setItem(
                    number_of_rows, 0, QtWidgets.QTableWidgetItem(contest_id)
                )
                self.contest_dialog.contest_list.setItem(
                    number_of_rows, 1, QtWidgets.QTableWidgetItem(contest_name)
                )
                self.contest_dialog.contest_list.setItem(
                    number_of_rows, 2, QtWidgets.QTableWidgetItem(start_date)
                )
        self.contest_dialog.show()

    def open_contest_return(self):
        """Called by open_contest"""
        selected_row = self.contest_dialog.contest_list.currentRow()
        contest = self.contest_dialog.contest_list.item(selected_row, 0).text()
        self.pref["contest"] = contest
        self.write_preference()
        logger.debug("Selected contest: %s", f"{contest}")
        self.load_contest()
        self.worked_list = self.database.get_calls_and_bands()
        self.send_worked_list()

    def refill_dropdown(self, target, source):
        """Refill QCombobox widget with value."""
        index = target.findText(source)
        target.setCurrentIndex(index)

    def edit_contest(self):
        """Edit the current contest"""
        logger.debug("Edit contest Dialog")
        if self.contest is None:
            self.show_message_box("You have no contest defined.")
            return
        if self.contest_settings is None:
            return
        self.contest_dialog = NewContest(WORKING_PATH)
        self.contest_dialog.setWindowTitle("Edit Contest")
        self.contest_dialog.title.setText("")
        self.contest_dialog.accepted.connect(self.save_edited_contest)
        value = self.contest_settings.get("ContestName").upper().replace("_", " ")
        if value == "GENERAL LOGGING":
            value = "General Logging"
        self.refill_dropdown(self.contest_dialog.contest, value)
        value = self.contest_settings.get("OperatorCategory")
        self.refill_dropdown(self.contest_dialog.operator_class, value)
        value = self.contest_settings.get("BandCategory")
        self.refill_dropdown(self.contest_dialog.band, value)
        value = self.contest_settings.get("PowerCategory")
        self.refill_dropdown(self.contest_dialog.power, value)
        value = self.contest_settings.get("ModeCategory")
        self.refill_dropdown(self.contest_dialog.mode, value)
        value = self.contest_settings.get("OverlayCategory")
        self.refill_dropdown(self.contest_dialog.overlay, value)
        self.contest_dialog.operators.setText(self.contest_settings.get("Operators"))
        self.contest_dialog.soapbox.setPlainText(self.contest_settings.get("Soapbox"))
        self.contest_dialog.exchange.setText(self.contest_settings.get("SentExchange"))
        value = self.contest_settings.get("StationCategory")
        self.refill_dropdown(self.contest_dialog.station, value)
        value = self.contest_settings.get("AssistedCategory")
        self.refill_dropdown(self.contest_dialog.assisted, value)
        value = self.contest_settings.get("TransmitterCategory")
        self.refill_dropdown(self.contest_dialog.transmitter, value)
        value = self.contest_settings.get("StartDate")
        the_date, the_time = value.split()
        self.contest_dialog.dateTimeEdit.setDate(
            QtCore.QDate.fromString(the_date, "yyyy-MM-dd")
        )
        self.contest_dialog.dateTimeEdit.setCalendarPopup(True)
        self.contest_dialog.dateTimeEdit.setTime(
            QtCore.QTime.fromString(the_time, "hh:mm:ss")
        )
        self.contest_dialog.open()

    def save_edited_contest(self):
        """Save the edited contest"""
        contest = {}
        contest["ContestName"] = (
            self.contest_dialog.contest.currentText().lower().replace(" ", "_")
        )
        contest["StartDate"] = self.contest_dialog.dateTimeEdit.dateTime().toString(
            "yyyy-MM-dd hh:mm:ss"
        )
        contest["OperatorCategory"] = self.contest_dialog.operator_class.currentText()
        contest["BandCategory"] = self.contest_dialog.band.currentText()
        contest["PowerCategory"] = self.contest_dialog.power.currentText()
        contest["ModeCategory"] = self.contest_dialog.mode.currentText()
        contest["OverlayCategory"] = self.contest_dialog.overlay.currentText()
        contest["Operators"] = self.contest_dialog.operators.text()
        contest["Soapbox"] = self.contest_dialog.soapbox.toPlainText()
        contest["SentExchange"] = self.contest_dialog.exchange.text()
        contest["ContestNR"] = self.pref.get("contest", 1)
        contest["StationCategory"] = self.contest_dialog.station.currentText()
        contest["AssistedCategory"] = self.contest_dialog.assisted.currentText()
        contest["TransmitterCategory"] = self.contest_dialog.transmitter.currentText()

        logger.debug("%s", f"{contest}")
        self.database.update_contest(contest)
        self.write_preference()
        self.load_contest()

    def load_contest(self):
        """load a contest"""
        if self.pref.get("contest"):
            self.contest_settings = self.database.fetch_contest_by_id(
                self.pref.get("contest")
            )
            if self.contest_settings:
                self.database.current_contest = self.pref.get("contest")
                if self.contest_settings.get("ContestName"):
                    self.contest = doimp(self.contest_settings.get("ContestName"))
                    logger.debug("Loaded Contest Name = %s", self.contest.name)
                    self.set_window_title()
                    self.contest.init_contest(self)
                    self.hide_band_mode(self.contest_settings.get("ModeCategory", ""))
                    logger.debug("%s", f"{self.contest_settings}")
                    if self.contest_settings.get("ModeCategory", "") == "CW":
                        self.setmode("CW")
                        self.radio_state["mode"] = "CW"
                        if self.rig_control:
                            if self.rig_control.online:
                                self.rig_control.set_mode("CW")
                        band = getband(str(self.radio_state.get("vfoa", "0.0")))
                        self.set_band_indicator(band)
                        self.set_window_title()
                    if self.contest_settings.get("ModeCategory", "") == "SSB":
                        self.setmode("SSB")
                        if int(self.radio_state.get("vfoa", 0)) > 10000000:
                            self.radio_state["mode"] = "USB"
                        else:
                            self.radio_state["mode"] = "LSB"
                        band = getband(str(self.radio_state.get("vfoa", "0.0")))
                        self.set_band_indicator(band)
                        self.set_window_title()
                        if self.rig_control:
                            self.rig_control.set_mode(self.radio_state.get("mode"))

                if hasattr(self.contest, "mode"):
                    logger.debug("%s", f"  ****  {self.contest}")
                    if self.contest.mode in ["CW", "BOTH"]:
                        self.cw_speed.show()
                    else:
                        self.cw_speed.hide()

                cmd = {}
                cmd["cmd"] = "NEWDB"
                cmd["station"] = platform.node()
                self.multicast_interface.send_as_json(cmd)
                if hasattr(self.contest, "columns"):
                    cmd = {}
                    cmd["cmd"] = "SHOWCOLUMNS"
                    cmd["station"] = platform.node()
                    cmd["COLUMNS"] = self.contest.columns
                    self.multicast_interface.send_as_json(cmd)

    def check_for_new_cty(self):
        """
        Checks for a new cty.dat file.
        Loads it if available.
        """
        try:
            cty = notctyparser.BigCty(WORKING_PATH + "/data/cty.json")
            update_available = cty.check_update()
        except AttributeError as the_error:
            logger.debug("cty parser returned an error: %s", the_error)
            return
        except ValueError as the_error:
            print("cty parser returned an error: %s", the_error)
            logger.debug("cty parser returned an error: %s", the_error)
            return
        except locale.Error as the_error:
            print("cty parser returned an error: %s", the_error)
            logger.debug("cty parser returned an error: %s", the_error)
            return
        logger.debug("Newer cty file available %s", str(update_available))

        if update_available:
            try:
                updated = cty.update()
            except ResourceWarning as the_error:
                logger.debug("cty parser returned an error: %s", the_error)
                return
            if updated:
                cty.dump(WORKING_PATH + "/data/cty.json")
                self.show_message_box("cty file updated.")
                with open(
                    WORKING_PATH + "/data/cty.json", "rt", encoding="utf-8"
                ) as ctyfile:
                    globals()["CTYFILE"] = loads(ctyfile.read())
            else:
                self.show_message_box("An Error occured updating file.")
        else:
            self.show_message_box("CTY file is up to date.")

    def hide_band_mode(self, the_mode: str) -> None:
        """hide"""
        logger.debug("%s", f"{the_mode}")
        self.Band_Mode_Frame_CW.hide()
        self.Band_Mode_Frame_SSB.hide()
        self.Band_Mode_Frame_RTTY.hide()
        modes = {
            "CW": (self.Band_Mode_Frame_CW,),
            "SSB": (self.Band_Mode_Frame_SSB,),
            "RTTY": (self.Band_Mode_Frame_RTTY,),
            "PSK": (self.Band_Mode_Frame_RTTY,),
            "SSB+CW": (self.Band_Mode_Frame_CW, self.Band_Mode_Frame_SSB),
            "BOTH": (self.Band_Mode_Frame_CW, self.Band_Mode_Frame_SSB),
            "DIGITAL": (self.Band_Mode_Frame_RTTY,),
            "SSB+CW+DIGITAL": (
                self.Band_Mode_Frame_RTTY,
                self.Band_Mode_Frame_CW,
                self.Band_Mode_Frame_SSB,
            ),
            "FM": (self.Band_Mode_Frame_SSB,),
        }
        frames = modes.get(the_mode)
        if frames:
            for frame in frames:
                frame.show()

    def show_key_help(self) -> None:
        """Show help box for hotkeys"""
        self.show_message_box(
            "[Esc]\tClears the input fields of any text.\n"
            "[CTRL-Esc]\tStops cwdaemon from sending Morse.\n"
            "[PgUp]\tIncreases the cw sending speed.\n"
            "[PgDown]\tDecreases the cw sending speed.\n"
            "[Arrow-Up] Jump to the next spot above the current VFO cursor\n"
            "\tin the bandmap window (CAT Required).\n"
            "[Arrow-Down] Jump to the next spot below the current\n"
            "\tVFO cursor in the bandmap window (CAT Required).\n"
            "[TAB]\tMove cursor to the right one field.\n"
            "[Shift-Tab]\tMove cursor left One field.\n"
            "[SPACE]\tWhen in the callsign field, will move the input to the\n"
            "\tfirst field needed for the exchange.\n"
            "[Enter]\tSubmits the fields to the log.\n"
            "[F1-F12]\tSend (CW or Voice) macros.\n"
            "[CTRL-S]\tSpot Callsign to the cluster.\n"
            "[CTRL-G]\tTune to a spot matching partial text in the callsign\n"
            "\tentry field (CAT Required).\n"
        )

    def filepicker(self, action: str) -> str:
        """
        Get a filename
        action: "new" or "open"
        """
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        options |= QFileDialog.DontConfirmOverwrite
        if action == "new":
            file, _ = QFileDialog.getSaveFileName(
                self,
                "Choose a Database",
                DATA_PATH,
                "Database (*.db)",
                options=options,
            )
        if action == "open":
            file, _ = QFileDialog.getOpenFileName(
                self,
                "Choose a Database",
                DATA_PATH,
                "Database (*.db)",
                options=options,
            )
        return file

    def recalculate_mults(self):
        """Recalculate Multipliers"""
        self.contest.recalculate_mults(self)
        self.clearinputs()

    def launch_log_window(self):
        """launch the Log Window"""
        if not check_process("logwindow.py"):
            _ = subprocess.Popen([sys.executable, WORKING_PATH + "/logwindow.py"])

    def launch_bandmap_window(self):
        """launch the Log Window"""
        if not check_process("bandmap.py"):
            _ = subprocess.Popen([sys.executable, WORKING_PATH + "/bandmap.py"])

    def launch_check_window(self):
        """launch the Log Window"""
        if not check_process("checkwindow.py"):
            _ = subprocess.Popen([sys.executable, WORKING_PATH + "/checkwindow.py"])

    def launch_vfo(self):
        """launch the Log Window"""
        if not check_process("vfo.py"):
            _ = subprocess.Popen([sys.executable, WORKING_PATH + "/vfo.py"])

    def clear_band_indicators(self):
        """Clear the indicators"""
        for _, indicators in self.all_mode_indicators.items():
            for _, indicator in indicators.items():
                indicator.setFrameShape(QtWidgets.QFrame.NoFrame)
                indicator.setStyleSheet("font-family: JetBrains Mono;")

    def set_band_indicator(self, band: str) -> None:
        """Set the band indicator"""
        # logger.debug("%s", f"band:{band} mode: {self.current_mode}")
        if band and self.current_mode:
            self.clear_band_indicators()
            indicator = self.all_mode_indicators[self.current_mode].get(band, None)
            if indicator:
                indicator.setFrameShape(QtWidgets.QFrame.Box)
                indicator.setStyleSheet("font-family: JetBrains Mono; color: green;")

    def closeEvent(self, _event):
        """
        Write window size and position to config file
        """
        cmd = {}
        cmd["cmd"] = "HALT"
        cmd["station"] = platform.node()
        self.multicast_interface.send_as_json(cmd)
        self.pref["window_width"] = self.size().width()
        self.pref["window_height"] = self.size().height()
        self.pref["window_x"] = self.pos().x()
        self.pref["window_y"] = self.pos().y()
        self.write_preference()

    def cty_lookup(self, callsign: str):
        """Lookup callsign in cty.dat file.

        Parameters
        ----------
        callsign : str

        Returns
        -------
        return : list of dicts
        """
        callsign = callsign.upper()
        for count in reversed(range(len(callsign))):
            searchitem = callsign[: count + 1]
            result = {key: val for key, val in CTYFILE.items() if key == searchitem}
            if not result:
                continue
            if result.get(searchitem).get("exact_match"):
                if searchitem == callsign:
                    return result
                continue
            return result

    def cwspeed_spinbox_changed(self):
        """triggered when value of CW speed in the spinbox changes."""
        if self.cw is None:
            return
        if self.cw.servertype == 1:
            self.cw.speed = self.cw_speed.value()
            self.cw.sendcw(f"\x1b2{self.cw.speed}")
        if self.cw.servertype == 2:
            self.cw.set_winkeyer_speed(self.cw_speed.value())

    def keyPressEvent(self, event):  # pylint: disable=invalid-name
        """This overrides Qt key event."""
        modifier = event.modifiers()
        if event.key() == Qt.Key_S and modifier == Qt.ControlModifier:
            freq = self.radio_state.get("vfoa")
            dx = self.callsign.text()
            if freq and dx:
                cmd = {}
                cmd["cmd"] = "SPOTDX"
                cmd["station"] = platform.node()
                cmd["dx"] = dx
                cmd["freq"] = float(int(freq) / 1000)
                self.multicast_interface.send_as_json(cmd)
            return
        if event.key() == Qt.Key_G and modifier == Qt.ControlModifier:
            dx = self.callsign.text()
            if dx:
                cmd = {}
                cmd["cmd"] = "FINDDX"
                cmd["station"] = platform.node()
                cmd["dx"] = dx
                self.multicast_interface.send_as_json(cmd)
            return
        if (
            event.key() == Qt.Key.Key_Escape and modifier != Qt.ControlModifier
        ):  # pylint: disable=no-member
            self.clearinputs()
            return
        if event.key() == Qt.Key.Key_Escape and modifier == Qt.ControlModifier:
            if self.cw is not None:
                if self.cw.servertype == 1:
                    self.cw.sendcw("\x1b4")
                    return
        if event.key() == Qt.Key.Key_Up:
            cmd = {}
            cmd["cmd"] = "PREVSPOT"
            cmd["station"] = platform.node()
            self.multicast_interface.send_as_json(cmd)
            return
        if event.key() == Qt.Key.Key_Down:
            cmd = {}
            cmd["cmd"] = "NEXTSPOT"
            cmd["station"] = platform.node()
            self.multicast_interface.send_as_json(cmd)
            return
        if event.key() == Qt.Key.Key_PageUp and modifier != Qt.ControlModifier:
            if self.cw is not None:
                self.cw.speed += 1
                self.cw_speed.setValue(self.cw.speed)
                if self.cw.servertype == 1:
                    self.cw.sendcw(f"\x1b2{self.cw.speed}")
                if self.cw.servertype == 2:
                    self.cw.set_winkeyer_speed(self.cw_speed.value())
            return
        if event.key() == Qt.Key.Key_PageDown and modifier != Qt.ControlModifier:
            if self.cw is not None:
                self.cw.speed -= 1
                self.cw_speed.setValue(self.cw.speed)
                if self.cw.servertype == 1:
                    self.cw.sendcw(f"\x1b2{self.cw.speed}")
                if self.cw.servertype == 2:
                    self.cw.set_winkeyer_speed(self.cw_speed.value())
            return
        if event.key() == Qt.Key.Key_Tab or event.key() == Qt.Key.Key_Backtab:
            if self.sent.hasFocus():
                logger.debug("From sent")
                if modifier == Qt.ShiftModifier:
                    prev_tab = self.tab_prev.get(self.sent)
                    prev_tab.setFocus()
                    prev_tab.deselect()
                    prev_tab.end(False)
                else:
                    next_tab = self.tab_next.get(self.sent)
                    next_tab.setFocus()
                    next_tab.deselect()
                    next_tab.end(False)
                return
            if self.receive.hasFocus():
                logger.debug("From receive")
                if modifier == Qt.ShiftModifier:
                    prev_tab = self.tab_prev.get(self.receive)
                    prev_tab.setFocus()
                    prev_tab.deselect()
                    prev_tab.end(False)
                else:
                    next_tab = self.tab_next.get(self.receive)
                    next_tab.setFocus()
                    next_tab.deselect()
                    next_tab.end(False)
                return
            if self.other_1.hasFocus():
                logger.debug("From other_1")
                if modifier == Qt.ShiftModifier:
                    prev_tab = self.tab_prev.get(self.other_1)
                    prev_tab.setFocus()
                    prev_tab.deselect()
                    prev_tab.end(False)
                else:
                    next_tab = self.tab_next.get(self.other_1)
                    next_tab.setFocus()
                    next_tab.deselect()
                    next_tab.end(False)
                return
            if self.other_2.hasFocus():
                logger.debug("From other_2")
                if modifier == Qt.ShiftModifier:
                    prev_tab = self.tab_prev.get(self.other_2)
                    prev_tab.setFocus()
                    prev_tab.deselect()
                    prev_tab.end(False)
                else:
                    next_tab = self.tab_next.get(self.other_2)
                    next_tab.setFocus()
                    next_tab.deselect()
                    next_tab.end(False)
                return
            if self.callsign.hasFocus():
                logger.debug("From callsign")
                self.check_callsign(self.callsign.text())
                if self.check_dupe(self.callsign.text()):
                    self.dupe_indicator.show()
                else:
                    self.dupe_indicator.hide()
                if modifier == Qt.ShiftModifier:
                    prev_tab = self.tab_prev.get(self.callsign)
                    prev_tab.setFocus()
                    prev_tab.deselect()
                    prev_tab.end(False)
                else:
                    text = self.callsign.text()
                    text = text.upper()
                    _thethread = threading.Thread(
                        target=self.check_callsign2,
                        args=(text,),
                        daemon=True,
                    )
                    _thethread.start()
                    next_tab = self.tab_next.get(self.callsign)
                    next_tab.setFocus()
                    next_tab.deselect()
                    next_tab.end(False)
                return
        if event.key() == Qt.Key_F1:
            self.sendf1()
        if event.key() == Qt.Key_F2:
            self.sendf2()
        if event.key() == Qt.Key_F3:
            self.sendf3()
        if event.key() == Qt.Key_F4:
            self.sendf4()
        if event.key() == Qt.Key_F5:
            self.sendf5()
        if event.key() == Qt.Key_F6:
            self.sendf6()
        if event.key() == Qt.Key_F7:
            self.sendf7()
        if event.key() == Qt.Key_F8:
            self.sendf8()
        if event.key() == Qt.Key_F9:
            self.sendf9()
        if event.key() == Qt.Key_F10:
            self.sendf10()
        if event.key() == Qt.Key_F11:
            self.sendf11()
        if event.key() == Qt.Key_F12:
            self.sendf12()

    def set_window_title(self):
        """Set window title"""
        vfoa = self.radio_state.get("vfoa", "")
        if vfoa:
            try:
                vfoa = int(vfoa) / 1000
            except ValueError:
                vfoa = 0.0
        else:
            vfoa = 0.0
        contest_name = ""
        if self.contest:
            contest_name = self.contest.name
        line = (
            f"vfoa:{round(vfoa,2)} "
            f"mode:{self.radio_state.get('mode', '')} "
            f"OP:{self.current_op} {contest_name} "
            f"- Not1MM v{__version__}"
        )
        self.setWindowTitle(line)

    def send_worked_list(self) -> None:
        """Send message containing worked contacts and bands"""
        cmd = {}
        cmd["cmd"] = "WORKED"
        cmd["station"] = platform.node()
        cmd["worked"] = self.worked_list
        logger.debug("%s", f"{cmd}")
        self.multicast_interface.send_as_json(cmd)

    def clearinputs(self):
        """Clears the text input fields and sets focus to callsign field."""
        self.dupe_indicator.hide()
        self.contact = self.database.empty_contact
        self.heading_distance.setText("")
        self.dx_entity.setText("")
        if self.contest:
            mults = self.contest.show_mults(self)
            qsos = self.contest.show_qso(self)
            multstring = f"{qsos}/{mults}"
            self.mults.setText(multstring)
            score = self.contest.calc_score(self)
            self.score.setText(str(score))
            self.contest.reset_label(self)
        self.callsign.clear()
        if self.current_mode == "CW":
            self.sent.setText("599")
            self.receive.setText("599")
        else:
            self.sent.setText("59")
            self.receive.setText("59")
        self.other_1.clear()
        self.other_2.clear()
        self.callsign.setFocus()
        cmd = {}
        cmd["cmd"] = "CALLCHANGED"
        cmd["station"] = platform.node()
        cmd["call"] = ""
        self.multicast_interface.send_as_json(cmd)

    def save_contact(self):
        """Save to db"""
        logger.debug("saving contact")
        if self.contest is None:
            self.show_message_box("You have no contest defined.")
            return
        if len(self.callsign.text()) < 3:
            return
        if not any(char.isdigit() for char in self.callsign.text()):
            return
        if not any(char.isalpha() for char in self.callsign.text()):
            return

        self.contact["TS"] = datetime.utcnow().isoformat(" ")[:19]
        self.contact["Call"] = self.callsign.text()
        self.contact["Freq"] = round(float(self.radio_state.get("vfoa", 0.0)) / 1000, 2)
        self.contact["QSXFreq"] = round(
            float(self.radio_state.get("vfoa", 0.0)) / 1000, 2
        )
        self.contact["Mode"] = self.radio_state.get("mode", "")
        self.contact["ContestName"] = self.contest.cabrillo_name
        self.contact["ContestNR"] = self.pref.get("contest", "0")
        self.contact["StationPrefix"] = self.station.get("Call", "")
        self.contact["WPXPrefix"] = calculate_wpx_prefix(self.callsign.text())
        self.contact["IsRunQSO"] = self.radioButton_run.isChecked()
        self.contact["Operator"] = self.current_op
        self.contact["NetBiosName"] = socket.gethostname()
        self.contact["IsOriginal"] = 1
        self.contact["ID"] = uuid.uuid4().hex
        self.contest.set_contact_vars(self)
        self.contact["Points"] = self.contest.points(self)
        debug_output = f"{self.contact}"
        logger.debug(debug_output)

        if self.n1mm:
            logger.debug("packets %s", f"{self.n1mm.send_contact_packets}")
            if self.n1mm.send_contact_packets:
                self.n1mm.contact_info["timestamp"] = self.contact["TS"]
                self.n1mm.contact_info["oldcall"] = self.n1mm.contact_info[
                    "call"
                ] = self.contact["Call"]
                self.n1mm.contact_info["txfreq"] = self.n1mm.contact_info[
                    "rxfreq"
                ] = self.n1mm.radio_info["Freq"]
                self.n1mm.contact_info["mode"] = self.contact["Mode"]
                self.n1mm.contact_info["contestname"] = self.contact[
                    "ContestName"
                ].replace("-", "")
                self.n1mm.contact_info["contestnr"] = self.contact["ContestNR"]
                self.n1mm.contact_info["stationprefix"] = self.contact["StationPrefix"]
                self.n1mm.contact_info["wpxprefix"] = self.contact["WPXPrefix"]
                self.n1mm.contact_info["IsRunQSO"] = self.contact["IsRunQSO"]
                self.n1mm.contact_info["operator"] = self.contact["Operator"]
                self.n1mm.contact_info["mycall"] = self.contact["Operator"]
                self.n1mm.contact_info["StationName"] = self.n1mm.contact_info[
                    "NetBiosName"
                ] = self.contact["NetBiosName"]
                self.n1mm.contact_info["IsOriginal"] = self.contact["IsOriginal"]
                self.n1mm.contact_info["ID"] = self.contact["ID"]
                self.n1mm.contact_info["points"] = self.contact["Points"]
                self.n1mm.contact_info["snt"] = self.contact["SNT"]
                self.n1mm.contact_info["rcv"] = self.contact["RCV"]
                self.n1mm.contact_info["sntnr"] = self.contact["SentNr"]
                self.n1mm.contact_info["rcvnr"] = self.contact["NR"]
                self.n1mm.contact_info["ismultiplier1"] = self.contact.get(
                    "IsMultiplier1", 0
                )
                self.n1mm.contact_info["ismultiplier2"] = self.contact.get(
                    "IsMultiplier2", 0
                )
                self.n1mm.contact_info["ismultiplier3"] = self.contact.get(
                    "IsMultiplier3", "0"
                )
                self.n1mm.contact_info["section"] = self.contact["Sect"]
                self.n1mm.contact_info["prec"] = self.contact["Prec"]
                self.n1mm.contact_info["ck"] = self.contact["CK"]
                self.n1mm.contact_info["zn"] = self.contact["ZN"]
                self.n1mm.contact_info["power"] = self.contact["Power"]
                self.n1mm.contact_info["band"] = self.contact["Band"]
                # self.n1mm.contact_info['']
                # self.n1mm.contact_info['']
                # self.n1mm.contact_info['']
                # self.n1mm.contact_info['']
                # self.n1mm.contact_info['']
                # self.n1mm.contact_info['']
                logger.debug("%s", f"{self.n1mm.contact_info}")
                self.n1mm.send_contact_info()

        self.database.log_contact(self.contact)
        self.worked_list = self.database.get_calls_and_bands()
        self.send_worked_list()
        self.clearinputs()

        cmd = {}
        cmd["cmd"] = "UPDATELOG"
        cmd["station"] = platform.node()
        self.multicast_interface.send_as_json(cmd)

        # self.contact["ContestName"] = self.contest.name
        # self.contact["SNT"] = self.sent.text()
        # self.contact["RCV"] = self.receive.text()
        # self.contact["CountryPrefix"]
        # self.contact["StationPrefix"] = self.pref.get("callsign", "")
        # self.contact["QTH"]
        # self.contact["Name"] = self.other_1.text()
        # self.contact["Comment"] = self.other_2.text()
        # self.contact["NR"]
        # self.contact["Sect"]
        # self.contact["Prec"]
        # self.contact["CK"]
        # self.contact["ZN"]
        # self.contact["SentNr"]
        # self.contact["Points"]
        # self.contact["IsMultiplier1"]
        # self.contact["IsMultiplier2"]
        # self.contact["Power"]
        # self.contact["Band"]
        # self.contact["WPXPrefix"] = calculate_wpx_prefix(self.callsign.text())
        # self.contact["Exchange1"]
        # self.contact["RadioNR"]
        # self.contact["isMultiplier3"]
        # self.contact["MiscText"]
        # self.contact["ContactType"]
        # self.contact["Run1Run2"]
        # self.contact["GridSquare"]
        # self.contact["Continent"]
        # self.contact["RoverLocation"]
        # self.contact["RadioInterfaced"]
        # self.contact["NetworkedCompNr"]
        # self.contact["CLAIMEDQSO"]

    def new_contest_dialog(self):
        """Show new contest dialog"""
        logger.debug("New contest Dialog")
        self.contest_dialog = NewContest(WORKING_PATH)
        self.contest_dialog.accepted.connect(self.save_contest)
        self.contest_dialog.dateTimeEdit.setDate(QtCore.QDate.currentDate())
        self.contest_dialog.dateTimeEdit.setCalendarPopup(True)
        self.contest_dialog.dateTimeEdit.setTime(QtCore.QTime(0, 0))
        self.contest_dialog.power.setCurrentText("LOW")
        self.contest_dialog.station.setCurrentText("FIXED")
        self.contest_dialog.open()

    def save_contest(self):
        """Save Contest"""
        next_number = self.database.get_next_contest_nr()
        contest = {}
        contest["ContestName"] = (
            self.contest_dialog.contest.currentText().lower().replace(" ", "_")
        )
        contest["StartDate"] = self.contest_dialog.dateTimeEdit.dateTime().toString(
            "yyyy-MM-dd hh:mm:ss"
        )
        contest["OperatorCategory"] = self.contest_dialog.operator_class.currentText()
        contest["BandCategory"] = self.contest_dialog.band.currentText()
        contest["PowerCategory"] = self.contest_dialog.power.currentText()
        contest["ModeCategory"] = self.contest_dialog.mode.currentText()
        contest["OverlayCategory"] = self.contest_dialog.overlay.currentText()
        # contest['ClaimedScore'] = self.contest_dialog.
        contest["Operators"] = self.contest_dialog.operators.text()
        contest["Soapbox"] = self.contest_dialog.soapbox.toPlainText()
        contest["SentExchange"] = self.contest_dialog.exchange.text()
        contest["ContestNR"] = next_number.get("count", 1)
        self.pref["contest"] = next_number.get("count", 1)
        # contest['SubType'] = self.contest_dialog.
        contest["StationCategory"] = self.contest_dialog.station.currentText()
        contest["AssistedCategory"] = self.contest_dialog.assisted.currentText()
        contest["TransmitterCategory"] = self.contest_dialog.transmitter.currentText()
        # contest['TimeCategory'] = self.contest_dialog.
        logger.debug("%s", f"{contest}")
        self.database.add_contest(contest)
        self.write_preference()
        self.load_contest()

    def edit_station_settings(self):
        """Show settings dialog"""
        logger.debug("Station Settings selected")
        self.settings_dialog = EditStation(WORKING_PATH)
        self.settings_dialog.accepted.connect(self.save_settings)
        self.settings_dialog.Call.setText(self.station.get("Call", ""))
        self.settings_dialog.Name.setText(self.station.get("Name", ""))
        self.settings_dialog.Address1.setText(self.station.get("Street1", ""))
        self.settings_dialog.Address2.setText(self.station.get("Street2", ""))
        self.settings_dialog.City.setText(self.station.get("City", ""))
        self.settings_dialog.State.setText(self.station.get("State", ""))
        self.settings_dialog.Zip.setText(self.station.get("Zip", ""))
        self.settings_dialog.Country.setText(self.station.get("Country", ""))
        self.settings_dialog.GridSquare.setText(self.station.get("GridSquare", ""))
        self.settings_dialog.CQZone.setText(str(self.station.get("CQZone", "")))
        self.settings_dialog.ITUZone.setText(str(self.station.get("IARUZone", "")))
        self.settings_dialog.License.setText(self.station.get("LicenseClass", ""))
        self.settings_dialog.Latitude.setText(str(self.station.get("Latitude", "")))
        self.settings_dialog.Longitude.setText(str(self.station.get("Longitude", "")))
        self.settings_dialog.StationTXRX.setText(self.station.get("stationtxrx", ""))
        self.settings_dialog.Power.setText(self.station.get("SPowe", ""))
        self.settings_dialog.Antenna.setText(self.station.get("SAnte", ""))
        self.settings_dialog.AntHeight.setText(self.station.get("SAntH1", ""))
        self.settings_dialog.ASL.setText(self.station.get("SAntH2", ""))
        self.settings_dialog.ARRLSection.setText(self.station.get("ARRLSection", ""))
        self.settings_dialog.RoverQTH.setText(self.station.get("RoverQTH", ""))
        self.settings_dialog.Club.setText(self.station.get("Club", ""))
        self.settings_dialog.Email.setText(self.station.get("Email", ""))
        self.settings_dialog.open()

    def save_settings(self):
        """Save settings"""
        cs = self.settings_dialog.Call.text()
        self.station = {}
        self.station["Call"] = cs.upper()
        self.station["Name"] = self.settings_dialog.Name.text().title()
        self.station["Street1"] = self.settings_dialog.Address1.text().title()
        self.station["Street2"] = self.settings_dialog.Address2.text().title()
        self.station["City"] = self.settings_dialog.City.text().title()
        self.station["State"] = self.settings_dialog.State.text().upper()
        self.station["Zip"] = self.settings_dialog.Zip.text()
        self.station["Country"] = self.settings_dialog.Country.text().title()
        self.station["GridSquare"] = self.settings_dialog.GridSquare.text()
        self.station["CQZone"] = self.settings_dialog.CQZone.text()
        self.station["IARUZone"] = self.settings_dialog.ITUZone.text()
        self.station["LicenseClass"] = self.settings_dialog.License.text().title()
        self.station["Latitude"] = self.settings_dialog.Latitude.text()
        self.station["Longitude"] = self.settings_dialog.Longitude.text()
        self.station["STXeq"] = self.settings_dialog.StationTXRX.text()
        self.station["SPowe"] = self.settings_dialog.Power.text()
        self.station["SAnte"] = self.settings_dialog.Antenna.text()
        self.station["SAntH1"] = self.settings_dialog.AntHeight.text()
        self.station["SAntH2"] = self.settings_dialog.ASL.text()
        self.station["ARRLSection"] = self.settings_dialog.ARRLSection.text().upper()
        self.station["RoverQTH"] = self.settings_dialog.RoverQTH.text()
        self.station["Club"] = self.settings_dialog.Club.text().title()
        self.station["Email"] = self.settings_dialog.Email.text()
        self.database.add_station(self.station)
        self.settings_dialog.close()
        if self.current_op == "":
            self.current_op = self.station.get("Call", "")
            self.make_op_dir()
        contest_count = self.database.fetch_all_contests()
        if len(contest_count) == 0:
            self.new_contest_dialog()

    def edit_macro(self, function_key):
        """Show edit macro dialog"""
        self.edit_macro_dialog = EditMacro(function_key, WORKING_PATH)
        self.edit_macro_dialog.accepted.connect(self.edited_macro)
        self.edit_macro_dialog.open()

    def edited_macro(self):
        """Save edited macro"""
        self.edit_macro_dialog.function_key.setText(
            self.edit_macro_dialog.macro_label.text()
        )
        self.edit_macro_dialog.function_key.setToolTip(
            self.edit_macro_dialog.the_macro.text()
        )
        self.edit_macro_dialog.close()

    def edit_F1(self):
        """stub"""
        logger.debug("F1 Right Clicked.")
        self.edit_macro(self.F1)

    def edit_F2(self):
        """stub"""
        logger.debug("F2 Right Clicked.")
        self.edit_macro(self.F2)

    def edit_F3(self):
        """stub"""
        logger.debug("F3 Right Clicked.")
        self.edit_macro(self.F3)

    def edit_F4(self):
        """stub"""
        logger.debug("F4 Right Clicked.")
        self.edit_macro(self.F4)

    def edit_F5(self):
        """stub"""
        logger.debug("F5 Right Clicked.")
        self.edit_macro(self.F5)

    def edit_F6(self):
        """stub"""
        logger.debug("F6 Right Clicked.")
        self.edit_macro(self.F6)

    def edit_F7(self):
        """stub"""
        logger.debug("F7 Right Clicked.")
        self.edit_macro(self.F7)

    def edit_F8(self):
        """stub"""
        logger.debug("F8 Right Clicked.")
        self.edit_macro(self.F8)

    def edit_F9(self):
        """stub"""
        logger.debug("F9 Right Clicked.")
        self.edit_macro(self.F9)

    def edit_F10(self):
        """stub"""
        logger.debug("F10 Right Clicked.")
        self.edit_macro(self.F10)

    def edit_F11(self):
        """stub"""
        logger.debug("F11 Right Clicked.")
        self.edit_macro(self.F11)

    def edit_F12(self):
        """stub"""
        logger.debug("F12 Right Clicked.")
        self.edit_macro(self.F12)

    def process_macro(self, macro: str) -> str:
        """Process CW macro substitutions"""
        result = self.database.get_serial()
        next_serial = str(result.get("serial_nr", "1"))
        if next_serial == "None":
            next_serial = "1"
        macro = macro.upper()
        macro = macro.replace("#", next_serial)
        macro = macro.replace("{MYCALL}", self.station.get("Call", ""))
        macro = macro.replace("{HISCALL}", self.callsign.text())
        if self.radio_state.get("mode") == "CW":
            macro = macro.replace("{SNT}", self.sent.text().replace("9", "n"))
        else:
            macro = macro.replace("{SNT}", self.sent.text())
        macro = macro.replace("{SENTNR}", self.other_1.text())
        macro = macro.replace(
            "{EXCH}", self.contest_settings.get("SentExchange", "xxx")
        )
        return macro

    def voice_string(self, the_string: str) -> None:
        """voices string using nato phonetics"""
        logger.debug("Voicing: %s", the_string)
        op_path = Path(DATA_PATH) / self.current_op
        if "[" in the_string:
            sub_string = the_string.strip("[]").lower()
            filename = f"{str(op_path)}/{sub_string}.wav"
            if Path(filename).is_file():
                logger.debug("Voicing: %s", filename)
                data, _fs = sf.read(filename, dtype="float32")
                self.ptt_on()
                try:
                    sd.default.device = self.pref.get("sounddevice", "default")
                    sd.default.samplerate = 44100.0
                    sd.play(data, blocking=False)
                    # _status = sd.wait()
                    # https://snyk.io/advisor/python/sounddevice/functions/sounddevice.PortAudioError
                except sd.PortAudioError as err:
                    logger.warning("%s", f"{err}")

                self.ptt_off()
            return
        self.ptt_on()
        for letter in the_string.lower():
            if letter in "abcdefghijklmnopqrstuvwxyz 1234567890":
                if letter == " ":
                    letter = "space"
                filename = f"{str(op_path)}/{letter}.wav"
                if Path(filename).is_file():
                    logger.debug("Voicing: %s", filename)
                    data, _fs = sf.read(filename, dtype="float32")
                    try:
                        sd.default.device = self.pref.get("sounddevice", "default")
                        sd.default.samplerate = 44100.0
                        sd.play(data, blocking=False)
                        logger.debug("%s", f"{sd.wait()}")
                    except sd.PortAudioError as err:
                        logger.warning("%s", f"{err}")
        self.ptt_off()

    def ptt_on(self):
        """turn on ptt"""
        if self.rig_control:
            self.leftdot.setPixmap(self.greendot)
            app.processEvents()
            self.rig_control.ptt_on()

    def ptt_off(self):
        """turn off ptt"""
        if self.rig_control:
            self.leftdot.setPixmap(self.reddot)
            app.processEvents()
            self.rig_control.ptt_off()

    def sendf1(self):
        """stub"""
        logger.debug("F1 Clicked")
        if self.n1mm:
            self.n1mm.radio_info["FunctionKeyCaption"] = self.F1.text()
        if self.radio_state.get("mode") in ["LSB", "USB", "SSB"]:
            self.voice_string(self.process_macro(self.F1.toolTip()))
            return
        if self.cw:
            self.cw.sendcw(self.process_macro(self.F1.toolTip()))

    def sendf2(self):
        """stub"""
        logger.debug("F2 Clicked")
        if self.n1mm:
            self.n1mm.radio_info["FunctionKeyCaption"] = self.F2.text()
        if self.radio_state.get("mode") in ["LSB", "USB", "SSB"]:
            self.voice_string(self.process_macro(self.F2.toolTip()))
            return
        if self.cw:
            self.cw.sendcw(self.process_macro(self.F2.toolTip()))

    def sendf3(self):
        """stub"""
        logger.debug("F3 Clicked")
        if self.n1mm:
            self.n1mm.radio_info["FunctionKeyCaption"] = self.F3.text()
        if self.radio_state.get("mode") in ["LSB", "USB", "SSB"]:
            self.voice_string(self.process_macro(self.F3.toolTip()))
            return
        if self.cw:
            self.cw.sendcw(self.process_macro(self.F3.toolTip()))

    def sendf4(self):
        """stub"""
        logger.debug("F4 Clicked")
        if self.n1mm:
            self.n1mm.radio_info["FunctionKeyCaption"] = self.F4.text()
        if self.radio_state.get("mode") in ["LSB", "USB", "SSB"]:
            self.voice_string(self.process_macro(self.F4.toolTip()))
            return
        if self.cw:
            self.cw.sendcw(self.process_macro(self.F4.toolTip()))

    def sendf5(self):
        """stub"""
        logger.debug("F5 Clicked")
        if self.n1mm:
            self.n1mm.radio_info["FunctionKeyCaption"] = self.F5.text()
        if self.radio_state.get("mode") in ["LSB", "USB", "SSB"]:
            self.voice_string(self.process_macro(self.F5.toolTip()))
            return
        if self.cw:
            self.cw.sendcw(self.process_macro(self.F5.toolTip()))

    def sendf6(self):
        """stub"""
        logger.debug("F6 Clicked")
        if self.n1mm:
            self.n1mm.radio_info["FunctionKeyCaption"] = self.F6.text()
        if self.radio_state.get("mode") in ["LSB", "USB", "SSB"]:
            self.voice_string(self.process_macro(self.F6.toolTip()))
            return
        if self.cw:
            self.cw.sendcw(self.process_macro(self.F6.toolTip()))

    def sendf7(self):
        """stub"""
        logger.debug("F7 Clicked")
        if self.n1mm:
            self.n1mm.radio_info["FunctionKeyCaption"] = self.F7.text()
        if self.radio_state.get("mode") in ["LSB", "USB", "SSB"]:
            self.voice_string(self.process_macro(self.F7.toolTip()))
            return
        if self.cw:
            self.cw.sendcw(self.process_macro(self.F7.toolTip()))

    def sendf8(self):
        """stub"""
        logger.debug("F8 Clicked")
        if self.n1mm:
            self.n1mm.radio_info["FunctionKeyCaption"] = self.F8.text()
        if self.radio_state.get("mode") in ["LSB", "USB", "SSB"]:
            self.voice_string(self.process_macro(self.F8.toolTip()))
            return
        if self.cw:
            self.cw.sendcw(self.process_macro(self.F8.toolTip()))

    def sendf9(self):
        """stub"""
        logger.debug("F9 Clicked")
        if self.n1mm:
            self.n1mm.radio_info["FunctionKeyCaption"] = self.F9.text()
        if self.radio_state.get("mode") in ["LSB", "USB", "SSB"]:
            self.voice_string(self.process_macro(self.F9.toolTip()))
            return
        if self.cw:
            self.cw.sendcw(self.process_macro(self.F9.toolTip()))

    def sendf10(self):
        """stub"""
        logger.debug("F10 Clicked")
        if self.n1mm:
            self.n1mm.radio_info["FunctionKeyCaption"] = self.F10.text()
        if self.radio_state.get("mode") in ["LSB", "USB", "SSB"]:
            self.voice_string(self.process_macro(self.F10.toolTip()))
            return
        if self.cw:
            self.cw.sendcw(self.process_macro(self.F10.toolTip()))

    def sendf11(self):
        """stub"""
        logger.debug("F11 Clicked")
        if self.n1mm:
            self.n1mm.radio_info["FunctionKeyCaption"] = self.F11.text()
        if self.radio_state.get("mode") in ["LSB", "USB", "SSB"]:
            self.voice_string(self.process_macro(self.F11.toolTip()))
            return
        if self.cw:
            self.cw.sendcw(self.process_macro(self.F11.toolTip()))

    def sendf12(self):
        """stub"""
        logger.debug("F12 Clicked")
        if self.n1mm:
            self.n1mm.radio_info["FunctionKeyCaption"] = self.F12.text()
        if self.radio_state.get("mode") in ["LSB", "USB", "SSB"]:
            self.voice_string(self.process_macro(self.F12.toolTip()))
            return
        if self.cw:
            self.cw.sendcw(self.process_macro(self.F12.toolTip()))

    def run_sp_buttons_clicked(self):
        """Handle run/s&p mode"""
        self.pref["run_state"] = self.radioButton_run.isChecked()
        self.write_preference()
        self.read_cw_macros()

    def write_preference(self):
        """
        Write preferences to json file.
        """
        try:
            with open(
                CONFIG_PATH + "/not1mm.json", "wt", encoding="utf-8"
            ) as file_descriptor:
                file_descriptor.write(dumps(self.pref, indent=4))
                logger.info("writing: %s", self.pref)
        except IOError as exception:
            logger.critical("writepreferences: %s", exception)

    def readpreferences(self):
        """
        Restore preferences if they exist, otherwise create some sane defaults.
        """
        try:
            if os.path.exists(CONFIG_PATH + "/not1mm.json"):
                with open(
                    CONFIG_PATH + "/not1mm.json", "rt", encoding="utf-8"
                ) as file_descriptor:
                    self.pref = loads(file_descriptor.read())
                    logger.info("%s", self.pref)
            else:
                logger.info("No preference file. Writing preference.")
                with open(
                    CONFIG_PATH + "/not1mm.json", "wt", encoding="utf-8"
                ) as file_descriptor:
                    self.pref = self.pref_ref.copy()
                    file_descriptor.write(dumps(self.pref, indent=4))
                    logger.info("%s", self.pref)
        except IOError as exception:
            logger.critical("Error: %s", exception)

        self.look_up = None
        if self.pref.get("useqrz"):
            self.look_up = QRZlookup(
                self.pref.get("lookupusername"),
                self.pref.get("lookuppassword"),
            )
        # if self.pref.get("usehamdb"):
        #     self.look_up = HamDBlookup()
        if self.pref.get("usehamqth"):
            self.look_up = HamQTH(
                self.pref.get("lookupusername"),
                self.pref.get("lookuppassword"),
            )

        if self.pref.get("run_state"):
            self.radioButton_run.setChecked(True)
        else:
            self.radioButton_sp.setChecked(True)

        if self.pref.get("command_buttons"):
            self.actionCommand_Buttons.setChecked(True)
        else:
            self.actionCommand_Buttons.setChecked(False)

        if self.pref.get("cw_macros"):
            self.actionCW_Macros.setChecked(True)
        else:
            self.actionCW_Macros.setChecked(False)

        if self.pref.get("bands_modes"):
            self.actionMode_and_Bands.setChecked(True)
        else:
            self.actionMode_and_Bands.setChecked(False)

        multicast_group = self.pref.get("multicast_group", "239.1.1.1")
        multicast_port = self.pref.get("multicast_port", 2239)
        interface_ip = self.pref.get("interface_ip", "0.0.0.0")
        self.multicast_interface = Multicast(
            multicast_group, multicast_port, interface_ip
        )
        self.multicast_interface.ready_read_connect(self.watch_udp)

        self.rig_control = None

        if self.pref.get("useflrig", False):
            logger.debug(
                "Using flrig: %s",
                f"{self.pref.get('CAT_ip')} {self.pref.get('CAT_port')}",
            )
            self.rig_control = CAT(
                "flrig",
                self.pref.get("CAT_ip", "127.0.0.1"),
                int(self.pref.get("CAT_port", 12345)),
            )
        if self.pref.get("userigctld", False):
            logger.debug(
                "Using rigctld: %s",
                f"{self.pref.get('CAT_ip')} {self.pref.get('CAT_port')}",
            )
            self.rig_control = CAT(
                "rigctld",
                self.pref.get("CAT_ip", "127.0.0.1"),
                int(self.pref.get("CAT_port", 4532)),
            )

        if self.pref.get("cwtype", 0) == 0:
            self.cw = None
        else:
            self.cw = CW(
                int(self.pref.get("cwtype")),
                self.pref.get("cwip"),
                int(self.pref.get("cwport", 6789)),
            )
            self.cw.speed = 20
            if self.cw.servertype == 2:
                self.cw.set_winkeyer_speed(20)

        self.n1mm = None
        if self.pref.get("send_n1mm_packets", False):
            try:
                self.n1mm = N1MM(
                    self.pref.get("n1mm_radioport", "127.0.0.1:12060"),
                    self.pref.get("n1mm_contactport", "127.0.0.1:12061"),
                    self.pref.get("n1mm_lookupport", "127.0.0.1:12060"),
                    self.pref.get("n1mm_scoreport", "127.0.0.1:12060"),
                )
            except ValueError:
                logger.warning("%s", f"{ValueError}")
            self.n1mm.send_radio_packets = self.pref.get("send_n1mm_radio", False)
            self.n1mm.send_contact_packets = self.pref.get("send_n1mm_contact", False)
            self.n1mm.send_lookup_packets = self.pref.get("send_n1mm_lookup", False)
            self.n1mm.send_score_packets = self.pref.get("send_n1mm_score", False)
            self.n1mm.radio_info["StationName"] = self.pref.get("n1mm_station_name", "")

        self.show_command_buttons()
        self.show_CW_macros()
        # self.show_band_mode()

    def watch_udp(self):
        """Process UDP datagrams."""
        while self.multicast_interface.server_udp.hasPendingDatagrams():
            bundle = self.multicast_interface.server_udp.readDatagram(
                self.multicast_interface.server_udp.pendingDatagramSize()
            )
            datagram, _, _ = bundle
            # logger.debug(datagram.decode())
            if datagram:
                try:
                    # debug_info = f"{datagram.decode()}"
                    # logger.debug(debug_info)
                    json_data = loads(datagram.decode())
                except UnicodeDecodeError as err:
                    the_error = f"Not Unicode: {err}\n{datagram}"
                    logger.warning(the_error)
                    continue
                except JSONDecodeError as err:
                    the_error = f"Not JSON: {err}\n{datagram}"
                    logger.warning(the_error)
                    continue
                if (
                    json_data.get("cmd", "") == "GETCOLUMNS"
                    and json_data.get("station", "") == platform.node()
                ):
                    if hasattr(self.contest, "columns"):
                        cmd = {}
                        cmd["cmd"] = "SHOWCOLUMNS"
                        cmd["station"] = platform.node()
                        cmd["COLUMNS"] = self.contest.columns
                        self.multicast_interface.send_as_json(cmd)
                if (
                    json_data.get("cmd", "") == "TUNE"
                    and json_data.get("station", "") == platform.node()
                ):
                    # b'{"cmd": "TUNE", "freq": 7.0235, "spot": "MM0DGI"}'
                    vfo = json_data.get("freq")
                    vfo = float(vfo) * 1000000
                    self.radio_state["vfoa"] = int(vfo)
                    if self.rig_control:
                        self.rig_control.set_vfo(int(vfo))
                    spot = json_data.get("spot", "")
                    self.callsign.setText(spot)
                    self.callsign_changed()
                    self.callsign.setFocus()
                    self.callsign.activateWindow()
                    window.raise_()

                if (
                    json_data.get("cmd", "") == "GETWORKEDLIST"
                    and json_data.get("station", "") == platform.node()
                ):
                    result = self.database.get_calls_and_bands()
                    cmd = {}
                    cmd["cmd"] = "WORKED"
                    cmd["station"] = platform.node()
                    cmd["worked"] = result
                    self.multicast_interface.send_as_json(cmd)

    def cw_macros_state_changed(self):
        """Menu item to show/hide macro buttons"""
        self.pref["cw_macros"] = self.actionCW_Macros.isChecked()
        self.write_preference()
        self.show_CW_macros()

    def show_CW_macros(self):
        """macro button state change"""
        if self.pref.get("cw_macros"):
            self.Button_Row1.show()
            self.Button_Row2.show()
        else:
            self.Button_Row1.hide()
            self.Button_Row2.hide()

    def command_buttons_state_change(self):
        """Menu item to show/hide command buttons"""
        self.pref["command_buttons"] = self.actionCommand_Buttons.isChecked()
        self.write_preference()
        self.show_command_buttons()

    def show_command_buttons(self):
        """command button state change"""
        if self.pref.get("command_buttons"):
            self.Command_Buttons.show()
        else:
            self.Command_Buttons.hide()

    def is_floatable(self, item: str) -> bool:
        """check to see if string can be a float"""
        if item.isnumeric():
            return True
        try:
            _test = float(item)
        except ValueError:
            return False
        return True

    def other_1_changed(self):
        """Called when... you know."""
        if self.contest:
            if hasattr(self.contest, "advance_on_space"):
                if self.contest.advance_on_space[3]:
                    text = self.other_1.text()
                    text = text.upper()
                    # position = self.other_1.cursorPosition()
                    stripped_text = text.strip().replace(" ", "")
                    self.other_1.setText(stripped_text)
                    # self.other_1.setCursorPosition(position)
                    if " " in text:
                        next_tab = self.tab_next.get(self.other_1)
                        next_tab.setFocus()
                        next_tab.deselect()
                        next_tab.end(False)

    def other_2_changed(self):
        """Called when we need to parse SS exchange."""
        if self.contest:
            if "ARRL Sweepstakes" in self.contest.name:
                self.contest.parse_exchange(self)
                return
            if hasattr(self.contest, "advance_on_space"):
                if self.contest.advance_on_space[3]:
                    text = self.other_2.text()
                    text = text.upper()
                    # position = self.other_2.cursorPosition()
                    stripped_text = text.strip().replace(" ", "")
                    self.other_2.setText(stripped_text)
                    # self.other_2.setCursorPosition(position)
                    if " " in text:
                        next_tab = self.tab_next.get(self.other_2)
                        next_tab.setFocus()
                        next_tab.deselect()
                        next_tab.end(False)

    def callsign_changed(self):
        """Called when text in the callsign field has changed"""
        text = self.callsign.text()
        text = text.upper()
        position = self.callsign.cursorPosition()
        stripped_text = text.strip().replace(" ", "")
        self.callsign.setText(stripped_text)
        self.callsign.setCursorPosition(position)
        results = self.mscp.super_check(stripped_text)
        logger.debug(f"{results}")

        if " " in text:
            if stripped_text == "CW":
                self.change_mode(stripped_text)
                return
            if stripped_text == "RTTY":
                self.change_mode(stripped_text)
                return
            if stripped_text == "SSB":
                self.change_mode(stripped_text)
                return
            if stripped_text == "OPON":
                self.get_opon()
                self.clearinputs()
                return
            if stripped_text == "HELP":
                self.show_help_dialog()
                self.clearinputs()
                return
            if stripped_text == "TEST":
                result = self.database.get_calls_and_bands()
                cmd = {}
                cmd["cmd"] = "WORKED"
                cmd["station"] = platform.node()
                cmd["worked"] = result
                self.multicast_interface.send_as_json(cmd)
                self.clearinputs()
                return
            if self.is_floatable(stripped_text):
                self.change_freq(stripped_text)
                return

            self.check_callsign(stripped_text)
            if self.check_dupe(stripped_text):
                self.dupe_indicator.show()
            else:
                self.dupe_indicator.hide()
            _thethread = threading.Thread(
                target=self.check_callsign2,
                args=(text,),
                daemon=True,
            )
            _thethread.start()
            self.next_field.setFocus()
            return
        cmd = {}
        cmd["cmd"] = "CALLCHANGED"
        cmd["station"] = platform.node()
        cmd["call"] = stripped_text
        self.multicast_interface.send_as_json(cmd)
        self.check_callsign(stripped_text)

    def change_freq(self, stripped_text: str) -> None:
        """Change VFO to given frequency in Khz"""
        vfo = float(stripped_text)
        vfo = int(vfo * 1000)
        band = getband(str(vfo))
        self.set_band_indicator(band)
        self.radio_state["vfoa"] = vfo
        self.radio_state["band"] = band
        self.contact["Band"] = get_logged_band(str(vfo))
        self.set_window_title()
        self.clearinputs()
        if self.rig_control:
            self.rig_control.set_vfo(vfo)
            return
        cmd = {}
        cmd["cmd"] = "RADIO_STATE"
        cmd["station"] = platform.node()
        cmd["band"] = band
        cmd["vfoa"] = vfo
        self.multicast_interface.send_as_json(cmd)

    def change_mode(self, mode: str) -> None:
        """Change mode"""
        if mode == "CW":
            self.setmode("CW")
            self.radio_state["mode"] = "CW"
            if self.rig_control:
                if self.rig_control.online:
                    self.rig_control.set_mode("CW")
            band = getband(str(self.radio_state.get("vfoa", "0.0")))
            self.set_band_indicator(band)
            self.set_window_title()
            self.clearinputs()
            self.read_cw_macros()
            return
        if mode == "RTTY":
            self.setmode("RTTY")
            if self.rig_control:
                if self.rig_control.online:
                    self.rig_control.set_mode("RTTY")
                else:
                    self.radio_state["mode"] = "RTTY"
            band = getband(str(self.radio_state.get("vfoa", "0.0")))
            self.set_band_indicator(band)
            self.set_window_title()
            self.clearinputs()
            return
        if mode == "SSB":
            self.setmode("SSB")
            if int(self.radio_state.get("vfoa", 0)) > 10000000:
                self.radio_state["mode"] = "USB"
            else:
                self.radio_state["mode"] = "LSB"
            band = getband(str(self.radio_state.get("vfoa", "0.0")))
            self.set_band_indicator(band)
            self.set_window_title()
            if self.rig_control:
                self.rig_control.set_mode(self.radio_state.get("mode"))
            self.clearinputs()
            self.read_cw_macros()

    def check_callsign(self, callsign):
        """Check call as entered"""
        result = self.cty_lookup(callsign)
        debug_result = f"{result}"
        logger.debug("%s", debug_result)
        if result:
            for a in result.items():
                entity = a[1].get("entity", "")
                cq = a[1].get("cq", "")
                itu = a[1].get("itu", "")
                continent = a[1].get("continent")
                lat = float(a[1].get("lat", "0.0"))
                lon = float(a[1].get("long", "0.0"))
                lon = lon * -1  # cty.dat file inverts longitudes
                primary_pfx = a[1].get("primary_pfx", "")
                heading = bearing_with_latlon(self.station.get("GridSquare"), lat, lon)
                kilometers = distance_with_latlon(
                    self.station.get("GridSquare"), lat, lon
                )
                self.heading_distance.setText(
                    f"Regional Hdg {heading}° LP {reciprocol(heading)}° / "
                    f"distance {int(kilometers*0.621371)}mi {kilometers}km"
                )
                self.contact["CountryPrefix"] = primary_pfx
                self.contact["ZN"] = int(cq)
                if self.contest:
                    if self.contest.name == "IARU HF":
                        self.contact["ZN"] = int(itu)
                self.contact["Continent"] = continent
                self.dx_entity.setText(
                    f"{primary_pfx}: {continent}/{entity} cq:{cq} itu:{itu}"
                )
                if len(callsign) > 2:
                    if self.contest:
                        self.contest.prefill(self)

    def check_callsign2(self, callsign):
        """Check call once entered"""
        callsign = callsign.strip()
        debug_lookup = f"{self.look_up}"
        logger.debug("%s, %s", callsign, debug_lookup)
        if hasattr(self.look_up, "session"):
            if self.look_up.session:
                response = self.look_up.lookup(callsign)
                debug_response = f"{response}"
                logger.debug("The Response: %s\n", debug_response)
                if response:
                    theirgrid = response.get("grid")
                    self.contact["GridSquare"] = theirgrid
                    _theircountry = response.get("country")
                    if self.station.get("GridSquare", ""):
                        heading = bearing(self.station.get("GridSquare", ""), theirgrid)
                        kilometers = distance(self.station.get("GridSquare"), theirgrid)
                        self.heading_distance.setText(
                            f"{theirgrid} Hdg {heading}° LP {reciprocol(heading)}° / "
                            f"distance {int(kilometers*0.621371)}mi {kilometers}km"
                        )

    def check_dupe(self, call: str) -> bool:
        """Checks if a callsign is a dupe on current band/mode."""
        if self.contest is None:
            self.show_message_box("You have no contest loaded.")
            return False
        self.contest.predupe(self)
        band = float(get_logged_band(str(self.radio_state.get("vfoa", 0.0))))
        mode = self.radio_state.get("mode", "")
        debugline = (
            f"Call: {call} Band: {band} Mode: {mode} Dupetype: {self.contest.dupe_type}"
        )
        logger.debug("%s", debugline)
        if self.contest.dupe_type == 1:
            result = self.database.check_dupe(call)
        if self.contest.dupe_type == 2:
            result = self.database.check_dupe_on_band(call, band)
        if self.contest.dupe_type == 3:
            result = self.database.check_dupe_on_band_mode(call, band, mode)
        if self.contest.dupe_type == 4:
            result = {"isdupe": False}
        debugline = f"{result}"
        logger.debug("%s", debugline)
        return result.get("isdupe", False)

    def setmode(self, mode: str) -> None:
        """stub for when the mode changes."""
        if mode == "CW":
            if self.current_mode != "CW":
                self.current_mode = "CW"
                # self.mode.setText("CW")
                self.sent.setText("599")
                self.receive.setText("599")
                self.read_cw_macros()
            return
        if mode == "SSB":
            if self.current_mode != "SSB":
                self.current_mode = "SSB"
                # self.mode.setText("SSB")
                self.sent.setText("59")
                self.receive.setText("59")
                self.read_cw_macros()
            return
        if mode == "RTTY":
            if self.current_mode != "RTTY":
                self.current_mode = "RTTY"
                # self.mode.setText("RTTY")
                self.sent.setText("59")
                self.receive.setText("59")

    def get_opon(self):
        """Ctrl+O or OPON dialog"""
        self.opon_dialog = OpOn(WORKING_PATH)
        self.opon_dialog.accepted.connect(self.new_op)
        self.opon_dialog.open()

    def new_op(self):
        """Save new OP"""
        if self.opon_dialog.NewOperator.text():
            self.current_op = self.opon_dialog.NewOperator.text().upper()
        self.opon_dialog.close()
        logger.debug("New Op: %s", self.current_op)
        self.make_op_dir()

    def make_op_dir(self):
        """Create OP directory if it does not exist."""
        if self.current_op:
            op_path = Path(DATA_PATH) / self.current_op
            logger.debug("op_path: %s", str(op_path))
            if op_path.is_dir() is False:
                logger.debug("Creating Op Directory: %s", str(op_path))
                os.mkdir(str(op_path))
            if op_path.is_dir():
                source_path = Path(WORKING_PATH) / "data" / "phonetics"
                logger.debug("source_path: %s", str(source_path))
                for child in source_path.iterdir():
                    destination_file = op_path / child.name
                    if destination_file.is_file() is False:
                        logger.debug("Destination: %s", str(destination_file))
                        destination_file.write_bytes(child.read_bytes())

    def poll_radio(self):
        """stub"""
        if self.rig_control:
            if self.rig_control.online is False:
                self.rig_control.reinit()
            if self.rig_control.online:
                info_dirty = False
                vfo = self.rig_control.get_vfo()
                mode = self.rig_control.get_mode()
                bw = self.rig_control.get_bw()

                if mode == "CW":
                    self.setmode(mode)
                if mode == "LSB" or mode == "USB":
                    self.setmode("SSB")
                if mode == "RTTY":
                    self.setmode("RTTY")

                if self.radio_state.get("vfoa") != vfo:
                    info_dirty = True
                    self.radio_state["vfoa"] = vfo
                band = getband(str(vfo))
                self.radio_state["band"] = band
                self.contact["Band"] = get_logged_band(str(vfo))
                self.set_band_indicator(band)

                if self.radio_state.get("mode") != mode:
                    info_dirty = True
                    self.radio_state["mode"] = mode

                if self.radio_state.get("bw") != bw:
                    info_dirty = True
                    self.radio_state["bw"] = bw

                if datetime.now() > globals()["poll_time"] or info_dirty:
                    logger.debug("VFO: %s  MODE: %s BW: %s", vfo, mode, bw)
                    self.set_window_title()
                    cmd = {}
                    cmd["cmd"] = "RADIO_STATE"
                    cmd["station"] = platform.node()
                    cmd["band"] = band
                    cmd["vfoa"] = vfo
                    cmd["mode"] = mode
                    cmd["bw"] = bw
                    self.multicast_interface.send_as_json(cmd)
                    if self.n1mm:
                        if self.n1mm.send_radio_packets:
                            self.n1mm.radio_info["Freq"] = vfo[:-1]
                            self.n1mm.radio_info["TXFreq"] = vfo[:-1]
                            self.n1mm.radio_info["Mode"] = mode
                            self.n1mm.radio_info["OpCall"] = self.current_op
                            self.n1mm.radio_info["IsRunning"] = str(
                                self.pref.get("run_state", False)
                            )
                            self.n1mm.send_radio()
                    globals()["poll_time"] = datetime.now() + dt.timedelta(seconds=10)

    def edit_cw_macros(self) -> None:
        """
        Calls the default text editor to edit the CW macro file.
        """
        if self.radio_state.get("mode") == "CW":
            macro_file = "/cwmacros.txt"
        else:
            macro_file = "/ssbmacros.txt"
        if not Path(DATA_PATH + macro_file).exists():
            logger.debug("read_cw_macros: copying default macro file.")
            copyfile(WORKING_PATH + "/data" + macro_file, DATA_PATH + macro_file)
        os.system(f"xdg-open {DATA_PATH}{macro_file}")

    def read_cw_macros(self) -> None:
        """
        Reads in the CW macros, firsts it checks to see if the file exists. If it does not,
        and this has been packaged with pyinstaller it will copy the default file from the
        temp directory this is running from... In theory.
        """

        if self.radio_state.get("mode") == "CW":
            macro_file = "/cwmacros.txt"
        else:
            macro_file = "/ssbmacros.txt"

        if not Path(DATA_PATH + macro_file).exists():
            logger.debug("read_cw_macros: copying default macro file.")
            copyfile(WORKING_PATH + "/data" + macro_file, DATA_PATH + macro_file)
        with open(DATA_PATH + macro_file, "r", encoding="utf-8") as file_descriptor:
            for line in file_descriptor:
                try:
                    mode, fkey, buttonname, cwtext = line.split("|")
                    if mode.strip().upper() == "R" and self.pref.get("run_state"):
                        self.fkeys[fkey.strip()] = (buttonname.strip(), cwtext.strip())
                    if mode.strip().upper() != "R" and not self.pref.get("run_state"):
                        self.fkeys[fkey.strip()] = (buttonname.strip(), cwtext.strip())
                except ValueError as err:
                    logger.info("read_cw_macros: %s", err)
        keys = self.fkeys.keys()
        if "F1" in keys:
            self.F1.setText(f"F1: {self.fkeys['F1'][0]}")
            self.F1.setToolTip(self.fkeys["F1"][1])
        if "F2" in keys:
            self.F2.setText(f"F2: {self.fkeys['F2'][0]}")
            self.F2.setToolTip(self.fkeys["F2"][1])
        if "F3" in keys:
            self.F3.setText(f"F3: {self.fkeys['F3'][0]}")
            self.F3.setToolTip(self.fkeys["F3"][1])
        if "F4" in keys:
            self.F4.setText(f"F4: {self.fkeys['F4'][0]}")
            self.F4.setToolTip(self.fkeys["F4"][1])
        if "F5" in keys:
            self.F5.setText(f"F5: {self.fkeys['F5'][0]}")
            self.F5.setToolTip(self.fkeys["F5"][1])
        if "F6" in keys:
            self.F6.setText(f"F6: {self.fkeys['F6'][0]}")
            self.F6.setToolTip(self.fkeys["F6"][1])
        if "F7" in keys:
            self.F7.setText(f"F7: {self.fkeys['F7'][0]}")
            self.F7.setToolTip(self.fkeys["F7"][1])
        if "F8" in keys:
            self.F8.setText(f"F8: {self.fkeys['F8'][0]}")
            self.F8.setToolTip(self.fkeys["F8"][1])
        if "F9" in keys:
            self.F9.setText(f"F9: {self.fkeys['F9'][0]}")
            self.F9.setToolTip(self.fkeys["F9"][1])
        if "F10" in keys:
            self.F10.setText(f"F10: {self.fkeys['F10'][0]}")
            self.F10.setToolTip(self.fkeys["F10"][1])
        if "F11" in keys:
            self.F11.setText(f"F11: {self.fkeys['F11'][0]}")
            self.F11.setToolTip(self.fkeys["F11"][1])
        if "F12" in keys:
            self.F12.setText(f"F12: {self.fkeys['F12'][0]}")
            self.F12.setToolTip(self.fkeys["F12"][1])

    def generate_adif(self):
        """Generate ADIF"""
        logger.debug("******ADIF*****")
        self.contest.adif(self)

    def generate_cabrillo(self):
        """Generates Cabrillo file. Maybe."""
        # https://www.cqwpx.com/cabrillo.htm
        logger.debug("******Cabrillo*****")
        self.contest.cabrillo(self)


def load_fonts_from_dir(directory: str) -> set:
    """
    Well it loads fonts from a directory...
    """
    font_families = set()
    for _fi in QDir(directory).entryInfoList(["*.ttf", "*.woff", "*.woff2"]):
        _id = QFontDatabase.addApplicationFont(_fi.absoluteFilePath())
        font_families |= set(QFontDatabase.applicationFontFamilies(_id))
    return font_families


def install_icons():
    """Install icons"""
    os.system(
        "xdg-icon-resource install --size 32 --context apps --mode user "
        f"{WORKING_PATH}/data/k6gte.not1mm-32.png k6gte-not1mm"
    )
    os.system(
        "xdg-icon-resource install --size 64 --context apps --mode user "
        f"{WORKING_PATH}/data/k6gte.not1mm-64.png k6gte-not1mm"
    )
    os.system(
        "xdg-icon-resource install --size 128 --context apps --mode user "
        f"{WORKING_PATH}/data/k6gte.not1mm-128.png k6gte-not1mm"
    )
    os.system(f"xdg-desktop-menu install {WORKING_PATH}/data/k6gte-not1mm.desktop")


def doimp(modname):
    """return module path"""
    return importlib.import_module(f"not1mm.plugins.{modname}")


def run():
    """
    Main Entry
    """
    install_icons()
    timer.start(250)
    sys.exit(app.exec())


logger = logging.getLogger("__main__")
handler = logging.StreamHandler()
formatter = logging.Formatter(
    datefmt="%H:%M:%S",
    fmt="[%(asctime)s] %(levelname)s %(module)s - %(funcName)s Line %(lineno)d: %(message)s",
)
handler.setFormatter(formatter)
logger.addHandler(handler)

BETA_TEST = False
if Path("./betatest").exists():
    BETA_TEST = True

if Path("./debug").exists():
    logger.setLevel(logging.DEBUG)
    logger.debug("debugging on")
else:
    logger.setLevel(logging.WARNING)
    logger.warning("debugging off")

app = QtWidgets.QApplication(sys.argv)
app.setStyle("Adwaita-Dark")
font_path = WORKING_PATH + "/data"
families = load_fonts_from_dir(os.fspath(font_path))
logger.info(families)
window = MainWindow()
height = window.pref.get("window_height", 300)
width = window.pref.get("window_width", 700)
x = window.pref.get("window_x", -1)
y = window.pref.get("window_y", -1)
window.setGeometry(x, y, width, height)
window.callsign.setFocus()
window.show()
timer = QtCore.QTimer()
timer.timeout.connect(window.poll_radio)

if __name__ == "__main__":
    run()
