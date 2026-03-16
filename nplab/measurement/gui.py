from math import inf
from typing import Generic, List, Tuple, TypeVar, Callable, Optional
import sys

from PyQt5.QtWidgets import *

from nplab.measurement import Action, PValue, Parameter, Type

import sys
from PyQt5.QtCore import Qt, pyqtSignal


A = TypeVar("A", bound=Action)
T = TypeVar("T")

class Setup(Generic[A], QWidget):

    def __init__(self, action: A, equipment: List):

        super().__init__()

        self._callbacks: List[Callable] = []

        self.vbox  = QVBoxLayout(self)
        self.hbox  = QHBoxLayout()
        self.form  = QFormLayout()
        self.okBtn = QPushButton("OK")
        self.cnBtn = QPushButton("Cancel")

        self.hbox.addWidget(self.okBtn)
        self.hbox.addWidget(self.cnBtn)

        self.vbox.addLayout(self.form)
        self.vbox.addLayout(self.hbox)

        self.setLayout(self.vbox)

        for parameter in action.getParameters():
            self.form.addRow(parameter.name, self.generateField(parameter))
            


        for instrument in action.getInstruments():

            names    = []
            filtered = [e for e in equipment if isinstance(e, instrument.type)]

            for eq in filtered:

                if hasattr(eq, "getName"):
                    nm = eq.getName()
                elif hasattr(eq, "name"):
                    nm = eq.name
                else:
                    nm = str(eq)

                names.append(nm)


            widget = QComboBox()
            widget.addItems(names)

            if (instrument.value in filtered):
                widget.setCurrentIndex(filtered.index(instrument.value))

            self.form.addRow(instrument.name, widget)
            self._callbacks.append(lambda: instrument.set(filtered[widget.currentIndex()]))

        
        self.okBtn.clicked.connect(self.okay)
        self.cnBtn.clicked.connect(self.close)
        

    def generateField(self, parameter: PValue[T]) -> QWidget:

        widget = None
        tp     = type(parameter.value)

        # We need to determine what type of field to create based on the details in the supplied parameter
        if parameter.type == Type.AUTO:

            if tp is float:
                widget = QDoubleSpinBox()
                widget.setValue(parameter.value)
                widget.setMinimum(parameter.range[0] if parameter.range[0] is not None else -inf)
                widget.setMaximum(parameter.range[1] if parameter.range[1] is not None else +inf)
                self._callbacks.append(lambda: parameter.set(widget.value()))

            elif tp is int:
                widget = QSpinBox()
                widget.setValue(parameter.value)
                widget.setMinimum(parameter.range[0] if parameter.range[0] is not None else -2147483648)
                widget.setMaximum(parameter.range[1] if parameter.range[1] is not None else +2147483647)
                self._callbacks.append(lambda: parameter.set(widget.value()))

            elif tp is bool:
                widget = QCheckBox()
                widget.setChecked(parameter.value)
                self._callbacks.append(lambda: parameter.set(widget.isChecked()))

            elif tp is str:
                widget = QLineEdit()
                widget.setText(parameter.value)
                self._callbacks.append(lambda: parameter.set(widget.text()))

            elif tp is list and type(parameter.value[0]) is float:
                widget = ListWidget[float](lambda v : str(v), QInputDialog.getDouble, 0.0)
                widget.setValues(parameter.value)
                self._callbacks.append(lambda: parameter.set(widget.getValues()))

            elif tp is list and type(parameter.value[0]) is int:
                widget = ListWidget[int](lambda v : str(v), QInputDialog.getInt, 0)
                widget.setValues(parameter.value)
                self._callbacks.append(lambda: parameter.set(widget.getValues()))

            elif tp is list and type(parameter.value[0]) is str:
                widget = ListWidget[str](lambda v : v, QInputDialog.getText, "")
                widget.setValues(parameter.value)
                self._callbacks.append(lambda: parameter.set(widget.getValues()))


        elif parameter.type == Type.TIME and tp is int:
            widget = TimeIntervalWidget(self)
            widget.setValue(parameter.value)
            self._callbacks.append(lambda: parameter.set(widget.value()))

        elif parameter.type == Type.TIME and tp is float:
            widget = TimeIntervalWidget(self)
            widget.setValue(int(parameter.value * 1e3))
            self._callbacks.append(lambda: parameter.set(float(widget.value()) / 1e3))

        return widget
    

    def okay(self):

        for callback in self._callbacks:
            callback()

        self.close()
    

T = TypeVar("T")

