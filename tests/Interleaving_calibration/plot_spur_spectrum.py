import numpy as np
import matplotlib.pyplot as plt
import epics
from scipy.signal import find_peaks

def plot_spur_spectrum(I_WAVEFORM_PV, Q_WAVEFORM_PV, FS_EFFECTIVE_MHZ):
    print("Reading live waveforms from EPICS...")

    # Grab the active waveform arrays over the network
    i_arr = epics.caget(I_WAVEFORM_PV)
    q_arr = epics.caget(Q_WAVEFORM_PV)

    if i_arr is None or q_arr is None:
        print("ERROR: Could not read PVs.")
        return

    # Construct the complex baseband vector
    iq_complex = i_arr.astype(np.float64) + 1j * q_arr.astype(np.float64)
    iq_active = iq_complex
    N = len(iq_active)

    # 1. Apply a window scaled specifically to the active pulse length
    window = np.blackman(N)
    windowed_signal = iq_active * window

    # 2. Compute FFT and center the 0 Hz DC term
    fft_raw = np.fft.fft(windowed_signal)
    fft_shifted = np.fft.fftshift(fft_raw)

    # 3. Scale magnitude based on active window coherent gain
    amplitude = np.abs(fft_shifted) / np.sum(window)

    # 4. Convert to dBFS (relative to 16-bit signed full scale max of 32768)
    dbfs = 20 * np.log10(amplitude / 32768.0 + 1e-15)

    # 5. Build symmetric frequency axis matching the active slice span
    freq_axis = np.linspace(-FS_EFFECTIVE_MHZ / 2, FS_EFFECTIVE_MHZ / 2, N)

    # --- SPUR DETECTOR & TABULATION (> -95 dBFS) ---
    peaks, _ = find_peaks(dbfs, height=-95.0, distance=15, prominence=0.5)

    spur_freqs = freq_axis[peaks]
    spur_amps = dbfs[peaks]

    # Sort detected spurs by power (highest power first)
    sorted_indices = np.argsort(spur_amps)[::-1]
    spur_freqs = spur_freqs[sorted_indices]
    spur_amps = spur_amps[sorted_indices]

    # Print Formatted Terminal Table
    print("\n" + "="*58)
    print(f" {'DETECTED SPURS / PEAKS (> -95 dBFS)':^56} ")
    print("="*58)
    print(f" {'#':<4} | {'Frequency Offset (MHz)':<22} | {'Power (dBFS)':<14} | Type")
    print("-" * 58)

    if len(spur_freqs) == 0:
        print(" No spurs detected above the -95 dBFS floor.")
    else:
        for idx, (f, amp) in enumerate(zip(spur_freqs, spur_amps), 1):
            peak_type = "Carrier" if idx == 1 else "Spur / Image"
            print(f" {idx:<4} | {f:>20.3f}    | {amp:>12.2f}    | {peak_type}")

    print("="*58 + "\n")

    # --- PLOTTING (2-ROW SUBPLOT) ---
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 10))

    # --- PLOT 1: FULL SPECTRUM ---
    ax1.plot(freq_axis, dbfs, color='blue', linewidth=1.0, label='Baseband Trace')
    ax1.axhline(-95, color='red', linestyle=':', alpha=0.7, label='Reference Floor (-95 dBFS)')

    if len(spur_freqs) > 0:
        ax1.plot(spur_freqs, spur_amps, 'r*', markersize=6, label=f'Spurs > -95 dBFS ({len(spur_freqs)})')

        # Limit embedded plot table to top 8 spurs
        max_plot_spurs = min(8, len(spur_freqs))
        table_rows = []
        for i in range(max_plot_spurs):
            f_val = spur_freqs[i]
            a_val = spur_amps[i]
            p_type = "Carrier" if i == 0 else "Spur"
            table_rows.append([f"{i+1}", f"{f_val:+.2f} MHz", f"{a_val:.1f} dBFS", p_type])

        col_labels = ["#", "Freq Offset", "Power", "Type"]

        plot_table = ax1.table(
            cellText=table_rows,
            colLabels=col_labels,
            loc='upper left',
            cellLoc='center',
            colWidths=[0.06, 0.22, 0.20, 0.16]
        )

        plot_table.auto_set_font_size(False)
        plot_table.set_fontsize(8)
        plot_table.scale(1.0, 1.2)

        for k, cell in plot_table.get_celld().items():
            if k[0] == 0:
                cell.set_facecolor('#e6e6e6')
                cell.set_text_props(weight='bold')

    ax1.set_title("Full Baseband Power Spectrum", fontsize=12, fontweight='bold')
    ax1.set_xlabel("Baseband Frequency Offset from NCO Carrier (MHz)", fontsize=10)
    ax1.set_ylabel("Power Spectrum (dBFS)", fontsize=10)
    ax1.grid(True, linestyle=':', alpha=0.5)
    ax1.set_ylim(-150, 10)
    ax1.set_xlim(-FS_EFFECTIVE_MHZ / 2, FS_EFFECTIVE_MHZ / 2)
    ax1.legend(loc='upper right')

    # --- PLOT 2: ZOOMED 1 MHz SPAN ---
    center_freq = spur_freqs[0] if len(spur_freqs) > 0 else 0.0
    zoom_min = center_freq - 0.5
    zoom_max = center_freq + 0.5

    ax2.plot(freq_axis, dbfs, color='darkcyan', linewidth=1.2, label='Baseband Trace')
    ax2.axhline(-95, color='red', linestyle=':', alpha=0.7, label='Reference Floor (-95 dBFS)')

    if len(spur_freqs) > 0:
        in_zoom_mask = (spur_freqs >= zoom_min) & (spur_freqs <= zoom_max)
        if np.any(in_zoom_mask):
            ax2.plot(spur_freqs[in_zoom_mask], spur_amps[in_zoom_mask], 'r*', markersize=8, label='In-Span Peaks')

    ax2.set_title(f"Zoomed Power Spectrum (1 MHz Span: {zoom_min:+.2f} to {zoom_max:+.2f} MHz)", fontsize=12, fontweight='bold')
    ax2.set_xlabel("Baseband Frequency Offset from NCO Carrier (MHz)", fontsize=10)
    ax2.set_ylabel("Power Spectrum (dBFS)", fontsize=10)
    ax2.grid(True, linestyle=':', alpha=0.5)
    ax2.set_ylim(-150, 10)
    ax2.set_xlim(zoom_min, zoom_max)
    ax2.legend(loc='upper right')

    plt.tight_layout()
    plt.show()