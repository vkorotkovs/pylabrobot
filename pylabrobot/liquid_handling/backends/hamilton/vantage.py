# pylint: disable=invalid-name

import re
import sys
from typing import Dict, List, Optional, Sequence, Union, cast

from pylabrobot.liquid_handling.backends.hamilton.base import (
  HamiltonLiquidHandler,
  HamiltonFirmwareError
)
from pylabrobot.liquid_handling.liquid_classes.hamilton import get_vantage_liquid_class
from pylabrobot.liquid_handling.standard import (
  Pickup,
  PickupTipRack,
  Drop,
  DropTipRack,
  Aspiration,
  AspirationPlate,
  Dispense,
  DispensePlate,
  Move
)
from pylabrobot.resources import Coordinate, Liquid, Resource, Plate, Well
from pylabrobot.resources.ml_star import HamiltonTip, TipPickupMethod, TipSize


if sys.version_info >= (3, 8):
  from typing import Literal
else:
  from typing_extensions import Literal


def parse_vantage_fw_string(s: str, fmt: Optional[Dict[str, str]] = None) -> dict:
  """ Parse a Vantage firmware string into a dict.

  The identifier parameter (id<int>) is added automatically.

  `fmt` is a dict that specifies the format of the string. The keys are the parameter names and the
  values are the types. The following types are supported:

    - `"int"`: a single integer
    - `"str"`: a string
    - `"[int]"`: a list of integers
    - `"hex"`: a hexadecimal number

  Example:
    >>> parse_fw_string("id0xs30 -100 +1 1000", {"id": "int", "x": "[int]"})
    {"id": 0, "x": [30, -100, 1, 1000]}

    >>> parse_fw_string("es\"error string\"", {"es": "str"})
    {"es": "error string"}
  """

  parsed: dict = {}

  if fmt is None:
    fmt = {}

  if not isinstance(fmt, dict):
    raise TypeError(f"invalid fmt for fmt: expected dict, got {type(fmt)}")

  if "id" not in fmt:
    fmt["id"] = "int"

  for key, data_type in fmt.items():
    if data_type == "int":
      matches = re.findall(fr"{key}([-+]?\d+)", s)
      if len(matches) != 1:
        raise ValueError(f"Expected exactly one match for {key} in {s}")
      parsed[key] = int(matches[0])
    elif data_type == "str":
      matches = re.findall(fr"{key}\"(.*)\"", s)
      if len(matches) != 1:
        raise ValueError(f"Expected exactly one match for {key} in {s}")
      parsed[key] = matches[0]
    elif data_type == "[int]":
      matches = re.findall(fr"{key}((?:[-+]?[\d ]+)+)", s)
      if len(matches) != 1:
        raise ValueError(f"Expected exactly one match for {key} in {s}")
      parsed[key] = [int(x) for x in matches[0].split()]
    elif data_type == "hex":
      matches = re.findall(fr"{key}([0-9a-fA-F]+)", s)
      if len(matches) != 1:
        raise ValueError(f"Expected exactly one match for {key} in {s}")
      parsed[key] = int(matches[0], 16)
    else:
      raise ValueError(f"Unknown data type {data_type}")

  return parsed

core96_errors = {
  0: "No error",
  21: "No communication to digital potentiometer",
  25: "Wrong Flash EPROM data",
  26: "Flash EPROM not programmable",
  27: "Flash EPROM not erasable",
  28: "Flash EPROM checksum error",
  29: "Wrong FW loaded",
  30: "Undefined command",
  31: "Undefined parameter",
  32: "Parameter out of range",
  35: "Voltages out of range",
  36: "Stop during command execution",
  37: "Adjustment sensor didn't switch (no teach in signal)",
  40: "No parallel processes on level 1 permitted",
  41: "No parallel processes on level 2 permitted",
  42: "No parallel processes on level 3 permitted",
  50: "Dispensing drive initialization failed",
  51: "Dispensing drive not initialized",
  52: "Dispensing drive movement error",
  53: "Maximum volume in tip reached",
  54: "Dispensing drive position out of permitted area",
  55: "Y drive initialization failed",
  56: "Y drive not initialized",
  57: "Y drive movement error",
  58: "Y drive position out of permitted area",
  60: "Z drive initialization failed",
  61: "Z drive not initialized",
  62: "Z drive movement error",
  63: "Z drive position out of permitted area",
  65: "Squeezer drive initialization failed",
  66: "Squeezer drive not initialized",
  67: "Squeezer drive movement error",
  68: "Squeezer drive position out of permitted area",
  70: "No liquid level found",
  71: "Not enough liquid present",
  75: "No tip picked up",
  76: "Tip already picked up",
  81: "Clot detected with LLD sensor",
  82: "TADM measurement out of lower limit curve",
  83: "TADM measurement out of upper limit curve",
  84: "Not enough memory for TADM measurement",
  90: "Limit curve not resetable",
  91: "Limit curve not programmable",
  92: "Limit curve name not found",
  93: "Limit curve data incorrect",
  94: "Not enough memory for limit curve",
  95: "Not allowed limit curve index",
  96: "Limit curve already stored",
}

pip_errors = {
  22:	"Drive controller message error",
  23:	"EC drive controller setup not executed",
  25:	"wrong Flash EPROM data",
  26:	"Flash EPROM not programmable",
  27:	"Flash EPROM not erasable",
  28:	"Flash EPROM checksum error",
  29:	"wrong FW loaded",
  30:	"Undefined command",
  31:	"Undefined parameter",
  32:	"Parameter out of range",
  35:	"Voltages out of range",
  36:	"Stop during command execution",
  37:	"Adjustment sensor didn't switch (no teach in signal)",
  38:	"Movement interrupted by partner channel",
  39:	"Angle alignment offset error",
  40:	"No parallel processes on level 1 permitted",
  41:	"No parallel processes on level 2 permitted",
  42:	"No parallel processes on level 3 permitted",
  50:	"D drive initialization failed",
  51:	"D drive not initialized",
  52:	"D drive movement error",
  53:	"Maximum volume in tip reached",
  54:	"D drive position out of permitted area",
  55:	"Y drive initialization failed",
  56:	"Y drive not initialized",
  57:	"Y drive movement error",
  58:	"Y drive position out of permitted area",
  59:	"Divergance Y motion controller to linear encoder to heigh",
  60:	"Z drive initialization failed",
  61:	"Z drive not initialized",
  62:	"Z drive movement error",
  63:	"Z drive position out of permitted area",
  64:	"Limit stop not found",
  65:	"S drive initialization failed",
  66:	"S drive not initialized",
  67:	"S drive movement error",
  68:	"S drive position out of permitted area",
  69:	"Init. position adjustment error",
  70:	"No liquid level found",
  71:	"Not enough liquid present",
  74:	"Liquid at a not allowed position detected",
  75:	"No tip picked up",
  76:	"Tip already picked up",
  77:	"Tip not discarded",
  78:	"Wrong tip detected",
  79:	"Tip not correct squeezed",
  80:	"Liquid not correctly aspirated",
  81:	"Clot detected",
  82:	"TADM measurement out of lower limit curve",
  83:	"TADM measurement out of upper limit curve",
  84:	"Not enough memory for TADM measurement",
  85:	"Jet dispense pressure not reached",
  86:	"ADC algorithm error",
  90:	"Limit curve not resetable",
  91:	"Limit curve not programmable",
  92:	"Limit curve name not found",
  93:	"Limit curve data incorrect",
  94:	"Not enough memory for limit curve",
  95:	"Not allowed limit curve index",
  96:	"Limit curve already stored",
}

ipg_errors = {
  0: "No error",
  22:	"Drive controller message error",
  23:	"EC drive controller setup not executed",
  25:	"Wrong Flash EPROM data",
  26:	"Flash EPROM not programmable",
  27:	"Flash EPROM not erasable",
  28:	"Flash EPROM checksum error",
  29:	"Wrong FW loaded",
  30:	"Undefined command",
  31:	"Undefined parameter",
  32:	"Parameter out of range",
  35:	"Voltages out of range",
  36:	"Stop during command execution",
  37:	"Adjustment sensor didn't switch (no teach in signal)",
  39:	"Angle alignment offset error",
  40:	"No parallel processes on level 1 permitted",
  41:	"No parallel processes on level 2 permitted",
  42:	"No parallel processes on level 3 permitted",
  50:	"Y Drive initialization failed",
  51:	"Y Drive not initialized",
  52:	"Y Drive movement error",
  53:	"Y Drive position out of permitted area",
  54:	"Diff. motion controller and lin. encoder counter too high",
  55:	"Z Drive initialization failed",
  56:	"Z Drive not initialized",
  57:	"Z Drive movement error",
  58:	"Z Drive position out of permitted area",
  59:	"Z Drive limit stop not found",
  60:	"Rotation Drive initialization failed",
  61:	"Rotation Drive not initialized",
  62:	"Rotation Drive movement error",
  63:	"Rotation Drive position out of permitted area",
  65:	"Wrist Twist Drive initialization failed",
  66:	"Wrist Twist Drive not initialized",
  67:	"Wrist Twist Drive movement error",
  68:	"Wrist Twist Drive position out of permitted area",
  70:	"Gripper Drive initialization failed",
  71:	"Gripper Drive not initialized",
  72:	"Gripper Drive movement error",
  73:	"Gripper Drive position out of permitted area",
  80:	"Plate not found",
  81:	"Plate is still held",
  82:	"No plate is held",
}


class VantageFirmwareError(HamiltonFirmwareError):
  def __init__(self, errors, raw_response):
    self.errors = errors
    self.raw_response = raw_response

  def __str__(self):
    return f"VantageFirmwareError(errors={self.errors}, raw_response={self.raw_response})"

  def __eq__(self, __value: object) -> bool:
    return isinstance(__value, VantageFirmwareError) and \
      self.errors == __value.errors and \
      self.raw_response == __value.raw_response


def vantage_response_string_to_error(string: str) -> HamiltonFirmwareError:
  """ Convert a Vantage firmware response string to a HamiltonFirmwareError. Assumes that the
  response is an error response. """

  try:
    error_format = r"[A-Z0-9]{2}[0-9]{2}"
    error_string = parse_vantage_fw_string(string, {"es": "str"})["es"]
    error_codes = re.findall(error_format, error_string)
    errors = {}
    num_channels = 16
    for error in error_codes:
      module, error_code = error[:2], error[2:]
      error_code = int(error_code)
      for channel in range(1, num_channels + 1):
        if module == f"P{channel}":
          errors[f"Pipetting channel {channel}"] = pip_errors.get(error_code, "Unknown error")
        elif module in ("H0", "HM"):
          errors["Core 96"] = core96_errors.get(error_code, "Unknown error")
        elif module == "RM":
          errors["IPG"] = ipg_errors.get(error_code, "Unknown error")
        elif module == "AM":
          errors["Cover"] = "Unknown error"
  except ValueError:
    module_id = string[:4]
    module = modules = {
      "I1AM": "Cover",
      "C0AM": "Master",
      "A1PM": "Pip",
      "A1HM": "Core 96",
      "A1RM": "IPG",
    }.get(module_id, "Unknown module")
    error_string = parse_vantage_fw_string(string, {"et": "str"})["et"]
    errors = {modules: error_string}

  return VantageFirmwareError(errors, string)


