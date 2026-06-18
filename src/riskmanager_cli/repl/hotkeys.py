"""Control-character hotkey constants shared by the dispatcher and screens.

Each value is ``str(key)`` for a Ctrl-<letter> keystroke as delivered by the
blessed event loop. Terminal-reserved combos are avoided: Ctrl-C/D (interrupt/EOF,
handled in the loop), Ctrl-S/Q (flow control), Ctrl-Z (suspend), Ctrl-H/I/J/M
(backspace, tab, newline, carriage return), and Ctrl-[ (escape).
"""

from __future__ import annotations

CTRL_A = "\x01"  # add
CTRL_B = "\x02"  # library
CTRL_E = "\x05"  # edit
CTRL_F = "\x06"  # focus / filter
CTRL_G = "\x07"  # go home
CTRL_K = "\x0b"  # view molecular structure
CTRL_L = "\x0c"  # list
CTRL_N = "\x0e"  # admin
CTRL_O = "\x0f"  # open / show
CTRL_P = "\x10"  # project (project list)
CTRL_R = "\x12"  # risks
CTRL_T = "\x14"  # routes
CTRL_U = "\x15"  # unassign
CTRL_X = "\x18"  # delete
