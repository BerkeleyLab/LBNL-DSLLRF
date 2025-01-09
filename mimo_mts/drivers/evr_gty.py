from pynq import DefaultIP
import time


class GTY_EVR(DefaultIP):
    bindto = ['xilinx.com:module_ref:evr_gty_wrapper_axi:1.0']

    def __init__(self, description):
        description['registers'] = {
            'gty_evr_status': {
                'address_offset': 0x0,
                'access': 'read-only',
                'description': 'GTY EVR status register',
                'size': 32,
                'fields': {
                    'gty_reset_all': {
                        'bit_offset': 0,
                        'bit_width': 1,
                        'access': 'read-only',
                        'description': 'GTY transceiver reset_all_in signal',
                    },
                    'reset_all': {
                        'bit_offset': 1,
                        'bit_width': 1,
                        'access': 'read-only',
                        'description': 'reset_all from axi bus',
                    },
                    'cplllocked': {
                        'bit_offset': 2,
                        'bit_width': 1,
                        'access': 'read-only',
                        'description': 'CPLL locked',
                    },
                    'reset_rx_done': {
                        'bit_offset': 3,
                        'bit_width': 1,
                        'access': 'read-only',
                        'description': 'GTY RX reset done',
                    },
                    'reset_tx_done': {
                        'bit_offset': 4,
                        'bit_width': 1,
                        'access': 'read-only',
                        'description': 'GTY TX reset done',
                    },
                    'rx_aligned': {
                        'bit_offset': 5,
                        'bit_width': 1,
                        'access': 'read-only',
                        'description': 'EVR RX aligned',
                    }
                }
            },
            'gty_reset_count': {
                'address_offset': 0x4,
                'access': 'read-only',
                'size': 32,
                'description': 'Number of resets issued to GTY to align EVR'
            },
            'evr_timestamp_valid': {
                'address_offset': 0x8,
                'access': 'read-only',
                'size': 32,
                'description': 'EVR timestamp valid'
            },
            'evr_event_count': {
                'address_offset': 0xC,
                'access': 'read-only',
                'size': 32,
                'description': 'EVR event1 count'
            },
            'evr_timestamp_lo': {
                'address_offset': 0x10,
                'access': 'read-only',
                'size': 32,
                'description': 'EVR timestamp low 32 bits'
            },
            'evr_timestamp_hi': {
                'address_offset': 0x14,
                'access': 'read-only',
                'size': 32,
                'description': 'EVR timestamp high 32 bits'
            },
            'si570_freq': {
                'address_offset': 0x18,
                'access': 'read-only',
                'size': 32,
                'description': 'GTY referece clock, SI570 frequency counter'
            },
            'gty_rx_freq': {
                'address_offset': 0x1C,
                'access': 'read-only',
                'size': 32,
                'description': 'GTY RX CDR frequency counter'
            },
            'reset_all': {
                'address_offset': 0x20,
                'access': 'write-only',
                'size': 32
            },
            'rx_slide': {
                'address_offset': 0x24,
                'access': 'write-only',
                'size': 32
            }
        }
        super().__init__(description=description)

    def check_alignment(self,
                        si570_freq_expect=156.1375e6,
                        rx_freq_expect=124.91e6):
        print(f"si570_freq : {self.si570_freq * 1e-6:8.5f} MHz")
        print(f"gty_rx_freq: {self.gty_rx_freq * 1e-6:8.5f} MHz")
        gty_status = int(self.register_map.gty_evr_status)
        evr_aligned = self.register_map.gty_evr_status.rx_aligned
        assert evr_aligned, f"GTY is not aligned, got 0x{gty_status:x}"
        print(f"GTY status: 0x{gty_status:x}, GTY is aligned.")
        self.check_freq(self.si570_freq, si570_freq_expect)
        self.check_freq(self.gty_rx_freq, rx_freq_expect)
        self.check_reset_cnt()

    def convert_freq_to_hz(self, f_cnt, f_ref=100.0e6):
        """Convert the frequency counter value to Hz"""
        return (f_cnt / 2**24) * f_ref

    @property
    def si570_freq(self):
        return self.convert_freq_to_hz(int(self.register_map.si570_freq))

    @property
    def gty_rx_freq(self):
        return self.convert_freq_to_hz(int(self.register_map.gty_rx_freq))

    def check_freq(self, freq, freq_expect, tolerance_ppm=50.0):
        ppm = ((freq / freq_expect) - 1.0) * 1e6
        assert abs(ppm) < tolerance_ppm, \
            f"Freq is out of spec by {ppm:3.0f} ppm"

    def check_reset_cnt(self):
        """ Check if the GTY has been reset during 1 second """
        init_val = self.register_map.gty_reset_count
        time.sleep(1)
        new_val = self.register_map.gty_reset_count
        assert init_val == new_val, "GTY has been reset during 1 second"

    def read_evr_regs(self):
        tvalid = self.register_map.evr_timestamp_valid
        assert tvalid != 1, "EVR timestamps are not valid"
        evcnt = self.register_map.evr_event_count
        tslo = self.register_map.evr_timestamp_lo
        tshi = self.register_map.evr_timestamp_hi
        print(f"EVR special event count: {evcnt}")
        print(f"EVR timestamp higher 32-bits: {tshi}, lower 32-bits: {tslo}")
