"""
Type stub for PYNQ's xrfclk module, which only exists on the board.
https://github.com/Xilinx/PYNQ/blob/master/sdbuild/packages/xrfclk/package/xrfclk/xrfclk.py

Lets Pylance/pyright resolve `import xrfclk` on a development machine. Not used at runtime.
Covers the private helpers used by mimo_mts/utils/config_clk104.py.
"""

from pathlib import Path
from typing import Any

def _spidev_bind(dev: Path) -> None: ...
def _get_spidev_path(dev: Path) -> Path: ...
def _write_LMK_regs(reg_vals: list[int], devinfo: dict[str, Any]) -> None: ...
def _write_LMX_regs(reg_vals: list[int], devinfo: dict[str, Any]) -> None: ...
def __getattr__(name: str) -> Any: ...  # other xrfclk names: unknown type, but not an error
