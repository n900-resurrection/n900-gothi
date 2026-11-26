"""python3 -m gothi [--mode auto|keyboard|touch] [--windowed] [--screenshot FILE.bmp --frames N --keys down,ok,...]"""
import argparse

from . import keys
from .apps import main_menu
from .dolphin import SHIPPED, DolphinState, config_dir, load_rules
from .modules import discover
from .settings import Settings
from .ui import Gothi


def main():
    ap = argparse.ArgumentParser(prog="gothi", description=__doc__)
    ap.add_argument("--mode", choices=("auto", "keyboard", "touch"), default="auto", help="layout; auto = by the keyboard slide of the N900")
    ap.add_argument("--windowed", action="store_true", help="a window even on the N900")
    ap.add_argument("--frames", type=int, help="stop after N frames (tests)")
    ap.add_argument("--keys", default="", help="keys fed one per frame: up,down,left,right,ok,back; t:text types text (no commas)")
    ap.add_argument("--screenshot", metavar="FILE.bmp", help="save the window at the end")
    ap.add_argument("--rules", action="store_true", help="show where the rules of the dolphin (XP, levels, butthurt) are, and exit")
    ap.add_argument("--modules", action="store_true", help="list the folders searched for modules and the modules found, and exit")
    a = ap.parse_args()
    if a.modules:
        from .modules import search_dirs
        mods, errs = discover()
        print("search folders: " + ", ".join(search_dirs()))
        for m in mods:
            print(f"  {m.id}: {m.title} ({m.kind}) {m.path}")
        for n, e in errs:
            print(f"  {n}: FAILED {e}")
        print(f"{len(mods)} modules, {len(errs)} failed")
        return
    if a.rules:
        print(f"shipped rules (copy what you change): {SHIPPED}\nyour overrides: {config_dir()}/rules.json\ndolphin state: {config_dir()}/dolphin-state.json")
        return
    found = discover()
    from .sdl_frontend import Frontend
    script = [k for k in a.keys.split(",") if k in keys.ALL or k.startswith("t:")]
    fe = Frontend(Gothi(main_menu(found), Settings(), DolphinState(load_rules(extra=[{"deeds": m.deeds} for m in found[0]]))), mode=a.mode, fullscreen=False if a.windowed else None)
    fe.run(frames=a.frames, script=script, shot=a.screenshot)


if __name__ == "__main__":
    main()
