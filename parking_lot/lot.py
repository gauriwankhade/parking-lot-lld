import threading
from datetime import datetime
from uuid import uuid4

from parking_lot.enums import Size, VehicleType
from parking_lot.exceptions import (
    DuplicateTicketError,
    LotFullError,
    SpotUnavailableError,
    TicketNotFoundError,
)
from parking_lot.strategies.payment import PaymentStrategy
from parking_lot.strategies.pricing import PricingStrategy

REQUIRED_SIZES = {
    VehicleType.BIKE: Size.SMALL,
    VehicleType.CAR: Size.MEDIUM,
    VehicleType.BUS: Size.LARGE,
}


class Vehicle:
    def __init__(self, plate: str, vehicle_type: VehicleType):
        self.plate = plate
        self.type = vehicle_type


class Spot:
    def __init__(self, id: str, size: Size):
        self.id = id
        self.size = size
        self.vehicle = None

    def is_available(self) -> bool:
        return self.vehicle is None

    def can_fit(self, vehicle: Vehicle) -> bool:
        return self.is_available() and REQUIRED_SIZES[vehicle.type] == self.size

    def occupy(self, vehicle: Vehicle) -> None:
        if not self.can_fit(vehicle):
            raise SpotUnavailableError(f"Spot {self.id} cannot fit {vehicle.plate}")
        self.vehicle = vehicle

    def vacate(self) -> None:
        self.vehicle = None


class Floor:
    def __init__(self, number: int, spots: list[Spot]):
        self.number = number
        self.spots = spots

    def find_spot(self, vehicle: Vehicle):
        for spot in self.spots:
            if spot.can_fit(vehicle):
                return spot
        return None


class Ticket:
    def __init__(self, vehicle: Vehicle, spot: Spot, gate_id):
        self.id = uuid4().hex
        self.vehicle = vehicle
        self.spot = spot
        self.gate_id = gate_id
        self.entry_time = datetime.now()
        self.exit_time = None
        self.fare = None


class ParkingLot:
    def __init__(self, floors: list[Floor], pricing_strategy: PricingStrategy):
        self.floors = floors
        self.pricing_strategy = pricing_strategy      # lot-wide configuration
        self.lock = threading.Lock()
        self.active_tickets = {}                      # plate -> Ticket

    def park(self, gate_id, vehicle: Vehicle) -> Ticket:
        with self.lock:
            if vehicle.plate in self.active_tickets:
                raise DuplicateTicketError(f"Ticket for {vehicle.plate} already exists")
            for floor in self.floors:
                spot = floor.find_spot(vehicle)
                if spot is not None:
                    spot.occupy(vehicle)
                    ticket = Ticket(vehicle, spot, gate_id)
                    self.active_tickets[vehicle.plate] = ticket
                    return ticket
            raise LotFullError("No spot available")

    def exit(self, vehicle: Vehicle, payment: PaymentStrategy, exit_time=None) -> Ticket:
        # Taken before waiting for the lock, so queueing is not billed.
        exit_time = exit_time or datetime.now()
        with self.lock:
            ticket = self.active_tickets.get(vehicle.plate)
            if ticket is None:
                raise TicketNotFoundError(f"No ticket found for plate: {vehicle.plate}")
            if exit_time < ticket.entry_time:
                raise ValueError("Exit time cannot be before entry time")

            fare = self.pricing_strategy.calculate_fare(vehicle, ticket.entry_time, exit_time)
            payment.pay(fare)       

            ticket.exit_time = exit_time
            ticket.fare = fare
            ticket.spot.vacate()
            del self.active_tickets[vehicle.plate]
            return ticket