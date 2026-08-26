#!/usr/bin/env python3
"""
RFSoC ADC Calibration & Interleaving Control Utilities

Provides functions to read, save, restore, zero, freeze, unfreeze, and verify
background interleaving calibration registers for Xilinx RFSoC ADCs.
All public functions accept a single ADC channel (int), a list/tuple of channels,
'all' / None (defaults to all 8 ADC channels).
"""

import os
import sys
import json
import xrfdc

# ==============================================================================
# GLOBAL CALIBRATION BLOCK MAPS
# ==============================================================================
CAL_BLOCKS = {
    "OCB1": getattr(xrfdc, "XRFDC_CAL_BLOCK_OCB1", 0),
    "OCB2": getattr(xrfdc, "XRFDC_CAL_BLOCK_OCB2", 1),
    "GCB":  getattr(xrfdc, "XRFDC_CAL_BLOCK_GCB", 2),
    "TSCB": getattr(xrfdc, "XRFDC_CAL_BLOCK_TSCB", 3),
}

CAL_BLOCK_LABELS = {
    "OCB1": "OCB1 (Offset Background) ",
    "OCB2": "OCB2 (Offset Foreground) ",
    "GCB":  "GCB  (Gain Cal Block)     ",
    "TSCB": "TSCB (Time Skew Cal Block)",
}


# ==============================================================================
# PRIVATE COMMON HELPERS
# ==============================================================================
def _parse_adc_channels(adc_ch):
    """Converts int, list/tuple, str ('all'), or None into a list of integer ADC channels [0..7]."""
    if adc_ch is None:
        return list(range(8))
    if isinstance(adc_ch, str):
        if adc_ch.lower() == "all":
            return list(range(8))
        return [int(adc_ch)]
    if isinstance(adc_ch, (list, tuple, set)):
        res = []
        for item in adc_ch:
            if isinstance(item, str) and item.lower() == "all":
                return list(range(8))
            res.append(int(item))
        return sorted(list(set(res)))
    return [int(adc_ch)]


def _get_rfdc_context(rfdc, adc_ch: int):
    """Returns (rfdc_inst, tile_idx, block_idx) for a target ADC channel."""
    tile = adc_ch // 2
    block = adc_ch % 2
    rfdc_inst = getattr(rfdc, "_instance", rfdc)
    return rfdc_inst, tile, block


def _get_cal_coefficients(rfdc_inst, tile: int, block: int, block_id: int):
    """Reads 8 coefficient taps for a sub-ADC calibration block."""
    coeff_ptr = xrfdc._ffi.new("XRFdc_Calibration_Coefficients *")
    status = xrfdc._lib.XRFdc_GetCalCoefficients(rfdc_inst, tile, block, block_id, coeff_ptr)
    if status == 0:
        return [
            int(coeff_ptr.Coeff0), int(coeff_ptr.Coeff1),
            int(coeff_ptr.Coeff2), int(coeff_ptr.Coeff3),
            int(coeff_ptr.Coeff4), int(coeff_ptr.Coeff5),
            int(coeff_ptr.Coeff6), int(coeff_ptr.Coeff7)
        ]
    return None


def _set_cal_coefficients(rfdc_inst, tile: int, block: int, block_id: int, coeffs: list):
    """Writes 8 coefficient taps to a sub-ADC calibration block."""
    coeff_ptr = xrfdc._ffi.new("XRFdc_Calibration_Coefficients *")
    for i in range(8):
        setattr(coeff_ptr, f"Coeff{i}", coeffs[i])
    return xrfdc._lib.XRFdc_SetCalCoefficients(rfdc_inst, tile, block, block_id, coeff_ptr)


def _get_freeze_status(rfdc_inst, tile: int, block: int) -> bool:
    """Returns True if calibration is frozen, False if active."""
    freeze_settings = xrfdc._ffi.new("XRFdc_Cal_Freeze_Settings *")
    xrfdc._lib.XRFdc_GetCalFreeze(rfdc_inst, tile, block, freeze_settings)
    return freeze_settings[0].FreezeCalibration == 1


# ==============================================================================
# PUBLIC MODULE FUNCTIONS
# ==============================================================================
def read_adc_cal(rfdc, adc_ch=None):
    """
    Reads back and displays interleaving calibration status and coefficients.

    Parameters:
        rfdc: Active RFDC driver block instance (e.g., ol.rfdc).
        adc_ch (int, list, str, None): Single channel ID (0-7), list [4, 5], 'all', or None (all 8 ADCs).
    """
    channels = _parse_adc_channels(adc_ch)

    for ch in channels:
        rfdc_inst, tile, block = _get_rfdc_context(rfdc, ch)
        is_frozen = _get_freeze_status(rfdc_inst, tile, block)

        print(f"\n--- ADC {ch} Interleaving Readback (Tile {tile}, Block {block}) ---")
        print(f"Status: {'🔴 FROZEN' if is_frozen else '🟢 ACTIVE'}")
        print("-" * 80)

        for name, cal_id in CAL_BLOCKS.items():
            label = CAL_BLOCK_LABELS.get(name, name)
            taps = _get_cal_coefficients(rfdc_inst, tile, block, cal_id)
            if taps is not None:
                print(f"  ├── {label} : {taps}")
            else:
                print(f"  ├── {label} : Read Error")

        print("-" * 80)
    print()


