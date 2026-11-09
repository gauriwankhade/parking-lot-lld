from parking_lot.enums import *
from parking_lot.exceptions import *
from abc import ABC, abstractmethod
import math

class PricingStrategy(ABC):
    @abstractmethod
    def calculate_fare(self, vehicle, entry_time=None, exit_time=None):
        pass

RATES_BY_HOUR = {
    VehicleType.BIKE: 50,
    VehicleType.CAR: 70,
    VehicleType.BUS: 100
}

CONSTANT_RATES_BY_VEHICLE = {
    VehicleType.BIKE: 100,
    VehicleType.CAR: 200,
    VehicleType.BUS: 300   
}

class HourlyPricingStrategy(PricingStrategy):

    def calculate_fare(self, vehicle, entry_time, exit_time):
        duration = (exit_time - entry_time).total_seconds()

        if duration < 0:
            raise ValueError("Exit time cannot be before entry time") 
        
        hours = max(1, math.ceil(duration / 3600))

        return hours * RATES_BY_HOUR[vehicle.type]
    

class FlatPricingStrategy(PricingStrategy):

    def calculate_fare(self, vehicle, entry_time=None, exit_time=None):
        return CONSTANT_RATES_BY_VEHICLE[vehicle.type]
    
        