class Vantage(HamiltonLiquidHandler):
  """ A Hamilton Vantage liquid handler. """

  def __init__(
    self,
    device_address: Optional[int] = None,
    packet_read_timeout: int = 3,
    read_timeout: int = 30,
    write_timeout: int = 30,
  ):
    """ Create a new STAR interface.

    Args:
      device_address: the USB device address of the Hamilton STAR. Only useful if using more than
        one Hamilton machine over USB.
      packet_read_timeout: timeout in seconds for reading a single packet.
      read_timeout: timeout in seconds for reading a full response.
      write_timeout: timeout in seconds for writing a command.
      num_channels: the number of pipette channels present on the robot.
    """

    super().__init__(
      device_address=device_address,
      packet_read_timeout=packet_read_timeout,
      read_timeout=read_timeout,
      write_timeout=write_timeout,
      id_product=0x8003)

    self._iswap_parked: Optional[bool] = None
    self._num_channels: Optional[int] = None

  @property
  def module_id_length(self) -> int:
    return  4

  def get_id_from_fw_response(self, resp: str) -> Optional[int]:
    """ Get the id from a firmware response. """
    parsed = parse_vantage_fw_string(resp, {"id": "int"})
    if "id" in parsed and parsed["id"] is not None:
      return int(parsed["id"])
    return None

  def check_fw_string_error(self, resp: str):
    """ Raise an error if the firmware response is an error response. """

    if "er" in resp and not "er0" in resp:
      error = vantage_response_string_to_error(resp)
      raise error

  async def setup(self):
    """ setup

    Creates a USB connection and finds read/write interfaces.
    """

    await super().setup()

    self._num_channels = 8 # TODO: query

    await self.pre_initialize_instrument()

    # TODO: check if already initialized
    await self.pip_initialize(
      x_position=[7095]*self.num_channels,
      y_position=[3891, 3623, 3355, 3087, 2819, 2551, 2283, 2016],
      begin_z_deposit_position=[2450] * self.num_channels,
      end_z_deposit_position=[1235] * self.num_channels,
      minimal_height_at_command_end=[2450] * self.num_channels,
      tip_pattern=[True]*self.num_channels,
      tip_type=[1]*self.num_channels,
      TODO_DI_2=70
    )

    await self.loading_cover_initialize()

    await self.core96_initialize(
      x_position=7347, # TODO: get trash location from deck.
      y_position=2684, # TODO: get trash location from deck.
      minimal_traverse_height_at_begin_of_command=2450,
      minimal_height_at_command_end=2450,
      end_z_deposit_position=2020,
    )

  @property
  def num_channels(self) -> int:
    """ The number of channels on the robot. """
    if self._num_channels is None:
      raise RuntimeError("num_channels is not set.")
    return self._num_channels

  # ============== LiquidHandlerBackend methods ==============

  async def pick_up_tips(self, ops: List[Pickup], use_channels: List[int]):
    x_positions, y_positions, tip_pattern = \
      self._ops_to_fw_positions(ops, use_channels)

    tips = [cast(HamiltonTip, op.resource.get_tip()) for op in ops]
    ttti = await self.get_ttti(tips)

    max_z = max(op.resource.get_absolute_location().z + \
                 (op.offset.z if op.offset is not None else 0) for op in ops)
    max_total_tip_length = max(op.tip.total_tip_length for op in ops)
    max_tip_length = max((op.tip.total_tip_length-op.tip.fitting_depth) for op in ops)

    # not sure why this is necessary, but it is according to log files and experiments
    if self._get_hamilton_tip([op.resource for op in ops]).tip_size == TipSize.LOW_VOLUME:
      max_tip_length += 2
    elif self._get_hamilton_tip([op.resource for op in ops]).tip_size != TipSize.STANDARD_VOLUME:
      max_tip_length -= 2

    try:
      return await self.pip_tip_pick_up(
        x_position=x_positions,
        y_position=y_positions,
        tip_pattern=tip_pattern,
        tip_type=ttti,
        begin_z_deposit_position=[int((max_z + max_total_tip_length)*10)]*len(ops),
        end_z_deposit_position=[int((max_z + max_tip_length)*10)]*len(ops),
        minimal_traverse_height_at_begin_of_command=[2450]*len(ops),
        minimal_height_at_command_end=[2450]*len(ops),
        tip_handling_method=[1 for _ in tips], # always appears to be 1 # tip.pickup_method.value
        blow_out_air_volume=[0]*len(ops), # Why is this here? Who knows.
      )
    except Exception as e:
      raise e

  # @need_iswap_parked
  async def drop_tips(
    self,
    ops: List[Drop],
    use_channels: List[int],
  ):
    """ Drop tips to a resource. """

    x_positions, y_positions, channels_involved = \
      self._ops_to_fw_positions(ops, use_channels)

    max_z = max(op.resource.get_absolute_location().z + \
                (op.offset.z if op.offset is not None else 0) for op in ops)

    try:
      return await self.pip_tip_discard(
        x_position=x_positions,
        y_position=y_positions,
        tip_pattern=channels_involved,
        begin_z_deposit_position=[int((max_z+10)*10)]*len(ops), # +10
        end_z_deposit_position=[int(max_z*10)]*len(ops),
        minimal_traverse_height_at_begin_of_command=[2450]*len(ops),
        minimal_height_at_command_end=[2450]*len(ops),
        tip_handling_method=[0 for _ in ops], # Always appears to be 0, even in trash.
        # tip_handling_method=[TipDropMethod.DROP.value if isinstance(op.resource, TipSpot) \
        #                      else TipDropMethod.PLACE_SHIFT.value for op in ops],
        TODO_TR_2=0,
      )
    except Exception as e:
      raise e

  def _assert_valid_resources(self, resources: Sequence[Resource]) -> None:
    """ Assert that resources are in a valid location for pipetting. """
    for resource in resources:
      if resource.get_absolute_location().z < 100:
        raise ValueError(
          f"Resource {resource} is too low: {resource.get_absolute_location().z} < 100")

  async def aspirate(
    self,
    ops: List[Aspiration],
    use_channels: List[int],
    type_of_aspiration: Optional[List[int]] = None,
    minimal_traverse_height_at_begin_of_command: Optional[List[int]] = None,
    minimal_height_at_command_end: Optional[List[int]] = None,
    lld_search_height: Optional[List[int]] = None,
    clot_detection_height: Optional[List[int]] = None,
    liquid_surface_at_function_without_lld: Optional[List[int]] = None,
    pull_out_distance_to_take_transport_air_in_function_without_lld: Optional[List[int]] = None,
    tube_2nd_section_height_measured_from_zm: Optional[List[int]] = None,
    tube_2nd_section_ratio: Optional[List[int]] = None,
    minimum_height: Optional[List[int]] = None,
    immersion_depth: Optional[List[int]] = None,
    surface_following_distance: Optional[List[int]] = None,
    transport_air_volume: Optional[List[int]] = None,
    pre_wetting_volume: Optional[List[int]] = None,
    lld_mode: Optional[List[int]] = None,
    lld_sensitivity: Optional[List[int]] = None,
    pressure_lld_sensitivity: Optional[List[int]] = None,
    aspirate_position_above_z_touch_off: Optional[List[int]] = None,
    swap_speed: Optional[List[int]] = None,
    settling_time: Optional[List[int]] = None,
    mix_volume: Optional[List[int]] = None,
    mix_cycles: Optional[List[int]] = None,
    mix_position_in_z_direction_from_liquid_surface: Optional[List[int]] = None,
    mix_speed: Optional[List[int]] = None,
    surface_following_distance_during_mixing: Optional[List[int]] = None,
    TODO_DA_5: Optional[List[int]] = None,
    capacitive_mad_supervision_on_off: Optional[List[int]] = None,
    pressure_mad_supervision_on_off: Optional[List[int]] = None,
    tadm_algorithm_on_off: int = 0,
    limit_curve_index: Optional[List[int]] = None,
    recording_mode: int = 0,
  ):
    """ Aspirate from (a) resource(s).

    See :meth:`pip_aspirate` (the firmware command) for parameter documentation. This method serves
    as a wrapper for that command, and will convert operations into the appropriate format. This
    method additionally provides default values based on firmware instructions sent by Venus on
    Vantage, rather than machine default values (which are often not what you want).

    Args:
      ops: The aspiration operations.
      use_channels: The channels to use.
    """

    x_positions, y_positions, channels_involved = \
      self._ops_to_fw_positions(ops, use_channels)

    hamilton_liquid_classes = [
      get_vantage_liquid_class(
        tip_volume=op.tip.maximal_volume,
        is_core=False,
        is_tip=True,
        has_filter=op.tip.has_filter,
        liquid=op.liquids[-1][0] or Liquid.WATER,
        jet=False, # for aspiration
        empty=False # for aspiration
      ) for op in ops]

    self._assert_valid_resources([op.resource for op in ops])

    # correct volumes using the liquid class
    for op, hlc in zip(ops, hamilton_liquid_classes):
      op.volume = hlc.compute_corrected_volume(op.volume) if hlc is not None else op.volume

    well_bottoms = [op.resource.get_absolute_location().z + \
                    (op.offset.z if op.offset is not None else 0) for op in ops]
    liquid_surfaces_no_lld = [wb + (op.liquid_height or 0)
                              for wb, op in zip(well_bottoms, ops)]
    # -1 compared to STAR?
    lld_search_heights = [wb + op.resource.get_size_z() + \
                          (2.7-1 if isinstance(op.resource, Well) else 5) #?
                          for wb, op in zip(well_bottoms, ops)]

    flow_rates = [
      op.flow_rate or (hlc.aspiration_flow_rate if hlc is not None else 100)
        for op, hlc in zip(ops, hamilton_liquid_classes)]

    return await self.pip_aspirate(
      x_position=x_positions,
      y_position=y_positions,
      type_of_aspiration=type_of_aspiration or [0]*len(ops),
      tip_pattern=channels_involved,
      minimal_traverse_height_at_begin_of_command=minimal_traverse_height_at_begin_of_command or
        [2450]*len(ops),
      minimal_height_at_command_end=minimal_height_at_command_end or [2450]*len(ops),
      lld_search_height=lld_search_height or [int(ls*10) for ls in lld_search_heights],
      clot_detection_height=clot_detection_height or [0]*len(ops),
      liquid_surface_at_function_without_lld=liquid_surface_at_function_without_lld or
        [int(lsn * 10) for lsn in liquid_surfaces_no_lld],
      pull_out_distance_to_take_transport_air_in_function_without_lld=\
        pull_out_distance_to_take_transport_air_in_function_without_lld or [109]*len(ops),
      tube_2nd_section_height_measured_from_zm=tube_2nd_section_height_measured_from_zm or
        [0]*len(ops),
      tube_2nd_section_ratio=tube_2nd_section_ratio or [0]*len(ops),
      minimum_height=minimum_height or [1871]*len(ops),
      immersion_depth=immersion_depth or [0]*len(ops),
      surface_following_distance=surface_following_distance or [0]*len(ops),
      aspiration_volume=[int(op.volume*100) for op in ops],
      aspiration_speed=[int(fr * 10) for fr in flow_rates],
      transport_air_volume=transport_air_volume or
        [int(hlc.aspiration_air_transport_volume*10) if hlc is not None else 0
          for hlc in hamilton_liquid_classes],
      blow_out_air_volume=[int(op.blow_out_air_volume*100) for op in ops],
      pre_wetting_volume=pre_wetting_volume or [0]*len(ops),
      lld_mode=lld_mode or [0]*len(ops),
      lld_sensitivity=lld_sensitivity or [4]*len(ops),
      pressure_lld_sensitivity=pressure_lld_sensitivity or [4]*len(ops),
      aspirate_position_above_z_touch_off=aspirate_position_above_z_touch_off or [5]*len(ops),
      swap_speed=swap_speed or [20]*len(ops),
      settling_time=settling_time or [10]*len(ops),
      mix_volume=mix_volume or [0]*len(ops),
      mix_cycles=mix_cycles or [0]*len(ops),
      mix_position_in_z_direction_from_liquid_surface=
        mix_position_in_z_direction_from_liquid_surface or [0]*len(ops),
      mix_speed=mix_speed or [2500]*len(ops),
      surface_following_distance_during_mixing=surface_following_distance_during_mixing or
        [0]*len(ops),
      TODO_DA_5=TODO_DA_5 or [0]*len(ops),
      capacitive_mad_supervision_on_off=capacitive_mad_supervision_on_off or [0]*len(ops),
      pressure_mad_supervision_on_off=pressure_mad_supervision_on_off or [0]*len(ops),
      tadm_algorithm_on_off=tadm_algorithm_on_off or 0,
      limit_curve_index=limit_curve_index or [0]*len(ops),
      recording_mode=recording_mode or 0,
    )

  async def dispense(
    self,
    ops: List[Dispense],
    use_channels: List[int],
    jet: Optional[List[bool]] = None,
    empty: Optional[List[bool]] = None,
    type_of_dispensing_mode: Optional[List[int]] = None,
    minimum_height: Optional[List[int]] = None,
    pull_out_distance_to_take_transport_air_in_function_without_lld: Optional[List[int]] = None,
    immersion_depth: Optional[List[int]] = None,
    surface_following_distance: Optional[List[int]] = None,
    tube_2nd_section_height_measured_from_zm: Optional[List[int]] = None,
    tube_2nd_section_ratio: Optional[List[int]] = None,
    minimal_traverse_height_at_begin_of_command: Optional[List[int]] = None,
    minimal_height_at_command_end: Optional[List[int]] = None,
    cut_off_speed: Optional[List[int]] = None,
    stop_back_volume: Optional[List[int]] = None,
    transport_air_volume: Optional[List[int]] = None,
    lld_mode: Optional[List[int]] = None,
    side_touch_off_distance: int = 0,
    dispense_position_above_z_touch_off: Optional[List[int]] = None,
    lld_sensitivity: Optional[List[int]] = None,
    pressure_lld_sensitivity: Optional[List[int]] = None,
    swap_speed: Optional[List[int]] = None,
    settling_time: Optional[List[int]] = None,
    mix_volume: Optional[List[int]] = None,
    mix_cycles: Optional[List[int]] = None,
    mix_position_in_z_direction_from_liquid_surface: Optional[List[int]] = None,
    mix_speed: Optional[List[int]] = None,
    surface_following_distance_during_mixing: Optional[List[int]] = None,
    TODO_DD_2: Optional[List[int]] = None,
    tadm_algorithm_on_off: int = 0,
    limit_curve_index: Optional[List[int]] = None,
    recording_mode: int = 0,
  ):
    """ Dispense to (a) resource(s).

    See :meth:`pip_dispense` (the firmware command) for parameter documentation. This method serves
    as a wrapper for that command, and will convert operations into the appropriate format. This
    method additionally provides default values based on firmware instructions sent by Venus on
    Vantage, rather than machine default values (which are often not what you want).

    Args:
      ops: The aspiration operations.
      use_channels: The channels to use.
      jet: Whether to jet. If `True`, jet dispense will be used. If `False`, surface dispense will
        be used. If `None`, dispense will be jet if the liquid_height for an operation is greater
        than 0, or if the tip is empty. Otherwise, surface dispense will be used.
    """

    x_positions, y_positions, channels_involved = \
      self._ops_to_fw_positions(ops, use_channels)

    def should_jet(op):
      if op.liquid_height is not None and op.liquid_height > 0:
        return True
      if hasattr(op.resource, "tracker") and op.resource.tracker.get_used_volume() == 0:
        return True
      return False

    def should_empty(op):
      return op.tip.tracker.get_used_volume() == 0

    if jet is None:
      jet = [should_jet(op) for op in ops]
    if empty is None:
      empty = [should_empty(op) for op in ops]

    hamilton_liquid_classes = [
      get_vantage_liquid_class(
        tip_volume=op.tip.maximal_volume,
        is_core=False,
        is_tip=True,
        has_filter=op.tip.has_filter,
        liquid=op.liquids[-1][0] or Liquid.WATER,
        jet=jet,
        empty=empty
      ) for jet, empty, op in zip(jet, empty, ops)]
    self._assert_valid_resources([op.resource for op in ops])

    # correct volumes using the liquid class
    for op, hlc in zip(ops, hamilton_liquid_classes):
      op.volume = hlc.compute_corrected_volume(op.volume) if hlc is not None else op.volume

    well_bottoms = [op.resource.get_absolute_location().z + \
                    (op.offset.z if op.offset is not None else 0) for op in ops]
    liquid_surfaces_no_lld = [wb + (op.liquid_height or 0)
                              for wb, op in zip(well_bottoms, ops)]
    # -1 compared to STAR?
    lld_search_heights = [wb + op.resource.get_size_z() + \
                          (2.7-1 if isinstance(op.resource, Well) else 5) #?
                          for wb, op in zip(well_bottoms, ops)]


    flow_rates = [
      op.flow_rate or (hlc.dispense_flow_rate if hlc is not None else 100)
        for op, hlc in zip(ops, hamilton_liquid_classes)]

    return await self.pip_dispense(
      x_position=x_positions,
      y_position=y_positions,
      tip_pattern=channels_involved,
      type_of_dispensing_mode=type_of_dispensing_mode or [1]*len(ops),
      minimum_height=minimum_height or [int(wb*10) for wb in well_bottoms],
      lld_search_height=[int(sh*10) for sh in lld_search_heights],
      liquid_surface_at_function_without_lld=[int(ls*10) for ls in liquid_surfaces_no_lld],
      pull_out_distance_to_take_transport_air_in_function_without_lld=
        pull_out_distance_to_take_transport_air_in_function_without_lld or [50]*len(ops),
      immersion_depth=immersion_depth or [0]*len(ops),
      surface_following_distance=surface_following_distance or [21]*len(ops),
      tube_2nd_section_height_measured_from_zm=tube_2nd_section_height_measured_from_zm or
        [0]*len(ops),
      tube_2nd_section_ratio=tube_2nd_section_ratio or [0]*len(ops),
      minimal_traverse_height_at_begin_of_command=minimal_traverse_height_at_begin_of_command or
        [2450]*len(ops),
      minimal_height_at_command_end=minimal_height_at_command_end or [2450]*len(ops),
      dispense_volume=[int(op.volume * 100) for op in ops],
      dispense_speed=[int(fr*10) for fr in flow_rates],
      cut_off_speed=cut_off_speed or [2500]*len(ops),
      stop_back_volume=stop_back_volume or [0]*len(ops),
      transport_air_volume=transport_air_volume or
        [int(hlc.dispense_air_transport_volume*10) if hlc is not None else 0
        for hlc in hamilton_liquid_classes],
      blow_out_air_volume=[int(op.blow_out_air_volume*100) for op in ops],
      lld_mode=lld_mode or [0]*len(ops),
      side_touch_off_distance=side_touch_off_distance or 0,
      dispense_position_above_z_touch_off=dispense_position_above_z_touch_off or [5]*len(ops),
      lld_sensitivity=lld_sensitivity or [1]*len(ops),
      pressure_lld_sensitivity=pressure_lld_sensitivity or [1]*len(ops),
      swap_speed=swap_speed or [10]*len(ops),
      settling_time=settling_time or [0]*len(ops),
      mix_volume=mix_volume or [0]*len(ops),
      mix_cycles=mix_cycles or [0]*len(ops),
      mix_position_in_z_direction_from_liquid_surface=
        mix_position_in_z_direction_from_liquid_surface or [0]*len(ops),
      mix_speed=mix_speed or [10]*len(ops),
      surface_following_distance_during_mixing=surface_following_distance_during_mixing or
        [0]*len(ops),
      TODO_DD_2=TODO_DD_2 or [0]*len(ops),
      tadm_algorithm_on_off=tadm_algorithm_on_off or 0,
      limit_curve_index=limit_curve_index or [0]*len(ops),
      recording_mode=recording_mode or 0,
    )

  async def pick_up_tips96(
    self,
    pickup: PickupTipRack,
    tip_handling_method: int = 0,
    z_deposit_position: int = 2164,
    minimal_traverse_height_at_begin_of_command: int = 2450,
    minimal_height_at_command_end: int = 2450,
  ):
    # assert self.core96_head_installed, "96 head must be installed"
    tip_spot_a1 = pickup.resource.get_item("A1")
    tip_a1 = tip_spot_a1.get_tip()
    assert isinstance(tip_a1, HamiltonTip), "Tip type must be HamiltonTip."
    ttti = await self.get_or_assign_tip_type_index(tip_a1)
    position = tip_spot_a1.get_absolute_location() + tip_spot_a1.center() + pickup.offset

    return await self.core96_tip_pick_up(
      x_position=int(position.x * 10),
      y_position=int(position.y * 10),
      tip_type=ttti,
      tip_handling_method=tip_handling_method,
      z_deposit_position=z_deposit_position,
      minimal_traverse_height_at_begin_of_command=minimal_traverse_height_at_begin_of_command,
      minimal_height_at_command_end=minimal_height_at_command_end,
    )

  async def drop_tips96(
    self,
    drop: DropTipRack,
    z_deposit_position: int = 2164,
    minimal_traverse_height_at_begin_of_command: int = 2450,
    minimal_height_at_command_end: int = 2450
  ):
    # assert self.core96_head_installed, "96 head must be installed"
    tip_spot_a1 = drop.resource.get_item("A1")
    position = tip_spot_a1.get_absolute_location() + tip_spot_a1.center() + drop.offset

    return await self.core96_tip_discard(
      x_position=int(position.x * 10),
      y_position=int(position.y * 10),
      z_deposit_position=z_deposit_position,
      minimal_traverse_height_at_begin_of_command=minimal_traverse_height_at_begin_of_command,
      minimal_height_at_command_end=minimal_height_at_command_end,
    )

  async def aspirate96(
    self,
    aspiration: AspirationPlate,
    jet: bool = True,
    empty: bool = True,
    type_of_aspiration: int = 0,
    minimal_traverse_height_at_begin_of_command: int = 2450,
    minimal_height_at_command_end: int = 2450,
    pull_out_distance_to_take_transport_air_in_function_without_lld: int = 50,
    tube_2nd_section_height_measured_from_zm: int = 0,
    tube_2nd_section_ratio: int = 0,
    immersion_depth: int = 0,
    surface_following_distance: int = 0,
    transport_air_volume: Optional[int] = None,
    blow_out_air_volume: Optional[int] = None,
    pre_wetting_volume: int = 0,
    lld_mode: int = 0,
    lld_sensitivity: int = 4,
    swap_speed: Optional[int] = None,
    settling_time: Optional[int] = None,
    mix_volume: int = 0,
    mix_cycles: int = 0,
    mix_position_in_z_direction_from_liquid_surface: int = 0,
    surface_following_distance_during_mixing: int = 0,
    mix_speed: int = 2000,
    limit_curve_index: int = 0,
    tadm_channel_pattern: Optional[List[bool]] = None,
    tadm_algorithm_on_off: int = 0,
    recording_mode: int = 0,
  ):
    # assert self.core96_head_installed, "96 head must be installed"

    assert isinstance(aspiration.resource, Plate), "Only Plate is supported."
    well_a1 = aspiration.resource.get_item("A1")
    position = well_a1.get_absolute_location() + well_a1.center()

    liquid_height = well_a1.get_absolute_location().z + (aspiration.liquid_height or 0)

    well_bottoms = well_a1.get_absolute_location().z + \
      (aspiration.offset.z if aspiration.offset is not None else 0)

    tip = aspiration.tips[0]
    hlc = get_vantage_liquid_class(
      tip_volume=tip.maximal_volume,
      is_core=True,
      is_tip=True,
      has_filter=tip.has_filter,
      # first part of tuple in last liquid of first well
      liquid=aspiration.liquids[0][-1][0] or Liquid.WATER,
      jet=jet,
      empty=empty
    )
    volume = hlc.compute_corrected_volume(aspiration.volume) if hlc is not None \
      else aspiration.volume

    # -1 compared to STAR?
    lld_search_height = well_bottoms + well_a1.get_size_z() + 2.7-1

    transport_air_volume = transport_air_volume or \
      (int(hlc.aspiration_air_transport_volume*10) if hlc is not None else 0)
    blow_out_air_volume = blow_out_air_volume or \
      (int(hlc.aspiration_blow_out_volume * 100) if hlc is not None else 0)
    flow_rate = aspiration.flow_rate or (hlc.aspiration_flow_rate if hlc is not None else 250)
    swap_speed = swap_speed or (int(hlc.aspiration_swap_speed*10) if hlc is not None else 100)
    settling_time = settling_time or \
      (int(hlc.aspiration_settling_time*10) if hlc is not None else 5)

    return await self.core96_aspiration_of_liquid(
      x_position=int(position.x * 10),
      y_position=int(position.y * 10),
      type_of_aspiration=type_of_aspiration,
      minimal_traverse_height_at_begin_of_command=minimal_traverse_height_at_begin_of_command,
      minimal_height_at_command_end=minimal_height_at_command_end,
      lld_search_height=int(lld_search_height * 10),
      liquid_surface_at_function_without_lld=int(liquid_height * 10),
      pull_out_distance_to_take_transport_air_in_function_without_lld=\
        pull_out_distance_to_take_transport_air_in_function_without_lld,
      minimum_height=int(well_bottoms * 10),
      tube_2nd_section_height_measured_from_zm=tube_2nd_section_height_measured_from_zm,
      tube_2nd_section_ratio=tube_2nd_section_ratio,
      immersion_depth=immersion_depth,
      surface_following_distance=surface_following_distance,
      aspiration_volume=int(volume * 100),
      aspiration_speed=int(flow_rate * 10),
      transport_air_volume=transport_air_volume,
      blow_out_air_volume=blow_out_air_volume,
      pre_wetting_volume=pre_wetting_volume,
      lld_mode=lld_mode,
      lld_sensitivity=lld_sensitivity,
      swap_speed=swap_speed,
      settling_time=settling_time,
      mix_volume=mix_volume,
      mix_cycles=mix_cycles,
      mix_position_in_z_direction_from_liquid_surface=\
        mix_position_in_z_direction_from_liquid_surface,
      surface_following_distance_during_mixing=surface_following_distance_during_mixing,
      mix_speed=mix_speed,
      limit_curve_index=limit_curve_index,
      tadm_channel_pattern=tadm_channel_pattern,
      tadm_algorithm_on_off=tadm_algorithm_on_off,
      recording_mode=recording_mode,
    )

  async def dispense96(
    self,
    dispense: DispensePlate,
    jet: Optional[bool] = None,
    empty: Optional[bool] = None,
    type_of_dispensing_mode: int = 0,
    tube_2nd_section_height_measured_from_zm: int = 0,
    tube_2nd_section_ratio: int = 0,
    pull_out_distance_to_take_transport_air_in_function_without_lld: int = 50,
    immersion_depth: int = 0,
    surface_following_distance: int = 29,
    minimal_traverse_height_at_begin_of_command: int = 2450,
    minimal_height_at_command_end: int = 2450,
    cut_off_speed: int = 2500,
    stop_back_volume: int = 0,
    transport_air_volume: Optional[int] = None,
    blow_out_air_volume: Optional[int] = None,
    lld_mode: int = 0,
    lld_sensitivity: int = 4,
    side_touch_off_distance: int = 0,
    swap_speed: Optional[int] = None,
    settling_time: Optional[int] = None,
    mix_volume: int = 0,
    mix_cycles: int = 0,
    mix_position_in_z_direction_from_liquid_surface: int = 0,
    surface_following_distance_during_mixing: int = 0,
    mix_speed: Optional[int] = None,
    limit_curve_index: int = 0,
    tadm_channel_pattern: Optional[List[bool]] = None,
    tadm_algorithm_on_off: int = 0,
    recording_mode: int = 0,
  ):
    assert isinstance(dispense.resource, Plate), "Only Plate is supported."
    well_a1 = dispense.resource.get_item("A1")
    position = well_a1.get_absolute_location() + well_a1.center()

    liquid_height = well_a1.get_absolute_location().z + (dispense.liquid_height or 0) + \
      (dispense.offset.z if dispense.offset is not None else 0) + 10 # +10?

    well_bottoms = well_a1.get_absolute_location().z + \
      (dispense.offset.z if dispense.offset is not None else 0)

    if jet is None:
      jet = dispense.liquid_height is None or dispense.liquid_height > 0
    if empty is None:
      empty = all(tip.tracker.get_used_volume() == 0 for tip in dispense.tips)

    tip = dispense.tips[0]
    hlc = get_vantage_liquid_class(
      tip_volume=tip.maximal_volume,
      is_core=True,
      is_tip=True,
      has_filter=tip.has_filter,
      # first part of tuple in last liquid of first well
      liquid=dispense.liquids[0][-1][0] or Liquid.WATER,
      jet=jet,
      empty=empty
    )
    volume = hlc.compute_corrected_volume(dispense.volume) if hlc is not None \
      else dispense.volume

    # -1 compared to STAR?
    lld_search_height = well_bottoms + well_a1.get_size_z() + 2.7-1

    transport_air_volume = transport_air_volume or \
      (int(hlc.dispense_air_transport_volume*10) if hlc is not None else 0)
    blow_out_air_volume = blow_out_air_volume or \
      (int(hlc.dispense_blow_out_volume * 100) if hlc is not None else 0)
    flow_rate = dispense.flow_rate or (hlc.dispense_flow_rate if hlc is not None else 250)
    swap_speed = swap_speed or (int(hlc.dispense_swap_speed*10) if hlc is not None else 100)
    settling_time = settling_time or \
      (int(hlc.dispense_settling_time*10) if hlc is not None else 5)
    mix_speed = mix_speed or (int(hlc.dispense_mix_flow_rate*10) if hlc is not None else 100)

    return await self.core96_dispensing_of_liquid(
      x_position=int(position.x * 10),
      y_position=int(position.y * 10),
      type_of_dispensing_mode=type_of_dispensing_mode,
      minimum_height=int(well_bottoms * 10),
      tube_2nd_section_height_measured_from_zm=tube_2nd_section_height_measured_from_zm,
      tube_2nd_section_ratio=tube_2nd_section_ratio,
      lld_search_height=int(lld_search_height * 10),
      liquid_surface_at_function_without_lld=int(liquid_height * 10),
      pull_out_distance_to_take_transport_air_in_function_without_lld=\
        pull_out_distance_to_take_transport_air_in_function_without_lld,
      immersion_depth=immersion_depth,
      surface_following_distance=surface_following_distance,
      minimal_traverse_height_at_begin_of_command=minimal_traverse_height_at_begin_of_command,
      minimal_height_at_command_end=minimal_height_at_command_end,
      dispense_volume=int(volume * 100),
      dispense_speed=int(flow_rate * 10),
      cut_off_speed=cut_off_speed,
      stop_back_volume=stop_back_volume,
      transport_air_volume=transport_air_volume,
      blow_out_air_volume=blow_out_air_volume,
      lld_mode=lld_mode,
      lld_sensitivity=lld_sensitivity,
      side_touch_off_distance=side_touch_off_distance,
      swap_speed=swap_speed,
      settling_time=settling_time,
      mix_volume=mix_volume,
      mix_cycles=mix_cycles,
      mix_position_in_z_direction_from_liquid_surface=\
        mix_position_in_z_direction_from_liquid_surface,
      surface_following_distance_during_mixing=surface_following_distance_during_mixing,
      mix_speed=mix_speed,
      limit_curve_index=limit_curve_index,
      tadm_channel_pattern=tadm_channel_pattern,
      tadm_algorithm_on_off=tadm_algorithm_on_off,
      recording_mode=recording_mode,
    )

  async def move_resource(self, move: Move):
    await self.pick_up_resource(
      resource=move.resource,
      offset=move.resource_offset,
      pickup_distance_from_top=move.pickup_distance_from_top)

    await self.release_picked_up_resource(
      resource=move.resource,
      destination=move.destination,
      offset=move.destination_offset,
      pickup_distance_from_top=move.pickup_distance_from_top)

  async def pick_up_resource(
    self,
    resource: Resource,
    offset: Coordinate,
    pickup_distance_from_top: float,
    grip_strength: int = 81,
    plate_width_tolerance: int = 20,
    acceleration_index: int = 4,
    z_clearance_height: int = 0,
    hotel_depth: int = 0,
    minimal_height_at_command_end: int = 2840,
  ):
    """ Pick up a resource with the IPG. You probably want to use :meth:`move_resource`, which
    allows you to pick up and move a resource with a single command. """

    center = resource.get_absolute_location() + resource.center() + offset
    grip_height = center.z + resource.get_size_z() - pickup_distance_from_top
    plate_width = resource.get_size_x()

    await self.ipg_grip_plate(
      x_position=int(center.x * 10),
      y_position=int(center.y * 10),
      z_position=int(grip_height * 10),
      grip_strength=grip_strength,
      open_gripper_position=int(plate_width*10) + 32,
      plate_width=int(plate_width * 10) - 33,
      plate_width_tolerance=plate_width_tolerance,
      acceleration_index=acceleration_index,
      z_clearance_height=z_clearance_height,
      hotel_depth=hotel_depth,
      minimal_height_at_command_end=minimal_height_at_command_end,
    )

  async def move_picked_up_resource(self):
    """ Move a resource picked up with the IPG. See :meth:`pick_up_resource`.

    You probably want to use :meth:`move_resource`, which allows you to pick up and move a resource
    with a single command.
    """

    raise NotImplementedError()

  async def release_picked_up_resource(
    self,
    resource: Resource,
    destination: Coordinate,
    offset: Coordinate,
    pickup_distance_from_top: float,
    z_clearance_height: int = 0,
    press_on_distance: int = 5,
    hotel_depth: int = 0,
    minimal_height_at_command_end: int = 2840
  ):
    """ Release a resource picked up with the IPG. See :meth:`pick_up_resource`.

    You probably want to use :meth:`move_resource`, which allows you to pick up and move a resource
    with a single command.
    """

    center = destination + resource.center() + offset
    grip_height = center.z + resource.get_size_z() - pickup_distance_from_top
    plate_width = resource.get_size_x()

    await self.ipg_put_plate(
      x_position=int(center.x * 10),
      y_position=int(center.y * 10),
      z_position=int(grip_height * 10),
      z_clearance_height=z_clearance_height,
      open_gripper_position=int(plate_width*10) + 32,
      press_on_distance=press_on_distance,
      hotel_depth=hotel_depth,
      minimal_height_at_command_end=minimal_height_at_command_end
    )

  # ============== Firmware Commands ==============

  async def set_led_color(
    self,
    mode: Union[Literal["on"], Literal["off"], Literal["blink"]],
    intensity: int,
    white: int,
    red: int,
    green: int,
    blue: int,
    uv: int,
    blink_interval: Optional[int] = None,
  ):
    """ Set the LED color.

    Args:
      mode: The mode of the LED. One of "on", "off", or "blink".
      intensity: The intensity of the LED. 0-100.
      white: The white color of the LED. 0-100.
      red: The red color of the LED. 0-100.
      green: The green color of the LED. 0-100.
      blue: The blue color of the LED. 0-100.
      uv: The UV color of the LED. 0-100.
      blink_interval: The blink interval in ms. Only used if mode is "blink".
    """

    if blink_interval is not None:
      if mode != "blink":
        raise ValueError("blink_interval is only used when mode is 'blink'.")

    return await self.send_command(
      module="C0AM",
      command="LI",
      li={
        "on": 1,
        "off": 0,
        "blink": 2,
      }[mode],
      os=intensity,
      ok=blink_interval or 750, # default non zero value
      ol=f"{white} {red} {green} {blue} {uv}",
    )

  async def set_loading_cover(self, cover_open: bool):
    """ Set the loading cover.

    Args:
      cover_open: Whether the cover should be open or closed.
    """

    return await self.send_command(
      module="I1AM",
      command="LP",
      lc=not cover_open
    )

  def loading_cover_initialize(self):
    """ Initialize the loading cover. """

    return self.send_command(
      module="I1AM",
      command="MI",
    )

  async def pre_initialize_instrument(self):
    """ Initialize the main instrument. """

    return await self.send_command(module="A1AM", command="MI")

  async def pip_initialize(
    self,
    x_position: List[int],
    y_position: List[int],
    begin_z_deposit_position: Optional[List[int]] = None,
    end_z_deposit_position: Optional[List[int]] = None,
    minimal_height_at_command_end: Optional[List[int]] = None,
    tip_pattern: Optional[List[bool]] = None,
    tip_type: Optional[List[int]] = None,
    TODO_DI_2: int = 0,
  ):
    """ Initialize

    Args:
      x_position: X Position [0.1mm].
      y_position: Y Position [0.1mm].
      begin_z_deposit_position: Begin of tip deposit process (Z- discard range) [0.1mm] ??
      end_z_deposit_position: Z deposit position [0.1mm] (collar bearing position).
      minimal_height_at_command_end: Minimal height at command end [0.1mm].
      tip_pattern: Tip pattern (channels involved). [0 = not involved, 1 = involved].
      tip_type: Tip type (see command TT).
      TODO_DI_2: Unknown.
    """

    if not all(0 <= x <= 50000 for x in x_position):
      raise ValueError("x_position must be in range 0 to 50000")

    if y_position is None:
      y_position = [3000] * self.num_channels
    elif not all(0 <= x <= 6500 for x in y_position):
      raise ValueError("y_position must be in range 0 to 6500")

    if begin_z_deposit_position is None:
      begin_z_deposit_position = [0] * self.num_channels
    elif not all(0 <= x <= 3600 for x in begin_z_deposit_position):
      raise ValueError("begin_z_deposit_position must be in range 0 to 3600")

    if end_z_deposit_position is None:
      end_z_deposit_position = [0] * self.num_channels
    elif not all(0 <= x <= 3600 for x in end_z_deposit_position):
      raise ValueError("end_z_deposit_position must be in range 0 to 3600")

    if minimal_height_at_command_end is None:
      minimal_height_at_command_end = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in minimal_height_at_command_end):
      raise ValueError("minimal_height_at_command_end must be in range 0 to 3600")

    if tip_pattern is None:
      tip_pattern = [False] * self.num_channels
    elif not all(0 <= x <= 1 for x in tip_pattern):
      raise ValueError("tip_pattern must be in range 0 to 1")

    if tip_type is None:
      tip_type = [4] * self.num_channels
    elif not all(0 <= x <= 199 for x in tip_type):
      raise ValueError("tip_type must be in range 0 to 199")

    if not -1000 <= TODO_DI_2 <= 1000:
      raise ValueError("TODO_DI_2 must be in range -1000 to 1000")

    return await self.send_command(
      module="A1PM",
      command="DI",
      xp=x_position,
      yp=y_position,
      tp=begin_z_deposit_position,
      tz=end_z_deposit_position,
      te=minimal_height_at_command_end,
      tm=tip_pattern,
      tt=tip_type,
      ts=TODO_DI_2,
    )

  async def define_tip_needle(
    self,
    tip_type_table_index: int,
    has_filter: bool,
    tip_length: int,
    maximum_tip_volume: int,
    tip_size: TipSize,
    pickup_method: TipPickupMethod
  ):
    """ Tip/needle definition.

    Args:
      tip_type_table_index: tip_table_index
      filter: with(out) filter
      tip_length: Tip length [0.1mm]
      maximum_tip_volume: Maximum volume of tip [0.1ul] Note! it's automatically limited to max.
        channel capacity
      tip_type: Type of tip collar (Tip type identification)
      pickup_method: pick up method.  Attention! The values set here are temporary and apply only
        until power OFF or RESET. After power ON the default values apply. (see Table 3)
    """

    if not 0 <= tip_type_table_index <= 99:
      raise ValueError("tip_type_table_index must be between 0 and 99, but is "
                       f"{tip_type_table_index}")
    if not 0 <= tip_type_table_index <= 99:
      raise ValueError("tip_type_table_index must be between 0 and 99, but is "
                       f"{tip_type_table_index}")
    if not 1 <= tip_length <= 1999:
      raise ValueError("tip_length must be between 1 and 1999, but is "
                       f"{tip_length}")
    if not 1 <= maximum_tip_volume <= 56000:
      raise ValueError("maximum_tip_volume must be between 1 and 56000, but is "
                       f"{maximum_tip_volume}")

    return await self.send_command(
      module="A1AM",
      command="TT",
      ti=f"{tip_type_table_index:02}",
      tf=has_filter,
      tl=f"{tip_length:04}",
      tv=f"{maximum_tip_volume:05}",
      tg=tip_size.value,
      tu=pickup_method.value
    )

  async def pip_aspirate(
    self,
    x_position: List[int],
    y_position: List[int],
    type_of_aspiration: Optional[List[int]] = None,
    tip_pattern: Optional[List[bool]] = None,
    minimal_traverse_height_at_begin_of_command: Optional[List[int]] = None,
    minimal_height_at_command_end: Optional[List[int]] = None,
    lld_search_height: Optional[List[int]] = None,
    clot_detection_height: Optional[List[int]] = None,
    liquid_surface_at_function_without_lld: Optional[List[int]] = None,
    pull_out_distance_to_take_transport_air_in_function_without_lld: Optional[List[int]] = None,
    tube_2nd_section_height_measured_from_zm: Optional[List[int]] = None,
    tube_2nd_section_ratio: Optional[List[int]] = None,
    minimum_height: Optional[List[int]] = None,
    immersion_depth: Optional[List[int]] = None,
    surface_following_distance: Optional[List[int]] = None,
    aspiration_volume: Optional[List[int]] = None,
    TODO_DA_2: Optional[List[int]] = None,
    aspiration_speed: Optional[List[int]] = None,
    transport_air_volume: Optional[List[int]] = None,
    blow_out_air_volume: Optional[List[int]] = None,
    pre_wetting_volume: Optional[List[int]] = None,
    lld_mode: Optional[List[int]] = None,
    lld_sensitivity: Optional[List[int]] = None,
    pressure_lld_sensitivity: Optional[List[int]] = None,
    aspirate_position_above_z_touch_off: Optional[List[int]] = None,
    TODO_DA_4: Optional[List[int]] = None,
    swap_speed: Optional[List[int]] = None,
    settling_time: Optional[List[int]] = None,
    mix_volume: Optional[List[int]] = None,
    mix_cycles: Optional[List[int]] = None,
    mix_position_in_z_direction_from_liquid_surface: Optional[List[int]] = None,
    mix_speed: Optional[List[int]] = None,
    surface_following_distance_during_mixing: Optional[List[int]] = None,
    TODO_DA_5: Optional[List[int]] = None,
    capacitive_mad_supervision_on_off: Optional[List[int]] = None,
    pressure_mad_supervision_on_off: Optional[List[int]] = None,
    tadm_algorithm_on_off: int = 0,
    limit_curve_index: Optional[List[int]] = None,
    recording_mode: int = 0,
  ):
    """ Aspiration of liquid

    Args:
      type_of_aspiration: Type of aspiration (0 = simple 1 = sequence 2 = cup emptied).
      tip_pattern: Tip pattern (channels involved). [0 = not involved, 1 = involved].
      x_position: X Position [0.1mm].
      y_position: Y Position [0.1mm].
      minimal_traverse_height_at_begin_of_command: Minimal traverse height at begin of command
        [0.1mm].
      minimal_height_at_command_end: Minimal height at command end [0.1mm].
      lld_search_height: LLD search height [0.1mm].
      clot_detection_height: (0).
      liquid_surface_at_function_without_lld: Liquid surface at function without LLD [0.1mm].
      pull_out_distance_to_take_transport_air_in_function_without_lld:
          Pull out distance to take transp. air in function without LLD [0.1mm].
      tube_2nd_section_height_measured_from_zm: Tube 2nd section height measured from zm [0.1mm].
      tube_2nd_section_ratio: Tube 2nd section ratio.
      minimum_height: Minimum height (maximum immersion depth) [0.1mm].
      immersion_depth: Immersion depth [0.1mm].
      surface_following_distance: Surface following distance [0.1mm].
      aspiration_volume: Aspiration volume [0.01ul].
      TODO_DA_2: (0).
      aspiration_speed: Aspiration speed [0.1ul]/s.
      transport_air_volume: Transport air volume [0.1ul].
      blow_out_air_volume: Blow out air volume [0.01ul].
      pre_wetting_volume: Pre wetting volume [0.1ul].
      lld_mode: LLD Mode (0 = off).
      lld_sensitivity: LLD sensitivity (1 = high, 4 = low).
      pressure_lld_sensitivity: Pressure LLD sensitivity (1= high, 4=low).
      aspirate_position_above_z_touch_off: (0).
      TODO_DA_4: (0).
      swap_speed: Swap speed (on leaving liquid) [0.1mm/s].
      settling_time: Settling time [0.1s].
      mix_volume: Mix volume [0.1ul].
      mix_cycles: Mix cycles.
      mix_position_in_z_direction_from_liquid_surface: Mix position in Z direction from liquid
        surface[0.1mm].
      mix_speed: Mix speed [0.1ul/s].
      surface_following_distance_during_mixing: Surface following distance during mixing [0.1mm].
      TODO_DA_5: (0).
      capacitive_mad_supervision_on_off: Capacitive MAD supervision on/off (0 = OFF).
      pressure_mad_supervision_on_off: Pressure MAD supervision on/off (0 = OFF).
      tadm_algorithm_on_off: TADM algorithm on/off (0 = off).
      limit_curve_index: Limit curve index.
      recording_mode: Recording mode (0 = no 1 = TADM errors only 2 = all TADM measurements).
    """

    if type_of_aspiration is None:
      type_of_aspiration = [0] * self.num_channels
    elif not all(0 <= x <= 2 for x in type_of_aspiration):
      raise ValueError("type_of_aspiration must be in range 0 to 2")

    if tip_pattern is None:
      tip_pattern = [False] * self.num_channels
    elif not all(0 <= x <= 1 for x in tip_pattern):
      raise ValueError("tip_pattern must be in range 0 to 1")

    if not all(0 <= x <= 50000 for x in x_position):
      raise ValueError("x_position must be in range 0 to 50000")

    if y_position is None:
      y_position = [3000] * self.num_channels
    elif not all(0 <= x <= 6500 for x in y_position):
      raise ValueError("y_position must be in range 0 to 6500")

    if minimal_traverse_height_at_begin_of_command is None:
      minimal_traverse_height_at_begin_of_command = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in minimal_traverse_height_at_begin_of_command):
      raise ValueError("minimal_traverse_height_at_begin_of_command must be in range 0 to 3600")

    if minimal_height_at_command_end is None:
      minimal_height_at_command_end = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in minimal_height_at_command_end):
      raise ValueError("minimal_height_at_command_end must be in range 0 to 3600")

    if lld_search_height is None:
      lld_search_height = [0] * self.num_channels
    elif not all(0 <= x <= 3600 for x in lld_search_height):
      raise ValueError("lld_search_height must be in range 0 to 3600")

    if clot_detection_height is None:
      clot_detection_height = [60] * self.num_channels
    elif not all(0 <= x <= 500 for x in clot_detection_height):
      raise ValueError("clot_detection_height must be in range 0 to 500")

    if liquid_surface_at_function_without_lld is None:
      liquid_surface_at_function_without_lld = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in liquid_surface_at_function_without_lld):
      raise ValueError("liquid_surface_at_function_without_lld must be in range 0 to 3600")

    if pull_out_distance_to_take_transport_air_in_function_without_lld is None:
      pull_out_distance_to_take_transport_air_in_function_without_lld = [50] * self.num_channels
    elif not all(0 <= x <= 3600 for x in
                 pull_out_distance_to_take_transport_air_in_function_without_lld):
      raise ValueError("pull_out_distance_to_take_transport_air_in_function_without_lld must be "
                       "in range 0 to 3600")

    if tube_2nd_section_height_measured_from_zm is None:
      tube_2nd_section_height_measured_from_zm = [0] * self.num_channels
    elif not all(0 <= x <= 3600 for x in tube_2nd_section_height_measured_from_zm):
      raise ValueError("tube_2nd_section_height_measured_from_zm must be in range 0 to 3600")

    if tube_2nd_section_ratio is None:
      tube_2nd_section_ratio = [0] * self.num_channels
    elif not all(0 <= x <= 10000 for x in tube_2nd_section_ratio):
      raise ValueError("tube_2nd_section_ratio must be in range 0 to 10000")

    if minimum_height is None:
      minimum_height = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in minimum_height):
      raise ValueError("minimum_height must be in range 0 to 3600")

    if immersion_depth is None:
      immersion_depth = [0] * self.num_channels
    elif not all(-3600 <= x <= 3600 for x in immersion_depth):
      raise ValueError("immersion_depth must be in range -3600 to 3600")

    if surface_following_distance is None:
      surface_following_distance = [0] * self.num_channels
    elif not all(0 <= x <= 3600 for x in surface_following_distance):
      raise ValueError("surface_following_distance must be in range 0 to 3600")

    if aspiration_volume is None:
      aspiration_volume = [0] * self.num_channels
    elif not all(0 <= x <= 125000 for x in aspiration_volume):
      raise ValueError("aspiration_volume must be in range 0 to 125000")

    if TODO_DA_2 is None:
      TODO_DA_2 = [0] * self.num_channels
    elif not all(0 <= x <= 125000 for x in TODO_DA_2):
      raise ValueError("TODO_DA_2 must be in range 0 to 125000")

    if aspiration_speed is None:
      aspiration_speed = [500] * self.num_channels
    elif not all(10 <= x <= 10000 for x in aspiration_speed):
      raise ValueError("aspiration_speed must be in range 10 to 10000")

    if transport_air_volume is None:
      transport_air_volume = [0] * self.num_channels
    elif not all(0 <= x <= 500 for x in transport_air_volume):
      raise ValueError("transport_air_volume must be in range 0 to 500")

    if blow_out_air_volume is None:
      blow_out_air_volume = [0] * self.num_channels
    elif not all(0 <= x <= 125000 for x in blow_out_air_volume):
      raise ValueError("blow_out_air_volume must be in range 0 to 125000")

    if pre_wetting_volume is None:
      pre_wetting_volume = [0] * self.num_channels
    elif not all(0 <= x <= 999 for x in pre_wetting_volume):
      raise ValueError("pre_wetting_volume must be in range 0 to 999")

    if lld_mode is None:
      lld_mode = [1] * self.num_channels
    elif not all(0 <= x <= 4 for x in lld_mode):
      raise ValueError("lld_mode must be in range 0 to 4")

    if lld_sensitivity is None:
      lld_sensitivity = [1] * self.num_channels
    elif not all(1 <= x <= 4 for x in lld_sensitivity):
      raise ValueError("lld_sensitivity must be in range 1 to 4")

    if pressure_lld_sensitivity is None:
      pressure_lld_sensitivity = [1] * self.num_channels
    elif not all(1 <= x <= 4 for x in pressure_lld_sensitivity):
      raise ValueError("pressure_lld_sensitivity must be in range 1 to 4")

    if aspirate_position_above_z_touch_off is None:
      aspirate_position_above_z_touch_off = [5] * self.num_channels
    elif not all(0 <= x <= 100 for x in aspirate_position_above_z_touch_off):
      raise ValueError("aspirate_position_above_z_touch_off must be in range 0 to 100")

    if TODO_DA_4 is None:
      TODO_DA_4 = [0] * self.num_channels
    elif not all(0 <= x <= 1 for x in TODO_DA_4):
      raise ValueError("TODO_DA_4 must be in range 0 to 1")

    if swap_speed is None:
      swap_speed = [100] * self.num_channels
    elif not all(3 <= x <= 1600 for x in swap_speed):
      raise ValueError("swap_speed must be in range 3 to 1600")

    if settling_time is None:
      settling_time = [5] * self.num_channels
    elif not all(0 <= x <= 99 for x in settling_time):
      raise ValueError("settling_time must be in range 0 to 99")

    if mix_volume is None:
      mix_volume = [0] * self.num_channels
    elif not all(0 <= x <= 12500 for x in mix_volume):
      raise ValueError("mix_volume must be in range 0 to 12500")

    if mix_cycles is None:
      mix_cycles = [0] * self.num_channels
    elif not all(0 <= x <= 99 for x in mix_cycles):
      raise ValueError("mix_cycles must be in range 0 to 99")

    if mix_position_in_z_direction_from_liquid_surface is None:
      mix_position_in_z_direction_from_liquid_surface = [250] * self.num_channels
    elif not all(0 <= x <= 900 for x in mix_position_in_z_direction_from_liquid_surface):
      raise ValueError("mix_position_in_z_direction_from_liquid_surface must be in range 0 to 900")

    if mix_speed is None:
      mix_speed = [500] * self.num_channels
    elif not all(10 <= x <= 10000 for x in mix_speed):
      raise ValueError("mix_speed must be in range 10 to 10000")

    if surface_following_distance_during_mixing is None:
      surface_following_distance_during_mixing = [0] * self.num_channels
    elif not all(0 <= x <= 3600 for x in surface_following_distance_during_mixing):
      raise ValueError("surface_following_distance_during_mixing must be in range 0 to 3600")

    if TODO_DA_5 is None:
      TODO_DA_5 = [0] * self.num_channels
    elif not all(0 <= x <= 1 for x in TODO_DA_5):
      raise ValueError("TODO_DA_5 must be in range 0 to 1")

    if capacitive_mad_supervision_on_off is None:
      capacitive_mad_supervision_on_off = [0] * self.num_channels
    elif not all(0 <= x <= 1 for x in capacitive_mad_supervision_on_off):
      raise ValueError("capacitive_mad_supervision_on_off must be in range 0 to 1")

    if pressure_mad_supervision_on_off is None:
      pressure_mad_supervision_on_off = [0] * self.num_channels
    elif not all(0 <= x <= 1 for x in pressure_mad_supervision_on_off):
      raise ValueError("pressure_mad_supervision_on_off must be in range 0 to 1")

    if not 0 <= tadm_algorithm_on_off <= 1:
      raise ValueError("tadm_algorithm_on_off must be in range 0 to 1")

    if limit_curve_index is None:
      limit_curve_index = [0] * self.num_channels
    elif not all(0 <= x <= 999 for x in limit_curve_index):
      raise ValueError("limit_curve_index must be in range 0 to 999")

    if not 0 <= recording_mode <= 2:
      raise ValueError("recording_mode must be in range 0 to 2")

    return await self.send_command(
      module="A1PM",
      command="DA",
      at=type_of_aspiration,
      tm=tip_pattern,
      xp=x_position,
      yp=y_position,
      th=minimal_traverse_height_at_begin_of_command,
      te=minimal_height_at_command_end,
      lp=lld_search_height,
      ch=clot_detection_height,
      zl=liquid_surface_at_function_without_lld,
      po=pull_out_distance_to_take_transport_air_in_function_without_lld,
      zu=tube_2nd_section_height_measured_from_zm,
      zr=tube_2nd_section_ratio,
      zx=minimum_height,
      ip=immersion_depth,
      fp=surface_following_distance,
      av=aspiration_volume,
      # ar=TODO_DA_2, # this parameters is not used by VoV
      as_=aspiration_speed,
      ta=transport_air_volume,
      ba=blow_out_air_volume,
      oa=pre_wetting_volume,
      lm=lld_mode,
      ll=lld_sensitivity,
      lv=pressure_lld_sensitivity,
      zo=aspirate_position_above_z_touch_off,
      # lg=TODO_DA_4,
      de=swap_speed,
      wt=settling_time,
      mv=mix_volume,
      mc=mix_cycles,
      mp=mix_position_in_z_direction_from_liquid_surface,
      ms=mix_speed,
      mh=surface_following_distance_during_mixing,
      la=TODO_DA_5,
      lb=capacitive_mad_supervision_on_off,
      lc=pressure_mad_supervision_on_off,
      gj=tadm_algorithm_on_off,
      gi=limit_curve_index,
      gk=recording_mode,
    )

  async def pip_dispense(
    self,
    x_position: List[int],
    y_position: List[int],
    type_of_dispensing_mode: Optional[List[int]] = None,
    tip_pattern: Optional[List[bool]] = None,
    minimum_height: Optional[List[int]] = None,
    lld_search_height: Optional[List[int]] = None,
    liquid_surface_at_function_without_lld: Optional[List[int]] = None,
    pull_out_distance_to_take_transport_air_in_function_without_lld: Optional[List[int]] = None,
    immersion_depth: Optional[List[int]] = None,
    surface_following_distance: Optional[List[int]] = None,
    tube_2nd_section_height_measured_from_zm: Optional[List[int]] = None,
    tube_2nd_section_ratio: Optional[List[int]] = None,
    minimal_traverse_height_at_begin_of_command: Optional[List[int]] = None,
    minimal_height_at_command_end: Optional[List[int]] = None,
    dispense_volume: Optional[List[int]] = None,
    dispense_speed: Optional[List[int]] = None,
    cut_off_speed: Optional[List[int]] = None,
    stop_back_volume: Optional[List[int]] = None,
    transport_air_volume: Optional[List[int]] = None,
    blow_out_air_volume: Optional[List[int]] = None,
    lld_mode: Optional[List[int]] = None,
    side_touch_off_distance: int = 0,
    dispense_position_above_z_touch_off: Optional[List[int]] = None,
    lld_sensitivity: Optional[List[int]] = None,
    pressure_lld_sensitivity: Optional[List[int]] = None,
    swap_speed: Optional[List[int]] = None,
    settling_time: Optional[List[int]] = None,
    mix_volume: Optional[List[int]] = None,
    mix_cycles: Optional[List[int]] = None,
    mix_position_in_z_direction_from_liquid_surface: Optional[List[int]] = None,
    mix_speed: Optional[List[int]] = None,
    surface_following_distance_during_mixing: Optional[List[int]] = None,
    TODO_DD_2: Optional[List[int]] = None,
    tadm_algorithm_on_off: int = 0,
    limit_curve_index: Optional[List[int]] = None,
    recording_mode: int = 0,
  ):
    """ Dispensing of liquid

    Args:
      type_of_dispensing_mode: Type of dispensing mode 0 = part in jet 1 = blow in jet 2 = Part at
          surface 3 = Blow at surface 4 = Empty.
      tip_pattern: Tip pattern (channels involved). [0 = not involved, 1 = involved].
      x_position: X Position [0.1mm].
      y_position: Y Position [0.1mm].
      minimum_height: Minimum height (maximum immersion depth) [0.1mm].
      lld_search_height: LLD search height [0.1mm].
      liquid_surface_at_function_without_lld: Liquid surface at function without LLD [0.1mm].
      pull_out_distance_to_take_transport_air_in_function_without_lld:
          Pull out distance to take transp. air in function without LLD [0.1mm]
        .
      immersion_depth: Immersion depth [0.1mm].
      surface_following_distance: Surface following distance [0.1mm].
      tube_2nd_section_height_measured_from_zm: Tube 2nd section height measured from zm [0.1mm].
      tube_2nd_section_ratio: Tube 2nd section ratio.
      minimal_traverse_height_at_begin_of_command: Minimal traverse height at begin of command
        [0.1mm].
      minimal_height_at_command_end: Minimal height at command end [0.1mm].
      dispense_volume: Dispense volume [0.01ul].
      dispense_speed: Dispense speed [0.1ul/s].
      cut_off_speed: Cut off speed [0.1ul/s].
      stop_back_volume: Stop back volume [0.1ul].
      transport_air_volume: Transport air volume [0.1ul].
      blow_out_air_volume: Blow out air volume [0.01ul].
      lld_mode: LLD Mode (0 = off).
      side_touch_off_distance: Side touch off distance [0.1mm].
      dispense_position_above_z_touch_off: (0).
      lld_sensitivity: LLD sensitivity (1 = high, 4 = low).
      pressure_lld_sensitivity: Pressure LLD sensitivity (1= high, 4=low).
      swap_speed: Swap speed (on leaving liquid) [0.1mm/s].
      settling_time: Settling time [0.1s].
      mix_volume: Mix volume [0.1ul].
      mix_cycles: Mix cycles.
      mix_position_in_z_direction_from_liquid_surface: Mix position in Z direction from liquid
        surface[0.1mm].
      mix_speed: Mix speed [0.1ul/s].
      surface_following_distance_during_mixing: Surface following distance during mixing [0.1mm].
      TODO_DD_2: (0).
      tadm_algorithm_on_off: TADM algorithm on/off (0 = off).
      limit_curve_index: Limit curve index.
      recording_mode:
          Recording mode (0 = no 1 = TADM errors only 2 = all TADM measurements)
        .
    """

    if type_of_dispensing_mode is None:
      type_of_dispensing_mode = [0] * self.num_channels
    elif not all(0 <= x <= 4 for x in type_of_dispensing_mode):
      raise ValueError("type_of_dispensing_mode must be in range 0 to 4")

    if tip_pattern is None:
      tip_pattern = [False] * self.num_channels
    elif not all(0 <= x <= 1 for x in tip_pattern):
      raise ValueError("tip_pattern must be in range 0 to 1")

    if not all(0 <= x <= 50000 for x in x_position):
      raise ValueError("x_position must be in range 0 to 50000")

    if y_position is None:
      y_position = [3000] * self.num_channels
    elif not all(0 <= x <= 6500 for x in y_position):
      raise ValueError("y_position must be in range 0 to 6500")

    if minimum_height is None:
      minimum_height = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in minimum_height):
      raise ValueError("minimum_height must be in range 0 to 3600")

    if lld_search_height is None:
      lld_search_height = [0] * self.num_channels
    elif not all(0 <= x <= 3600 for x in lld_search_height):
      raise ValueError("lld_search_height must be in range 0 to 3600")

    if liquid_surface_at_function_without_lld is None:
      liquid_surface_at_function_without_lld = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in liquid_surface_at_function_without_lld):
      raise ValueError("liquid_surface_at_function_without_lld must be in range 0 to 3600")

    if pull_out_distance_to_take_transport_air_in_function_without_lld is None:
      pull_out_distance_to_take_transport_air_in_function_without_lld = [50] * self.num_channels
    elif not all(0 <= x <= 3600 for x in
                  pull_out_distance_to_take_transport_air_in_function_without_lld):
      raise ValueError("pull_out_distance_to_take_transport_air_in_function_without_lld must be "
                       "in range 0 to 3600")

    if immersion_depth is None:
      immersion_depth = [0] * self.num_channels
    elif not all(-3600 <= x <= 3600 for x in immersion_depth):
      raise ValueError("immersion_depth must be in range -3600 to 3600")

    if surface_following_distance is None:
      surface_following_distance = [0] * self.num_channels
    elif not all(0 <= x <= 3600 for x in surface_following_distance):
      raise ValueError("surface_following_distance must be in range 0 to 3600")

    if tube_2nd_section_height_measured_from_zm is None:
      tube_2nd_section_height_measured_from_zm = [0] * self.num_channels
    elif not all(0 <= x <= 3600 for x in tube_2nd_section_height_measured_from_zm):
      raise ValueError("tube_2nd_section_height_measured_from_zm must be in range 0 to 3600")

    if tube_2nd_section_ratio is None:
      tube_2nd_section_ratio = [0] * self.num_channels
    elif not all(0 <= x <= 10000 for x in tube_2nd_section_ratio):
      raise ValueError("tube_2nd_section_ratio must be in range 0 to 10000")

    if minimal_traverse_height_at_begin_of_command is None:
      minimal_traverse_height_at_begin_of_command = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in minimal_traverse_height_at_begin_of_command):
      raise ValueError("minimal_traverse_height_at_begin_of_command must be in range 0 to 3600")

    if minimal_height_at_command_end is None:
      minimal_height_at_command_end = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in minimal_height_at_command_end):
      raise ValueError("minimal_height_at_command_end must be in range 0 to 3600")

    if dispense_volume is None:
      dispense_volume = [0] * self.num_channels
    elif not all(0 <= x <= 125000 for x in dispense_volume):
      raise ValueError("dispense_volume must be in range 0 to 125000")

    if dispense_speed is None:
      dispense_speed = [500] * self.num_channels
    elif not all(10 <= x <= 10000 for x in dispense_speed):
      raise ValueError("dispense_speed must be in range 10 to 10000")

    if cut_off_speed is None:
      cut_off_speed = [250] * self.num_channels
    elif not all(10 <= x <= 10000 for x in cut_off_speed):
      raise ValueError("cut_off_speed must be in range 10 to 10000")

    if stop_back_volume is None:
      stop_back_volume = [0] * self.num_channels
    elif not all(0 <= x <= 180 for x in stop_back_volume):
      raise ValueError("stop_back_volume must be in range 0 to 180")

    if transport_air_volume is None:
      transport_air_volume = [0] * self.num_channels
    elif not all(0 <= x <= 500 for x in transport_air_volume):
      raise ValueError("transport_air_volume must be in range 0 to 500")

    if blow_out_air_volume is None:
      blow_out_air_volume = [0] * self.num_channels
    elif not all(0 <= x <= 125000 for x in blow_out_air_volume):
      raise ValueError("blow_out_air_volume must be in range 0 to 125000")

    if lld_mode is None:
      lld_mode = [1] * self.num_channels
    elif not all(0 <= x <= 4 for x in lld_mode):
      raise ValueError("lld_mode must be in range 0 to 4")

    if not 0 <= side_touch_off_distance <= 45:
      raise ValueError("side_touch_off_distance must be in range 0 to 45")

    if dispense_position_above_z_touch_off is None:
      dispense_position_above_z_touch_off = [5] * self.num_channels
    elif not all(0 <= x <= 100 for x in dispense_position_above_z_touch_off):
      raise ValueError("dispense_position_above_z_touch_off must be in range 0 to 100")

    if lld_sensitivity is None:
      lld_sensitivity = [1] * self.num_channels
    elif not all(1 <= x <= 4 for x in lld_sensitivity):
      raise ValueError("lld_sensitivity must be in range 1 to 4")

    if pressure_lld_sensitivity is None:
      pressure_lld_sensitivity = [1] * self.num_channels
    elif not all(1 <= x <= 4 for x in pressure_lld_sensitivity):
      raise ValueError("pressure_lld_sensitivity must be in range 1 to 4")

    if swap_speed is None:
      swap_speed = [100] * self.num_channels
    elif not all(3 <= x <= 1600 for x in swap_speed):
      raise ValueError("swap_speed must be in range 3 to 1600")

    if settling_time is None:
      settling_time = [5] * self.num_channels
    elif not all(0 <= x <= 99 for x in settling_time):
      raise ValueError("settling_time must be in range 0 to 99")

    if mix_volume is None:
      mix_volume = [0] * self.num_channels
    elif not all(0 <= x <= 12500 for x in mix_volume):
      raise ValueError("mix_volume must be in range 0 to 12500")

    if mix_cycles is None:
      mix_cycles = [0] * self.num_channels
    elif not all(0 <= x <= 99 for x in mix_cycles):
      raise ValueError("mix_cycles must be in range 0 to 99")

    if mix_position_in_z_direction_from_liquid_surface is None:
      mix_position_in_z_direction_from_liquid_surface = [250] * self.num_channels
    elif not all(0 <= x <= 900 for x in mix_position_in_z_direction_from_liquid_surface):
      raise ValueError("mix_position_in_z_direction_from_liquid_surface must be in range 0 to 900")

    if mix_speed is None:
      mix_speed = [500] * self.num_channels
    elif not all(10 <= x <= 10000 for x in mix_speed):
      raise ValueError("mix_speed must be in range 10 to 10000")

    if surface_following_distance_during_mixing is None:
      surface_following_distance_during_mixing = [0] * self.num_channels
    elif not all(0 <= x <= 3600 for x in surface_following_distance_during_mixing):
      raise ValueError("surface_following_distance_during_mixing must be in range 0 to 3600")

    if TODO_DD_2 is None:
      TODO_DD_2 = [0] * self.num_channels
    elif not all(0 <= x <= 1 for x in TODO_DD_2):
      raise ValueError("TODO_DD_2 must be in range 0 to 1")

    if not 0 <= tadm_algorithm_on_off <= 1:
      raise ValueError("tadm_algorithm_on_off must be in range 0 to 1")

    if limit_curve_index is None:
      limit_curve_index = [0] * self.num_channels
    elif not all(0 <= x <= 999 for x in limit_curve_index):
      raise ValueError("limit_curve_index must be in range 0 to 999")

    if not 0 <= recording_mode <= 2:
      raise ValueError("recording_mode must be in range 0 to 2")

    return await self.send_command(
      module="A1PM",
      command="DD",
      dm=type_of_dispensing_mode,
      tm=tip_pattern,
      xp=x_position,
      yp=y_position,
      zx=minimum_height,
      lp=lld_search_height,
      zl=liquid_surface_at_function_without_lld,
      po=pull_out_distance_to_take_transport_air_in_function_without_lld,
      ip=immersion_depth,
      fp=surface_following_distance,
      zu=tube_2nd_section_height_measured_from_zm,
      zr=tube_2nd_section_ratio,
      th=minimal_traverse_height_at_begin_of_command,
      te=minimal_height_at_command_end,
      dv=dispense_volume,
      ds=dispense_speed,
      ss=cut_off_speed,
      rv=stop_back_volume,
      ta=transport_air_volume,
      ba=blow_out_air_volume,
      lm=lld_mode,
      dj=side_touch_off_distance,
      zo=dispense_position_above_z_touch_off,
      ll=lld_sensitivity,
      lv=pressure_lld_sensitivity,
      de=swap_speed,
      wt=settling_time,
      mv=mix_volume,
      mc=mix_cycles,
      mp=mix_position_in_z_direction_from_liquid_surface,
      ms=mix_speed,
      mh=surface_following_distance_during_mixing,
      la=TODO_DD_2,
      gj=tadm_algorithm_on_off,
      gi=limit_curve_index,
      gk=recording_mode,
    )

  async def simultaneous_aspiration_dispensation_of_liquid(
    self,
    x_position: List[int],
    y_position: List[int],
    type_of_aspiration: Optional[List[int]] = None,
    type_of_dispensing_mode: Optional[List[int]] = None,
    tip_pattern: Optional[List[bool]] = None,
    TODO_DM_1: Optional[List[int]] = None,
    minimal_traverse_height_at_begin_of_command: Optional[List[int]] = None,
    minimal_height_at_command_end: Optional[List[int]] = None,
    lld_search_height: Optional[List[int]] = None,
    clot_detection_height: Optional[List[int]] = None,
    liquid_surface_at_function_without_lld: Optional[List[int]] = None,
    pull_out_distance_to_take_transport_air_in_function_without_lld: Optional[List[int]] = None,
    minimum_height: Optional[List[int]] = None,
    immersion_depth: Optional[List[int]] = None,
    surface_following_distance: Optional[List[int]] = None,
    tube_2nd_section_height_measured_from_zm: Optional[List[int]] = None,
    tube_2nd_section_ratio: Optional[List[int]] = None,
    aspiration_volume: Optional[List[int]] = None,
    TODO_DM_3: Optional[List[int]] = None,
    aspiration_speed: Optional[List[int]] = None,
    dispense_volume: Optional[List[int]] = None,
    dispense_speed: Optional[List[int]] = None,
    cut_off_speed: Optional[List[int]] = None,
    stop_back_volume: Optional[List[int]] = None,
    transport_air_volume: Optional[List[int]] = None,
    blow_out_air_volume: Optional[List[int]] = None,
    pre_wetting_volume: Optional[List[int]] = None,
    lld_mode: Optional[List[int]] = None,
    aspirate_position_above_z_touch_off: Optional[List[int]] = None,
    lld_sensitivity: Optional[List[int]] = None,
    pressure_lld_sensitivity: Optional[List[int]] = None,
    swap_speed: Optional[List[int]] = None,
    settling_time: Optional[List[int]] = None,
    mix_volume: Optional[List[int]] = None,
    mix_cycles: Optional[List[int]] = None,
    mix_position_in_z_direction_from_liquid_surface: Optional[List[int]] = None,
    mix_speed: Optional[List[int]] = None,
    surface_following_distance_during_mixing: Optional[List[int]] = None,
    TODO_DM_5: Optional[List[int]] = None,
    capacitive_mad_supervision_on_off: Optional[List[int]] = None,
    pressure_mad_supervision_on_off: Optional[List[int]] = None,
    tadm_algorithm_on_off: int = 0,
    limit_curve_index: Optional[List[int]] = None,
    recording_mode: int = 0,
  ):
    """ Simultaneous aspiration & dispensation of liquid

    Args:
      type_of_aspiration: Type of aspiration (0 = simple 1 = sequence 2 = cup emptied).
      type_of_dispensing_mode: Type of dispensing mode 0 = part in jet 1 = blow in jet 2 = Part at
          surface 3 = Blow at surface 4 = Empty.
      tip_pattern: Tip pattern (channels involved). [0 = not involved, 1 = involved].
      TODO_DM_1: (0).
      x_position: X Position [0.1mm].
      y_position: Y Position [0.1mm].
      minimal_traverse_height_at_begin_of_command: Minimal traverse height at begin of command
        [0.1mm].
      minimal_height_at_command_end: Minimal height at command end [0.1mm].
      lld_search_height: LLD search height [0.1mm].
      clot_detection_height: (0).
      liquid_surface_at_function_without_lld: Liquid surface at function without LLD [0.1mm].
      pull_out_distance_to_take_transport_air_in_function_without_lld:
          Pull out distance to take transp. air in function without LLD [0.1mm]
        .
      minimum_height: Minimum height (maximum immersion depth) [0.1mm].
      immersion_depth: Immersion depth [0.1mm].
      surface_following_distance: Surface following distance [0.1mm].
      tube_2nd_section_height_measured_from_zm: Tube 2nd section height measured from zm [0.1mm].
      tube_2nd_section_ratio: Tube 2nd section ratio.
      aspiration_volume: Aspiration volume [0.01ul].
      TODO_DM_3: (0).
      aspiration_speed: Aspiration speed [0.1ul]/s.
      dispense_volume: Dispense volume [0.01ul].
      dispense_speed: Dispense speed [0.1ul/s].
      cut_off_speed: Cut off speed [0.1ul/s].
      stop_back_volume: Stop back volume [0.1ul].
      transport_air_volume: Transport air volume [0.1ul].
      blow_out_air_volume: Blow out air volume [0.01ul].
      pre_wetting_volume: Pre wetting volume [0.1ul].
      lld_mode: LLD Mode (0 = off).
      aspirate_position_above_z_touch_off: (0).
      lld_sensitivity: LLD sensitivity (1 = high, 4 = low).
      pressure_lld_sensitivity: Pressure LLD sensitivity (1= high, 4=low).
      swap_speed: Swap speed (on leaving liquid) [0.1mm/s].
      settling_time: Settling time [0.1s].
      mix_volume: Mix volume [0.1ul].
      mix_cycles: Mix cycles.
      mix_position_in_z_direction_from_liquid_surface: Mix position in Z direction from liquid
        surface[0.1mm].
      mix_speed: Mix speed [0.1ul/s].
      surface_following_distance_during_mixing: Surface following distance during mixing [0.1mm].
      TODO_DM_5: (0).
      capacitive_mad_supervision_on_off: Capacitive MAD supervision on/off (0 = OFF).
      pressure_mad_supervision_on_off: Pressure MAD supervision on/off (0 = OFF).
      tadm_algorithm_on_off: TADM algorithm on/off (0 = off).
      limit_curve_index: Limit curve index.
      recording_mode:
          Recording mode (0 = no 1 = TADM errors only 2 = all TADM measurements)
        .
    """

    if type_of_aspiration is None:
      type_of_aspiration = [0] * self.num_channels
    elif not all(0 <= x <= 2 for x in type_of_aspiration):
      raise ValueError("type_of_aspiration must be in range 0 to 2")

    if type_of_dispensing_mode is None:
      type_of_dispensing_mode = [0] * self.num_channels
    elif not all(0 <= x <= 4 for x in type_of_dispensing_mode):
      raise ValueError("type_of_dispensing_mode must be in range 0 to 4")

    if tip_pattern is None:
      tip_pattern = [False] * self.num_channels
    elif not all(0 <= x <= 1 for x in tip_pattern):
      raise ValueError("tip_pattern must be in range 0 to 1")

    if TODO_DM_1 is None:
      TODO_DM_1 = [0] * self.num_channels
    elif not all(0 <= x <= 1 for x in TODO_DM_1):
      raise ValueError("TODO_DM_1 must be in range 0 to 1")

    if not all(0 <= x <= 50000 for x in x_position):
      raise ValueError("x_position must be in range 0 to 50000")

    if y_position is None:
      y_position = [3000] * self.num_channels
    elif not all(0 <= x <= 6500 for x in y_position):
      raise ValueError("y_position must be in range 0 to 6500")

    if minimal_traverse_height_at_begin_of_command is None:
      minimal_traverse_height_at_begin_of_command = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in minimal_traverse_height_at_begin_of_command):
      raise ValueError("minimal_traverse_height_at_begin_of_command must be in range 0 to 3600")

    if minimal_height_at_command_end is None:
      minimal_height_at_command_end = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in minimal_height_at_command_end):
      raise ValueError("minimal_height_at_command_end must be in range 0 to 3600")

    if lld_search_height is None:
      lld_search_height = [0] * self.num_channels
    elif not all(0 <= x <= 3600 for x in lld_search_height):
      raise ValueError("lld_search_height must be in range 0 to 3600")

    if clot_detection_height is None:
      clot_detection_height = [60] * self.num_channels
    elif not all(0 <= x <= 500 for x in clot_detection_height):
      raise ValueError("clot_detection_height must be in range 0 to 500")

    if liquid_surface_at_function_without_lld is None:
      liquid_surface_at_function_without_lld = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in liquid_surface_at_function_without_lld):
      raise ValueError("liquid_surface_at_function_without_lld must be in range 0 to 3600")

    if pull_out_distance_to_take_transport_air_in_function_without_lld is None:
      pull_out_distance_to_take_transport_air_in_function_without_lld = [50] * self.num_channels
    elif not all(0 <= x <= 3600
      for x in pull_out_distance_to_take_transport_air_in_function_without_lld):
      raise ValueError("pull_out_distance_to_take_transport_air_in_function_without_lld must be "
                       "in range 0 to 3600")

    if minimum_height is None:
      minimum_height = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in minimum_height):
      raise ValueError("minimum_height must be in range 0 to 3600")

    if immersion_depth is None:
      immersion_depth = [0] * self.num_channels
    elif not all(-3600 <= x <= 3600 for x in immersion_depth):
      raise ValueError("immersion_depth must be in range -3600 to 3600")

    if surface_following_distance is None:
      surface_following_distance = [0] * self.num_channels
    elif not all(0 <= x <= 3600 for x in surface_following_distance):
      raise ValueError("surface_following_distance must be in range 0 to 3600")

    if tube_2nd_section_height_measured_from_zm is None:
      tube_2nd_section_height_measured_from_zm = [0] * self.num_channels
    elif not all(0 <= x <= 3600 for x in tube_2nd_section_height_measured_from_zm):
      raise ValueError("tube_2nd_section_height_measured_from_zm must be in range 0 to 3600")

    if tube_2nd_section_ratio is None:
      tube_2nd_section_ratio = [0] * self.num_channels
    elif not all(0 <= x <= 10000 for x in tube_2nd_section_ratio):
      raise ValueError("tube_2nd_section_ratio must be in range 0 to 10000")

    if aspiration_volume is None:
      aspiration_volume = [0] * self.num_channels
    elif not all(0 <= x <= 125000 for x in aspiration_volume):
      raise ValueError("aspiration_volume must be in range 0 to 125000")

    if TODO_DM_3 is None:
      TODO_DM_3 = [0] * self.num_channels
    elif not all(0 <= x <= 125000 for x in TODO_DM_3):
      raise ValueError("TODO_DM_3 must be in range 0 to 125000")

    if aspiration_speed is None:
      aspiration_speed = [500] * self.num_channels
    elif not all(10 <= x <= 10000 for x in aspiration_speed):
      raise ValueError("aspiration_speed must be in range 10 to 10000")

    if dispense_volume is None:
      dispense_volume = [0] * self.num_channels
    elif not all(0 <= x <= 125000 for x in dispense_volume):
      raise ValueError("dispense_volume must be in range 0 to 125000")

    if dispense_speed is None:
      dispense_speed = [500] * self.num_channels
    elif not all(10 <= x <= 10000 for x in dispense_speed):
      raise ValueError("dispense_speed must be in range 10 to 10000")

    if cut_off_speed is None:
      cut_off_speed = [250] * self.num_channels
    elif not all(10 <= x <= 10000 for x in cut_off_speed):
      raise ValueError("cut_off_speed must be in range 10 to 10000")

    if stop_back_volume is None:
      stop_back_volume = [0] * self.num_channels
    elif not all(0 <= x <= 180 for x in stop_back_volume):
      raise ValueError("stop_back_volume must be in range 0 to 180")

    if transport_air_volume is None:
      transport_air_volume = [0] * self.num_channels
    elif not all(0 <= x <= 500 for x in transport_air_volume):
      raise ValueError("transport_air_volume must be in range 0 to 500")

    if blow_out_air_volume is None:
      blow_out_air_volume = [0] * self.num_channels
    elif not all(0 <= x <= 125000 for x in blow_out_air_volume):
      raise ValueError("blow_out_air_volume must be in range 0 to 125000")

    if pre_wetting_volume is None:
      pre_wetting_volume = [0] * self.num_channels
    elif not all(0 <= x <= 999 for x in pre_wetting_volume):
      raise ValueError("pre_wetting_volume must be in range 0 to 999")

    if lld_mode is None:
      lld_mode = [1] * self.num_channels
    elif not all(0 <= x <= 4 for x in lld_mode):
      raise ValueError("lld_mode must be in range 0 to 4")

    if aspirate_position_above_z_touch_off is None:
      aspirate_position_above_z_touch_off = [5] * self.num_channels
    elif not all(0 <= x <= 100 for x in aspirate_position_above_z_touch_off):
      raise ValueError("aspirate_position_above_z_touch_off must be in range 0 to 100")

    if lld_sensitivity is None:
      lld_sensitivity = [1] * self.num_channels
    elif not all(1 <= x <= 4 for x in lld_sensitivity):
      raise ValueError("lld_sensitivity must be in range 1 to 4")

    if pressure_lld_sensitivity is None:
      pressure_lld_sensitivity = [1] * self.num_channels
    elif not all(1 <= x <= 4 for x in pressure_lld_sensitivity):
      raise ValueError("pressure_lld_sensitivity must be in range 1 to 4")

    if swap_speed is None:
      swap_speed = [100] * self.num_channels
    elif not all(3 <= x <= 1600 for x in swap_speed):
      raise ValueError("swap_speed must be in range 3 to 1600")

    if settling_time is None:
      settling_time = [5] * self.num_channels
    elif not all(0 <= x <= 99 for x in settling_time):
      raise ValueError("settling_time must be in range 0 to 99")

    if mix_volume is None:
      mix_volume = [0] * self.num_channels
    elif not all(0 <= x <= 12500 for x in mix_volume):
      raise ValueError("mix_volume must be in range 0 to 12500")

    if mix_cycles is None:
      mix_cycles = [0] * self.num_channels
    elif not all(0 <= x <= 99 for x in mix_cycles):
      raise ValueError("mix_cycles must be in range 0 to 99")

    if mix_position_in_z_direction_from_liquid_surface is None:
      mix_position_in_z_direction_from_liquid_surface = [250] * self.num_channels
    elif not all(0 <= x <= 900 for x in mix_position_in_z_direction_from_liquid_surface):
      raise ValueError("mix_position_in_z_direction_from_liquid_surface must be in range 0 to 900")

    if mix_speed is None:
      mix_speed = [500] * self.num_channels
    elif not all(10 <= x <= 10000 for x in mix_speed):
      raise ValueError("mix_speed must be in range 10 to 10000")

    if surface_following_distance_during_mixing is None:
      surface_following_distance_during_mixing = [0] * self.num_channels
    elif not all(0 <= x <= 3600 for x in surface_following_distance_during_mixing):
      raise ValueError("surface_following_distance_during_mixing must be in range 0 to 3600")

    if TODO_DM_5 is None:
      TODO_DM_5 = [0] * self.num_channels
    elif not all(0 <= x <= 1 for x in TODO_DM_5):
      raise ValueError("TODO_DM_5 must be in range 0 to 1")

    if capacitive_mad_supervision_on_off is None:
      capacitive_mad_supervision_on_off = [0] * self.num_channels
    elif not all(0 <= x <= 1 for x in capacitive_mad_supervision_on_off):
      raise ValueError("capacitive_mad_supervision_on_off must be in range 0 to 1")

    if pressure_mad_supervision_on_off is None:
      pressure_mad_supervision_on_off = [0] * self.num_channels
    elif not all(0 <= x <= 1 for x in pressure_mad_supervision_on_off):
      raise ValueError("pressure_mad_supervision_on_off must be in range 0 to 1")

    if not 0 <= tadm_algorithm_on_off <= 1:
      raise ValueError("tadm_algorithm_on_off must be in range 0 to 1")

    if limit_curve_index is None:
      limit_curve_index = [0] * self.num_channels
    elif not all(0 <= x <= 999 for x in limit_curve_index):
      raise ValueError("limit_curve_index must be in range 0 to 999")

    if not 0 <= recording_mode <= 2:
      raise ValueError("recording_mode must be in range 0 to 2")

    return await self.send_command(
      module="A1PM",
      command="DM",
      at=type_of_aspiration,
      dm=type_of_dispensing_mode,
      tm=tip_pattern,
      dd=TODO_DM_1,
      xp=x_position,
      yp=y_position,
      th=minimal_traverse_height_at_begin_of_command,
      te=minimal_height_at_command_end,
      lp=lld_search_height,
      ch=clot_detection_height,
      zl=liquid_surface_at_function_without_lld,
      po=pull_out_distance_to_take_transport_air_in_function_without_lld,
      zx=minimum_height,
      ip=immersion_depth,
      fp=surface_following_distance,
      zu=tube_2nd_section_height_measured_from_zm,
      zr=tube_2nd_section_ratio,
      av=aspiration_volume,
      ar=TODO_DM_3,
      as_=aspiration_speed,
      dv=dispense_volume,
      ds=dispense_speed,
      ss=cut_off_speed,
      rv=stop_back_volume,
      ta=transport_air_volume,
      ba=blow_out_air_volume,
      oa=pre_wetting_volume,
      lm=lld_mode,
      zo=aspirate_position_above_z_touch_off,
      ll=lld_sensitivity,
      lv=pressure_lld_sensitivity,
      de=swap_speed,
      wt=settling_time,
      mv=mix_volume,
      mc=mix_cycles,
      mp=mix_position_in_z_direction_from_liquid_surface,
      ms=mix_speed,
      mh=surface_following_distance_during_mixing,
      la=TODO_DM_5,
      lb=capacitive_mad_supervision_on_off,
      lc=pressure_mad_supervision_on_off,
      gj=tadm_algorithm_on_off,
      gi=limit_curve_index,
      gk=recording_mode,
    )

  async def dispense_on_fly(
    self,
    y_position: List[int],
    tip_pattern: Optional[List[bool]] = None,
    TODO_DF_1: int = 0,
    TODO_DF_2: int = 0,
    TODO_DF_3: int = 100,
    TODO_DF_4: int = 900,
    x_speed: int = 270,
    TODO_DF_5: int = 1,
    minimal_traverse_height_at_begin_of_command: Optional[List[int]] = None,
    minimal_height_at_command_end: Optional[List[int]] = None,
    liquid_surface_at_function_without_lld: Optional[List[int]] = None,
    dispense_volume: Optional[List[int]] = None,
    dispense_speed: Optional[List[int]] = None,
    cut_off_speed: Optional[List[int]] = None,
    stop_back_volume: Optional[List[int]] = None,
    transport_air_volume: Optional[List[int]] = None,
    tadm_algorithm_on_off: int = 0,
    limit_curve_index: Optional[List[int]] = None,
    recording_mode: int = 0,
  ):
    """ Dispense on fly

    Args:
      tip_pattern: Tip pattern (channels involved). [0 = not involved, 1 = involved].
      TODO_DF_1: (0).
      TODO_DF_2: (0).
      TODO_DF_3: (0).
      TODO_DF_4: (0).
      x_speed: X speed [0.1mm/s].
      TODO_DF_5: (0).
      minimal_traverse_height_at_begin_of_command: Minimal traverse height at begin of command
        [0.1mm].
      minimal_height_at_command_end: Minimal height at command end [0.1mm].
      y_position: Y Position [0.1mm].
      liquid_surface_at_function_without_lld: Liquid surface at function without LLD [0.1mm].
      dispense_volume: Dispense volume [0.01ul].
      dispense_speed: Dispense speed [0.1ul/s].
      cut_off_speed: Cut off speed [0.1ul/s].
      stop_back_volume: Stop back volume [0.1ul].
      transport_air_volume: Transport air volume [0.1ul].
      tadm_algorithm_on_off: TADM algorithm on/off (0 = off).
      limit_curve_index: Limit curve index.
      recording_mode: Recording mode (0 = no 1 = TADM errors only 2 = all TADM measurements).
    """

    if tip_pattern is None:
      tip_pattern = [False] * self.num_channels
    elif not all(0 <= x <= 1 for x in tip_pattern):
      raise ValueError("tip_pattern must be in range 0 to 1")

    if not -50000 <= TODO_DF_1 <= 50000:
      raise ValueError("TODO_DF_1 must be in range -50000 to 50000")

    if not -50000 <= TODO_DF_2 <= 50000:
      raise ValueError("TODO_DF_2 must be in range -50000 to 50000")

    if not 0 <= TODO_DF_3 <= 900:
      raise ValueError("TODO_DF_3 must be in range 0 to 900")

    if not 1 <= TODO_DF_4 <= 2500:
      raise ValueError("TODO_DF_4 must be in range 1 to 2500")

    if not 20 <= x_speed <= 25000:
      raise ValueError("x_speed must be in range 20 to 25000")

    if not 1 <= TODO_DF_5 <= 48:
      raise ValueError("TODO_DF_5 must be in range 1 to 48")

    if minimal_traverse_height_at_begin_of_command is None:
      minimal_traverse_height_at_begin_of_command = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in minimal_traverse_height_at_begin_of_command):
      raise ValueError("minimal_traverse_height_at_begin_of_command must be in range 0 to 3600")

    if minimal_height_at_command_end is None:
      minimal_height_at_command_end = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in minimal_height_at_command_end):
      raise ValueError("minimal_height_at_command_end must be in range 0 to 3600")

    if y_position is None:
      y_position = [3000] * self.num_channels
    elif not all(0 <= x <= 6500 for x in y_position):
      raise ValueError("y_position must be in range 0 to 6500")

    if liquid_surface_at_function_without_lld is None:
      liquid_surface_at_function_without_lld = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in liquid_surface_at_function_without_lld):
      raise ValueError("liquid_surface_at_function_without_lld must be in range 0 to 3600")

    if dispense_volume is None:
      dispense_volume = [0] * self.num_channels
    elif not all(0 <= x <= 125000 for x in dispense_volume):
      raise ValueError("dispense_volume must be in range 0 to 125000")

    if dispense_speed is None:
      dispense_speed = [500] * self.num_channels
    elif not all(10 <= x <= 10000 for x in dispense_speed):
      raise ValueError("dispense_speed must be in range 10 to 10000")

    if cut_off_speed is None:
      cut_off_speed = [250] * self.num_channels
    elif not all(10 <= x <= 10000 for x in cut_off_speed):
      raise ValueError("cut_off_speed must be in range 10 to 10000")

    if stop_back_volume is None:
      stop_back_volume = [0] * self.num_channels
    elif not all(0 <= x <= 180 for x in stop_back_volume):
      raise ValueError("stop_back_volume must be in range 0 to 180")

    if transport_air_volume is None:
      transport_air_volume = [0] * self.num_channels
    elif not all(0 <= x <= 500 for x in transport_air_volume):
      raise ValueError("transport_air_volume must be in range 0 to 500")

    if not 0 <= tadm_algorithm_on_off <= 1:
      raise ValueError("tadm_algorithm_on_off must be in range 0 to 1")

    if limit_curve_index is None:
      limit_curve_index = [0] * self.num_channels
    elif not all(0 <= x <= 999 for x in limit_curve_index):
      raise ValueError("limit_curve_index must be in range 0 to 999")

    if not 0 <= recording_mode <= 2:
      raise ValueError("recording_mode must be in range 0 to 2")

    return await self.send_command(
      module="A1PM",
      command="DF",
      tm=tip_pattern,
      xa=TODO_DF_1,
      xf=TODO_DF_2,
      xh=TODO_DF_3,
      xy=TODO_DF_4,
      xv=x_speed,
      xi=TODO_DF_5,
      th=minimal_traverse_height_at_begin_of_command,
      te=minimal_height_at_command_end,
      yp=y_position,
      zl=liquid_surface_at_function_without_lld,
      dv=dispense_volume,
      ds=dispense_speed,
      ss=cut_off_speed,
      rv=stop_back_volume,
      ta=transport_air_volume,
      gj=tadm_algorithm_on_off,
      gi=limit_curve_index,
      gk=recording_mode,
    )

  async def nano_pulse_dispense(
    self,
    x_position: List[int],
    y_position: List[int],
    TODO_DB_0: Optional[List[int]] = None,
    liquid_surface_at_function_without_lld: Optional[List[int]] = None,
    minimal_traverse_height_at_begin_of_command: Optional[List[int]] = None,
    minimal_height_at_command_end: Optional[List[int]] = None,
    TODO_DB_1: Optional[List[int]] = None,
    TODO_DB_2: Optional[List[int]] = None,
    TODO_DB_3: Optional[List[int]] = None,
    TODO_DB_4: Optional[List[int]] = None,
    TODO_DB_5: Optional[List[int]] = None,
    TODO_DB_6: Optional[List[int]] = None,
    TODO_DB_7: Optional[List[int]] = None,
    TODO_DB_8: Optional[List[int]] = None,
    TODO_DB_9: Optional[List[int]] = None,
    TODO_DB_10: Optional[List[int]] = None,
    TODO_DB_11: Optional[List[int]] = None,
    TODO_DB_12: Optional[List[int]] = None,
  ):
    """ Nano pulse dispense

    Args:
      TODO_DB_0: (0).
      x_position: X Position [0.1mm].
      y_position: Y Position [0.1mm].
      liquid_surface_at_function_without_lld: Liquid surface at function without LLD [0.1mm].
      minimal_traverse_height_at_begin_of_command: Minimal traverse height at begin of command
        [0.1mm].
      minimal_height_at_command_end: Minimal height at command end [0.1mm].
      TODO_DB_1: (0).
      TODO_DB_2: (0).
      TODO_DB_3: (0).
      TODO_DB_4: (0).
      TODO_DB_5: (0).
      TODO_DB_6: (0).
      TODO_DB_7: (0).
      TODO_DB_8: (0).
      TODO_DB_9: (0).
      TODO_DB_10: (0).
      TODO_DB_11: (0).
      TODO_DB_12: (0).
    """

    if TODO_DB_0 is None:
      TODO_DB_0 = [1] * self.num_channels
    elif not all(0 <= x <= 1 for x in TODO_DB_0):
      raise ValueError("TODO_DB_0 must be in range 0 to 1")

    if not all(0 <= x <= 50000 for x in x_position):
      raise ValueError("x_position must be in range 0 to 50000")

    if y_position is None:
      y_position = [3000] * self.num_channels
    elif not all(0 <= x <= 6500 for x in y_position):
      raise ValueError("y_position must be in range 0 to 6500")

    if liquid_surface_at_function_without_lld is None:
      liquid_surface_at_function_without_lld = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in liquid_surface_at_function_without_lld):
      raise ValueError("liquid_surface_at_function_without_lld must be in range 0 to 3600")

    if minimal_traverse_height_at_begin_of_command is None:
      minimal_traverse_height_at_begin_of_command = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in minimal_traverse_height_at_begin_of_command):
      raise ValueError("minimal_traverse_height_at_begin_of_command must be in range 0 to 3600")

    if minimal_height_at_command_end is None:
      minimal_height_at_command_end = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in minimal_height_at_command_end):
      raise ValueError("minimal_height_at_command_end must be in range 0 to 3600")

    if TODO_DB_1 is None:
      TODO_DB_1 = [0] * self.num_channels
    elif not all(0 <= x <= 20000 for x in TODO_DB_1):
      raise ValueError("TODO_DB_1 must be in range 0 to 20000")

    if TODO_DB_2 is None:
      TODO_DB_2 = [0] * self.num_channels
    elif not all(0 <= x <= 1 for x in TODO_DB_2):
      raise ValueError("TODO_DB_2 must be in range 0 to 1")

    if TODO_DB_3 is None:
      TODO_DB_3 = [0] * self.num_channels
    elif not all(0 <= x <= 10000 for x in TODO_DB_3):
      raise ValueError("TODO_DB_3 must be in range 0 to 10000")

    if TODO_DB_4 is None:
      TODO_DB_4 = [0] * self.num_channels
    elif not all(0 <= x <= 100 for x in TODO_DB_4):
      raise ValueError("TODO_DB_4 must be in range 0 to 100")

    if TODO_DB_5 is None:
      TODO_DB_5 = [0] * self.num_channels
    elif not all(0 <= x <= 1 for x in TODO_DB_5):
      raise ValueError("TODO_DB_5 must be in range 0 to 1")

    if TODO_DB_6 is None:
      TODO_DB_6 = [0] * self.num_channels
    elif not all(0 <= x <= 10000 for x in TODO_DB_6):
      raise ValueError("TODO_DB_6 must be in range 0 to 10000")

    if TODO_DB_7 is None:
      TODO_DB_7 = [0] * self.num_channels
    elif not all(0 <= x <= 100 for x in TODO_DB_7):
      raise ValueError("TODO_DB_7 must be in range 0 to 100")

    if TODO_DB_8 is None:
      TODO_DB_8 = [0] * self.num_channels
    elif not all(0 <= x <= 1 for x in TODO_DB_8):
      raise ValueError("TODO_DB_8 must be in range 0 to 1")

    if TODO_DB_9 is None:
      TODO_DB_9 = [0] * self.num_channels
    elif not all(0 <= x <= 10000 for x in TODO_DB_9):
      raise ValueError("TODO_DB_9 must be in range 0 to 10000")

    if TODO_DB_10 is None:
      TODO_DB_10 = [0] * self.num_channels
    elif not all(0 <= x <= 100 for x in TODO_DB_10):
      raise ValueError("TODO_DB_10 must be in range 0 to 100")

    if TODO_DB_11 is None:
      TODO_DB_11 = [0] * self.num_channels
    elif not all(0 <= x <= 3600 for x in TODO_DB_11):
      raise ValueError("TODO_DB_11 must be in range 0 to 3600")

    if TODO_DB_12 is None:
      TODO_DB_12 = [1] * self.num_channels
    elif not all(0 <= x <= 1 for x in TODO_DB_12):
      raise ValueError("TODO_DB_12 must be in range 0 to 1")

    return await self.send_command(
      module="A1PM",
      command="DB",
      tm=TODO_DB_0,
      xp=x_position,
      yp=y_position,
      zl=liquid_surface_at_function_without_lld,
      th=minimal_traverse_height_at_begin_of_command,
      te=minimal_height_at_command_end,
      pe=TODO_DB_1,
      pd=TODO_DB_2,
      pf=TODO_DB_3,
      pg=TODO_DB_4,
      ph=TODO_DB_5,
      pj=TODO_DB_6,
      pk=TODO_DB_7,
      pl=TODO_DB_8,
      pp=TODO_DB_9,
      pq=TODO_DB_10,
      pi=TODO_DB_11,
      pm=TODO_DB_12,
    )

  async def wash_tips(
    self,
    x_position: List[int],
    y_position: List[int],
    tip_pattern: Optional[List[bool]] = None,
    minimal_traverse_height_at_begin_of_command: Optional[List[int]] = None,
    liquid_surface_at_function_without_lld: Optional[List[int]] = None,
    aspiration_volume: Optional[List[int]] = None,
    aspiration_speed: Optional[List[int]] = None,
    dispense_speed: Optional[List[int]] = None,
    swap_speed: Optional[List[int]] = None,
    soak_time: int = 0,
    wash_cycles: int = 0,
    minimal_height_at_command_end: Optional[List[int]] = None,
  ):
    """ Wash tips

    Args:
      tip_pattern: Tip pattern (channels involved). [0 = not involved, 1 = involved].
      x_position: X Position [0.1mm].
      y_position: Y Position [0.1mm].
      minimal_traverse_height_at_begin_of_command: Minimal traverse height at begin of command
        [0.1mm].
      liquid_surface_at_function_without_lld: Liquid surface at function without LLD [0.1mm].
      aspiration_volume: Aspiration volume [0.01ul].
      aspiration_speed: Aspiration speed [0.1ul]/s.
      dispense_speed: Dispense speed [0.1ul/s].
      swap_speed: Swap speed (on leaving liquid) [0.1mm/s].
      soak_time: (0).
      wash_cycles: (0).
      minimal_height_at_command_end: Minimal height at command end [0.1mm].
    """

    if tip_pattern is None:
      tip_pattern = [False] * self.num_channels
    elif not all(0 <= x <= 1 for x in tip_pattern):
      raise ValueError("tip_pattern must be in range 0 to 1")

    if not all(0 <= x <= 50000 for x in x_position):
      raise ValueError("x_position must be in range 0 to 50000")

    if y_position is None:
      y_position = [3000] * self.num_channels
    elif not all(0 <= x <= 6500 for x in y_position):
      raise ValueError("y_position must be in range 0 to 6500")

    if minimal_traverse_height_at_begin_of_command is None:
      minimal_traverse_height_at_begin_of_command = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in minimal_traverse_height_at_begin_of_command):
      raise ValueError("minimal_traverse_height_at_begin_of_command must be in range 0 to 3600")

    if liquid_surface_at_function_without_lld is None:
      liquid_surface_at_function_without_lld = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in liquid_surface_at_function_without_lld):
      raise ValueError("liquid_surface_at_function_without_lld must be in range 0 to 3600")

    if aspiration_volume is None:
      aspiration_volume = [0] * self.num_channels
    elif not all(0 <= x <= 125000 for x in aspiration_volume):
      raise ValueError("aspiration_volume must be in range 0 to 125000")

    if aspiration_speed is None:
      aspiration_speed = [500] * self.num_channels
    elif not all(10 <= x <= 10000 for x in aspiration_speed):
      raise ValueError("aspiration_speed must be in range 10 to 10000")

    if dispense_speed is None:
      dispense_speed = [500] * self.num_channels
    elif not all(10 <= x <= 10000 for x in dispense_speed):
      raise ValueError("dispense_speed must be in range 10 to 10000")

    if swap_speed is None:
      swap_speed = [100] * self.num_channels
    elif not all(3 <= x <= 1600 for x in swap_speed):
      raise ValueError("swap_speed must be in range 3 to 1600")

    if not 0 <= soak_time <= 3600:
      raise ValueError("soak_time must be in range 0 to 3600")

    if not 0 <= wash_cycles <= 99:
      raise ValueError("wash_cycles must be in range 0 to 99")

    if minimal_height_at_command_end is None:
      minimal_height_at_command_end = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in minimal_height_at_command_end):
      raise ValueError("minimal_height_at_command_end must be in range 0 to 3600")

    return await self.send_command(
      module="A1PM",
      command="DW",
      tm=tip_pattern,
      xp=x_position,
      yp=y_position,
      th=minimal_traverse_height_at_begin_of_command,
      zl=liquid_surface_at_function_without_lld,
      av=aspiration_volume,
      as_=aspiration_speed,
      ds=dispense_speed,
      de=swap_speed,
      sa=soak_time,
      dc=wash_cycles,
      te=minimal_height_at_command_end,
    )

  async def pip_tip_pick_up(
    self,
    x_position: List[int],
    y_position: List[int],
    tip_pattern: Optional[List[bool]] = None,
    tip_type: Optional[List[int]] = None,
    begin_z_deposit_position: Optional[List[int]] = None,
    end_z_deposit_position: Optional[List[int]] = None,
    minimal_traverse_height_at_begin_of_command: Optional[List[int]] = None,
    minimal_height_at_command_end: Optional[List[int]] = None,
    blow_out_air_volume: Optional[List[int]] = None,
    tip_handling_method: Optional[List[int]] = None,
  ):
    """ Tip Pick up

    Args:
      x_position: X Position [0.1mm].
      y_position: Y Position [0.1mm].
      tip_pattern: Tip pattern (channels involved). [0 = not involved, 1 = involved].
      tip_type: Tip type (see command TT).
      begin_z_deposit_position: (0).
      end_z_deposit_position: Z deposit position [0.1mm] (collar bearing position).
      minimal_traverse_height_at_begin_of_command: Minimal traverse height at begin of command
       [0.1mm].
      minimal_height_at_command_end: Minimal height at command end [0.1mm].
      blow_out_air_volume: Blow out air volume [0.01ul].
      tip_handling_method: Tip handling method. (Unconfirmed, but likely: 0 = auto selection (see
        command TT parameter tu), 1 = pick up out of rack, 2 = pick up out of wash liquid (slowly))
    """

    if not all(0 <= x <= 50000 for x in x_position):
      raise ValueError("x_position must be in range 0 to 50000")

    if y_position is None:
      y_position = [3000] * self.num_channels
    elif not all(0 <= x <= 6500 for x in y_position):
      raise ValueError("y_position must be in range 0 to 6500")

    if tip_pattern is None:
      tip_pattern = [False] * self.num_channels
    elif not all(0 <= x <= 1 for x in tip_pattern):
      raise ValueError("tip_pattern must be in range 0 to 1")

    if tip_type is None:
      tip_type = [4] * self.num_channels
    elif not all(0 <= x <= 199 for x in tip_type):
      raise ValueError("tip_type must be in range 0 to 199")

    if begin_z_deposit_position is None:
      begin_z_deposit_position = [0] * self.num_channels
    elif not all(0 <= x <= 3600 for x in begin_z_deposit_position):
      raise ValueError("begin_z_deposit_position must be in range 0 to 3600")

    if end_z_deposit_position is None:
      end_z_deposit_position = [0] * self.num_channels
    elif not all(0 <= x <= 3600 for x in end_z_deposit_position):
      raise ValueError("end_z_deposit_position must be in range 0 to 3600")

    if minimal_traverse_height_at_begin_of_command is None:
      minimal_traverse_height_at_begin_of_command = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in minimal_traverse_height_at_begin_of_command):
      raise ValueError("minimal_traverse_height_at_begin_of_command must be in range 0 to 3600")

    if minimal_height_at_command_end is None:
      minimal_height_at_command_end = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in minimal_height_at_command_end):
      raise ValueError("minimal_height_at_command_end must be in range 0 to 3600")

    if blow_out_air_volume is None:
      blow_out_air_volume = [0] * self.num_channels
    elif not all(0 <= x <= 125000 for x in blow_out_air_volume):
      raise ValueError("blow_out_air_volume must be in range 0 to 125000")

    if tip_handling_method is None:
      tip_handling_method = [0] * self.num_channels
    elif not all(0 <= x <= 9 for x in tip_handling_method):
      raise ValueError("tip_handling_method must be in range 0 to 9")

    return await self.send_command(
      module="A1PM",
      command="TP",
      xp=x_position,
      yp=y_position,
      tm=tip_pattern,
      tt=tip_type,
      tp=begin_z_deposit_position,
      tz=end_z_deposit_position,
      th=minimal_traverse_height_at_begin_of_command,
      te=minimal_height_at_command_end,
      ba=blow_out_air_volume,
      td=tip_handling_method,
    )

  async def pip_tip_discard(
    self,
    x_position: List[int],
    y_position: List[int],
    begin_z_deposit_position: Optional[List[int]] = None,
    end_z_deposit_position: Optional[List[int]] = None,
    minimal_traverse_height_at_begin_of_command: Optional[List[int]] = None,
    minimal_height_at_command_end: Optional[List[int]] = None,
    tip_pattern: Optional[List[bool]] = None,
    TODO_TR_2: int = 0,
    tip_handling_method: Optional[List[int]] = None,
  ):
    """ Tip Discard

    Args:
      x_position: X Position [0.1mm].
      y_position: Y Position [0.1mm].
      begin_z_deposit_position: (0).
      end_z_deposit_position: Z deposit position [0.1mm] (collar bearing position).
      minimal_traverse_height_at_begin_of_command: Minimal traverse height at begin of command
        [0.1mm].
      minimal_height_at_command_end: Minimal height at command end [0.1mm].
      tip_pattern: Tip pattern (channels involved). [0 = not involved, 1 = involved].
      TODO_TR_2: (0).
      tip_handling_method: Tip handling method.
    """

    if not all(0 <= x <= 50000 for x in x_position):
      raise ValueError("x_position must be in range 0 to 50000")

    if y_position is None:
      y_position = [3000] * self.num_channels
    elif not all(0 <= x <= 6500 for x in y_position):
      raise ValueError("y_position must be in range 0 to 6500")

    if begin_z_deposit_position is None:
      begin_z_deposit_position = [0] * self.num_channels
    elif not all(0 <= x <= 3600 for x in begin_z_deposit_position):
      raise ValueError("begin_z_deposit_position must be in range 0 to 3600")

    if end_z_deposit_position is None:
      end_z_deposit_position = [0] * self.num_channels
    elif not all(0 <= x <= 3600 for x in end_z_deposit_position):
      raise ValueError("end_z_deposit_position must be in range 0 to 3600")

    if minimal_traverse_height_at_begin_of_command is None:
      minimal_traverse_height_at_begin_of_command = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in minimal_traverse_height_at_begin_of_command):
      raise ValueError("minimal_traverse_height_at_begin_of_command must be in range 0 to 3600")

    if minimal_height_at_command_end is None:
      minimal_height_at_command_end = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in minimal_height_at_command_end):
      raise ValueError("minimal_height_at_command_end must be in range 0 to 3600")

    if tip_pattern is None:
      tip_pattern = [False] * self.num_channels
    elif not all(0 <= x <= 1 for x in tip_pattern):
      raise ValueError("tip_pattern must be in range 0 to 1")

    if not -1000 <= TODO_TR_2 <= 1000:
      raise ValueError("TODO_TR_2 must be in range -1000 to 1000")

    if tip_handling_method is None:
      tip_handling_method = [0] * self.num_channels
    elif not all(0 <= x <= 9 for x in tip_handling_method):
      raise ValueError("tip_handling_method must be in range 0 to 9")

    return await self.send_command(
      module="A1PM",
      command="TR",
      xp=x_position,
      yp=y_position,
      tp=begin_z_deposit_position,
      tz=end_z_deposit_position,
      th=minimal_traverse_height_at_begin_of_command,
      te=minimal_height_at_command_end,
      tm=tip_pattern,
      ts=TODO_TR_2,
      td=tip_handling_method,
    )

  async def search_for_teach_in_signal_in_x_direction(
    self,
    channel_index: int = 1,
    x_search_distance: int = 0,
    x_speed: int = 270,
  ):
    """ Search for Teach in signal in X direction

    Args:
      channel_index: Channel index.
      x_search_distance: X search distance [0.1mm].
      x_speed: X speed [0.1mm/s].
    """

    if not 1 <= channel_index <= 16:
      raise ValueError("channel_index must be in range 1 to 16")

    if not -50000 <= x_search_distance <= 50000:
      raise ValueError("x_search_distance must be in range -50000 to 50000")

    if not 20 <= x_speed <= 25000:
      raise ValueError("x_speed must be in range 20 to 25000")

    return await self.send_command(
      module="A1PM",
      command="DL",
      pn=channel_index,
      xs=x_search_distance,
      xv=x_speed,
    )

  async def position_all_channels_in_y_direction(
    self,
    y_position: List[int],
  ):
    """ Position all channels in Y direction

    Args:
      y_position: Y Position [0.1mm].
    """

    if y_position is None:
      y_position = [3000] * self.num_channels
    elif not all(0 <= x <= 6500 for x in y_position):
      raise ValueError("y_position must be in range 0 to 6500")

    return await self.send_command(
      module="A1PM",
      command="DY",
      yp=y_position,
    )

  async def position_all_channels_in_z_direction(
    self,
    z_position: Optional[List[int]] = None,
  ):
    """ Position all channels in Z direction

    Args:
      z_position: Z Position [0.1mm].
    """

    if z_position is None:
      z_position = [0] * self.num_channels
    elif not all(0 <= x <= 3600 for x in z_position):
      raise ValueError("z_position must be in range 0 to 3600")

    return await self.send_command(
      module="A1PM",
      command="DZ",
      zp=z_position,
    )

  async def position_single_channel_in_y_direction(
    self,
    channel_index: int = 1,
    y_position: int = 3000,
  ):
    """ Position single channel in Y direction

    Args:
      channel_index: Channel index.
      y_position: Y Position [0.1mm].
    """

    if not 1 <= channel_index <= 16:
      raise ValueError("channel_index must be in range 1 to 16")

    if not 0 <= y_position <= 6500:
      raise ValueError("y_position must be in range 0 to 6500")

    return await self.send_command(
      module="A1PM",
      command="DV",
      pn=channel_index,
      yj=y_position,
    )

  async def position_single_channel_in_z_direction(
    self,
    channel_index: int = 1,
    z_position: int = 0,
  ):
    """ Position single channel in Z direction

    Args:
      channel_index: Channel index.
      z_position: Z Position [0.1mm].
    """

    if not 1 <= channel_index <= 16:
      raise ValueError("channel_index must be in range 1 to 16")

    if not 0 <= z_position <= 3600:
      raise ValueError("z_position must be in range 0 to 3600")

    return await self.send_command(
      module="A1PM",
      command="DU",
      pn=channel_index,
      zj=z_position,
    )

  async def move_to_defined_position(
    self,
    x_position: List[int],
    y_position: List[int],
    tip_pattern: Optional[List[bool]] = None,
    minimal_traverse_height_at_begin_of_command: Optional[List[int]] = None,
    z_position: Optional[List[int]] = None,
  ):
    """ Move to defined position

    Args:
      tip_pattern: Tip pattern (channels involved). [0 = not involved, 1 = involved].
      x_position: X Position [0.1mm].
      y_position: Y Position [0.1mm].
      minimal_traverse_height_at_begin_of_command: Minimal traverse height at begin of command
        [0.1mm].
      z_position: Z Position [0.1mm].
    """

    if tip_pattern is None:
      tip_pattern = [False] * self.num_channels
    elif not all(0 <= x <= 1 for x in tip_pattern):
      raise ValueError("tip_pattern must be in range 0 to 1")

    if not all(0 <= x <= 50000 for x in x_position):
      raise ValueError("x_position must be in range 0 to 50000")

    if y_position is None:
      y_position = [3000] * self.num_channels
    elif not all(0 <= x <= 6500 for x in y_position):
      raise ValueError("y_position must be in range 0 to 6500")

    if minimal_traverse_height_at_begin_of_command is None:
      minimal_traverse_height_at_begin_of_command = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in minimal_traverse_height_at_begin_of_command):
      raise ValueError("minimal_traverse_height_at_begin_of_command must be in range 0 to 3600")

    if z_position is None:
      z_position = [0] * self.num_channels
    elif not all(0 <= x <= 3600 for x in z_position):
      raise ValueError("z_position must be in range 0 to 3600")

    return await self.send_command(
      module="A1PM",
      command="DN",
      tm=tip_pattern,
      xp=x_position,
      yp=y_position,
      th=minimal_traverse_height_at_begin_of_command,
      zp=z_position,
    )

  async def teach_rack_using_channel_n(
    self,
    channel_index: int = 1,
    gap_center_x_direction: int = 0,
    gap_center_y_direction: int = 3000,
    gap_center_z_direction: int = 0,
    minimal_height_at_command_end: Optional[List[int]] = None,
  ):
    """ Teach rack using channel n

    Attention! Channels not involved must first be taken out of measurement range.

    Args:
      channel_index: Channel index.
      gap_center_x_direction: Gap center X direction [0.1mm].
      gap_center_y_direction: Gap center Y direction [0.1mm].
      gap_center_z_direction: Gap center Z direction [0.1mm].
      minimal_height_at_command_end: Minimal height at command end [0.1mm].
    """

    if not 1 <= channel_index <= 16:
      raise ValueError("channel_index must be in range 1 to 16")

    if not -50000 <= gap_center_x_direction <= 50000:
      raise ValueError("gap_center_x_direction must be in range -50000 to 50000")

    if not 0 <= gap_center_y_direction <= 6500:
      raise ValueError("gap_center_y_direction must be in range 0 to 6500")

    if not 0 <= gap_center_z_direction <= 3600:
      raise ValueError("gap_center_z_direction must be in range 0 to 3600")

    if minimal_height_at_command_end is None:
      minimal_height_at_command_end = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in minimal_height_at_command_end):
      raise ValueError("minimal_height_at_command_end must be in range 0 to 3600")

    return await self.send_command(
      module="A1PM",
      command="DT",
      pn=channel_index,
      xa=gap_center_x_direction,
      yj=gap_center_y_direction,
      zj=gap_center_z_direction,
      te=minimal_height_at_command_end,
    )

  async def expose_channel_n(
    self,
    channel_index: int = 1,
  ):
    """ Expose channel n

    Args:
      channel_index: Channel index.
    """

    if not 1 <= channel_index <= 16:
      raise ValueError("channel_index must be in range 1 to 16")

    return await self.send_command(
      module="A1PM",
      command="DQ",
      pn=channel_index,
    )

  async def calculates_check_sums_and_compares_them_with_the_value_saved_in_flash_eprom(
    self,
    TODO_DC_0: int = 0,
    TODO_DC_1: int = 3000,
    tip_type: Optional[List[int]] = None,
    TODO_DC_2: Optional[List[int]] = None,
    z_deposit_position: Optional[List[int]] = None,
    minimal_traverse_height_at_begin_of_command: Optional[List[int]] = None,
    first_pip_channel_node_no: int = 1,
  ):
    """ Calculates check sums and compares them with the value saved in Flash EPROM

    Args:
      TODO_DC_0: (0).
      TODO_DC_1: (0).
      tip_type: Tip type (see command TT).
      TODO_DC_2: (0).
      z_deposit_position: Z deposit position [0.1mm] (collar bearing position).
      minimal_traverse_height_at_begin_of_command: Minimal traverse height at begin of command
        [0.1mm].
      first_pip_channel_node_no: First (lower) pip. channel node no. (0 = disabled).
    """

    if not -50000 <= TODO_DC_0 <= 50000:
      raise ValueError("TODO_DC_0 must be in range -50000 to 50000")

    if not 0 <= TODO_DC_1 <= 6500:
      raise ValueError("TODO_DC_1 must be in range 0 to 6500")

    if tip_type is None:
      tip_type = [4] * self.num_channels
    elif not all(0 <= x <= 199 for x in tip_type):
      raise ValueError("tip_type must be in range 0 to 199")

    if TODO_DC_2 is None:
      TODO_DC_2 = [0] * self.num_channels
    elif not all(0 <= x <= 3600 for x in TODO_DC_2):
      raise ValueError("TODO_DC_2 must be in range 0 to 3600")

    if z_deposit_position is None:
      z_deposit_position = [0] * self.num_channels
    elif not all(0 <= x <= 3600 for x in z_deposit_position):
      raise ValueError("z_deposit_position must be in range 0 to 3600")

    if minimal_traverse_height_at_begin_of_command is None:
      minimal_traverse_height_at_begin_of_command = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in minimal_traverse_height_at_begin_of_command):
      raise ValueError("minimal_traverse_height_at_begin_of_command must be in range 0 to 3600")

    if not 1 <= first_pip_channel_node_no <= 16:
      raise ValueError("first_pip_channel_node_no must be in range 1 to 16")

    return await self.send_command(
      module="A1PM",
      command="DC",
      xa=TODO_DC_0,
      yj=TODO_DC_1,
      tt=tip_type,
      tp=TODO_DC_2,
      tz=z_deposit_position,
      th=minimal_traverse_height_at_begin_of_command,
      pa=first_pip_channel_node_no,
    )

  async def discard_core_gripper_tool(
    self,
    gripper_tool_x_position: int = 0,
    first_gripper_tool_y_pos: int = 3000,
    tip_type: Optional[List[int]] = None,
    begin_z_deposit_position: Optional[List[int]] = None,
    end_z_deposit_position: Optional[List[int]] = None,
    minimal_traverse_height_at_begin_of_command: Optional[List[int]] = None,
    first_pip_channel_node_no: int = 1,
    minimal_height_at_command_end: Optional[List[int]] = None,
  ):
    """ Discard CoRe gripper tool

    Args:
      gripper_tool_x_position: (0).
      first_gripper_tool_y_pos: First (lower channel) CoRe gripper tool Y pos. [0.1mm]
      tip_type: Tip type (see command TT).
      begin_z_deposit_position: (0).
      end_z_deposit_position: Z deposit position [0.1mm] (collar bearing position).
      minimal_traverse_height_at_begin_of_command: Minimal traverse height at begin of command
        [0.1mm].
      first_pip_channel_node_no: First (lower) pip. channel node no. (0 = disabled).
      minimal_height_at_command_end: Minimal height at command end [0.1mm].
    """

    if not -50000 <= gripper_tool_x_position <= 50000:
      raise ValueError("gripper_tool_x_position must be in range -50000 to 50000")

    if not 0 <= first_gripper_tool_y_pos <= 6500:
      raise ValueError("first_gripper_tool_y_pos must be in range 0 to 6500")

    if tip_type is None:
      tip_type = [4] * self.num_channels
    elif not all(0 <= x <= 199 for x in tip_type):
      raise ValueError("tip_type must be in range 0 to 199")

    if begin_z_deposit_position is None:
      begin_z_deposit_position = [0] * self.num_channels
    elif not all(0 <= x <= 3600 for x in begin_z_deposit_position):
      raise ValueError("begin_z_deposit_position must be in range 0 to 3600")

    if end_z_deposit_position is None:
      end_z_deposit_position = [0] * self.num_channels
    elif not all(0 <= x <= 3600 for x in end_z_deposit_position):
      raise ValueError("end_z_deposit_position must be in range 0 to 3600")

    if minimal_traverse_height_at_begin_of_command is None:
      minimal_traverse_height_at_begin_of_command = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in minimal_traverse_height_at_begin_of_command):
      raise ValueError("minimal_traverse_height_at_begin_of_command must be in range 0 to 3600")

    if not 1 <= first_pip_channel_node_no <= 16:
      raise ValueError("first_pip_channel_node_no must be in range 1 to 16")

    if minimal_height_at_command_end is None:
      minimal_height_at_command_end = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in minimal_height_at_command_end):
      raise ValueError("minimal_height_at_command_end must be in range 0 to 3600")

    return await self.send_command(
      module="A1PM",
      command="DJ",
      xa=gripper_tool_x_position,
      yj=first_gripper_tool_y_pos,
      tt=tip_type,
      tp=begin_z_deposit_position,
      tz=end_z_deposit_position,
      th=minimal_traverse_height_at_begin_of_command,
      pa=first_pip_channel_node_no,
      te=minimal_height_at_command_end,
    )

  async def grip_plate(
    self,
    plate_center_x_direction: int = 0,
    plate_center_y_direction: int = 3000,
    plate_center_z_direction: int = 0,
    z_speed: int = 1287,
    open_gripper_position: int = 860,
    plate_width: int = 800,
    acceleration_index: int = 4,
    grip_strength: int = 30,
    minimal_traverse_height_at_begin_of_command: Optional[List[int]] = None,
    minimal_height_at_command_end: Optional[List[int]] = None,
  ):
    """ Grip plate

    Args:
      plate_center_x_direction: Plate center X direction [0.1mm].
      plate_center_y_direction: Plate center Y direction [0.1mm].
      plate_center_z_direction: Plate center Z direction [0.1mm].
      z_speed: Z speed [0.1mm/sec].
      open_gripper_position: Open gripper position [0.1mm].
      plate_width: Plate width [0.1mm].
      acceleration_index: Acceleration index.
      grip_strength: Grip strength (0 = low 99 = high).
      minimal_traverse_height_at_begin_of_command: Minimal traverse height at begin of command
        [0.1mm].
      minimal_height_at_command_end: Minimal height at command end [0.1mm].
    """

    if not -50000 <= plate_center_x_direction <= 50000:
      raise ValueError("plate_center_x_direction must be in range -50000 to 50000")

    if not 0 <= plate_center_y_direction <= 6500:
      raise ValueError("plate_center_y_direction must be in range 0 to 6500")

    if not 0 <= plate_center_z_direction <= 3600:
      raise ValueError("plate_center_z_direction must be in range 0 to 3600")

    if not 3 <= z_speed <= 1600:
      raise ValueError("z_speed must be in range 3 to 1600")

    if not 0 <= open_gripper_position <= 9999:
      raise ValueError("open_gripper_position must be in range 0 to 9999")

    if not 0 <= plate_width <= 9999:
      raise ValueError("plate_width must be in range 0 to 9999")

    if not 0 <= acceleration_index <= 4:
      raise ValueError("acceleration_index must be in range 0 to 4")

    if not 0 <= grip_strength <= 99:
      raise ValueError("grip_strength must be in range 0 to 99")

    if minimal_traverse_height_at_begin_of_command is None:
      minimal_traverse_height_at_begin_of_command = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in minimal_traverse_height_at_begin_of_command):
      raise ValueError("minimal_traverse_height_at_begin_of_command must be in range 0 to 3600")

    if minimal_height_at_command_end is None:
      minimal_height_at_command_end = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in minimal_height_at_command_end):
      raise ValueError("minimal_height_at_command_end must be in range 0 to 3600")

    return await self.send_command(
      module="A1PM",
      command="DG",
      xa=plate_center_x_direction,
      yj=plate_center_y_direction,
      zj=plate_center_z_direction,
      zy=z_speed,
      yo=open_gripper_position,
      yg=plate_width,
      ai=acceleration_index,
      yw=grip_strength,
      th=minimal_traverse_height_at_begin_of_command,
      te=minimal_height_at_command_end,
    )

  async def put_plate(
    self,
    plate_center_x_direction: int = 0,
    plate_center_y_direction: int = 3000,
    plate_center_z_direction: int = 0,
    press_on_distance: int = 5,
    z_speed: int = 1287,
    open_gripper_position: int = 860,
    minimal_traverse_height_at_begin_of_command: Optional[List[int]] = None,
    minimal_height_at_command_end: Optional[List[int]] = None,
  ):
    """ Put plate

    Args:
      plate_center_x_direction: Plate center X direction [0.1mm].
      plate_center_y_direction: Plate center Y direction [0.1mm].
      plate_center_z_direction: Plate center Z direction [0.1mm].
      press_on_distance: Press on distance [0.1mm].
      z_speed: Z speed [0.1mm/sec].
      open_gripper_position: Open gripper position [0.1mm].
      minimal_traverse_height_at_begin_of_command: Minimal traverse height at begin of command
        [0.1mm].
      minimal_height_at_command_end: Minimal height at command end [0.1mm].
    """

    if not -50000 <= plate_center_x_direction <= 50000:
      raise ValueError("plate_center_x_direction must be in range -50000 to 50000")

    if not 0 <= plate_center_y_direction <= 6500:
      raise ValueError("plate_center_y_direction must be in range 0 to 6500")

    if not 0 <= plate_center_z_direction <= 3600:
      raise ValueError("plate_center_z_direction must be in range 0 to 3600")

    if not 0 <= press_on_distance <= 999:
      raise ValueError("press_on_distance must be in range 0 to 999")

    if not 3 <= z_speed <= 1600:
      raise ValueError("z_speed must be in range 3 to 1600")

    if not 0 <= open_gripper_position <= 9999:
      raise ValueError("open_gripper_position must be in range 0 to 9999")

    if minimal_traverse_height_at_begin_of_command is None:
      minimal_traverse_height_at_begin_of_command = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in minimal_traverse_height_at_begin_of_command):
      raise ValueError("minimal_traverse_height_at_begin_of_command must be in range 0 to 3600")

    if minimal_height_at_command_end is None:
      minimal_height_at_command_end = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in minimal_height_at_command_end):
      raise ValueError("minimal_height_at_command_end must be in range 0 to 3600")

    return await self.send_command(
      module="A1PM",
      command="DR",
      xa=plate_center_x_direction,
      yj=plate_center_y_direction,
      zj=plate_center_z_direction,
      zi=press_on_distance,
      zy=z_speed,
      yo=open_gripper_position,
      th=minimal_traverse_height_at_begin_of_command,
      te=minimal_height_at_command_end,
    )

  async def move_to_position(
    self,
    plate_center_x_direction: int = 0,
    plate_center_y_direction: int = 3000,
    plate_center_z_direction: int = 0,
    z_speed: int = 1287,
    minimal_traverse_height_at_begin_of_command: Optional[List[int]] = None,
  ):
    """ Move to position

    Args:
      plate_center_x_direction: Plate center X direction [0.1mm].
      plate_center_y_direction: Plate center Y direction [0.1mm].
      plate_center_z_direction: Plate center Z direction [0.1mm].
      z_speed: Z speed [0.1mm/sec].
      minimal_traverse_height_at_begin_of_command: Minimal traverse height at begin of command
        [0.1mm].
    """

    if not -50000 <= plate_center_x_direction <= 50000:
      raise ValueError("plate_center_x_direction must be in range -50000 to 50000")

    if not 0 <= plate_center_y_direction <= 6500:
      raise ValueError("plate_center_y_direction must be in range 0 to 6500")

    if not 0 <= plate_center_z_direction <= 3600:
      raise ValueError("plate_center_z_direction must be in range 0 to 3600")

    if not 3 <= z_speed <= 1600:
      raise ValueError("z_speed must be in range 3 to 1600")

    if minimal_traverse_height_at_begin_of_command is None:
      minimal_traverse_height_at_begin_of_command = [3600] * self.num_channels
    elif not all(0 <= x <= 3600 for x in minimal_traverse_height_at_begin_of_command):
      raise ValueError("minimal_traverse_height_at_begin_of_command must be in range 0 to 3600")

    return await self.send_command(
      module="A1PM",
      command="DH",
      xa=plate_center_x_direction,
      yj=plate_center_y_direction,
      zj=plate_center_z_direction,
      zy=z_speed,
      th=minimal_traverse_height_at_begin_of_command,
    )

  async def release_object(
    self,
    first_pip_channel_node_no: int = 1,
  ):
    """ Release object

    Args:
      first_pip_channel_node_no: First (lower) pip. channel node no. (0 = disabled).
    """

    if not 1 <= first_pip_channel_node_no <= 16:
      raise ValueError("first_pip_channel_node_no must be in range 1 to 16")

    return await self.send_command(
      module="A1PM",
      command="DO",
      pa=first_pip_channel_node_no,
    )

  async def set_any_parameter_within_this_module(self):
    """ Set any parameter within this module """

    return await self.send_command(
      module="A1PM",
      command="AA",
    )

  async def request_y_positions_of_all_channels(self):
    """ Request Y Positions of all channels """

    return await self.send_command(
      module="A1PM",
      command="RY",
    )

  async def request_y_position_of_channel_n(self):
    """ Request Y Position of channel n """

    return await self.send_command(
      module="A1PM",
      command="RB",
    )

  async def request_z_positions_of_all_channels(self):
    """ Request Z Positions of all channels """

    return await self.send_command(
      module="A1PM",
      command="RZ",
    )

  async def request_z_position_of_channel_n(self):
    """ Request Z Position of channel n """

    return await self.send_command(
      module="A1PM",
      command="RD",
    )

  async def query_tip_presence(self):
    """ Query Tip presence """

    return await self.send_command(
      module="A1PM",
      command="QA",
    )

  async def request_height_of_last_lld(self):
    """ Request height of last LLD """

    return await self.send_command(
      module="A1PM",
      command="RL",
    )

  async def request_channel_dispense_on_fly_status(self):
    """ Request channel dispense on fly status """

    return await self.send_command(
      module="A1PM",
      command="QF",
    )

  async def core96_initialize(
    self,
    x_position: int = 5000,
    y_position: int = 5000,
    z_position: int = 0,
    minimal_traverse_height_at_begin_of_command: int = 3900,
    minimal_height_at_command_end: int = 3900,
    end_z_deposit_position: int = 0,
    tip_type: int = 4,
  ):
    """ Initialize 96 head.

    Args:
      x_position: X Position [0.1mm].
      y_position: Y Position [0.1mm].
      z_position: Z Position [0.1mm].
      minimal_traverse_height_at_begin_of_command: Minimal traverse height at begin of command
        [0.1mm].
      minimal_height_at_command_end: Minimal height at command end [0.1mm].
      end_z_deposit_position: Z deposit position [0.1mm] (collar bearing position). (not documented,
        but present in the log files.)
      tip_type: Tip type (see command TT).
    """

    if not -500000 <= x_position <= 50000:
      raise ValueError("x_position must be in range -500000 to 50000")

    if not 422 <= y_position <= 5921:
      raise ValueError("y_position must be in range 422 to 5921")

    if not 0 <= z_position <= 3900:
      raise ValueError("z_position must be in range 0 to 3900")

    if not 0 <= minimal_traverse_height_at_begin_of_command <= 3900:
      raise ValueError("minimal_traverse_height_at_begin_of_command must be in range 0 to 3900")

    if not 0 <= minimal_height_at_command_end <= 3900:
      raise ValueError("minimal_height_at_command_end must be in range 0 to 3900")

    if not 0 <= end_z_deposit_position <= 3600:
      raise ValueError("end_z_deposit_position must be in range 0 to 3600")

    if not 0 <= tip_type <= 199:
      raise ValueError("tip_type must be in range 0 to 199")

    return await self.send_command(
      module="A1HM",
      command="DI",
      xp=x_position,
      yp=y_position,
      zp=z_position,
      th=minimal_traverse_height_at_begin_of_command,
      te=minimal_height_at_command_end,
      tz=end_z_deposit_position,
      tt=tip_type,
    )

  async def core96_aspiration_of_liquid(
    self,
    type_of_aspiration: int = 0,
    x_position: int = 5000,
    y_position: int = 5000,
    minimal_traverse_height_at_begin_of_command: int = 3900,
    minimal_height_at_command_end: int = 3900,
    lld_search_height: int = 0,
    liquid_surface_at_function_without_lld: int = 3900,
    pull_out_distance_to_take_transport_air_in_function_without_lld: int = 50,
    minimum_height: int = 3900,
    tube_2nd_section_height_measured_from_zm: int = 0,
    tube_2nd_section_ratio: int = 0,
    immersion_depth: int = 0,
    surface_following_distance: int = 0,
    aspiration_volume: int = 0,
    aspiration_speed: int = 2000,
    transport_air_volume: int = 0,
    blow_out_air_volume: int = 1000,
    pre_wetting_volume: int = 0,
    lld_mode: int = 1,
    lld_sensitivity: int = 1,
    swap_speed: int = 100,
    settling_time: int = 5,
    mix_volume: int = 0,
    mix_cycles: int = 0,
    mix_position_in_z_direction_from_liquid_surface: int = 0,
    surface_following_distance_during_mixing: int = 0,
    mix_speed: int = 2000,
    limit_curve_index: int = 0,
    tadm_channel_pattern: Optional[List[bool]] = None,
    tadm_algorithm_on_off: int = 0,
    recording_mode: int = 0,
  ):
    """ Aspiration of liquid using the 96 head.

    Args:
      type_of_aspiration: Type of aspiration (0 = simple 1 = sequence 2 = cup emptied).
      x_position: X Position [0.1mm].
      y_position: Y Position [0.1mm].
      minimal_traverse_height_at_begin_of_command: Minimal traverse height at begin of
        command [0.1mm].
      minimal_height_at_command_end: Minimal height at command end [0.1mm].
      lld_search_height: LLD search height [0.1mm].
      liquid_surface_at_function_without_lld: Liquid surface at function without LLD [0.1mm].
      pull_out_distance_to_take_transport_air_in_function_without_lld:
          Pull out distance to take transp. air in function without LLD [0.1mm]
        .
      minimum_height: Minimum height (maximum immersion depth) [0.1mm].
      tube_2nd_section_height_measured_from_zm: Tube 2nd section height measured from zm [0.1mm].
      tube_2nd_section_ratio: Tube 2nd section ratio.
      immersion_depth: Immersion depth [0.1mm].
      surface_following_distance: Surface following distance [0.1mm].
      aspiration_volume: Aspiration volume [0.01ul].
      aspiration_speed: Aspiration speed [0.1ul]/s.
      transport_air_volume: Transport air volume [0.1ul].
      blow_out_air_volume: Blow out air volume [0.01ul].
      pre_wetting_volume: Pre wetting volume [0.1ul].
      lld_mode: LLD Mode (0 = off).
      lld_sensitivity: LLD sensitivity (1 = high, 4 = low).
      swap_speed: Swap speed (on leaving liquid) [0.1mm/s].
      settling_time: Settling time [0.1s].
      mix_volume: Mix volume [0.1ul].
      mix_cycles: Mix cycles.
      mix_position_in_z_direction_from_liquid_surface: Mix position in Z direction from liquid
        surface[0.1mm].
      surface_following_distance_during_mixing: Surface following distance during mixing [0.1mm].
      mix_speed: Mix speed [0.1ul/s].
      limit_curve_index: Limit curve index.
      tadm_channel_pattern: TADM Channel pattern.
      tadm_algorithm_on_off: TADM algorithm on/off (0 = off).
      recording_mode:
          Recording mode (0 = no 1 = TADM errors only 2 = all TADM measurements)
        .
    """

    if not 0 <= type_of_aspiration <= 2:
      raise ValueError("type_of_aspiration must be in range 0 to 2")

    if not -500000 <= x_position <= 50000:
      raise ValueError("x_position must be in range -500000 to 50000")

    if not 422 <= y_position <= 5921:
      raise ValueError("y_position must be in range 422 to 5921")

    if not 0 <= minimal_traverse_height_at_begin_of_command <= 3900:
      raise ValueError("minimal_traverse_height_at_begin_of_command must be in range 0 to 3900")

    if not 0 <= minimal_height_at_command_end <= 3900:
      raise ValueError("minimal_height_at_command_end must be in range 0 to 3900")

    if not 0 <= lld_search_height <= 3900:
      raise ValueError("lld_search_height must be in range 0 to 3900")

    if not 0 <= liquid_surface_at_function_without_lld <= 3900:
      raise ValueError("liquid_surface_at_function_without_lld must be in range 0 to 3900")

    if not 0 <= pull_out_distance_to_take_transport_air_in_function_without_lld <= 3900:
      raise ValueError("pull_out_distance_to_take_transport_air_in_function_without_lld must be in "
                       "range 0 to 3900")

    if not 0 <= minimum_height <= 3900:
      raise ValueError("minimum_height must be in range 0 to 3900")

    if not 0 <= tube_2nd_section_height_measured_from_zm <= 3900:
      raise ValueError("tube_2nd_section_height_measured_from_zm must be in range 0 to 3900")

    if not 0 <= tube_2nd_section_ratio <= 10000:
      raise ValueError("tube_2nd_section_ratio must be in range 0 to 10000")

    if not -990 <= immersion_depth <= 990:
      raise ValueError("immersion_depth must be in range -990 to 990")

    if not 0 <= surface_following_distance <= 990:
      raise ValueError("surface_following_distance must be in range 0 to 990")

    if not 0 <= aspiration_volume <= 115000:
      raise ValueError("aspiration_volume must be in range 0 to 115000")

    if not 3 <= aspiration_speed <= 5000:
      raise ValueError("aspiration_speed must be in range 3 to 5000")

    if not 0 <= transport_air_volume <= 1000:
      raise ValueError("transport_air_volume must be in range 0 to 1000")

    if not 0 <= blow_out_air_volume <= 115000:
      raise ValueError("blow_out_air_volume must be in range 0 to 115000")

    if not 0 <= pre_wetting_volume <= 11500:
      raise ValueError("pre_wetting_volume must be in range 0 to 11500")

    if not 0 <= lld_mode <= 1:
      raise ValueError("lld_mode must be in range 0 to 1")

    if not 1 <= lld_sensitivity <= 4:
      raise ValueError("lld_sensitivity must be in range 1 to 4")

    if not 3 <= swap_speed <= 1000:
      raise ValueError("swap_speed must be in range 3 to 1000")

    if not 0 <= settling_time <= 99:
      raise ValueError("settling_time must be in range 0 to 99")

    if not 0 <= mix_volume <= 11500:
      raise ValueError("mix_volume must be in range 0 to 11500")

    if not 0 <= mix_cycles <= 99:
      raise ValueError("mix_cycles must be in range 0 to 99")

    if not 0 <= mix_position_in_z_direction_from_liquid_surface <= 990:
      raise ValueError("mix_position_in_z_direction_from_liquid_surface must be in range 0 to 990")

    if not 0 <= surface_following_distance_during_mixing <= 990:
      raise ValueError("surface_following_distance_during_mixing must be in range 0 to 990")

    if not 3 <= mix_speed <= 5000:
      raise ValueError("mix_speed must be in range 3 to 5000")

    if not 0 <= limit_curve_index <= 999:
      raise ValueError("limit_curve_index must be in range 0 to 999")

    if tadm_channel_pattern is None:
      tadm_channel_pattern = [True] * 96
    elif not len(tadm_channel_pattern) < 24:
      raise ValueError("tadm_channel_pattern must be of length 24, but is "
                        f"'{len(tadm_channel_pattern)}'")
    tadm_channel_pattern_num = sum(2**i if tadm_channel_pattern[i] else 0 for i in range(96))

    if not 0 <= tadm_algorithm_on_off <= 1:
      raise ValueError("tadm_algorithm_on_off must be in range 0 to 1")

    if not 0 <= recording_mode <= 2:
      raise ValueError("recording_mode must be in range 0 to 2")

    return await self.send_command(
      module="A1HM",
      command="DA",
      at=type_of_aspiration,
      xp=x_position,
      yp=y_position,
      th=minimal_traverse_height_at_begin_of_command,
      te=minimal_height_at_command_end,
      lp=lld_search_height,
      zl=liquid_surface_at_function_without_lld,
      po=pull_out_distance_to_take_transport_air_in_function_without_lld,
      zx=minimum_height,
      zu=tube_2nd_section_height_measured_from_zm,
      zr=tube_2nd_section_ratio,
      ip=immersion_depth,
      fp=surface_following_distance,
      av=aspiration_volume,
      as_=aspiration_speed,
      ta=transport_air_volume,
      ba=blow_out_air_volume,
      oa=pre_wetting_volume,
      lm=lld_mode,
      ll=lld_sensitivity,
      de=swap_speed,
      wt=settling_time,
      mv=mix_volume,
      mc=mix_cycles,
      mp=mix_position_in_z_direction_from_liquid_surface,
      mh=surface_following_distance_during_mixing,
      ms=mix_speed,
      gi=limit_curve_index,
      cw=hex(tadm_channel_pattern_num)[2:].upper(),
      gj=tadm_algorithm_on_off,
      gk=recording_mode,
    )

  async def core96_dispensing_of_liquid(
    self,
    type_of_dispensing_mode: int = 0,
    x_position: int = 5000,
    y_position: int = 5000,
    minimum_height: int = 3900,
    tube_2nd_section_height_measured_from_zm: int = 0,
    tube_2nd_section_ratio: int = 0,
    lld_search_height: int = 0,
    liquid_surface_at_function_without_lld: int = 3900,
    pull_out_distance_to_take_transport_air_in_function_without_lld: int = 50,
    immersion_depth: int = 0,
    surface_following_distance: int = 0,
    minimal_traverse_height_at_begin_of_command: int = 3900,
    minimal_height_at_command_end: int = 3900,
    dispense_volume: int = 0,
    dispense_speed: int = 2000,
    cut_off_speed: int = 1500,
    stop_back_volume: int = 0,
    transport_air_volume: int = 0,
    blow_out_air_volume: int = 1000,
    lld_mode: int = 1,
    lld_sensitivity: int = 1,
    side_touch_off_distance: int = 0,
    swap_speed: int = 100,
    settling_time: int = 5,
    mix_volume: int = 0,
    mix_cycles: int = 0,
    mix_position_in_z_direction_from_liquid_surface: int = 0,
    surface_following_distance_during_mixing: int = 0,
    mix_speed: int = 2000,
    limit_curve_index: int = 0,
    tadm_channel_pattern: Optional[List[bool]] = None,
    tadm_algorithm_on_off: int = 0,
    recording_mode: int = 0,
  ):
    """ Dispensing of liquid using the 96 head.

    Args:
      type_of_dispensing_mode: Type of dispensing mode 0 = part in jet 1 = blow in jet 2 = Part at
          surface 3 = Blow at surface 4 = Empty.
      x_position: X Position [0.1mm].
      y_position: Y Position [0.1mm].
      minimum_height: Minimum height (maximum immersion depth) [0.1mm].
      tube_2nd_section_height_measured_from_zm: Tube 2nd section height measured from zm [0.1mm].
      tube_2nd_section_ratio: Tube 2nd section ratio.
      lld_search_height: LLD search height [0.1mm].
      liquid_surface_at_function_without_lld: Liquid surface at function without LLD [0.1mm].
      pull_out_distance_to_take_transport_air_in_function_without_lld:
          Pull out distance to take transp. air in function without LLD [0.1mm]
        .
      immersion_depth: Immersion depth [0.1mm].
      surface_following_distance: Surface following distance [0.1mm].
      minimal_traverse_height_at_begin_of_command: Minimal traverse height at begin of
        command [0.1mm].
      minimal_height_at_command_end: Minimal height at command end [0.1mm].
      dispense_volume: Dispense volume [0.01ul].
      dispense_speed: Dispense speed [0.1ul/s].
      cut_off_speed: Cut off speed [0.1ul/s].
      stop_back_volume: Stop back volume [0.1ul].
      transport_air_volume: Transport air volume [0.1ul].
      blow_out_air_volume: Blow out air volume [0.01ul].
      lld_mode: LLD Mode (0 = off).
      lld_sensitivity: LLD sensitivity (1 = high, 4 = low).
      side_touch_off_distance: Side touch off distance [0.1mm].
      swap_speed: Swap speed (on leaving liquid) [0.1mm/s].
      settling_time: Settling time [0.1s].
      mix_volume: Mix volume [0.1ul].
      mix_cycles: Mix cycles.
      mix_position_in_z_direction_from_liquid_surface: Mix position in Z direction from liquid
        surface[0.1mm].
      surface_following_distance_during_mixing: Surface following distance during mixing [0.1mm].
      mix_speed: Mix speed [0.1ul/s].
      limit_curve_index: Limit curve index.
      tadm_channel_pattern: TADM Channel pattern.
      tadm_algorithm_on_off: TADM algorithm on/off (0 = off).
      recording_mode:
          Recording mode (0 = no 1 = TADM errors only 2 = all TADM measurements)
        .
    """

    if not 0 <= type_of_dispensing_mode <= 4:
      raise ValueError("type_of_dispensing_mode must be in range 0 to 4")

    if not -500000 <= x_position <= 50000:
      raise ValueError("x_position must be in range -500000 to 50000")

    if not 422 <= y_position <= 5921:
      raise ValueError("y_position must be in range 422 to 5921")

    if not 0 <= minimum_height <= 3900:
      raise ValueError("minimum_height must be in range 0 to 3900")

    if not 0 <= tube_2nd_section_height_measured_from_zm <= 3900:
      raise ValueError("tube_2nd_section_height_measured_from_zm must be in range 0 to 3900")

    if not 0 <= tube_2nd_section_ratio <= 10000:
      raise ValueError("tube_2nd_section_ratio must be in range 0 to 10000")

    if not 0 <= lld_search_height <= 3900:
      raise ValueError("lld_search_height must be in range 0 to 3900")

    if not 0 <= liquid_surface_at_function_without_lld <= 3900:
      raise ValueError("liquid_surface_at_function_without_lld must be in range 0 to 3900")

    if not 0 <= pull_out_distance_to_take_transport_air_in_function_without_lld <= 3900:
      raise ValueError("pull_out_distance_to_take_transport_air_in_function_without_lld must be in "
                       "range 0 to 3900")

    if not -990 <= immersion_depth <= 990:
      raise ValueError("immersion_depth must be in range -990 to 990")

    if not 0 <= surface_following_distance <= 990:
      raise ValueError("surface_following_distance must be in range 0 to 990")

    if not 0 <= minimal_traverse_height_at_begin_of_command <= 3900:
      raise ValueError("minimal_traverse_height_at_begin_of_command must be in range 0 to 3900")

    if not 0 <= minimal_height_at_command_end <= 3900:
      raise ValueError("minimal_height_at_command_end must be in range 0 to 3900")

    if not 0 <= dispense_volume <= 115000:
      raise ValueError("dispense_volume must be in range 0 to 115000")

    if not 3 <= dispense_speed <= 5000:
      raise ValueError("dispense_speed must be in range 3 to 5000")

    if not 3 <= cut_off_speed <= 5000:
      raise ValueError("cut_off_speed must be in range 3 to 5000")

    if not 0 <= stop_back_volume <= 2000:
      raise ValueError("stop_back_volume must be in range 0 to 2000")

    if not 0 <= transport_air_volume <= 1000:
      raise ValueError("transport_air_volume must be in range 0 to 1000")

    if not 0 <= blow_out_air_volume <= 115000:
      raise ValueError("blow_out_air_volume must be in range 0 to 115000")

    if not 0 <= lld_mode <= 1:
      raise ValueError("lld_mode must be in range 0 to 1")

    if not 1 <= lld_sensitivity <= 4:
      raise ValueError("lld_sensitivity must be in range 1 to 4")

    if not 0 <= side_touch_off_distance <= 30:
      raise ValueError("side_touch_off_distance must be in range 0 to 30")

    if not 3 <= swap_speed <= 1000:
      raise ValueError("swap_speed must be in range 3 to 1000")

    if not 0 <= settling_time <= 99:
      raise ValueError("settling_time must be in range 0 to 99")

    if not 0 <= mix_volume <= 11500:
      raise ValueError("mix_volume must be in range 0 to 11500")

    if not 0 <= mix_cycles <= 99:
      raise ValueError("mix_cycles must be in range 0 to 99")

    if not 0 <= mix_position_in_z_direction_from_liquid_surface <= 990:
      raise ValueError("mix_position_in_z_direction_from_liquid_surface must be in range 0 to 990")

    if not 0 <= surface_following_distance_during_mixing <= 990:
      raise ValueError("surface_following_distance_during_mixing must be in range 0 to 990")

    if not 3 <= mix_speed <= 5000:
      raise ValueError("mix_speed must be in range 3 to 5000")

    if not 0 <= limit_curve_index <= 999:
      raise ValueError("limit_curve_index must be in range 0 to 999")

    if tadm_channel_pattern is None:
      tadm_channel_pattern = [True] * 96
    elif not len(tadm_channel_pattern) < 24:
      raise ValueError("tadm_channel_pattern must be of length 24, but is "
                        f"'{len(tadm_channel_pattern)}'")
    tadm_channel_pattern_num = sum(2**i if tadm_channel_pattern[i] else 0 for i in range(96))

    if not 0 <= tadm_algorithm_on_off <= 1:
      raise ValueError("tadm_algorithm_on_off must be in range 0 to 1")

    if not 0 <= recording_mode <= 2:
      raise ValueError("recording_mode must be in range 0 to 2")

    return await self.send_command(
      module="A1HM",
      command="DD",
      dm=type_of_dispensing_mode,
      xp=x_position,
      yp=y_position,
      zx=minimum_height,
      zu=tube_2nd_section_height_measured_from_zm,
      zr=tube_2nd_section_ratio,
      lp=lld_search_height,
      zl=liquid_surface_at_function_without_lld,
      po=pull_out_distance_to_take_transport_air_in_function_without_lld,
      ip=immersion_depth,
      fp=surface_following_distance,
      th=minimal_traverse_height_at_begin_of_command,
      te=minimal_height_at_command_end,
      dv=dispense_volume,
      ds=dispense_speed,
      ss=cut_off_speed,
      rv=stop_back_volume,
      ta=transport_air_volume,
      ba=blow_out_air_volume,
      lm=lld_mode,
      ll=lld_sensitivity,
      dj=side_touch_off_distance,
      de=swap_speed,
      wt=settling_time,
      mv=mix_volume,
      mc=mix_cycles,
      mp=mix_position_in_z_direction_from_liquid_surface,
      mh=surface_following_distance_during_mixing,
      ms=mix_speed,
      gi=limit_curve_index,
      cw=hex(tadm_channel_pattern_num)[2:].upper(),
      gj=tadm_algorithm_on_off,
      gk=recording_mode,
    )

  async def core96_tip_pick_up(
    self,
    x_position: int = 5000,
    y_position: int = 5000,
    tip_type: int = 4,
    tip_handling_method: int = 0,
    z_deposit_position: int = 0,
    minimal_traverse_height_at_begin_of_command: int = 3900,
    minimal_height_at_command_end: int = 3900,
  ):
    """ Tip Pick up using the 96 head.

    Args:
      x_position: X Position [0.1mm].
      y_position: Y Position [0.1mm].
      tip_type: Tip type (see command TT).
      tip_handling_method: Tip handling method.
      z_deposit_position: Z deposit position [0.1mm] (collar bearing position).
      minimal_traverse_height_at_begin_of_command: Minimal traverse height at begin of
        command [0.1mm].
      minimal_height_at_command_end: Minimal height at command end [0.1mm].
    """

    if not -500000 <= x_position <= 50000:
      raise ValueError("x_position must be in range -500000 to 50000")

    if not 422 <= y_position <= 5921:
      raise ValueError("y_position must be in range 422 to 5921")

    if not 0 <= tip_type <= 199:
      raise ValueError("tip_type must be in range 0 to 199")

    if not 0 <= tip_handling_method <= 2:
      raise ValueError("tip_handling_method must be in range 0 to 2")

    if not 0 <= z_deposit_position <= 3900:
      raise ValueError("z_deposit_position must be in range 0 to 3900")

    if not 0 <= minimal_traverse_height_at_begin_of_command <= 3900:
      raise ValueError("minimal_traverse_height_at_begin_of_command must be in range 0 to 3900")

    if not 0 <= minimal_height_at_command_end <= 3900:
      raise ValueError("minimal_height_at_command_end must be in range 0 to 3900")

    return await self.send_command(
      module="A1HM",
      command="TP",
      xp=x_position,
      yp=y_position,
      tt=tip_type,
      td=tip_handling_method,
      tz=z_deposit_position,
      th=minimal_traverse_height_at_begin_of_command,
      te=minimal_height_at_command_end,
    )

  async def core96_tip_discard(
    self,
    x_position: int = 5000,
    y_position: int = 5000,
    z_deposit_position: int = 0,
    minimal_traverse_height_at_begin_of_command: int = 3900,
    minimal_height_at_command_end: int = 3900,
  ):
    """ Tip Discard using the 96 head.

    Args:
      x_position: X Position [0.1mm].
      y_position: Y Position [0.1mm].
      z_deposit_position: Z deposit position [0.1mm] (collar bearing position).
      minimal_traverse_height_at_begin_of_command: Minimal traverse height at begin of
        command [0.1mm].
      minimal_height_at_command_end: Minimal height at command end [0.1mm].
    """

    if not -500000 <= x_position <= 50000:
      raise ValueError("x_position must be in range -500000 to 50000")

    if not 422 <= y_position <= 5921:
      raise ValueError("y_position must be in range 422 to 5921")

    if not 0 <= z_deposit_position <= 3900:
      raise ValueError("z_deposit_position must be in range 0 to 3900")

    if not 0 <= minimal_traverse_height_at_begin_of_command <= 3900:
      raise ValueError("minimal_traverse_height_at_begin_of_command must be in range 0 to 3900")

    if not 0 <= minimal_height_at_command_end <= 3900:
      raise ValueError("minimal_height_at_command_end must be in range 0 to 3900")

    return await self.send_command(
      module="A1HM",
      command="TR",
      xp=x_position,
      yp=y_position,
      tz=z_deposit_position,
      th=minimal_traverse_height_at_begin_of_command,
      te=minimal_height_at_command_end,
    )

  async def core96_move_to_defined_position(
    self,
    x_position: int = 5000,
    y_position: int = 5000,
    z_position: int = 0,
    minimal_traverse_height_at_begin_of_command: int = 3900,
  ):
    """ Move to defined position using the 96 head.

    Args:
      x_position: X Position [0.1mm].
      y_position: Y Position [0.1mm].
      z_position: Z Position [0.1mm].
      minimal_traverse_height_at_begin_of_command: Minimal traverse height at begin of
       command [0.1mm].
    """

    if not -500000 <= x_position <= 50000:
      raise ValueError("x_position must be in range -500000 to 50000")

    if not 422 <= y_position <= 5921:
      raise ValueError("y_position must be in range 422 to 5921")

    if not 0 <= z_position <= 3900:
      raise ValueError("z_position must be in range 0 to 3900")

    if not 0 <= minimal_traverse_height_at_begin_of_command <= 3900:
      raise ValueError("minimal_traverse_height_at_begin_of_command must be in range 0 to 3900")

    return await self.send_command(
      module="A1HM",
      command="DN",
      xp=x_position,
      yp=y_position,
      zp=z_position,
      th=minimal_traverse_height_at_begin_of_command,
    )

  async def core96_wash_tips(
    self,
    x_position: int = 5000,
    y_position: int = 5000,
    liquid_surface_at_function_without_lld: int = 3900,
    minimum_height: int = 3900,
    surface_following_distance_during_mixing: int = 0,
    minimal_traverse_height_at_begin_of_command: int = 3900,
    mix_volume: int = 0,
    mix_cycles: int = 0,
    mix_speed: int = 2000,
  ):
    """ Wash tips on the 96 head.

    Args:
      x_position: X Position [0.1mm].
      y_position: Y Position [0.1mm].
      liquid_surface_at_function_without_lld: Liquid surface at function without LLD [0.1mm].
      minimum_height: Minimum height (maximum immersion depth) [0.1mm].
      surface_following_distance_during_mixing: Surface following distance during mixing [0.1mm].
      minimal_traverse_height_at_begin_of_command: Minimal traverse height at begin of command
        [0.1mm].
      mix_volume: Mix volume [0.1ul].
      mix_cycles: Mix cycles.
      mix_speed: Mix speed [0.1ul/s].
    """

    if not -500000 <= x_position <= 50000:
      raise ValueError("x_position must be in range -500000 to 50000")

    if not 422 <= y_position <= 5921:
      raise ValueError("y_position must be in range 422 to 5921")

    if not 0 <= liquid_surface_at_function_without_lld <= 3900:
      raise ValueError("liquid_surface_at_function_without_lld must be in range 0 to 3900")

    if not 0 <= minimum_height <= 3900:
      raise ValueError("minimum_height must be in range 0 to 3900")

    if not 0 <= surface_following_distance_during_mixing <= 990:
      raise ValueError("surface_following_distance_during_mixing must be in range 0 to 990")

    if not 0 <= minimal_traverse_height_at_begin_of_command <= 3900:
      raise ValueError("minimal_traverse_height_at_begin_of_command must be in range 0 to 3900")

    if not 0 <= mix_volume <= 11500:
      raise ValueError("mix_volume must be in range 0 to 11500")

    if not 0 <= mix_cycles <= 99:
      raise ValueError("mix_cycles must be in range 0 to 99")

    if not 3 <= mix_speed <= 5000:
      raise ValueError("mix_speed must be in range 3 to 5000")

    return await self.send_command(
      module="A1HM",
      command="DW",
      xp=x_position,
      yp=y_position,
      zl=liquid_surface_at_function_without_lld,
      zx=minimum_height,
      mh=surface_following_distance_during_mixing,
      th=minimal_traverse_height_at_begin_of_command,
      mv=mix_volume,
      mc=mix_cycles,
      ms=mix_speed,
    )

  async def core96_empty_washed_tips(
    self,
    liquid_surface_at_function_without_lld: int = 3900,
    minimal_height_at_command_end: int = 3900,
  ):
    """ Empty washed tips (end of wash procedure only) on the 96 head.

    Args:
      liquid_surface_at_function_without_lld: Liquid surface at function without LLD [0.1mm].
      minimal_height_at_command_end: Minimal height at command end [0.1mm].
    """

    if not 0 <= liquid_surface_at_function_without_lld <= 3900:
      raise ValueError("liquid_surface_at_function_without_lld must be in range 0 to 3900")

    if not 0 <= minimal_height_at_command_end <= 3900:
      raise ValueError("minimal_height_at_command_end must be in range 0 to 3900")

    return await self.send_command(
      module="A1HM",
      command="EE",
      zl=liquid_surface_at_function_without_lld,
      te=minimal_height_at_command_end,
    )

  async def core96_search_for_teach_in_signal_in_x_direction(
    self,
    x_search_distance: int = 0,
    x_speed: int = 50,
  ):
    """ Search for Teach in signal in X direction on the 96 head.

    Args:
      x_search_distance: X search distance [0.1mm].
      x_speed: X speed [0.1mm/s].
    """

    if not -50000 <= x_search_distance <= 50000:
      raise ValueError("x_search_distance must be in range -50000 to 50000")

    if not 20 <= x_speed <= 25000:
      raise ValueError("x_speed must be in range 20 to 25000")

    return await self.send_command(
      module="A1HM",
      command="DL",
      xs=x_search_distance,
      xv=x_speed,
    )

  async def core96_set_any_parameter(self):
    """ Set any parameter within the 96 head module. """

    return await self.send_command(
      module="A1HM",
      command="AA",
    )

  async def core96_query_tip_presence(self):
    """ Query Tip presence on the 96 head. """

    return await self.send_command(
      module="A1HM",
      command="QA",
    )

  async def core96_request_position(self):
    """ Request position of the 96 head. """

    return await self.send_command(
      module="A1HM",
      command="QI",
    )

  async def core96_request_tadm_error_status(
    self,
    tadm_channel_pattern: Optional[List[bool]] = None,
  ):
    """ Request TADM error status on the 96 head.

    Args:
      tadm_channel_pattern: TADM Channel pattern.
    """

    if tadm_channel_pattern is None:
      tadm_channel_pattern = [True] * 96
    elif not len(tadm_channel_pattern) < 24:
      raise ValueError("tadm_channel_pattern must be of length 24, but is "
                        f"'{len(tadm_channel_pattern)}'")
    tadm_channel_pattern_num = sum(2**i if tadm_channel_pattern[i] else 0 for i in range(96))

    return await self.send_command(
      module="A1HM",
      command="VB",
      cw=hex(tadm_channel_pattern_num)[2:].upper(),
    )

  async def ipg_initialize(self):
    """ Initialize IPG """

    return await self.send_command(
      module="A1RM",
      command="DI",
    )

  async def ipg_park(self):
    """ Park IPG """

    return await self.send_command(
      module="A1RM",
      command="GP",
    )

  async def ipg_expose_channel_n(self):
    """ Expose channel n """

    return await self.send_command(
      module="A1RM",
      command="DQ",
    )

  async def ipg_release_object(self):
    """ Release object """

    return await self.send_command(
      module="A1RM",
      command="DO",
    )

  async def ipg_search_for_teach_in_signal_in_x_direction(
    self,
    x_search_distance: int = 0,
    x_speed: int = 50,
  ):
    """ Search for Teach in signal in X direction

    Args:
      x_search_distance: X search distance [0.1mm].
      x_speed: X speed [0.1mm/s].
    """

    if not -50000 <= x_search_distance <= 50000:
      raise ValueError("x_search_distance must be in range -50000 to 50000")

    if not 20 <= x_speed <= 25000:
      raise ValueError("x_speed must be in range 20 to 25000")

    return await self.send_command(
      module="A1RM",
      command="DL",
      xs=x_search_distance,
      xv=x_speed,
    )

  async def ipg_grip_plate(
    self,
    x_position: int = 5000,
    y_position: int = 5600,
    z_position: int = 3600,
    grip_strength: int = 100,
    open_gripper_position: int = 860,
    plate_width: int = 800,
    plate_width_tolerance: int = 20,
    acceleration_index: int = 4,
    z_clearance_height: int = 50,
    hotel_depth: int = 0,
    minimal_height_at_command_end: int = 3600,
  ):
    """ Grip plate

    Args:
      x_position: X Position [0.1mm].
      y_position: Y Position [0.1mm].
      z_position: Z Position [0.1mm].
      grip_strength: Grip strength (0 = low 99 = high).
      open_gripper_position: Open gripper position [0.1mm].
      plate_width: Plate width [0.1mm].
      plate_width_tolerance: Plate width tolerance [0.1mm].
      acceleration_index: Acceleration index.
      z_clearance_height: Z clearance height [0.1mm].
      hotel_depth: Hotel depth [0.1mm] (0 = Stack).
      minimal_height_at_command_end: Minimal height at command end [0.1mm].
    """

    if not -50000 <= x_position <= 50000:
      raise ValueError("x_position must be in range -50000 to 50000")

    if not -10000 <= y_position <= 10000:
      raise ValueError("y_position must be in range -10000 to 10000")

    if not 0 <= z_position <= 4000:
      raise ValueError("z_position must be in range 0 to 4000")

    if not 0 <= grip_strength <= 160:
      raise ValueError("grip_strength must be in range 0 to 160")

    if not 0 <= open_gripper_position <= 9999:
      raise ValueError("open_gripper_position must be in range 0 to 9999")

    if not 0 <= plate_width <= 9999:
      raise ValueError("plate_width must be in range 0 to 9999")

    if not 0 <= plate_width_tolerance <= 99:
      raise ValueError("plate_width_tolerance must be in range 0 to 99")

    if not 0 <= acceleration_index <= 4:
      raise ValueError("acceleration_index must be in range 0 to 4")

    if not 0 <= z_clearance_height <= 999:
      raise ValueError("z_clearance_height must be in range 0 to 999")

    if not 0 <= hotel_depth <= 3000:
      raise ValueError("hotel_depth must be in range 0 to 3000")

    if not 0 <= minimal_height_at_command_end <= 4000:
      raise ValueError("minimal_height_at_command_end must be in range 0 to 4000")

    return await self.send_command(
      module="A1RM",
      command="DG",
      xp=x_position,
      yp=y_position,
      zp=z_position,
      yw=grip_strength,
      yo=open_gripper_position,
      yg=plate_width,
      pt=plate_width_tolerance,
      ai=acceleration_index,
      zc=z_clearance_height,
      hd=hotel_depth,
      te=minimal_height_at_command_end,
    )

  async def ipg_put_plate(
    self,
    x_position: int = 5000,
    y_position: int = 5600,
    z_position: int = 3600,
    open_gripper_position: int = 860,
    z_clearance_height: int = 50,
    press_on_distance: int = 5,
    hotel_depth: int = 0,
    minimal_height_at_command_end: int = 3600,
  ):
    """ Put plate

    Args:
      x_position: X Position [0.1mm].
      y_position: Y Position [0.1mm].
      z_position: Z Position [0.1mm].
      open_gripper_position: Open gripper position [0.1mm].
      z_clearance_height: Z clearance height [0.1mm].
      press_on_distance: Press on distance [0.1mm].
      hotel_depth: Hotel depth [0.1mm] (0 = Stack).
      minimal_height_at_command_end: Minimal height at command end [0.1mm].
    """

    if not -50000 <= x_position <= 50000:
      raise ValueError("x_position must be in range -50000 to 50000")

    if not -10000 <= y_position <= 10000:
      raise ValueError("y_position must be in range -10000 to 10000")

    if not 0 <= z_position <= 4000:
      raise ValueError("z_position must be in range 0 to 4000")

    if not 0 <= open_gripper_position <= 9999:
      raise ValueError("open_gripper_position must be in range 0 to 9999")

    if not 0 <= z_clearance_height <= 999:
      raise ValueError("z_clearance_height must be in range 0 to 999")

    if not 0 <= press_on_distance <= 999:
      raise ValueError("press_on_distance must be in range 0 to 999")

    if not 0 <= hotel_depth <= 3000:
      raise ValueError("hotel_depth must be in range 0 to 3000")

    if not 0 <= minimal_height_at_command_end <= 4000:
      raise ValueError("minimal_height_at_command_end must be in range 0 to 4000")

    return await self.send_command(
      module="A1RM",
      command="DR",
      xp=x_position,
      yp=y_position,
      zp=z_position,
      yo=open_gripper_position,
      zc=z_clearance_height,
      # zi=press_on_distance, # not sent?
      hd=hotel_depth,
      te=minimal_height_at_command_end,
    )

  async def ipg_prepare_gripper_orientation(
    self,
    grip_orientation: int = 32,
    minimal_traverse_height_at_begin_of_command: int = 3600,
  ):
    """ Prepare gripper orientation

    Args:
      grip_orientation: Grip orientation.
      minimal_traverse_height_at_begin_of_command: Minimal traverse height at begin of
        command [0.1mm].
    """

    if not 1 <= grip_orientation <= 44:
      raise ValueError("grip_orientation must be in range 1 to 44")

    if not 0 <= minimal_traverse_height_at_begin_of_command <= 4000:
      raise ValueError("minimal_traverse_height_at_begin_of_command must be in range 0 to 4000")

    return await self.send_command(
      module="A1RM",
      command="GA",
      gd=grip_orientation,
      th=minimal_traverse_height_at_begin_of_command,
    )

  async def ipg_move_to_defined_position(
    self,
    x_position: int = 5000,
    y_position: int = 5600,
    z_position: int = 3600,
    minimal_traverse_height_at_begin_of_command: int = 3600,
  ):
    """ Move to defined position

    Args:
      x_position: X Position [0.1mm].
      y_position: Y Position [0.1mm].
      z_position: Z Position [0.1mm].
      minimal_traverse_height_at_begin_of_command: Minimal traverse height at begin of
        command [0.1mm].
    """

    if not -50000 <= x_position <= 50000:
      raise ValueError("x_position must be in range -50000 to 50000")

    if not -10000 <= y_position <= 10000:
      raise ValueError("y_position must be in range -10000 to 10000")

    if not 0 <= z_position <= 4000:
      raise ValueError("z_position must be in range 0 to 4000")

    if not 0 <= minimal_traverse_height_at_begin_of_command <= 4000:
      raise ValueError("minimal_traverse_height_at_begin_of_command must be in range 0 to 4000")

    return await self.send_command(
      module="A1RM",
      command="DN",
      xp=x_position,
      yp=y_position,
      zp=z_position,
      th=minimal_traverse_height_at_begin_of_command,
    )

  async def ipg_set_any_parameter_within_this_module(self):
    """ Set any parameter within this module """

    return await self.send_command(
      module="A1RM",
      command="AA",
    )

  async def ipg_get_parking_status(self):
    """ Get parking status """

    return await self.send_command(
      module="A1RM",
      command="RG",
    )

  async def ipg_query_tip_presence(self):
    """ Query Tip presence """

    return await self.send_command(
      module="A1RM",
      command="QA",
    )

  async def ipg_request_access_range(self, grip_orientation: int = 32):
    """ Request access range

    Args:
      grip_orientation: Grip orientation.
    """

    if not 1 <= grip_orientation <= 44:
      raise ValueError("grip_orientation must be in range 1 to 44")

    return await self.send_command(
      module="A1RM",
      command="QR",
      gd=grip_orientation,
    )

  async def ipg_request_position(self, grip_orientation: int = 32):
    """ Request position

    Args:
      grip_orientation: Grip orientation.
    """

    if not 1 <= grip_orientation <= 44:
      raise ValueError("grip_orientation must be in range 1 to 44")

    return await self.send_command(
      module="A1RM",
      command="QI",
      gd=grip_orientation,
    )

  async def ipg_request_actual_angular_dimensions(self):
    """ Request actual angular dimensions """

    return await self.send_command(
      module="A1RM",
      command="RR",
    )

  async def ipg_request_configuration(self):
    """ Request configuration """

    return await self.send_command(
      module="A1RM",
      command="RS",
    )