def zero_adc_cal(rfdc, adc_ch=None):
    """
    Forces all sub-ADC calibration coefficient tap weights (OCB1, OCB2, GCB, TSCB) to zero.

    Parameters:
        rfdc: Active RFDC driver instance (e.g., ol.rfdc).
        adc_ch (int, list, str, None): Single channel ID (0-7), list [4, 5], 'all', or None (all 8 ADCs).
    """
    channels = _parse_adc_channels(adc_ch)
    zero_coeffs = [0] * 8

    print("\n" + "=" * 80)
    print(" 🔴 FORCING SUB-ADC CALIBRATION COEFFICIENTS TO ZERO")
    print("=" * 80)

    for ch in channels:
        rfdc_inst, tile, block = _get_rfdc_context(rfdc, ch)
        print(f"\n📍 ADC {ch} (Tile {tile}, Block {block}):")

        for name, cal_id in CAL_BLOCKS.items():
            label = CAL_BLOCK_LABELS.get(name, name)
            ret = _set_cal_coefficients(rfdc_inst, tile, block, cal_id, zero_coeffs)
            if ret == 0:
                print(f"    ├── {label} : Overwritten to {zero_coeffs}")
            else:
                print(f"    ├── {label} : Write Error (Code {ret})")

    print("=" * 80 + "\n")


def save_adc_cal(rfdc, cal_file: str, adc_ch=None):
    """
    Snapshots calibration coefficients into a JSON file.

    Parameters:
        rfdc: Active RFDC driver instance (e.g., ol.rfdc).
        cal_file (str): Target JSON calibration file path.
        adc_ch (int, list, str, None): Single channel ID (0-7), list [4, 5], 'all', or None (all 8 ADCs).
    """
    channels = _parse_adc_channels(adc_ch)

    data = {}
    if os.path.exists(cal_file):
        try:
            with open(cal_file, "r") as f:
                data = json.load(f)
        except Exception:
            data = {}

    for ch in channels:
        rfdc_inst, tile, block = _get_rfdc_context(rfdc, ch)
        coeffs_map = {}

        for name, block_id in CAL_BLOCKS.items():
            taps = _get_cal_coefficients(rfdc_inst, tile, block, block_id)
            if taps is not None:
                coeffs_map[name] = taps

        if not coeffs_map:
            print(f"[!] Read Error: Could not read calibration coefficients for ADC {ch} (Tile {tile}, Block {block}).")
            continue

        adc_key = f"ADC{ch}"
        data[adc_key] = {
            "adc_ch": ch,
            "tile": tile,
            "block": block,
            "coeffs": coeffs_map
        }
        print(f"[✔] Captured ADC {ch} coefficients (Tile {tile}, Block {block}) -> Updated '{adc_key}'")

    with open(cal_file, "w") as f:
        json.dump(data, f, indent=2)

    print(f"[✔] Saved calibration data to '{cal_file}'")


def restore_adc_cal(rfdc, cal_file: str, adc_ch=None):
    """
    Restores calibration coefficients from a JSON file.

    Parameters:
        rfdc: Active RFDC driver instance (e.g., ol.rfdc).
        cal_file (str): Source JSON calibration file path.
        adc_ch (int, list, str, None): Single channel ID (0-7), list [4, 5], 'all', or None (restores all channels present in file).
    """
    if not os.path.exists(cal_file):
        raise FileNotFoundError(f"Calibration file '{cal_file}' not found!")

    with open(cal_file, "r") as f:
        data = json.load(f)

    if adc_ch is None or (isinstance(adc_ch, str) and adc_ch.lower() == "all"):
        target_keys = sorted([k for k in data.keys() if k.startswith("ADC")])
    else:
        channels = _parse_adc_channels(adc_ch)
        target_keys = [f"ADC{ch}" for ch in channels]

    if not target_keys:
        print(f"[!] Warning: No valid ADC keys found to restore from '{cal_file}'.")
        return

    for adc_key in target_keys:
        if adc_key not in data:
            print(f"[!] Error: Key '{adc_key}' not found in '{cal_file}'.")
            continue

        adc_data = data[adc_key]
        ch = adc_data.get("adc_ch", int(adc_key.replace("ADC", "")))
        rfdc_inst, tile, block = _get_rfdc_context(rfdc, ch)

        for name, coeffs in adc_data.get("coeffs", {}).items():
            if name in CAL_BLOCKS:
                _set_cal_coefficients(rfdc_inst, tile, block, CAL_BLOCKS[name], coeffs)

        print(f"[✔] Restored ADC {ch} coefficients (Tile {tile}, Block {block}) <- Loaded '{adc_key}' from '{cal_file}'")