class ListWidget(QWidget, Generic[T]):

    def __init__(self, display: Callable[[T], str], dialog: Callable[[QWidget, str, str, T], Tuple[T, bool]], defValue: T):

        super().__init__()

        self.display          = display
        self.dialog           = dialog
        self.defValue         = defValue
        self._values: List[T] = []

        self.layout     = QVBoxLayout(self)
        self.listWidget = QListWidget()
        buttonLayout    = QHBoxLayout()

        self.addBtn  = QPushButton("Add")
        self.editBtn = QPushButton("Edit")
        self.remBtn  = QPushButton("Remove")
        self.upBtn   = QPushButton("Move Up")
        self.downBtn = QPushButton("Move Down")

        buttonLayout.addWidget(self.addBtn)
        buttonLayout.addWidget(self.editBtn)
        buttonLayout.addWidget(self.remBtn)
        buttonLayout.addWidget(self.upBtn)
        buttonLayout.addWidget(self.downBtn)

        self.layout.addLayout(buttonLayout)
        self.layout.addWidget(self.listWidget)

        # Connect signals
        self.addBtn.clicked.connect(self.addItem)
        self.editBtn.clicked.connect(self.editItem)
        self.remBtn.clicked.connect(self.removeItem)
        self.upBtn.clicked.connect(self.moveUp)
        self.downBtn.clicked.connect(self.moveDown)


    def add(self, value: T):
        """Add value of type T."""
        self.listWidget.addItem(self.display(value))
        self._values.append(value)


    def addItem(self):

        value, ok = self.dialog(self, "Add Item", "Enter Value...", self.defValue)

        if ok:
            self.add(value)


    def editItem(self):

        row = self.listWidget.currentRow()

        if row < 0:
            QMessageBox.warning(self, "No Selection", "Select an item to edit.")
            return

        item  = self.listWidget.item(row)
        value = self._values[row]

        value, ok = self.dialog(self, "Edit Item", "Enter Value...", value)

        if ok:
            item.setText(self.display(value))
            self._values[row] = value


    def removeItem(self):

        row = self.listWidget.currentRow()

        if row >= 0:
            self.listWidget.takeItem(row)
            self._values.pop(row)


    def moveUp(self):

        row = self.listWidget.currentRow()

        if row > 0:

            item = self.listWidget.takeItem(row)
            self.listWidget.insertItem(row - 1, item)
            self.listWidget.setCurrentRow(row - 1)

            self._values[row], self._values[row - 1] = (self._values[row - 1], self._values[row])


    def moveDown(self):

        row = self.listWidget.currentRow()

        if 0 <= row < self.listWidget.count() - 1:

            item = self.listWidget.takeItem(row)

            self.listWidget.insertItem(row + 1, item)
            self.listWidget.setCurrentRow(row + 1)

            self._values[row], self._values[row + 1] = (
                self._values[row + 1],
                self._values[row],
            )


    def getValues(self) -> List[T]:
        """Return list contents preserving original type."""
        return list(self._values)
    
    def setValues(self, values: List[T]):

        self._values.clear()
        self.listWidget.clear()

        for value in values:
            self.add(value)


class TimeIntervalWidget(QWidget):
    valueChanged = pyqtSignal(int)  # milliseconds

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(0, 0, 0, 0)

        self.hours = QSpinBox()
        self.hours.setRange(0, 9999)
        self.hours.setButtonSymbols(QSpinBox.NoButtons)
        self.hours.setMinimumWidth(60)
        self.hours.setAlignment(Qt.AlignRight)
        self.hours.setSuffix(" h")

        self.minutes = QSpinBox()
        self.minutes.setRange(0, 59)
        self.minutes.setButtonSymbols(QSpinBox.NoButtons)
        self.minutes.setFixedWidth(40)
        self.minutes.setAlignment(Qt.AlignRight)
        self.minutes.setSuffix(" m")

        self.seconds = QSpinBox()
        self.seconds.setRange(0, 59)
        self.seconds.setButtonSymbols(QSpinBox.NoButtons)
        self.seconds.setFixedWidth(40)
        self.seconds.setAlignment(Qt.AlignRight)
        self.seconds.setSuffix(" s")

        self.milliseconds = QSpinBox()
        self.milliseconds.setRange(0, 999)
        self.milliseconds.setButtonSymbols(QSpinBox.NoButtons)
        self.milliseconds.setFixedWidth(60)
        self.milliseconds.setAlignment(Qt.AlignRight)
        self.milliseconds.setSuffix(" ms")

        layout.addWidget(self.hours)
        layout.addWidget(QLabel(":"))
        layout.addWidget(self.minutes)
        layout.addWidget(QLabel(":"))
        layout.addWidget(self.seconds)
        layout.addWidget(QLabel(":"))
        layout.addWidget(self.milliseconds)

        for spin in (self.hours, self.minutes, self.seconds, self.milliseconds):
            spin.valueChanged.connect(self._valueChanged)

    def _valueChanged(self):
        self.valueChanged.emit(self.value())

    def value(self) -> int:
        """Return interval in milliseconds"""
        return (
            self.hours.value() * 3600000
            + self.minutes.value() * 60000
            + self.seconds.value() * 1000
            + self.milliseconds.value()
        )

    def setValue(self, ms: int):
        """Set interval from milliseconds"""

        hours = ms // 3600000
        ms %= 3600000

        minutes = ms // 60000
        ms %= 60000

        seconds = ms // 1000
        ms %= 1000

        milliseconds = ms

        self.hours.setValue(hours)
        self.minutes.setValue(minutes)
        self.seconds.setValue(seconds)
        self.milliseconds.setValue(milliseconds)