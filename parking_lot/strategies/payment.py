from abc import ABC, abstractmethod

class PaymentStrategy(ABC):
    @abstractmethod
    def pay(self, amount):
        pass 


class UPIPaymentStrategy(PaymentStrategy):
    def pay(self, amount):
        return "Paid via UPI"
    
class CardPaymentStrategy(PaymentStrategy):
    def pay(self, amount):
        return "Paid via Card"