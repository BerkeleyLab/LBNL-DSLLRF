import argparse
import logging
from mimo_mts.utils.config_clk104 import CLK104Config
from mimo_mts.config import ol_configs
import mimo_mts.overlays as overlays
from importlib.resources import files
from pynq import Overlay
from pprint import pformat
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TestCLK104:
    def __init__(self, conf: str = "ALS_LLRF_ZCU208", **kwargs):
        self.log_level = kwargs.get("log_level", logging.INFO)
        logger.setLevel(self.log_level)
        self.ol_info = ol_info = ol_configs.get(conf, {})
        board_name = ol_info["board"].name.lower()
        bitfile_name = files(overlays).joinpath(f'{board_name}/base.bit')
        assert Path(bitfile_name).exists(), f"Bitfile {bitfile_name} does not exist."
        overlay = Overlay(str(bitfile_name), download=False)
        if overlay.is_loaded():
            logger.info(f"Overlay {bitfile_name} already loaded")
        else:
            logger.info(f"Loading overlay {bitfile_name}")
            overlay.download()

        if 'clk104_tcs' in ol_info:
            logger.info(f"Programming CLK104 for overlay: {conf}, with verify")
            logger.debug(f"CLK104 configuration: {pformat(ol_info['clk104_tcs'])}")
            tcs = ol_info['clk104_tcs']
            tcs.pop('verify')
            # force verify since base.bit supports it
            self.clk104 = CLK104Config(**tcs, log_level=log_level,
                                       write=True, verify=True)
            self.clk104.verify_regs()
            # assert self.clk104.v_lmk.is_locked(), "LMK is not locked after configuration"
            assert self.clk104.v_lmx_adc.is_locked(), "LMX ADC is not locked after configuration"
            assert self.clk104.v_lmx_dac.is_locked(), "LMX DAC is not locked after configuration"
            logger.info("CLK104 configuration verified successfully")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Test CLK104 configuration')
    parser.add_argument('-c', '--config', default='ALS_LLRF_ZCU208', help='Overlay configuration')
    parser.add_argument('-d', '--debug', action='store_true', help='Enable debug logging')

    args = parser.parse_args()
    log_level = logging.DEBUG if args.debug else logging.INFO

    test_clk104 = TestCLK104(conf=args.config, log_level=log_level)
