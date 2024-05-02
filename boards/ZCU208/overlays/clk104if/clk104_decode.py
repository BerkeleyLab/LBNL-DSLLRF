#! python3
# Decode a TICS file for the LMK04828 or LMX2594

import re

PRINT_WARNINGS = False

CHIP_LMK = 0
CHIP_LMX = 1

def chip_str(chip):
    if chip == CHIP_LMK:
        return "LMK04828"
    elif chip == CHIP_LMX:
        return "LMX2594"
    return "UNKNOWN_{}".format(chip)
    
class Register():
    def __init__(self, fields, addr=None):
        self._fdict = {}
        for name, start, stop in fields:
            self._fdict[name] = (start, stop)
        self.addr = addr

    def decode(self, value):
        fdict = {}
        for name, rng in self._fdict.items():
            start, stop = rng
            mask = (1 << (stop-start+1))-1
            val = (value >> start) & mask
            fdict[name] = val
        return fdict

    def get_range(self, field_name):
        rng = self._fdict.get(field_name, None)
        if rng is None:
            return (None, None)
        else:
            start, stop = rng
        return start, stop

def load_regdict(chip):
    chip_indices = (CHIP_LMK, CHIP_LMX)
    if chip not in chip_indices:
        print("Chip index {} not supported. Use only {}".format(chip_indices))
        return None
    if chip == CHIP_LMK:
        from lmk04828_regmap import regdict
    elif chip == CHIP_LMX:
        from lmx2594_regmap import regdict
    _regdict = {}
    for key, val in regdict.items():
        if not hasattr(val, "get_range"): # isinstance() seems to be broken on this platform?
            _regdict[key] = Register(val, key)
        else:
            _regdict[key] = val
    return _regdict

def read_tics_list(rlist, chip=CHIP_LMK, doPrint=False, asHex=False):
    regdict = load_regdict(chip)
    handlers = {
        CHIP_LMK: handle_xact_lmk,
        CHIP_LMX: handle_xact_lmx,
    }
    field_dict = {}
    handler = handlers[chip]
    for xact in rlist:
        addr, fdict = handler(xact, regdict)
        if fdict is None:
            continue
        reg = regdict.get(addr)
        if doPrint:
            _print_field_dict(addr, fdict, asHex=asHex)
        for field_name, field_value in fdict.items():
            if reg is not None:
                start, stop = reg.get_range(field_name)
            if field_dict.get(field_name, None) is not None:
                print("WARNING: clobbering global field entry for {}".format(field_name))
            field_dict[field_name] = (field_value, addr, start, stop)
    return field_dict

def read_tics_file(filename, doPrint=False):
    import os
    path, name = os.path.split(filename)
    asHex = True
    if name.lower().startswith("lmk"):
        chip = CHIP_LMK
        print("LMK04828")
    elif name.lower().startswith("lmx"):
        chip = CHIP_LMX
        asHex = False
        print("LMX2594")
    else:
        print("Unrecognized filename. Guessing LMK04828")
        chip = CHIP_LMK
    tics_list = []
    with open(filename, 'r') as fd:
        line = fd.readline()
        while line:
            rnum, xact = handle_line(line)
            if vet_xact(rnum, xact, chip=chip):
                tics_list.append(xact)
            line = fd.readline()
    return read_tics_list(tics_list, chip=chip, doPrint=doPrint, asHex=asHex)

def vet_xact(rnum, xact, chip=CHIP_LMK):
    if xact is None:
        return False
    xact = int(xact, 16)
    rnum = int(rnum)
    if chip == CHIP_LMK:
        _rnum = (xact >> 8) & 0x1fff
    elif chip == CHIP_LMX:
        _rnum = (xact >> 16) & 0x7f
    if rnum == _rnum:
        return True
    return False

def handle_line(line):
    _regexp = "R([0-9]+)\s+([0-9a-fA-Fx]+)"
    _match = re.match(_regexp, line.strip())
    if _match:
        groups = _match.groups()
        rnum, xact = groups[:2]
        return rnum, xact
    else:
        #print("Failed to match: {}".format(line.strip()))
        pass
    return None, None

def handle_xact_lmk(xact, regdict):
    if hasattr(xact, "lower"):
        xact = int(xact, 16)
    rw = (xact >> 23) & 1
    rnum = (xact >> 8) & 0x1fff
    rval = (xact & 0xff)
    return _handle_xact(rnum, rval, regdict)

def handle_xact_lmx(xact, regdict):
    if hasattr(xact, "lower"):
        xact = int(xact, 16)
    rw = (xact >> 23) & 1
    rnum = (xact >> 16) & 0x7f
    rval = (xact & 0xffff)
    return _handle_xact(rnum, rval, regdict, asHex=False)

def _handle_xact(rnum, rval, regdict, asHex=True):
    reg = regdict.get(rnum, None)
    if reg is None:
        if asHex:
            rstr = "0x{:x}".format(rnum)
        else:
            rstr = str(rnum)
        if PRINT_WARNINGS:
            print("WARNING: Could not find definition for register {}".format(rstr))
        return None, None
    fdict = reg.decode(rval)
    return reg.addr, fdict

def _print_field_dict(addr, fdict, asHex=True):
    if asHex:
        print("0x{:03x}:".format(addr))
    else:
        print("{}:".format(addr))
    for name, val in fdict.items():
        print("  {} = {}".format(name, val))
    return

