"""General Logging plugin"""

# pylint: disable=invalid-name, unused-argument, unused-variable

import datetime
import logging
from decimal import Decimal
from pathlib import Path

from PyQt5 import QtWidgets

from not1mm.lib.version import __version__

logger = logging.getLogger("__main__")

name = "General Logging"
cabrillo_name = "General-Logging"
mode = "BOTH"  # CW SSB BOTH RTTY
columns = [0, 1, 2, 3, 4, 16, 17]
columns = [
    "YYYY-MM-DD HH:MM:SS",
    "Call",
    "Freq",
    "Snt",
    "Rcv",
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
    self.next_field = self.other_1


def interface(self):
    """Setup user interface"""
    self.field1.show()
    self.field2.show()
    self.field3.show()
    self.field4.show()
    label = self.field3.findChild(QtWidgets.QLabel)
    label.setText("Name")
    label = self.field4.findChild(QtWidgets.QLabel)
    label.setText("Comment")


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
    self.contact["SNT"] = self.sent.text()
    self.contact["RCV"] = self.receive.text()
    self.contact["Name"] = self.other_1.text()
    self.contact["Comment"] = self.other_2.text()


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
    now = datetime.datetime.now()
    date_time = now.strftime("%Y-%m-%d_%H-%M-%S")
    filename = (
        str(Path.home())
        + "/"
        + f"{self.station.get('Call').upper()}_{cabrillo_name}_{date_time}.adi"
    )
    log = self.database.fetch_all_contacts_asc()
    try:
        with open(filename, "w", encoding="utf-8") as file_descriptor:
            print("<ADIF_VER:5>2.2.0", end="\r\n", file=file_descriptor)
            print("<EOH>", end="\r\n", file=file_descriptor)
            for contact in log:
                hiscall = contact.get("Call", "")
                hisname = contact.get("Name", "")
                the_date_and_time = contact.get("TS")
                # band = contact.get("Band")
                themode = contact.get("Mode")
                frequency = str(Decimal(str(contact.get("Freq", 0))) / 1000)
                sentrst = contact.get("SNT", "")
                rcvrst = contact.get("RCV", "")
                sentnr = str(contact.get("SentNr", "0"))
                rcvnr = str(contact.get("NR", "0"))
                grid = contact.get("GridSquare", "")
                comment = contact.get("Comment", "")
                loggeddate = the_date_and_time[:10]
                loggedtime = the_date_and_time[11:13] + the_date_and_time[14:16]
                print(
                    f"<QSO_DATE:{len(''.join(loggeddate.split('-')))}:d>"
                    f"{''.join(loggeddate.split('-'))}",
                    end="\r\n",
                    file=file_descriptor,
                )
                print(
                    f"<TIME_ON:{len(loggedtime)}>{loggedtime}",
                    end="\r\n",
                    file=file_descriptor,
                )
                print(
                    f"<CALL:{len(hiscall)}>{hiscall.upper()}",
                    end="\r\n",
                    file=file_descriptor,
                )
                if len(hisname):
                    print(
                        f"<NAME:{len(hisname)}>{hisname.title()}",
                        end="\r\n",
                        file=file_descriptor,
                    )
                print(
                    f"<MODE:{len(themode)}>{themode}", end="\r\n", file=file_descriptor
                )
                # print(
                #     f"<BAND:{len(band + 'M')}>{band + 'M'}",
                #     end="\r\n",
                #     file=file_descriptor,
                # )
                try:
                    print(
                        f"<FREQ:{len(frequency)}>{frequency}",
                        end="\r\n",
                        file=file_descriptor,
                    )
                except TypeError:
                    pass  # This is bad form... I can't remember why this is in a try block

                print(
                    f"<RST_SENT:{len(sentrst)}>{sentrst}",
                    end="\r\n",
                    file=file_descriptor,
                )
                print(
                    f"<RST_RCVD:{len(rcvrst)}>{rcvrst}",
                    end="\r\n",
                    file=file_descriptor,
                )
                if sentnr != "0":
                    print(
                        f"<STX_STRING:{len(sentnr)}>{sentnr}",
                        end="\r\n",
                        file=file_descriptor,
                    )
                if rcvnr != "0":
                    print(
                        f"<SRX_STRING:{len(rcvnr)}>{rcvnr}",
                        end="\r\n",
                        file=file_descriptor,
                    )
                if len(grid) > 1:
                    print(
                        f"<GRIDSQUARE:{len(grid)}>{grid}",
                        end="\r\n",
                        file=file_descriptor,
                    )
                if len(comment):
                    print(
                        f"<COMMENT:{len(comment)}>{comment}",
                        end="\r\n",
                        file=file_descriptor,
                    )
                print("<EOR>", end="\r\n", file=file_descriptor)
                print("", end="\r\n", file=file_descriptor)
    except IOError:
        ...


def cabrillo(self):
    """Generates Cabrillo file. Maybe."""


def recalculate_mults(self):
    """Recalculates multipliers after change in logged qso."""
