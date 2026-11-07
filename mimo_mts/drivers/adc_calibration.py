"""
RF-ADC interleaving calibration control.

Each RF-ADC is built from interleaved sub-ADCs. Their mismatch is corrected by
calibration blocks described in PG269, "RF-ADC Calibration Mechanism":

    OCB1  sub-ADC offset              foreground + continuous background, cannot be frozen
    OCB2  offset / sampling-switch    foreground only (RF-ADC startup), frozen afterwards
    GCB   sub-ADC gain                background, needs signal > -40 dBFS, can be frozen
    TSCB  sub-ADC time skew           background, needs signal > -40 dBFS, can be frozen

Foreground calibration runs only inside the RF-ADC startup state machine, i.e. when the
bitstream is loaded or the tile is reset. Keep the ADC input muted while it runs.

Freezing (``freeze``/``unfreeze``) holds or resumes GCB and TSCB tracking. Writing
coefficients (``write``/``restore``) sets the driver's per-block *override* bit, so the
written values stay in use until ``release_override`` hands the block back to the
calibration engine.

All calls go through the PYNQ ``xrfdc`` block API. The only CFFI use is allocating the
``XRFdc_Calibration_Coefficients`` struct that ``GetCalCoefficients`` and
``SetCalCoefficients`` take as an argument.

Channel numbering matches the rest of ``mimo_mts``: ``ch = tile * converters_per_tile + block``.
"""

import json
import logging
import os
import time
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# XRFDC_CAL_BLOCK_* in xrfdc.h
CAL_BLOCKS = {"OCB1": 0, "OCB2": 1, "GCB": 2, "TSCB": 3}
N_COEFFS = 8

# Blocks that can only be trained by an input signal; these are what a pulsed application restores.
TRACKING_BLOCKS = ("GCB", "TSCB")

# Read-back does not show written values: on ZCU208 (Gen 3) a TSCB write sets the override-enable
# bit, but the value field keeps reading the calibration engine's value. Not used for verification.
READBACK_UNVERIFIABLE = ("TSCB",)

# XRFDC_CAL_FREEZE_CALIB / XRFDC_CAL_FRZ_PIN_DISABLE in xrfdc.h
_FREEZE_PIN_DISABLE = 1
_FREEZE_PIN_ENABLE = 0

# PG269: a freeze state change takes ~7 us; allow margin before checking status.
FREEZE_SETTLE_S = 10e-6
FREEZE_TIMEOUT_S = 10e-3

FILE_FORMAT_VERSION = 1

# One calibration file per physical board, outside the repository.
DEFAULT_CAL_FILE = Path(os.environ.get("MIMO_MTS_ADC_CAL_FILE", "/etc/mimo_mts/adc_cal.json"))


def _default_coeff_struct():
    import xrfdc  # imported lazily so the module can be imported off-board

    return xrfdc._ffi.new("XRFdc_Calibration_Coefficients *")


