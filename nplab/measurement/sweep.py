from abc import abstractmethod
from typing import Generic, TypeVar
from h5py import Group

from nplab.measurement import R, Action, InterruptedException, MessageType, Result, Status

D = TypeVar("D")

class Sweep(Action[R], Generic[R, D]):

    def __init__(self, name: str, tag: str, actions: list = []):

        super().__init__(name, "")

        self._tag     = tag
        self._actions = actions


    def addAction(self, action: Action[R]):
        self._actions.append(action)

    
    def removeAction(self, action: Action[R]):
        self._actions.remove(action)

    
    @abstractmethod
    def generate(self, value: D, actions: list) -> list:
        pass

    
    @abstractmethod
    def valueToString(self, value: D) -> str:
        pass


    @abstractmethod
    def prepareDataForIteration(self, tag: str, value: D, data: R) -> R:
        pass

    @abstractmethod
    def getValues(self) -> list:
        pass

    def main(self, data: R = None):

        values = self.getValues()

        for value in values:

            actions = self.generate(value, self._actions)

            self.message(MessageType.INFO, "%s = %s." % (self._tag, self.valueToString(value)))

            prepared = self.prepareDataForIteration(self._tag, value, data)

            for action in actions:

                listener = action.addMessageListener(lambda msg: self.pass_message(msg.propagate(self, value, "%s = %s" % (self._tag, self.valueToString(value)))))

                result: Result = action.run(prepared)

                action.removeMessageListener(listener)

                for error in result.errors:
                    self._errors.append(error)

                if result.type == Status.INTERRUPTED:
                    raise InterruptedException()

        if len(self._errors) > 0:
            raise Exception("Errors were encountered during the sweep.")


    def finish(self, data: R = None):
        pass


class H5Sweep(Sweep[Group, D], Generic[D]):

    def __init__(self, name, tag, actions = []):
        super().__init__(name, tag, actions)

    def prepareData(self, name, description, data):
        
        nm = "%s (%s)" % (name, self._tag)

        i = 1
        while nm in data:
            nm = "%s (%s) [%d]" % (name, self._tag, i)
            i += 1

        return data.create_group(nm)

    def prepareDataForIteration(self, tag: str, value: D, data: Group):
        return data.create_group("%s = %s" % (tag, self.valueToString(value)))
    
