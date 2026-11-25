"""python3 -m gothi [--mode auto|keyboard|touch] [--windowed] [--screenshot FILE.bmp --frames N --keys down,ok,...]"""
import argparse

from . import keys
from .apps import main_menu
from .settings import Settings
from .ui import Gothi


def main():
    ap = argparse.ArgumentParser(prog="gothi", description=__doc__)
    ap.add_argument("--mode", choices=("auto", "keyboard", "touch"), default="auto", help="layout; auto = by the keyboard slide of the N900")
    ap.add_argument("--windowed", action="store_true", help="a window even on the N900")
    ap.add_argument("--frames", type=int, help="stop after N frames (tests)")
    ap.add_argument("--keys", default="", help="keys fed one per frame: up,down,left,right,ok,back")
    ap.add_argument("--screenshot", metavar="FILE.bmp", help="save the window at the end")
    a = ap.parse_args()
    from .sdl_frontend import Frontend
    script = [k for k in a.keys.split(",") if k in keys.ALL]
    fe = Frontend(Gothi(main_menu(), Settings()), mode=a.mode, fullscreen=False if a.windowed else None)
    fe.run(frames=a.frames, script=script, shot=a.screenshot)


if __name__ == "__main__":
    main()
