import numpy as np
import pyjisa.autoload

from typing import Callable, Generic, List, Tuple, TypeVar

from jisa.devices import Instrument
from jisa.results import ResultTable
from java.lang    import Short, Integer, Long, Double, String, Boolean

from qtpy.QtCore import Qt
from qtpy.QtGui import QIcon
from qtpy.QtWidgets import QCheckBox, QComboBox, QErrorMessage, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLineEdit, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget

from nplab.ui.widgets.jisa.widgets import ResultTableWidget, ScientificSpinBox

I = TypeVar("I", bound=Instrument)

class JISAConfigPanel(QWidget, Generic[I]):
    
    warningIcon = QIcon.fromTheme("dialog-warning")
    all         = []

    def __init__(self, instrument: I, prepare: Callable[[I], bool] = None, restore: Callable[[I, bool], None] = None):

        super().__init__()
        
        self.instrument = instrument
        self.prepare    = prepare
        self.restore    = restore
        self.params     = []

        self.scrollArea    = QScrollArea()
        self.buttons       = QHBoxLayout()
        self.applyButton   = QPushButton("Apply")
        self.refreshButton = QPushButton("Refresh")
        self.errorMessage  = QErrorMessage()
        self.scrollWidget  = QWidget()
        self.scrollLayout  = QVBoxLayout()
        self.mainLayout    = QVBoxLayout()

        self.setLayout(self.mainLayout)

        self.buttons.addWidget(self.refreshButton)
        self.buttons.addWidget(self.applyButton)

        self.mainLayout.addWidget(self.scrollArea)
        self.mainLayout.addLayout(self.buttons)
        self.mainLayout.setContentsMargins(0,0,0,0)
        self.setContentsMargins(0,0,0,0)

        self.scrollWidget.setLayout(self.scrollLayout)
        self.scrollArea.setWidget(self.scrollWidget)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scrollArea.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scrollArea.setContentsMargins(0,0,0,0)
        self.scrollWidget.setContentsMargins(0,0,0,0)
        self.scrollLayout.setContentsMargins(0,0,0,0)
        self.scrollArea.setFrameShape(QFrame.NoFrame)
        self.setupParameters()
        self.setupConnections()

        JISAConfigPanel.all.append(self)


    def setupConnections(self):

        self.refreshButton.clicked.connect(self.refreshParameters)
        self.applyButton.clicked.connect(self.applyParameters)


    def setupParameters(self):

        forms = {"General": QFormLayout()}

        for param in self.instrument.getAllParameters():

            group = param.getGroup() if param.isGrouped() else "General"

            if group not in forms:
                forms[group] = QFormLayout()

            form = forms[group]

            widget, getter, setter = self.createParameterWidget(param.getDefaultValue(), param.getChoices())

            if widget is None:
                continue

            status = QPushButton()
            status.setIcon(self.warningIcon)
            status.setFixedSize(25, 25)
            status.setVisible(False)

            widget.setContentsMargins(0, 0, 0, 0)
            hbox = QHBoxLayout()
            hbox.addWidget(widget, 1)
            setB = QPushButton("✓")
            setB.setFixedWidth(25)
            hbox.addWidget(status, 0, Qt.AlignTop)

            form.addRow(param.getName(), hbox)

            try:
                setter(param.getCurrentValue())
            except:
                pass

            setB.clicked.connect(lambda v, getter=getter, setter=setter, param=param, status=status: self.applyParameter(getter, setter, param, status, True))
            self.params.append((widget, getter, setter, param, status))

        for name, form in forms.items():
            box = QGroupBox(name)
            box.setLayout(form)
            self.scrollLayout.addWidget(box)


    def createParameterWidget(self, defaultValue, choices: List = []) -> Tuple[QWidget, Callable, Callable]:

        if isinstance(defaultValue, Instrument.AutoQuantity):

            checkBox = QCheckBox("Auto")
            checkBox.setChecked(defaultValue.isAuto())

            widget, getter, setter = self.createParameterWidget(defaultValue.getValue(), choices)

            if widget is None:
                return (None, None, None)

            widget.setDisabled(checkBox.isChecked())

            def updateCheckBox():
                widget.setDisabled(checkBox.isChecked())

            checkBox.stateChanged.connect(updateCheckBox)
            
            hbox = QHBoxLayout() if not isinstance(defaultValue.getValue(), ResultTable) else QVBoxLayout()
            cont = QWidget()
            cont.setLayout(hbox)
            cont.setContentsMargins(0, 0, 0, 0)
            hbox.setContentsMargins(0, 0, 0, 0)

            hbox.addWidget(checkBox, 0)
            hbox.addWidget(widget, 1)

            def autoGetter():
                return Instrument.AutoQuantity(checkBox.isChecked(), getter())
            
            def autoSetter(aq: Instrument.AutoQuantity):
                checkBox.setChecked(aq.isAuto())
                setter(aq.getValue())

            return (cont, autoGetter, autoSetter)
        
        elif isinstance(defaultValue, Instrument.OptionalQuantity):

            checkBox = QCheckBox("Enabled")
            checkBox.setChecked(defaultValue.isUsed())
            
            widget, getter, setter = self.createParameterWidget(defaultValue.getValue(), choices)

            if widget is None:
                return (None, None, None)

            widget.setDisabled(not checkBox.isChecked())

            def updateCheckBox():
                widget.setDisabled(not checkBox.isChecked())

            checkBox.stateChanged.connect(updateCheckBox)
            
            hbox = QHBoxLayout() if not isinstance(defaultValue.getValue(), ResultTable) else QVBoxLayout()
            cont = QWidget()
            cont.setLayout(hbox)
            cont.setContentsMargins(0, 0, 0, 0)
            hbox.setContentsMargins(0, 0, 0, 0)

            hbox.addWidget(checkBox, 0)
            hbox.addWidget(widget, 1)

            def autoGetter():
                return Instrument.OptionalQuantity(checkBox.isChecked(), getter())
            
            def autoSetter(aq: Instrument.OptionalQuantity):
                checkBox.setChecked(aq.isUsed())
                setter(aq.getValue())

            return (cont, autoGetter, autoSetter)
        
        elif len(choices) > 0:

            choiceBox  = QComboBox()
            choiceBox.addItems([str(c) for c in choices])

            def getter(choices=choices, choiceBox=choiceBox):
                return choices[choiceBox.currentIndex()]
            
            def setter(value):
                choiceBox.setCurrentIndex(choices.index(value))

            setter(defaultValue)

            return (choiceBox, getter, setter)
        
        elif isinstance(defaultValue, (Double, float)):

            doubleBox = ScientificSpinBox()
            doubleBox.setValue(defaultValue)

            return (doubleBox, doubleBox.value, doubleBox.setValue)

        elif isinstance(defaultValue, (int, Integer)):

            intBox = QSpinBox()
            intBox.setMinimum(-2147483647)
            intBox.setMaximum(2147483647)
            intBox.setValue(defaultValue)

            return (intBox, lambda: np.int32(intBox.value()), intBox.setValue)
        
        elif isinstance(defaultValue, (bool, Boolean)):

            checkBox = QCheckBox()
            checkBox.setChecked(defaultValue)
            return (checkBox, checkBox.isChecked, checkBox.setChecked)
        
        elif isinstance(defaultValue, (str, String)):

            textBox = QLineEdit()
            textBox.setText(str(defaultValue))

            return (textBox, textBox.text, textBox.setText)
        
        elif isinstance(defaultValue, ResultTable):

            table = ResultTableWidget()
            table.setResultTable(defaultValue)

            return (table, table.getResultTable, table.setResultTable)

        else:
            
            return (None, None, None)


    def refreshParameters(self):

        for (w, g, s, p, st) in self.params:

            try:
                s(p.getCurrentValue())
            except Exception as e:
                print(e)


    def applyParameters(self):
        '''Applies all configuration parameters, then updates their displayed values'''

        if self.prepare is not None:
            result = self.prepare(self.instrument)
        else:
            result = False

        for (w, g, s, p, st) in self.params:
            self.applyParameter(g, s, p, st)

        for panel in JISAConfigPanel.all:
            panel.refreshParameters()

        if self.restore is not None:
            self.restore(self.instrument, result)


    def applyParameter(self, getter: Callable, setter: Callable, param: Instrument.Parameter, status: QPushButton, refresh = False):
        '''Applies one single parameter, optionally can refresh all others afterwards if specified'''

        status.setVisible(False)

        if self.prepare is not None:
            result = self.prepare(self.instrument)
        else:
            result = False

        try:
            status.clicked.disconnect()
        except:
            pass

        try:
            param.set(getter())
        except Exception as e:
            status.clicked.connect(lambda v, e=e: self.showException(e))
            status.setVisible(True)

        if refresh:
            self.refreshParameters()

        if self.restore is not None:
            self.restore(self.instrument, result)


    def showException(self, e: Exception):
        self.errorMessage.showMessage(str(e))