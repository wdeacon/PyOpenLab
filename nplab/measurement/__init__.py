from abc import ABC, abstractmethod
from enum import Enum
from threading import Thread
import threading
from typing import Generic, TypeVar, Union
import h5py
from typing_extensions import Self

class InterruptedException(Exception):
    
    def __init__(self, *args):
        super().__init__(*args)


class Status(Enum):
    '''Enumeration of all possible statuses for an action'''

    QUEUED      = 0
    RUNNING     = 1
    SUCCESS     = 2
    ERROR       = 3
    INTERRUPTED = 4


class Type(Enum):

    AUTO      = 0
    TIME      = 1
    FILE_SAVE = 2
    FILE_OPEN = 3
    DIRECTORY = 4


class MessageType(Enum):
    '''Enumeration of all possible types of message emitted by an action'''

    INFO    = 0
    WARNING = 1
    ERROR   = 2


T = TypeVar("T")

class Parameter(Generic[T]):

    def __init__(self, name: str, defaultValue: T, type: Type = Type.AUTO, options: list = []):

        self._name         : str             = name
        self._defaultValue : T               = defaultValue
        self._values       : dict[object, T] = {}
        self._type         : Type            = type
        self._options      : list[T]         = options


    def __set__(self, obj, value: T):
        self._values[obj] = value

    
    def __get__(self, obj, type=None) -> Union[T, Self]:

        if (obj is None):
            return self

        if (obj in self._values):
            return self._values[obj]
        else:
            return self._defaultValue
    

I = TypeVar("I")

class Instrument(Generic[I]):

    def __init__(self, name: str, required = True):

        self._name     = name
        self._required = required
        self._values   = {}


    def __set__(self, obj, value: I):
        self._values[obj] = value


    def __get__(self, obj, type=None) -> Union[I, Self]:

        if (obj is None):
            return self
        
        if (obj in self._values):
            return self._values[obj]
        else:
            return None
        
class PathPart:

    def __init__(self, part, sweepValue = None, sweepText: str = None):

        self.part       = part
        self.sweepValue = sweepValue
        self.sweepText  = sweepText


class Message:

    def __init__(self, type: MessageType, message: str, path: list, timestamp: int = None):

        if timestamp is None:
            import time
            timestamp = int(time.time())

        self.type      = type
        self.message   = message
        self.path      = path
        self.timestamp = timestamp


    def propagate(self, part, sweepValue = None, sweepText = None):
        return Message(self.type, self.message, [PathPart(part, sweepValue, sweepText)] + self.path, self.timestamp)


    @property
    def pathString(self):
        return " → ".join(["%s (%s)" % (p.part.name, p.sweepText) if p.sweepText is not None else p.part.name for p in self.path])


R = TypeVar("R")

class PValue:

    def __init__(self, parameter: Parameter, getter: callable, setter: callable):

        self._parameter = parameter
        self._getter    = getter
        self._setter    = setter

        self.name    = parameter._name
        self.options = parameter._options
        self.type    = parameter._type


    def get(self):
        return self._getter()
    

    def set(self, value):
        self._setter(value)


    value = property(get, set)

class IValue:

    def __init__(self, instrument: Instrument, getter: callable, setter: callable):

        self._instrument = instrument
        self._getter     = getter
        self._setter     = setter

        self.name     = instrument._name
        self.required = instrument._required


    def get(self):
        return self._getter()
    

    def set(self, value):
        self._setter(value)


    value = property(get, set)


class Result(Generic[R]):

    def __init__(self, type: Status, errors: list, messages: list, data: R = None):

        self.type     = type
        self.errors   = errors
        self.messages = messages
        self.data     = data



