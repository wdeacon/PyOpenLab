from abc import abstractmethod
from typing import Generic, TypeVar

from nplab.measurement import R, Action, InterruptedException, MessageType, Result, Status

D = TypeVar("D")

class Sweep(Action[R], Generic[R, D]):

    def __init__(self, name: str, tag: str, values: list, actions: list):

        super().__init__(name, "")

        self._tag     = tag
        self._values  = values
        self._actions = actions

    
    @abstractmethod
    def generate(self, value: D, actions: list) -> list:
        pass

    
    @abstractmethod
    def valueToString(self, value: D) -> str:
        pass


    @abstractmethod
    def prepareData(self, tag: str, value: D, data: R) -> R:
        pass


    def main(self, data: R = None):

        for value in self._values:

            actions = self.generate(value, self._actions)

            self.message(MessageType.INFO, "%s = %s." % (self._tag, self.valueToString(value)))

            for action in actions:

                listener = action.addMessageListener(lambda msg: self.pass_message(msg.propagate(self, value, "%s = %s" % (self._tag, self.valueToString(value)))))

                result: Result = action.run(self.prepareData(self._tag, value, data))

                action.removeMessageListener(listener)

                for error in result.errors:
                    self._errors.append(error)

                if result.type == Status.INTERRUPTED:
                    raise InterruptedException()

        if len(self._errors) > 0:
            raise Exception("Errors were encountered during the sweep.")