class AdcCalibration:
    """
    Read, freeze, save and restore RF-ADC calibration for the enabled ADC channels of an RFDC.

    Parameters:
        rfdc: PYNQ ``xrfdc.RFdc`` driver instance (e.g. ``overlay.rfdc``).
        active_tiles: bit mask of enabled ADC tiles.
        converters_per_tile: 2 for dual-ADC tiles (ZCU208/LBL208), 4 for quad-ADC tiles (ZCU216).
        context: static description written next to saved coefficients, e.g. board, overlay
            and ADC sampling rate. Restoring warns when the saved context differs.
        coeff_struct_factory: allocates an ``XRFdc_Calibration_Coefficients *``; override only for testing.
    """

    def __init__(
        self,
        rfdc,
        active_tiles: int,
        converters_per_tile: int,
        context: Mapping | None = None,
        coeff_struct_factory: Callable | None = None,
    ):
        self.rfdc = rfdc
        self.converters_per_tile = converters_per_tile
        self.context = dict(context or {})
        self._new_coeff_struct = coeff_struct_factory or _default_coeff_struct
        self.channels = {
            tile * converters_per_tile + block: (tile, block)
            for tile in range(4)
            if active_tiles >> tile & 1
            for block in range(converters_per_tile)
        }

    def __repr__(self):
        return f"<{self.__class__.__name__}: ADC channels {list(self.channels)}>"

    # ------------------------------------------------------------------
    # Channel helpers
    # ------------------------------------------------------------------
    def _parse_channels(self, adc_ch) -> list[int]:
        """None or 'all' -> all channels; int -> [int]; iterable -> sorted unique list."""
        if adc_ch is None or (isinstance(adc_ch, str) and adc_ch.lower() == "all"):
            return list(self.channels)
        if isinstance(adc_ch, Iterable) and not isinstance(adc_ch, str):
            chs = sorted({int(c) for c in adc_ch})
        else:
            chs = [int(adc_ch)]
        unknown = [c for c in chs if c not in self.channels]
        if unknown:
            raise ValueError(f"ADC channel(s) {unknown} not enabled; valid channels: {list(self.channels)}")
        return chs

    @staticmethod
    def _parse_blocks(blocks) -> list[str]:
        names = [blocks] if isinstance(blocks, str) else list(blocks)
        unknown = [b for b in names if b not in CAL_BLOCKS]
        if unknown:
            raise ValueError(f"Unknown calibration block(s) {unknown}; valid: {list(CAL_BLOCKS)}")
        return names

    def block(self, ch: int):
        """PYNQ ``RFdcAdcBlock`` for an ADC channel."""
        tile, block = self.channels[ch]
        return self.rfdc.adc_tiles[tile].blocks[block]

    # ------------------------------------------------------------------
    # Freeze control (GCB and TSCB)
    # ------------------------------------------------------------------
    def is_frozen(self, adc_ch=None) -> dict[int, bool]:
        """Freeze status (``CalFrozen``) per channel."""
        return {ch: bool(self.block(ch).CalFreeze["CalFrozen"]) for ch in self._parse_channels(adc_ch)}

    def freeze(self, adc_ch=None) -> dict[int, bool]:
        """Freeze GCB/TSCB tracking under software control; returns the frozen status per channel."""
        return self._set_freeze(adc_ch, freeze=True)

    def unfreeze(self, adc_ch=None) -> dict[int, bool]:
        """Resume GCB/TSCB tracking under software control; returns the frozen status per channel."""
        return self._set_freeze(adc_ch, freeze=False)

    def enable_freeze_pin(self, adc_ch=None):
        """Hand freeze control to the PL ``cal_freeze`` port, for designs that drive it."""
        for ch in self._parse_channels(adc_ch):
            self.block(ch).CalFreeze = {"CalFrozen": 0, "DisableFreezePin": _FREEZE_PIN_ENABLE, "FreezeCalibration": 0}

    def _set_freeze(self, adc_ch, freeze: bool) -> dict[int, bool]:
        chs = self._parse_channels(adc_ch)
        for ch in chs:
            # DisableFreezePin=1: software register controls freezing, the PL port is ignored.
            self.block(ch).CalFreeze = {
                "CalFrozen": 0,  # status field, ignored by XRFdc_SetCalFreeze
                "DisableFreezePin": _FREEZE_PIN_DISABLE,
                "FreezeCalibration": int(freeze),
            }

        time.sleep(FREEZE_SETTLE_S)
        deadline = time.monotonic() + FREEZE_TIMEOUT_S
        status = self.is_frozen(chs)
        while any(v != freeze for v in status.values()) and time.monotonic() < deadline:
            time.sleep(FREEZE_SETTLE_S)
            status = self.is_frozen(chs)

        lagging = [ch for ch, v in status.items() if v != freeze]
        if lagging:
            logger.warning("ADC %s did not report %s", lagging, "frozen" if freeze else "unfrozen")
        else:
            logger.info("ADC %s calibration %s", chs, "frozen" if freeze else "tracking")
        return status

    # ------------------------------------------------------------------
    # Calibration mode (Gen 1/2; Gen 3 selects automatically per PG269)
    # ------------------------------------------------------------------
    def calibration_mode(self, adc_ch=None) -> dict[int, int]:
        return {ch: int(self.block(ch).CalibrationMode) for ch in self._parse_channels(adc_ch)}

    def set_calibration_mode(self, mode: int, adc_ch=None):
        if mode not in (1, 2):
            raise ValueError(f"Calibration mode must be 1 or 2, got {mode}")
        for ch in self._parse_channels(adc_ch):
            self.block(ch).CalibrationMode = mode

    # ------------------------------------------------------------------
    # Coefficients
    # ------------------------------------------------------------------
    def _get_coeffs(self, ch: int, name: str) -> list[int]:
        ptr = self._new_coeff_struct()  # zero-initialized; the driver ORs into it
        self.block(ch).GetCalCoefficients(CAL_BLOCKS[name], ptr)
        return [int(getattr(ptr, f"Coeff{i}")) for i in range(N_COEFFS)]

    def _set_coeffs(self, ch: int, name: str, coeffs: list[int]):
        if len(coeffs) != N_COEFFS:
            raise ValueError(f"{name} needs {N_COEFFS} coefficients, got {len(coeffs)}")
        ptr = self._new_coeff_struct()
        for i, c in enumerate(coeffs):
            setattr(ptr, f"Coeff{i}", int(c))
        self.block(ch).SetCalCoefficients(CAL_BLOCKS[name], ptr)

    def read(self, adc_ch=None, blocks=tuple(CAL_BLOCKS)) -> dict[int, dict[str, list[int]]]:
        """Coefficients currently in use, per channel and calibration block."""
        names = self._parse_blocks(blocks)
        return {ch: {n: self._get_coeffs(ch, n) for n in names} for ch in self._parse_channels(adc_ch)}

    def write(self, coeffs: Mapping[int, Mapping[str, list[int]]]):
        """
        Write coefficients and enable the driver override for each written block.

        ``coeffs`` maps channel -> {block name -> 8 coefficients}. GCB/TSCB of the written
        channels are frozen first, so the engine does not move while values are replaced.
        """
        chs = self._parse_channels(list(coeffs))
        if any(n in TRACKING_BLOCKS for ch in chs for n in coeffs[ch]):
            self.freeze(chs)
        for ch in chs:
            for name in self._parse_blocks(list(coeffs[ch])):
                self._set_coeffs(ch, name, coeffs[ch][name])

    def release_override(self, adc_ch=None, blocks=tuple(CAL_BLOCKS)):
        """Return the blocks to engine-computed coefficients (undo ``write``/``restore``)."""
        names = self._parse_blocks(blocks)
        for ch in self._parse_channels(adc_ch):
            for name in names:
                self.block(ch).DisableCoefficientsOverride(CAL_BLOCKS[name])

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _channel_context(self, ch: int) -> dict:
        tile, block = self.channels[ch]
        ctx = {"tile": tile, "block": block, **self.context}
        ctx["nyquist_zone"] = int(self.block(ch).NyquistZone)
        return ctx

    def save(self, path=DEFAULT_CAL_FILE, adc_ch=None) -> Path:
        """
        Save the coefficients of all calibration blocks to ``path``.

        Channels already in the file and not selected by ``adc_ch`` are kept, so one file per
        board can be built up channel by channel. Freeze GCB/TSCB first for a consistent snapshot.
        """
        path = Path(path)
        chs = self._parse_channels(adc_ch)
        not_frozen = [ch for ch, frozen in self.is_frozen(chs).items() if not frozen]
        if not_frozen:
            logger.warning("Saving ADC %s while GCB/TSCB are tracking; values may be mid-update", not_frozen)

        data = self.load(path) if path.exists() else {}
        saved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for ch, coeffs in self.read(chs).items():
            data[f"ADC{ch}"] = {
                "adc_ch": ch,
                **self._channel_context(ch),
                "saved_at": saved_at,
                "coeffs": coeffs,
            }
        data["format_version"] = FILE_FORMAT_VERSION

        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        os.replace(tmp, path)
        logger.info("Saved ADC %s calibration to %s", chs, path)
        return path

    @staticmethod
    def load(path=DEFAULT_CAL_FILE) -> dict:
        """Load a calibration file (also accepts files written by the original demo script)."""
        return json.loads(Path(path).read_text())

    def _select_from_file(self, data: dict, adc_ch) -> list[int]:
        in_file = sorted(int(k[3:]) for k in data if k.startswith("ADC") and k[3:].isdigit())
        if adc_ch is None or (isinstance(adc_ch, str) and adc_ch.lower() == "all"):
            missing = [ch for ch in self.channels if ch not in in_file]
            if missing:
                logger.warning("ADC %s have no saved calibration", missing)
            return [ch for ch in in_file if ch in self.channels]
        chs = self._parse_channels(adc_ch)
        missing = [ch for ch in chs if ch not in in_file]
        if missing:
            raise KeyError(f"ADC {missing} not found in calibration file")
        return chs

    def _warn_context_mismatch(self, ch: int, entry: dict):
        current = self._channel_context(ch)
        diffs = {k: (entry[k], v) for k, v in current.items() if k in entry and entry[k] != v}
        if diffs:
            logger.warning(
                "ADC %d calibration was saved with different settings (saved, now): %s",
                ch,
                diffs,
            )

    def restore(self, path=DEFAULT_CAL_FILE, adc_ch=None, blocks=TRACKING_BLOCKS) -> dict[int, list[str]]:
        """
        Restore saved coefficients and leave GCB/TSCB frozen.

        By default only GCB and TSCB are restored: OCB2 comes from this boot's foreground
        calibration and OCB1 keeps tracking on any signal. Pass ``blocks=CAL_BLOCKS`` to
        restore all four. Returns the read-back mismatches per channel (empty when verified).
        """
        data = self.load(path)
        names = self._parse_blocks(blocks)
        chs = self._select_from_file(data, adc_ch)
        coeffs = {}
        for ch in chs:
            entry = data[f"ADC{ch}"]
            self._warn_context_mismatch(ch, entry)
            missing = [n for n in names if n not in entry["coeffs"]]
            if missing:
                raise KeyError(f"ADC{ch} in {path} has no {missing} coefficients")
            coeffs[ch] = {n: entry["coeffs"][n] for n in names}

        self.write(coeffs)
        self.freeze(chs)
        mismatches = self.verify(path, chs, [n for n in names if n not in READBACK_UNVERIFIABLE] or names)
        if any(mismatches.values()):
            logger.error("ADC calibration restore did not verify: %s", mismatches)
        else:
            logger.info("Restored %s for ADC %s from %s", names, chs, path)
        return mismatches

    def verify(
        self,
        path=DEFAULT_CAL_FILE,
        adc_ch=None,
        blocks=tuple(b for b in CAL_BLOCKS if b not in READBACK_UNVERIFIABLE),
    ) -> dict[int, list[str]]:
        """
        Compare hardware coefficients with a file; returns mismatch descriptions per channel.

        TSCB is skipped by default because its read-back does not reflect written values.
        """
        data = self.load(path)
        names = self._parse_blocks(blocks)
        result = {}
        for ch in self._select_from_file(data, adc_ch):
            saved = data[f"ADC{ch}"]["coeffs"]
            hw = self.read(ch, [n for n in names if n in saved])[ch]
            result[ch] = [f"{n}: hw={hw[n]} file={saved[n]}" for n in hw if hw[n] != saved[n]]
        return result

    def report(self, adc_ch=None) -> str:
        """Human-readable freeze status and coefficients."""
        lines = []
        frozen = self.is_frozen(adc_ch)
        for ch, coeffs in self.read(adc_ch).items():
            tile, block = self.channels[ch]
            lines.append(f"ADC{ch} (tile {tile}, block {block}): {'FROZEN' if frozen[ch] else 'tracking'}")
            lines += [f"  {name:4s}: {c}" for name, c in coeffs.items()]
        return "\n".join(lines)