class Action(ABC, Generic[R]):

    def __init__(self, name: str, description: str):
        
        self.name        : str    = name
        self.description : str    = description

        self._status : Status = Status.QUEUED

        self._statusListeners  : list[callable] = []
        self._messageListeners : list[callable] = []

        self._thread      : Thread = None
        self._interrupted : bool   = False
        self._errors      : list   = []


    def start(self, data: R = None):
        
        thread = Thread(None, lambda: self.run(data))
        thread.start()


    def interrupt(self):
        self._interrupted = True


    def getStatus(self):
        return self._status


    def setStatus(self, status: Status):

        self._status = status
        
        for listener in self._statusListeners:
            listener(status)

    status = property(getStatus, setStatus)

    def run(self, data: R = None) -> Result:

        self._interrupted = False
        self._thread      = threading.current_thread()

        self._errors.clear()

        messages = []

        listener = self.addMessageListener(lambda message: messages.append(message))

        self.status = Status.RUNNING
        self.message(MessageType.INFO, "Started.")

        prepared = self.prepareData(self.name, self.description, data)

        try:
            self.main(prepared)

            if self._interrupted:
                raise InterruptedException()
            else:
                self.status = Status.SUCCESS

        except InterruptedException as e:
            self.status = Status.INTERRUPTED
            self.message(MessageType.WARNING, "Interrupted.")
            self.interrupted(prepared)

        except Exception as e:
            self.status = Status.ERROR
            self._errors.append(e)
            self.message(MessageType.ERROR, str(e))
            self.error(self._errors, prepared)

        finally:
            self.finish(prepared)
            self.message(MessageType.INFO, "Finished.")
            self.removeMessageListener(listener)

        return Result(self.status, self._errors, messages, prepared)
    

    def addStatusListener(self, listener: callable) -> callable:
        self._statusListeners.append(listener)
        return listener
    

    def removeStatusListener(self, listener: callable):
        self._statusListeners.remove(listener)


    def addMessageListener(self, listener: callable) -> callable:
        self._messageListeners.append(listener)
        return listener


    def removeMessageListener(self, listener: callable):
        self._messageListeners.remove(listener)


    def message(self, type: MessageType, message: str):

        msg = Message(type, message, [PathPart(self)])
        self.pass_message(msg)


    def pass_message(self, msg: Message):
        for listener in self._messageListeners:
            listener(msg)


    def checkpoint(self):
        '''Call this at points in your measurement code where it is safe for the measurement to be interrupted'''

        if self._interrupted:
            raise InterruptedException()


    def sleep(self, milliseconds: int):
        '''Makes the current tread sleep for the specified integer number of milliseconds'''

        from time import sleep

        if self._interrupted:
            raise InterruptedException()

        sleep(milliseconds / 1e3)

        if self._interrupted:
            raise InterruptedException()
        
    
    def getParameters(self) -> list:

        cls    = type(self)
        params = []

        for name in dir(cls):

            obj = getattr(cls, name)

            if type(obj) is not Parameter:
                continue

            params.append(PValue(obj, lambda n=name: getattr(self, n), lambda v, n=name: setattr(self, n, v)))

        return params
        
    
    def getInstruments(self) -> list:

        cls         = type(self)
        instruments = []

        for name in dir(cls):

            obj = getattr(cls, name)

            if type(obj) is not Instrument:
                continue

            instruments.append(IValue(obj, lambda n=name: getattr(self, n), lambda v, n=name: setattr(self, n, v)))

        return instruments

        
    @abstractmethod
    def prepareData(self, name: str, description: str, data: R) -> R:
        pass

    @abstractmethod
    def main(self, data: R = None):
        '''The main method of this action. This is where one should put the code this action is meant to run'''
        pass


    @abstractmethod
    def finish(self, data: R = None):
        '''This method is always called after main() has finished, regardless of whether it finished successfully or not'''
        pass
    
    
    def error(self, errors: list, data = None):
        '''This method is only called if the main() method finished in error (called before calling finish())'''
        pass


    def interrupted(self, data: R = None):
        '''This method is only called in the main() method is interrupted before completion (called before finish())'''
        pass

class SimpleAction(Action[object]):

    def prepareData(self, name, decription, data):
        return data


class H5Action(Action[h5py.Group]):

    def prepareData(self, name: str, description: str, data: h5py.Group):

        nm = "%s (%s)" % (name, description)

        i = 1
        while nm in data:
            nm = "%s (%s) [%d]" % (name, description, i)
            i += 1

        return data.create_group(nm)