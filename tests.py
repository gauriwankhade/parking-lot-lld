"""Run from the repo root:   python tests.py"""
import threading
import unittest
from datetime import timedelta

from parking_lot.lot import Floor, ParkingLot, Size, Spot, Vehicle, VehicleType
from parking_lot.exceptions import (
    DuplicateTicketError,
    LotFullError,
    TicketNotFoundError,
)
from parking_lot.strategies.payment import PaymentStrategy, UPIPaymentStrategy
from parking_lot.strategies.pricing import FlatPricingStrategy, HourlyPricingStrategy



def make_floor(number):
    """A floor with exactly one small, one medium and one large spot."""
    return Floor(number, [
        Spot(f"{number}-small", Size.SMALL),
        Spot(f"{number}-medium", Size.MEDIUM),
        Spot(f"{number}-large", Size.LARGE),
    ])

def bike(plate): return Vehicle(plate, VehicleType.BIKE)
def car(plate):  return Vehicle(plate, VehicleType.CAR)
def bus(plate):  return Vehicle(plate, VehicleType.BUS)

class DecliningPayment(PaymentStrategy):
    """A payment method that always fails."""
    def pay(self, amount):
        raise RuntimeError("card declined")


# ---------- entry ----------

class EntryTests(unittest.TestCase):

    def setUp(self):
        self.lot = ParkingLot([make_floor(1), make_floor(2)], HourlyPricingStrategy())

    def test_each_vehicle_gets_a_spot_of_its_own_size(self):
        self.assertEqual(self.lot.park("G1", bike("B1")).spot.id, "1-small")
        self.assertEqual(self.lot.park("G1", car("C1")).spot.id, "1-medium")
        self.assertEqual(self.lot.park("G1", bus("U1")).spot.id, "1-large")

    def test_second_car_goes_to_floor_2_when_floor_1_is_taken(self):
        self.lot.park("G1", car("C1"))
        ticket = self.lot.park("G1", car("C2"))
        self.assertEqual(ticket.spot.id, "2-medium")

    def test_third_car_is_refused_when_both_medium_spots_are_taken(self):
        self.lot.park("G1", car("C1"))
        self.lot.park("G1", car("C2"))
        with self.assertRaises(LotFullError):
            self.lot.park("G1", car("C3"))

    def test_same_plate_cannot_park_twice(self):
        self.lot.park("G1", car("C1"))
        with self.assertRaises(DuplicateTicketError):
            self.lot.park("G2", car("C1"))

    def test_refused_duplicate_does_not_use_up_a_spot(self):
        self.lot.park("G1", car("C1"))
        with self.assertRaises(DuplicateTicketError):
            self.lot.park("G2", car("C1"))
        ticket = self.lot.park("G1", car("C2"))          # floor 2 must still be free
        self.assertEqual(ticket.spot.id, "2-medium")


# ---------- exit ----------