def build_dict_lmk(filename):
    _re_reg = "0x([0-9a-fA-F]+):"
    _re_field = "\s*(\S+)\s+\(end:([0-9])\|start:([0-9])\|width:[0-9]\)"
    # RESET (end:7|start:7|width:1)
    nreg = None
    rdict = {}
    rlist = []
    with open(filename, 'r') as fd:
        line = fd.readline()
        while line:
            _match = re.match(_re_field, line.strip())
            if _match:
                #print("matched field: {}".format(_match.groups()))
                name, end, start = _match.groups()
                if name not in ('0', '1', 'X'):
                    rlist.append((name, int(start), int(end)))
            else:
                _match = re.match(_re_reg, line.strip())
                if _match:
                    #print("matched nreg: {}".format(_match.groups()))
                    if nreg is not None:
                        rdict[nreg] = rlist
                    rlist = []
                    nreg = int(_match.groups()[0], 16)
            line = fd.readline()
    # Don't forget the last one
    if len(rlist) > 0 and nreg is not None:
        rdict[nreg] = rlist
    return rdict

def build_dict_lmx(filename):
    _re_rnum = "^R([0-9]+)\s"
    # R1 0 0 0 0 0 0 0 1 0 0 0 0 1 0 0 0 0 0 0 0 1 CAL_CLK_DIV
    rdict = {}
    with open(filename, 'r') as fd:
        line = fd.readline()
        while line:
            if line.startswith('#'):
                line = fd.readline()
                continue
            _match = re.match(_re_rnum, line.strip())
            if _match:
                rnum = int(_match.groups()[0])
                # Handle the remainder of the line
                line = line[_match.end():]
                rlist = line.split()
                # Discard the first 8 bits (R/W and Addr[6:0])
                rdict[rnum] = rlist[8:]
            else:
                print("Failed to match: {}".format(line))
            line = fd.readline()
    # Filter out any registers with no named fields (only 1 and 0)
    regdict = {}
    for rnum, fields in rdict.items():
        unique = False
        for field in fields:
            if field not in ('0', '1'):
                unique = True
        if unique:
            regdict[rnum] = fields
    rdict = {} # No need for original copy
    # Now guess at the start/end indicies of each field
    for rnum, fields in regdict.items():
        flen = len(fields)
        rlist = []
        num_unique = 0
        for field in fields:
            if field not in ('0', '1'):
                num_unique += 1
        first_unique = True
        for n in range(len(fields)):
            field = fields[n]
            if field not in ('0', '1'):
                if flen == 16:
                    end = 15-n
                    start = 15-n
                elif num_unique == 1:
                    end = 15-n
                    start = flen-n-1
                elif first_unique:
                    end = 15-n
                    start = "Unknown"
                else:
                    end = "Unknown"
                    start = "Unknown"
                first_unique = False
                rlist.append((field, start, end))
        rdict[rnum] = rlist
    return rdict

def print_dict(dd, indent=0, depth=-1):
    ind = " "*indent
    print("dict len {}".format(len(dd)))
    for key, val in dd.items():
        print("{}{}:".format(ind, key), end="")
        if hasattr(val, "keys"):
            if depth == 0:
                print(" dict len {}".format(len(val)))
            else:
                print()
                print_dict(val, indent+2, depth-1)
        else:
            print(" {}".format(val))

def print_dict_py(dd, header=None, asHex=True):
    print("#! python3")
    print("# Auto-generated by lmk_decode.print_dict_py()\n")
    if header is not None:
        print(header)
    print("regdict = {")
    for key, val in dd.items():
        valstr = []
        for field in val:
            valstr.append('("{}", {}, {})'.format(*field))
        if len(valstr) == 1:
            # Wacky hack to get an extra comma appended to convince Python it is actually a tuple of 1 element!
            valstr.append("")
        valstr = '(' + ','.join(valstr) + '),'
        if asHex:
            print("    0x{:03x}: {}".format(key, valstr))
        else:
            print("    {}: {}".format(key, valstr))
    print("}")
    return

def extract_from_xrfclk(_xrfclk, freq, chip=CHIP_LMK):
    if chip == CHIP_LMK:
        tics_list = _xrfclk._Config["lmk04828"].get(freq, None)
    elif chip == CHIP_LMX:
        tics_list = _xrfclk._Config["lmx2594"].get(freq, None)
    else:
        print("Invalid chip {}".format(chip))
        return
    if tics_list is None:
        print("Unsupported frequency {} for chip {}".format(freq, chip_str(chip)))
    field_dict = read_tics_list(tics_list, chip=chip, doPrint=False, asHex=False)
    return field_dict

def doBuildRegdictLMK(filename):
    """Build a register dict from the regmap file downloaded from:
    https://e2e.ti.com/support/clock-timing-group/clock-and-timing/f/clock-timing-forum/338078/plain-text-version-of-lmk04828-s-register-map
    """
    dd = build_dict_lmk(filename)
    header = (
        "# Extracted from plaintext file converted from datasheet by Frank Terbeck and posted to:",
        "# https://e2e.ti.com/support/clock-timing-group/clock-and-timing/f/clock-timing-forum/338078/plain-text-version-of-lmk04828-s-register-map\n",
    )
    header = "\n".join(header)
    print_dict_py(dd, header)
    return

def doBuildRegdictLMX(filename):
    """Build a register dict from the regmap file extracted from the datasheet via:
    pdftotext -f 41 -l 45 -raw lmx2594.pdf textlmx
    """
    dd = build_dict_lmx(filename)
    print_dict_py(dd, asHex=False)
    return

def doDecodeTICS(filename):
    field_dict = read_tics_file(filename, doPrint=False)
    print_dict(field_dict)

if __name__ == "__main__":
    import sys
    #doBuildRegdictLMK(sys.argv[1])
    doDecodeTICS(sys.argv[1])
    #doBuildRegdictLMX(sys.argv[1])