def verify_adc_cal(rfdc, cal_file: str, adc_ch=None, verbose: bool = True) -> bool:
    """
    Reads hardware registers and verifies that current hardware coefficients match a JSON calibration file.

    Parameters:
        rfdc: Active RFDC driver instance (e.g., ol.rfdc).
        cal_file (str): Source JSON calibration file path to verify against.
        adc_ch (int, list, str, None): Single channel ID (0-7), list, 'all', or None (verifies all present in file).
        verbose (bool): If True, prints comparison progress and mismatch details.

    Returns:
        bool: True if hardware registers match the calibration file, False otherwise.
    """
    if not os.path.exists(cal_file):
        if verbose:
            print(f"[!] Error: Calibration file '{cal_file}' not found!")
        return False

    with open(cal_file, "r") as f:
        data = json.load(f)

    if adc_ch is None or (isinstance(adc_ch, str) and adc_ch.lower() == "all"):
        target_keys = sorted([k for k in data.keys() if k.startswith("ADC")])
    else:
        channels = _parse_adc_channels(adc_ch)
        target_keys = [f"ADC{ch}" for ch in channels]

    if not target_keys:
        if verbose:
            print(f"[!] Warning: No valid ADC keys found to verify in '{cal_file}'.")
        return False

    all_match = True

    for adc_key in target_keys:
        if adc_key not in data:
            if verbose:
                print(f"[!] Error: Key '{adc_key}' not found in '{cal_file}'.")
            all_match = False
            continue

        adc_data = data[adc_key]
        ch = adc_data.get("adc_ch", int(adc_key.replace("ADC", "")))
        rfdc_inst, tile, block = _get_rfdc_context(rfdc, ch)
        file_coeffs = adc_data.get("coeffs", {})

        ch_match = True
        mismatches = []

        for name, cal_id in CAL_BLOCKS.items():
            if name not in file_coeffs:
                continue

            hw_taps = _get_cal_coefficients(rfdc_inst, tile, block, cal_id)
            expected_taps = file_coeffs[name]

            if hw_taps is None:
                ch_match = False
                mismatches.append(f"{name}: Failed to read HW coefficients")
            elif hw_taps != expected_taps:
                ch_match = False
                mismatches.append(f"{name}: HW={hw_taps} vs File={expected_taps}")

        if not ch_match:
            all_match = False
            if verbose:
                print(f"[✘] Mismatch on ADC {ch} (Tile {tile}, Block {block}):")
                for m in mismatches:
                    print(f"    ├── {m}")
        elif verbose:
            print(f"[✔] ADC {ch} (Tile {tile}, Block {block}) hardware registers match '{cal_file}'")

    if verbose:
        if all_match:
            print(f"\n[✔] VERIFICATION PASSED: All requested ADC calibration coefficients match '{cal_file}'.")
        else:
            print(f"\n[✘] VERIFICATION FAILED: Calibration coefficient mismatches detected.")

    return all_match


def freeze_adc_cal(rfdc, adc_ch=None, freeze: bool = True):
    """
    Freezes or unfreezes background interleaving calibration.

    Parameters:
        rfdc: Active RFDC driver block instance (e.g., ol.rfdc).
        adc_ch (int, list, str, None): Single channel ID (0-7), list [4, 5], 'all', or None (all 8 ADCs).
        freeze (bool): True to freeze (lock weights), False to unfreeze (active tracking).
    """
    channels = _parse_adc_channels(adc_ch)

    for ch in channels:
        rfdc_inst, tile, block = _get_rfdc_context(rfdc, ch)

        freeze_settings = xrfdc._ffi.new("XRFdc_Cal_Freeze_Settings *")
        available_fields = dir(freeze_settings[0])

        mode_attr = "CalFreezeMode" if "CalFreezeMode" in available_fields else "CalFrozen"
        disable_attr = "DisableContCal" if "DisableContCal" in available_fields else "DisableFreezePin"
        freeze_attr = "FreezeCalibration"

        state_to_set = 1 if freeze else 0

        setattr(freeze_settings[0], mode_attr, state_to_set)
        setattr(freeze_settings[0], disable_attr, state_to_set)
        setattr(freeze_settings[0], freeze_attr, state_to_set)

        xrfdc._lib.XRFdc_SetCalFreeze(rfdc_inst, tile, block, freeze_settings)

        if not freeze:
            xrfdc._lib.XRFdc_SetCalibrationMode(rfdc_inst, tile, block, 1)

        status_str = "🔴 [FROZEN]" if freeze else "🟢 [ACTIVE TRACKING]"
        print(f"{status_str} ADC {ch} (Tile {tile}, Block {block}) interleaving calibration updated.")