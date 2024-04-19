import numpy as np
from fractions import Fraction


# Calculations to get fractional frequencies based on
# reference freq of 114.67375 MHz
def calc_num_den(f_ref, freq):
    lo_ratio = Fraction(str(f_ref)).limit_denominator(10e9)
    ref2out_ratio = float(freq)/float(lo_ratio)
    ref2out = Fraction(str(ref2out_ratio)).limit_denominator(1000000000)
    num = ref2out.numerator
    den = ref2out.denominator
    return num, den


# calculate registers by given fractional frequency
def calc_dds(num_dds, den_dds, dwh=32, dwl=12):
    m, modulo = divmod((1 << dwl), den_dds)
    r = (1 << dwh) * num_dds
    phase_step_h = int(r/den_dds)
    phase_step_l = int(r % den_dds * m)
    return phase_step_h, phase_step_l, modulo


def save_data(freq_start, freq_stop, steps):
    f = np.arange(freq_start, freq_stop, steps)
    N = len(f)
    num = np.zeros(N)
    den = np.zeros(N)
    step_h = np.zeros(N)
    step_l = np.zeros(N)
    modulo = np.zeros(N)
    for i, j in enumerate(f):
        num[i], den[i] = calc_num_den(114.67375e6, j)
        step_h[i], step_l[i], modulo[i] = calc_dds(num[i], den[i])
    np.savetxt('ntw_analyzer.txt', np.column_stack((j, step_h, step_l,
               modulo)), fmt="%i")


def doDDSCalc(args):
    fclk = float(args.fclk)
    fdds = float(args.fdds)
    num, den = calc_num_den(fclk, fdds)
    dwh = int(args.dw_high)
    dwl = int(args.dw_low)
    phase_step_h, phase_step_l, modulo = calc_dds(num, den, dwh, dwl)
    print(f"// Frequency F_dds = {fdds*1.0e-6:.3f} MHz with F_clk = {fclk*1.0e-6:.3f} MHz")
    if fdds == 0:
        print(f"localparam MODULATED=\"false\";")
    else:
        print(f"localparam MODULATED=\"true\";")
    print(f"localparam [{dwh-1}:0] phase_step_h = {phase_step_h};")
    print(f"localparam [{dwl-1}:0] phase_step_l = {phase_step_l};")
    print(f"localparam [11:0] modulo = {modulo};")
    return

if __name__ == "__main__":
    from argparse import ArgumentParser
    parser = ArgumentParser(description="Ntw analyzer parameter generation")
    parser.add_argument("fclk", help="Clock Frequency (Hz)")
    parser.add_argument("fdds", help="DDS Target Frequency (Hz)")
    parser.add_argument("-d", "--dw_high", default=20, help="Data width for phase_step_h")
    parser.add_argument("-l", "--dw_low", default=12, help="Data width for phase_step_l")

    args = parser.parse_args()
    doDDSCalc(args)
    #save_data(100e3, 200e3, 100e3)
