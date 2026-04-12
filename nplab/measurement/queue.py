from abc import ABC, abstractmethod
from threading import Thread
from typing import Callable, Generic, List, TypeVar, Union

import h5py

from nplab.measurement.action import Action, Message, MessageType, Result, Status

R = TypeVar("R")

class ActionQueue(Generic[R], ABC):

    def __init__(self):
        
        self._actions  : List[Action[Union[R,None]]] = []
        self._messages : List[Message]               = []
        self._running  : bool                        = False
        self._thread   : Thread                      = None

        self._messageListeners : List[Callable[[Message], None]]      = []
        self._actionListeners  : List[Callable[[List[Action]], None]] = []


    @abstractmethod
    def prepareData(self, data: R) -> R:
        pass


    def run(self, data: R):

        if self._running:
            return

        self._running = True
        self.message(Message(MessageType.INFO, "Queue started."))

        data     = self.prepareData(data)
        errors   = []
        messages = []
        status   = Status.SUCCESS

        try:

            for action in self._actions:

                listener = action.addMessageListener(self.message)
                result   = action.run(data)
                
                action.removeMessageListener(listener)

                errors   += result.errors
                messages += result.messages

                if result.type == Status.INTERRUPTED:
                    status = Status.INTERRUPTED
                    break

                elif result.type == Status.ERROR:
                    status = Status.ERROR


            return Result(status, errors, messages)

        finally:
            
            self.message(Message(MessageType.INFO, "Queue finished (%s)." % status))
            self._running = False
            

    @property
    def actions(self) -> List[Action[Union[R,None]]]:
        return list(self._actions)

    
    def notifyActionListeners(self):
        for listener in self._actionListeners:
            listener(self._actions)

    
    def message(self, message: Message):

        self._messages.append(message)

        for listener in self._messageListeners:
            listener(message)


    def checkIsRunning(self):
        if self._running:
            raise Exception("Cannot modify an ActionQueue that is currently running.")
        

    def addAction(self, action: Action):
        self.checkIsRunning()
        self._actions.append(action)
        self.notifyActionListeners()


    def addActions(self, *actions: Action):
        self.checkIsRunning()
        self._actions += actions
        self.notifyActionListeners()

    
    def removeAction(self, action: Action):
        self.checkIsRunning()
        self._actions.remove(action)
        self.notifyActionListeners()


    def swapActions(self, a: Action, b: Action):

        self.checkIsRunning()

        if a not in self._actions or b not in self._actions:
            raise Exception("Can only swap actions that are both present in the queue already.")
        
        indexA = self._actions.index(a)
        indexB = self._actions.index(b)

        self._actions[indexA] = b
        self._actions[indexB] = a

        self.notifyActionListeners()


    def swapActionsByIndex(self, a: int, b: int):

        self.checkIsRunning()

        length = len(self._actions)

        if a >= length or a < 0 or b >= length or b < 0:
            raise IndexError("Invalid index.")
        
        actionA = self._actions[a]
        actionB = self._actions[b]

        self._actions[a] = actionB
        self._actions[b] = actionA

        self.notifyActionListeners()

    
class H5ActionQueue(ActionQueue[h5py.Group]):

    def __init__(self, namePattern: str = r"Queue Run %d"):
        super().__init__()
        self._namePattern = namePattern


    @property
    def namePattern(self) -> str:
        return self._namePattern


    @namePattern.setter
    def setNamePattern(self, pattern: str):
        self._namePattern = pattern


    def prepareData(self, data: h5py.Group) -> h5py.Group:
        
        try:
            self._namePattern % 1
        except:
            self._namePattern = self._namePattern.replace(r"%", r"") + r"_%d"

        counter = 0
        name    = self._namePattern % counter

        while name in data:
            count += 1
            name   = self._namePattern % counter

        return data.create_group(name)
    
