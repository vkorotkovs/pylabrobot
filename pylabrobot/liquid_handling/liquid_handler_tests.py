""" Tests for LiquidHandler """
# pylint: disable=missing-class-docstring

import tempfile
from typing import Any, Dict, List, Optional, cast
import unittest
import unittest.mock

from pylabrobot.liquid_handling.strictness import Strictness, set_strictness
from pylabrobot.resources import no_tip_tracking, set_tip_tracking
from pylabrobot.resources.errors import HasTipError, NoTipError
from pylabrobot.resources.volume_tracker import set_volume_tracking

from . import backends
from .liquid_handler import LiquidHandler
from pylabrobot.resources import (
  Coordinate,
  Deck,
  Lid,
  Container,
  TipRack,
  TIP_CAR_480_A00,
  PLT_CAR_L5AC_A00,
  Cos_96_DW_1mL,
  Cos_96_DW_500ul,
)
from pylabrobot.resources.hamilton import STARLetDeck
from pylabrobot.resources.ml_star import STF_L, HTF_L
from .standard import (
  Pickup,
  Drop,
  DropTipRack,
  Aspiration,
  Dispense,
  AspirationPlate,
  DispensePlate
)

def _make_asp(r: Container, vol: float, tip: Any, offset: Optional[Coordinate]=None) -> Aspiration:
  return Aspiration(resource=r, volume=vol, tip=tip, offset=offset,
                   flow_rate=None, liquid_height=None, blow_out_air_volume=0, liquids=[(None, vol)])
def _make_disp(r: Container, vol: float, tip: Any, offset: Optional[Coordinate]=None) -> Dispense:
  return Dispense(resource=r, volume=vol, tip=tip, offset=offset,
                  flow_rate=None, liquid_height=None, blow_out_air_volume=0, liquids=[(None, vol)])


