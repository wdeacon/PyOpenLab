from abc import ABC, abstractmethod
from enum import Enum
from threading import Thread
import threading
from typing import Generic, TypeVar, Union
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


class MessageType(Enum):
    '''Enumeration of all possible types of message emitted by an action'''

    INFO    = 0
    WARNING = 1
    ERROR   = 2


T = TypeVar("T")

class Parameter(Generic[T]):

    def __init__(self, name: str, defaultValue: T):

        self._name         : str             = name
        self._defaultValue : T               = defaultValue
        self._values       : dict[object, T] = {}


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
        
R = TypeVar("R")

class Action(ABC, Generic[R]):


    def __init__(self, name: str, description: str):
        
        self.name        : str    = name
        self.description : str    = description

        self._status : Status = Status.QUEUED

        self._statusListeners  : list[callable[Status]]           = []
        self._messageListeners : list[callable[MessageType, str]] = []

        self._thread      : Thread = None
        self._interrupted : bool   = False


    def start(self, data: R = None):
        
        thread = Thread(None, lambda: self.run(data))
        thread.start()


    def getStatus(self):
        return self._status


    def setStatus(self, status: Status):

        self._status = status
        
        for listener in self._statusListeners:
            listener(status)

    status = property(getStatus, setStatus)

    def run(self, data: R = None):

        self._thread = threading.current_thread()

        self.status = Status.RUNNING
        self.message(MessageType.INFO, "Started.")

        try:

            self.main(data)

            if self._interrupted:
                raise InterruptedException()
            else:
                self.status = Status.SUCCESS

        except InterruptedException as e:
            self.status = Status.INTERRUPTED
            self.message(MessageType.WARNING, "Interrupted.")
            self.interrupted(data)

        except Exception as e:
            self.status = Status.ERROR
            self.message(MessageType.ERROR, "Error encountered.")
            self.error([e], data)

        finally:
            self.finish(data)
            self.message(MessageType.INFO, "Finished.")



    def message(self, type: MessageType, message: str):

        for listener in self._messageListeners:
            listener(type, message)


    def checkpoint(self):
        if self._interrupted:
            raise InterruptedException()


    def sleep(self, time: int):

        from time import sleep

        if self._interrupted:
            raise InterruptedException()

        seconds = time / 1e3
        part    = seconds / 10

        for i in range(10):

            sleep(part)

            if self._interrupted:
                raise InterruptedException()


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