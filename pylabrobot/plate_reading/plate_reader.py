import sys
from typing import List, cast

from pylabrobot.machine import MachineFrontend, need_setup_finished
from pylabrobot.resources import Coordinate, Resource, Plate
from pylabrobot.plate_reading.backend import PlateReaderBackend

if sys.version_info >= (3, 8):
  from typing import Literal
else:
  from typing_extensions import Literal


class NoPlateError(Exception):
  pass


class PlateReader(Resource, MachineFrontend):
  """ The front end for plate readers. Plate readers are devices that can read luminescence,
  absorbance, or fluorescence from a plate.

  Plate readers are asynchronous, meaning that their methods will return immediately and
  will not block. If you want to use a plate reader in a synchronous context, use SyncPlateReader
  instead.

  Here's an example of how to use this class in a Juptyer Notebook:

  >>> from pylabrobot.plate_reading.clario_star import CLARIOStar
  >>> pr = PlateReader(backend=CLARIOStar())
  >>> pr.setup()
  >>> await pr.read_luminescence()
  [[value1, value2, value3, ...], [value1, value2, value3, ...], ...

  In a synchronous context, use asyncio.run() to run the asynchronous methods:

  >>> import asyncio
  >>> from pylabrobot.plate_reading.clario_star import CLARIOStar
  >>> pr = SyncPlateReader(backend=CLARIOStar())
  >>> pr.setup()
  >>> asyncio.run(pr.read_luminescence())
  [[value1, value2, value3, ...], [value1, value2, value3, ...], ...
  """

  def __init__(self, name: str, backend: PlateReaderBackend) -> None:
    MachineFrontend.__init__(self, backend=backend)
    self.backend: PlateReaderBackend = backend
    Resource.__init__(self, name=name, size_x=0, size_y=0, size_z=0, category="plate_reader")

  def assign_child_resource(self, resource):
    if len(self.children) >= 1:
      raise ValueError("There already is a plate in the plate reader.")
    if not isinstance(resource, Plate):
      raise ValueError("The resource must be a plate.")
    super().assign_child_resource(resource, location=Coordinate.zero())

  def get_plate(self) -> Plate:
    if len(self.children) == 0:
      raise NoPlateError("There is no plate in the plate reader.")
    return cast(Plate, self.children[0])

  async def open(self) -> None:
    await self.backend.open()

  async def close(self) -> None:
    await self.backend.close()

  @need_setup_finished
  async def read_luminescence(self, focal_height: float) -> List[List[float]]:
    """ Read the luminescence from the plate.

    Args:
      focal_height: The focal height to read the luminescence at, in micrometers.
    """

    return await self.backend.read_luminescence(focal_height=focal_height)

  @need_setup_finished
  async def read_absorbance(
    self,
    wavelength: int,
    report: Literal["OD", "transmittance"]
  ) -> List[List[float]]:
    """ Read the absorbance from the plate.

    Args:
      wavelength: The wavelength to read the absorbance at, in nanometers.
    """

    if report not in {"OD", "transmittance"}:
      raise ValueError("report must be either 'OD' or 'transmittance'.")

    return await self.backend.read_absorbance(wavelength=wavelength, report=report)
