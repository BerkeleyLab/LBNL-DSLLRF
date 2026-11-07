"""
Type stub for PYNQ's xrfdc module, which only exists on the board.
https://github.com/Xilinx/PYNQ/blob/master/sdbuild/packages/xrfdc/package/xrfdc/__init__.py

Lets Pylance/pyright resolve `import xrfdc` on a development machine. Not used at runtime.
Constant values are from xrfdc.h of the RFdc driver v8.0 (Vitis 2022.1, embeddedsw rfdc_v8_0);
PYNQ exposes each XRFDC_<NAME> define as xrfdc.<NAME>.
"""

from typing import Any, Final

MIXER_MODE_OFF: Final = 0
MIXER_MODE_C2C: Final = 1
MIXER_MODE_C2R: Final = 2
MIXER_MODE_R2C: Final = 3
MIXER_MODE_R2R: Final = 4
MIXER_TYPE_COARSE: Final = 1
MIXER_TYPE_FINE: Final = 2
COARSE_MIX_OFF: Final = 0
MIXER_SCALE_1P0: Final = 1
EVNT_SRC_SYSREF: Final = 3

class RFdc:
    def __getattr__(self, name: str) -> Any: ...

def __getattr__(name: str) -> Any: ...  # other xrfdc names: unknown type, but not an error
