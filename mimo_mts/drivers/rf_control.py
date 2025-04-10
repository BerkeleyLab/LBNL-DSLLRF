from pynq import DefaultIP
from pathlib import Path
import json


class RfControl(DefaultIP):
    bindto = ['xilinx.com:module_ref:axil_rf_control:1.0']

    def __init__(self, description):
        ip_path = Path(__file__).resolve().parent.parent.parent / \
            'designs' / 'ip'
        json_path = ip_path / 'rtl' / 'axil_rf_control.json'
        with open(json_path, 'r') as f:
            description['registers'] = json.load(f)
        super().__init__(description)

    def set_rf_enable(self, enable=True):
        self.register_map.dac_enable = enable