class TestLiquidHandlerLayout(unittest.IsolatedAsyncioTestCase):
  def setUp(self):
    self.backend = backends.SaverBackend(num_channels=8)
    self.deck = STARLetDeck()
    self.lh = LiquidHandler(self.backend, deck=self.deck)

  def test_resource_assignment(self):
    tip_car = TIP_CAR_480_A00(name="tip_carrier")
    tip_car[0] = STF_L(name="tip_rack_01")
    tip_car[1] = STF_L(name="tip_rack_02")
    tip_car[3] = HTF_L("tip_rack_04")

    plt_car = PLT_CAR_L5AC_A00(name="plate carrier")
    plt_car[0] = Cos_96_DW_1mL(name="aspiration plate")
    plt_car[2] = Cos_96_DW_500ul(name="dispense plate")

    self.deck.assign_child_resource(tip_car, rails=1)
    self.deck.assign_child_resource(plt_car, rails=21)

    # Test placing a carrier at a location where another carrier is located.
    with self.assertRaises(ValueError):
      dbl_plt_car_1 = PLT_CAR_L5AC_A00(name="double placed carrier 1")
      self.deck.assign_child_resource(dbl_plt_car_1, rails=1)

    with self.assertRaises(ValueError):
      dbl_plt_car_2 = PLT_CAR_L5AC_A00(name="double placed carrier 2")
      self.deck.assign_child_resource(dbl_plt_car_2, rails=2)

    with self.assertRaises(ValueError):
      dbl_plt_car_3 = PLT_CAR_L5AC_A00(name="double placed carrier 3")
      self.deck.assign_child_resource(dbl_plt_car_3, rails=20)

    # Test carrier with same name.
    with self.assertRaises(ValueError):
      same_name_carrier = PLT_CAR_L5AC_A00(name="plate carrier")
      self.deck.assign_child_resource(same_name_carrier, rails=10)
    # Should not raise when replacing.
    self.deck.assign_child_resource(same_name_carrier, rails=10, replace=True)
    # Should not raise when unassinged.
    self.lh.unassign_resource("plate carrier")
    self.deck.assign_child_resource(same_name_carrier, rails=10, replace=True)

    # Test unassigning unassigned resource
    self.lh.unassign_resource("plate carrier")
    with self.assertRaises(ValueError):
      self.lh.unassign_resource("plate carrier")
    with self.assertRaises(ValueError):
      self.lh.unassign_resource("this resource is completely new.")

    # Test invalid rails.
    with self.assertRaises(ValueError):
      self.deck.assign_child_resource(plt_car, rails=-1)
    with self.assertRaises(ValueError):
      self.deck.assign_child_resource(plt_car, rails=42)
    with self.assertRaises(ValueError):
      self.deck.assign_child_resource(plt_car, rails=27)

  def test_get_resource(self):
    tip_car = TIP_CAR_480_A00(name="tip_carrier")
    tip_car[0] = STF_L(name="tip_rack_01")
    plt_car = PLT_CAR_L5AC_A00(name="plate carrier")
    plt_car[0] = Cos_96_DW_1mL(name="aspiration plate")
    self.deck.assign_child_resource(tip_car, rails=1)
    self.deck.assign_child_resource(plt_car, rails=10)

    # Get resource.
    self.assertEqual(self.lh.get_resource("tip_carrier").name, "tip_carrier")
    self.assertEqual(self.lh.get_resource("plate carrier").name, "plate carrier")

    # Get subresource.
    self.assertEqual(self.lh.get_resource("tip_rack_01").name, "tip_rack_01")
    self.assertEqual(self.lh.get_resource("aspiration plate").name, "aspiration plate")

    # Get unknown resource.
    with self.assertRaises(ValueError):
      self.lh.get_resource("unknown resource")

  def test_subcoordinates(self):
    tip_car = TIP_CAR_480_A00(name="tip_carrier")
    tip_car[0] = STF_L(name="tip_rack_01")
    tip_car[3] = HTF_L(name="tip_rack_04")
    plt_car = PLT_CAR_L5AC_A00(name="plate carrier")
    plt_car[0] = Cos_96_DW_1mL(name="aspiration plate")
    plt_car[2] = Cos_96_DW_500ul(name="dispense plate")
    self.deck.assign_child_resource(tip_car, rails=1)
    self.deck.assign_child_resource(plt_car, rails=10)

    # Rails 10 should be left of rails 1.
    self.assertGreater(self.lh.get_resource("plate carrier").get_absolute_location().x,
                       self.lh.get_resource("tip_carrier").get_absolute_location().x)

    # Verified with Hamilton Method Editor.
    # Carriers.
    self.assertEqual(self.lh.get_resource("tip_carrier").get_absolute_location(),
                     Coordinate(100.0, 63.0, 100.0))
    self.assertEqual(self.lh.get_resource("plate carrier").get_absolute_location(),
                     Coordinate(302.5, 63.0, 100.0))

    # Subresources.
    self.assertEqual(
      cast(TipRack, self.lh.get_resource("tip_rack_01")).get_item("A1").get_absolute_location() +
      cast(TipRack, self.lh.get_resource("tip_rack_01")).get_item("A1").center(),
      Coordinate(117.900, 145.800, 164.450))
    self.assertEqual(
      cast(TipRack, self.lh.get_resource("tip_rack_04")).get_item("A1").get_absolute_location() +
      cast(TipRack, self.lh.get_resource("tip_rack_04")).get_item("A1").center(),
      Coordinate(117.900, 433.800, 131.450))

    self.assertEqual(
      cast(TipRack, self.lh.get_resource("aspiration plate")).get_item("A1")
        .get_absolute_location() +
      cast(TipRack, self.lh.get_resource("aspiration plate")).get_item("A1").center(),
        Coordinate(320.500, 146.000, 187.150))

  def test_illegal_subresource_assignment_before(self):
    # Test assigning subresource with the same name as another resource in another carrier. This
    # should raise an ValueError when the carrier is assigned to the liquid handler.
    tip_car = TIP_CAR_480_A00(name="tip_carrier")
    tip_car[0] = STF_L(name="sub")
    plt_car = PLT_CAR_L5AC_A00(name="plate carrier")
    plt_car[0] = Cos_96_DW_1mL(name="sub")
    self.deck.assign_child_resource(tip_car, rails=1)
    with self.assertRaises(ValueError):
      self.deck.assign_child_resource(plt_car, rails=10)

  def test_illegal_subresource_assignment_after(self):
    # Test assigning subresource with the same name as another resource in another carrier, after
    # the carrier has been assigned. This should raise an error.
    tip_car = TIP_CAR_480_A00(name="tip_carrier")
    tip_car[0] = STF_L(name="sub")
    plt_car = PLT_CAR_L5AC_A00(name="plate carrier")
    plt_car[0] = Cos_96_DW_1mL(name="ok")
    self.deck.assign_child_resource(tip_car, rails=1)
    self.deck.assign_child_resource(plt_car, rails=10)
    with self.assertRaises(ValueError):
      plt_car[1] = Cos_96_DW_500ul(name="sub")

  async def test_move_plate_to_site(self):
    plt_car = PLT_CAR_L5AC_A00(name="plate carrier")
    plt_car[0] = plate = Cos_96_DW_1mL(name="plate")
    self.deck.assign_child_resource(plt_car, rails=21)

    await self.lh.move_plate(plate, plt_car[2])
    self.assertIsNotNone(plt_car[2].resource)
    self.assertIsNone(plt_car[0].resource)
    self.assertEqual(plt_car[2].resource, self.lh.get_resource("plate"))
    self.assertEqual(plate.get_item("A1").get_absolute_location() + plate.get_item("A1").center(),
                     Coordinate(568.000, 338.000, 187.150))

  async def test_move_plate_free(self):
    plt_car = PLT_CAR_L5AC_A00(name="plate carrier")
    plt_car[0] = plate = Cos_96_DW_1mL(name="plate")
    self.deck.assign_child_resource(plt_car, rails=1)

    await self.lh.move_plate(plate, Coordinate(1000, 1000, 1000))
    self.assertIsNotNone(self.lh.get_resource("plate"))
    self.assertIsNone(plt_car[0].resource)
    self.assertEqual(plate.get_absolute_location(),
      Coordinate(1000, 1000, 1000))

  def test_serialize(self):
    serialized = self.lh.serialize()
    deserialized = LiquidHandler.deserialize(serialized)

    self.assertEqual(deserialized.deck, self.lh.deck)
    self.assertEqual(deserialized.backend.__class__.__name__,
      self.lh.backend.__class__.__name__)