class ExitTests(unittest.TestCase):

    def setUp(self):
        self.lot = ParkingLot([make_floor(1)], HourlyPricingStrategy())   # one floor only
        self.upi = UPIPaymentStrategy()

    def test_exit_records_exit_time_and_fare(self):
        vehicle = car("C1")
        self.lot.park("G1", vehicle)

        ticket = self.lot.exit(vehicle, self.upi)

        self.assertIsNotNone(ticket.exit_time)
        self.assertIsNotNone(ticket.fare)

    def test_exit_frees_the_spot_for_the_next_car(self):
        first = car("C1")
        self.lot.park("G1", first)
        with self.assertRaises(LotFullError):             # the only medium spot is taken
            self.lot.park("G1", car("C2"))

        self.lot.exit(first, self.upi)

        ticket = self.lot.park("G1", car("C2"))           # now it works
        self.assertEqual(ticket.spot.id, "1-medium")

    def test_exiting_a_car_that_is_not_parked_raises(self):
        with self.assertRaises(TicketNotFoundError):
            self.lot.exit(car("NEVER-PARKED"), self.upi)

    def test_exiting_twice_raises(self):
        vehicle = car("C1")
        self.lot.park("G1", vehicle)
        self.lot.exit(vehicle, self.upi)
        with self.assertRaises(TicketNotFoundError):
            self.lot.exit(vehicle, self.upi)

    def test_second_exit_does_not_free_a_spot_now_used_by_another_car(self):
        old_car, new_car = car("OLD"), car("NEW")
        self.lot.park("G1", old_car)
        self.lot.exit(old_car, self.upi)
        self.lot.park("G1", new_car)                      # NEW now holds the medium spot

        with self.assertRaises(TicketNotFoundError):      # OLD tries to exit again
            self.lot.exit(old_car, self.upi)

        with self.assertRaises(LotFullError):             # the spot must still be taken
            self.lot.park("G1", car("THIRD"))

    def test_exit_time_before_entry_time_is_rejected(self):
        vehicle = car("C1")
        ticket = self.lot.park("G1", vehicle)
        an_hour_before_entry = ticket.entry_time - timedelta(hours=1)
        with self.assertRaises(ValueError):
            self.lot.exit(vehicle, self.upi, exit_time=an_hour_before_entry)

    def test_failed_payment_keeps_the_car_parked(self):
        vehicle = car("C1")
        self.lot.park("G1", vehicle)

        with self.assertRaises(RuntimeError):
            self.lot.exit(vehicle, DecliningPayment())

        with self.assertRaises(LotFullError):             # spot is still occupied
            self.lot.park("G1", car("C2"))

    def test_driver_can_retry_with_another_payment_method_after_a_failure(self):
        vehicle = car("C1")
        self.lot.park("G1", vehicle)
        with self.assertRaises(RuntimeError):
            self.lot.exit(vehicle, DecliningPayment())

        ticket = self.lot.exit(vehicle, self.upi)         # second attempt works

        self.assertIsNotNone(ticket.fare)


# ---------- pricing (checked through exit) ----------

class PricingTests(unittest.TestCase):

    def stay_and_exit(self, pricing, vehicle, **duration):
        """Park the vehicle, leave after the given duration, return the fare."""
        lot = ParkingLot([make_floor(1)], pricing)
        ticket = lot.park("G1", vehicle)
        left_at = ticket.entry_time + timedelta(**duration)
        return lot.exit(vehicle, UPIPaymentStrategy(), exit_time=left_at).fare

    def test_hourly_car_for_3_hours_costs_210(self):
        fare = self.stay_and_exit(HourlyPricingStrategy(), car("C1"), hours=3)
        self.assertEqual(fare, 3 * 70)

    def test_hourly_under_one_hour_is_charged_one_hour(self):
        fare = self.stay_and_exit(HourlyPricingStrategy(), car("C1"), minutes=1)
        self.assertEqual(fare, 1 * 70)

    def test_hourly_61_minutes_is_charged_two_hours(self):
        fare = self.stay_and_exit(HourlyPricingStrategy(), car("C1"), minutes=61)
        self.assertEqual(fare, 2 * 70)

    def test_hourly_rates_differ_by_vehicle(self):
        self.assertEqual(self.stay_and_exit(HourlyPricingStrategy(), bike("B1"), hours=1), 50)
        self.assertEqual(self.stay_and_exit(HourlyPricingStrategy(), bus("U1"), hours=1), 100)

    def test_flat_fee_does_not_depend_on_duration(self):
        short = self.stay_and_exit(FlatPricingStrategy(), car("C1"), minutes=5)
        long = self.stay_and_exit(FlatPricingStrategy(), car("C2"), hours=9)
        self.assertEqual(short, 200)
        self.assertEqual(long, 200)


# ---------- many gates at once ----------

class ConcurrencyTests(unittest.TestCase):

    def test_sixty_cars_racing_for_five_spots_never_double_book(self):
        five_floors = [make_floor(n) for n in range(1, 6)]    # five medium spots in total
        lot = ParkingLot(five_floors, HourlyPricingStrategy())
        parked_spot_ids = []
        refused_count = []

        def one_car_arrives(i):
            try:
                ticket = lot.park(f"G{i % 3}", car(f"C{i}"))
                parked_spot_ids.append(ticket.spot.id)
            except LotFullError:
                refused_count.append(i)

        threads = [threading.Thread(target=one_car_arrives, args=(i,)) for i in range(60)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(parked_spot_ids), 5)             # exactly 5 got in
        self.assertEqual(len(set(parked_spot_ids)), 5)        # all in different spots
        self.assertEqual(len(refused_count), 55)              # everyone else was refused


if __name__ == "__main__":
    unittest.main(verbosity=2)