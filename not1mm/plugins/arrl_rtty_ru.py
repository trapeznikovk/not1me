"""ARRL plugin"""

# pylint: disable=invalid-name, unused-argument, unused-variable

import datetime
from PyQt5 import QtWidgets

name = "ARRL RTTY Round Up"
mode = "BOTH"  # CW SSB BOTH RTTY
columns = [
    "YYYY-MM-DD HH:MM:SS",
    "Call",
    "Freq",
    "Snt",
    "Rcv",
    "SentNr",
    "RcvNr",
    "Exchange1",
    "CK",
    "Prec",
    "Sect",
    "WPX",
    "Power",
    "M1",
    "ZN",
    "M2",
    "PFX",
    "PTS",
    "Name",
    "Comment",
]

# 1 once per contest, 2 work each band, 3 each band/mode, 4 no dupe checking
dupe_type = 4


def init_contest(self):
    """setup plugin"""
    set_tab_next(self)
    set_tab_prev(self)
    interface(self)


def interface(self):
    """Setup user interface"""


def reset_label(self):
    """reset label after field cleared"""


def set_tab_next(self):
    """Set TAB Advances"""
    self.tab_next = {
        self.callsign: self.field1.findChild(QtWidgets.QLineEdit),
        self.field1.findChild(QtWidgets.QLineEdit): self.field2.findChild(
            QtWidgets.QLineEdit
        ),
        self.field2.findChild(QtWidgets.QLineEdit): self.field3.findChild(
            QtWidgets.QLineEdit
        ),
        self.field3.findChild(QtWidgets.QLineEdit): self.field4.findChild(
            QtWidgets.QLineEdit
        ),
        self.field4.findChild(QtWidgets.QLineEdit): self.callsign,
    }


def set_tab_prev(self):
    """Set TAB Advances"""
    self.tab_prev = {
        self.callsign: self.field4.findChild(QtWidgets.QLineEdit),
        self.field1.findChild(QtWidgets.QLineEdit): self.callsign,
        self.field2.findChild(QtWidgets.QLineEdit): self.field1.findChild(
            QtWidgets.QLineEdit
        ),
        self.field3.findChild(QtWidgets.QLineEdit): self.field2.findChild(
            QtWidgets.QLineEdit
        ),
        self.field4.findChild(QtWidgets.QLineEdit): self.field3.findChild(
            QtWidgets.QLineEdit
        ),
    }


def set_contact_vars(self):
    """Contest Specific"""


def predupe(self):
    """called after callsign entered"""


def prefill(self):
    """Fill SentNR"""


def points(self):
    """Calc point"""


def show_mults(self):
    """Return display string for mults"""


def show_qso(self):
    """Return qso count"""
    result = self.database.fetch_qso_count()
    if result:
        return int(result.get("qsos", 0))
    return 0


def get_points(self):
    """Return raw points before mults"""
    result = self.database.fetch_points()
    if result:
        return int(result.get("Points", 0))
    return 0


def calc_score(self):
    """Return calculated score"""
    result = self.database.fetch_points()


def adif(self):
    """
    Creates an ADIF file of the contacts made.
    """


def cabrillo(self):
    """Generates Cabrillo file. Maybe."""


def recalculate_mults(self):
    """Recalculates multipliers after change in logged qso."""