class TestLiquidHandlerCommands(unittest.IsolatedAsyncioTestCase):
  async def asyncSetUp(self):
    self.maxDiff = None

    self.backend = backends.SaverBackend(num_channels=8)
    self.deck =STARLetDeck()
    self.lh = LiquidHandler(backend=self.backend, deck=self.deck)

    self.tip_rack = STF_L(name="tip_rack")
    self.plate = Cos_96_DW_1mL(name="plate")
    self.deck.assign_child_resource(self.tip_rack, location=Coordinate(0, 0, 0))
    self.deck.assign_child_resource(self.plate, location=Coordinate(100, 100, 0))
    await self.lh.setup()

  def get_first_command(self, command) -> Optional[Dict[str, Any]]:
    for sent_command in self.backend.commands_received:
      if sent_command["command"] == command:
        return sent_command
    return None

  async def test_offsets_tips(self):
    tip_spot = self.tip_rack.get_item("A1")
    tip = tip_spot.get_tip()
    await self.lh.pick_up_tips([tip_spot], offsets=Coordinate(x=1, y=1, z=1))
    await self.lh.drop_tips([tip_spot], offsets=Coordinate(x=1, y=1, z=1))

    self.assertEqual(self.get_first_command("pick_up_tips"), {
      "command": "pick_up_tips",
      "args": (),
      "kwargs": {
        "use_channels": [0],
        "ops": [
          Pickup(tip_spot, tip=tip, offset=Coordinate(x=1, y=1, z=1))]}})
    self.assertEqual(self.get_first_command("drop_tips"), {
      "command": "drop_tips",
      "args": (),
      "kwargs": {
        "use_channels": [0], "ops": [
          Drop(tip_spot, tip=tip, offset=Coordinate(x=1, y=1, z=1))]}})

  async def test_offsets_asp_disp(self):
    well = self.plate.get_item("A1")
    well.tracker.set_liquids([(None, 10)])
    t = self.tip_rack.get_item("A1").get_tip()
    self.lh.update_head_state({0: t})
    await self.lh.aspirate([well], vols=10, offsets=Coordinate(x=1, y=1, z=1))
    await self.lh.dispense([well], vols=10, offsets=Coordinate(x=1, y=1, z=1))

    self.assertEqual(self.get_first_command("aspirate"), {
      "command": "aspirate",
      "args": (),
      "kwargs": {
        "use_channels": [0],
        "ops": [_make_asp(well, vol=10, offset=Coordinate(x=1, y=1, z=1), tip=t)]}})
    self.assertEqual(self.get_first_command("dispense"), {
      "command": "dispense",
      "args": (),
      "kwargs": {
        "use_channels": [0],
        "ops": [_make_disp(well, vol=10, offset=Coordinate(x=1, y=1, z=1), tip=t)]}})

  async def test_return_tips(self):
    tip_spot = self.tip_rack.get_item("A1")
    tip = tip_spot.get_tip()
    await self.lh.pick_up_tips([tip_spot])
    await self.lh.return_tips()

    self.assertEqual(self.get_first_command("drop_tips"), {
      "command": "drop_tips",
      "args": (),
      "kwargs": {
        "use_channels": [0],
        "ops": [Drop(tip_spot, tip=tip, offset=None)]}})

    with self.assertRaises(RuntimeError):
      await self.lh.return_tips()

  async def test_return_tips96(self):
    await self.lh.pick_up_tips96(self.tip_rack)
    await self.lh.return_tips96()

    self.assertEqual(self.get_first_command("drop_tips96"), {
      "command": "drop_tips96",
      "args": (),
      "kwargs": {
        "drop": DropTipRack(resource=self.tip_rack, offset=Coordinate.zero())
      }})

    with self.assertRaises(RuntimeError):
      await self.lh.return_tips()

  async def test_transfer(self):
    t = self.tip_rack.get_item("A1").get_tip()
    self.lh.update_head_state({0: t})

    # Simple transfer
    self.plate.get_item("A1").tracker.set_liquids([(None, 10)])
    await self.lh.transfer(self.plate.get_well("A1"), self.plate["A2"], source_vol=10)

    self.assertEqual(self.get_first_command("aspirate"), {
      "command": "aspirate",
      "args": (),
      "kwargs": {
        "use_channels": [0],
        "ops": [_make_asp(self.plate.get_item("A1"), vol=10.0, tip=t)]}})
    self.assertEqual(self.get_first_command("dispense"), {
      "command": "dispense",
      "args": (),
      "kwargs": {
        "use_channels": [0],
        "ops": [_make_disp(self.plate.get_item("A2"), vol=10.0, tip=t)]}})
    self.backend.clear()

    # Transfer to multiple wells
    self.plate.get_item("A1").tracker.set_liquids([(None, 80)])
    await self.lh.transfer(self.plate.get_well("A1"), self.plate["A1:H1"], source_vol=80)
    self.assertEqual(self.get_first_command("aspirate"), {
      "command": "aspirate",
      "args": (),
      "kwargs": {
        "use_channels": [0],
        "ops": [_make_asp(self.plate.get_item("A1"), vol=80.0, tip=t)]}})

    dispenses = list(filter(lambda x: x["command"] == "dispense", self.backend.commands_received))
    self.assertEqual(dispenses, [{
      "command": "dispense",
      "args": (),
      "kwargs": {
        "use_channels": [0],
        "ops": [_make_disp(well, vol=10.0, tip=t)]}}
      for well in self.plate["A1:H1"]])
    self.backend.clear()

    # Transfer with ratios
    self.plate.get_item("A1").tracker.set_liquids([(None, 60)])
    await self.lh.transfer(self.plate.get_well("A1"), self.plate["B1:C1"], source_vol=60,
      ratios=[2, 1])
    self.assertEqual(self.get_first_command("aspirate"), {
      "command": "aspirate",
      "args": (),
      "kwargs": {
        "use_channels": [0],
        "ops": [_make_asp(self.plate.get_item("A1"), vol=60.0, tip=t)]}})
    dispenses = list(filter(lambda x: x["command"] == "dispense", self.backend.commands_received))
    self.assertEqual(dispenses, [{
      "command": "dispense",
      "args": (),
      "kwargs": {
        "use_channels": [0],
        "ops": [_make_disp(well, vol=vol, tip=t)]}}
      for well, vol in zip(self.plate["B1:C1"], [40, 20])])
    self.backend.clear()

    # Transfer with target_vols
    vols: List[float] = [3, 1, 4, 1, 5, 9, 6, 2]
    self.plate.get_item("A1").tracker.set_liquids([(None, sum(vols))])
    await self.lh.transfer(self.plate.get_well("A1"), self.plate["A1:H1"], target_vols=vols)
    self.assertEqual(self.get_first_command("aspirate"), {
      "command": "aspirate",
      "args": (),
      "kwargs": {
        "use_channels": [0],
        "ops": [_make_asp(self.plate.get_well("A1"), vol=sum(vols), tip=t)]}})
    dispenses = list(filter(lambda x: x["command"] == "dispense", self.backend.commands_received))
    self.assertEqual(dispenses, [{
      "command": "dispense",
      "args": (),
      "kwargs": {
        "use_channels": [0],
        "ops": [_make_disp(well, vol=vol, tip=t)]}}
      for well, vol in zip(self.plate["A1:H1"], vols)])
    self.backend.clear()

    # target_vols and source_vol specified
    with self.assertRaises(TypeError):
      await self.lh.transfer(self.plate.get_well("A1"), self.plate["A1:H1"],
        source_vol=100, target_vols=vols)

    # target_vols and ratios specified
    with self.assertRaises(TypeError):
      await self.lh.transfer(self.plate.get_well("A1"), self.plate["A1:H1"],
        ratios=[1]*8, target_vols=vols)

  async def test_stamp(self):
    # Simple transfer
    await self.lh.pick_up_tips96(self.tip_rack) # pick up tips first.
    await self.lh.stamp(self.plate, self.plate, volume=10)
    ts = self.tip_rack.get_all_tips()

    self.assertEqual(self.get_first_command("aspirate96"), {
      "command": "aspirate96",
      "args": (),
      "kwargs": {"aspiration":
        AspirationPlate(resource=self.plate, volume=10.0, tips=ts, offset=Coordinate.zero(),
                        flow_rate=None, liquid_height=None, blow_out_air_volume=0,
                        liquids=[[(None, 10)]]*96)}})
    self.assertEqual(self.get_first_command("dispense96"), {
      "command": "dispense96",
      "args": (),
      "kwargs": {"dispense":
        DispensePlate(resource=self.plate, volume=10.0, tips=ts, offset=Coordinate.zero(),
                flow_rate=None, liquid_height=None, blow_out_air_volume=0,
                liquids=[[(None, 10)]]*96)}})
    self.backend.clear()

  async def test_tip_tracking_double_pickup(self):
    await self.lh.pick_up_tips(self.tip_rack["A1"])

    set_tip_tracking(enabled=True)
    with self.assertRaises(HasTipError):
      await self.lh.pick_up_tips(self.tip_rack["A2"])
    set_tip_tracking(enabled=False)

    with no_tip_tracking():
      await self.lh.pick_up_tips(self.tip_rack["A2"])

  async def test_tip_tracking_empty_drop(self):
    with self.assertRaises(NoTipError):
      await self.lh.drop_tips(self.tip_rack["A1"])

    await self.lh.pick_up_tips(self.tip_rack["A2"])
    set_tip_tracking(enabled=True)
    with self.assertRaises(HasTipError):
      await self.lh.drop_tips(self.tip_rack["A3"])
    set_tip_tracking(enabled=False)

  async def test_tip_tracking_empty_pickup(self):
    self.tip_rack.get_item("A1").empty()

    set_tip_tracking(enabled=True)
    with self.assertRaises(NoTipError):
      await self.lh.pick_up_tips(self.tip_rack["A1"])
    set_tip_tracking(enabled=False)

  async def test_tip_tracking_full_spot(self):
    await self.lh.pick_up_tips(self.tip_rack["A1"])
    with self.assertRaises(HasTipError):
      set_tip_tracking(enabled=True)
      await self.lh.drop_tips(self.tip_rack["A2"])
      set_tip_tracking(enabled=False)

  async def test_tip_tracking_double_pickup_single_command(self):
    set_tip_tracking(enabled=True)
    with self.assertRaises(NoTipError):
      await self.lh.pick_up_tips(self.tip_rack["A1", "A1"])
    set_tip_tracking(enabled=False)

  async def test_discard_tips(self):
    tips = self.tip_rack.get_tips("A1:D1")
    await self.lh.pick_up_tips(self.tip_rack["A1", "B1", "C1", "D1"], use_channels=[0, 1, 3, 4])
    await self.lh.discard_tips()
    offsets = self.deck.get_trash_area().get_2d_center_offsets(n=4)

    self.assertEqual(self.get_first_command("drop_tips"), {
      "command": "drop_tips",
      "args": (),
      "kwargs": {
        "use_channels": [0, 1, 3, 4],
        "ops": [
          Drop(self.deck.get_trash_area(), tip=tips[3], offset=offsets[0]),
          Drop(self.deck.get_trash_area(), tip=tips[2], offset=offsets[1]),
          Drop(self.deck.get_trash_area(), tip=tips[1], offset=offsets[2]),
          Drop(self.deck.get_trash_area(), tip=tips[0], offset=offsets[3]),
        ]}})

    # test tip tracking
    with self.assertRaises(RuntimeError):
      await self.lh.discard_tips()

  async def test_aspirate_with_lid(self):
    lid = Lid("lid",
              size_x=self.plate.get_size_x(),
              size_y=self.plate.get_size_y(),
              size_z=self.plate.lid_height)
    self.plate.assign_child_resource(lid, location=Coordinate(0, 0,
                                     self.plate.get_size_z() - self.plate.lid_height))
    well = self.plate.get_item("A1")
    well.tracker.set_liquids([(None, 10)])
    t = self.tip_rack.get_item("A1").get_tip()
    self.lh.update_head_state({0: t})
    with self.assertRaises(ValueError):
      await self.lh.aspirate([well], vols=10)

  async def test_strictness(self):
    class TestBackend(backends.SaverBackend):
      """ Override pick_up_tips for testing. """
      async def pick_up_tips(self, ops, use_channels, non_default, default=True):
        # pylint: disable=unused-argument
        assert non_default == default

    self.backend = TestBackend(num_channels=16)
    self.lh = LiquidHandler(self.backend, deck=self.deck)
    await self.lh.setup()

    with no_tip_tracking():
      set_strictness(Strictness.IGNORE)
      await self.lh.pick_up_tips(self.tip_rack["A1"], non_default=True)
      await self.lh.pick_up_tips(self.tip_rack["A1"], use_channels=[1],
        non_default=True, does_not_exist=True)
      with self.assertRaises(TypeError): # missing non_default
        await self.lh.pick_up_tips(self.tip_rack["A1"], use_channels=[2])

      set_strictness(Strictness.WARN)
      await self.lh.pick_up_tips(self.tip_rack["A1"], non_default=True, use_channels=[3])
      with self.assertWarns(UserWarning): # extra kwargs should warn
        await self.lh.pick_up_tips(self.tip_rack["A1"], use_channels=[4],
          non_default=True, does_not_exist=True)
      # We override default to False, so this should raise an assertion error. To test whether
      # overriding default to True works.
      with self.assertRaises(AssertionError):
        await self.lh.pick_up_tips(self.tip_rack["A1"], use_channels=[4],
          non_default=True, does_not_exist=True, default=False)
      with self.assertRaises(TypeError): # missing non_default
        await self.lh.pick_up_tips(self.tip_rack["A1"], use_channels=[5])

      set_strictness(Strictness.STRICT)
      await self.lh.pick_up_tips(self.tip_rack["A1"], non_default=True, use_channels=[6])
      with self.assertRaises(TypeError): # cannot have extra kwargs
        await self.lh.pick_up_tips(self.tip_rack["A1"], use_channels=[7],
          non_default=True, does_not_exist=True)
      with self.assertRaises(TypeError): # missing non_default
        await self.lh.pick_up_tips(self.tip_rack["A1"], use_channels=[8])

      set_strictness(Strictness.WARN)

  async def test_save_state(self):
    set_volume_tracking(enabled=True)

    # a mini protocol
    self.plate.get_item("A1").tracker.set_liquids([(None, 10)])
    await self.lh.pick_up_tips(self.tip_rack["A1"])
    await self.lh.aspirate(self.plate["A1"], vols=10)
    await self.lh.dispense(self.plate["A2"], vols=10)

    # save the state
    state_filename = tempfile.mktemp()
    self.lh.deck.save_state_to_file(filename=state_filename)

    # save the deck
    deck_filename = tempfile.mktemp()
    self.lh.deck.save(fn=deck_filename)

    # create a new liquid handler, load the state and the deck
    lh2 = LiquidHandler(self.backend, deck=STARLetDeck())
    lh2.deck = Deck.load_from_json_file(json_file=deck_filename)
    lh2.deck.load_state_from_file(filename=state_filename)

    # assert that the state is the same
    well_a1 = lh2.deck.get_resource("plate").get_item("A1") # type: ignore
    self.assertEqual(well_a1.tracker.liquids, [])
    well_a2 = lh2.deck.get_resource("plate").get_item("A2") # type: ignore
    self.assertEqual(well_a2.tracker.liquids, [(None, 10)])

    set_volume_tracking(enabled=False)
