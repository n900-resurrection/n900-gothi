"""Tests of gothi/wifi.py (scan parsing, statistics, saved networks), fictional networks:  python3 -m unittest discover -s tests"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from gothi import wifi  # noqa: E402

SCAN = '''wlan0     Scan completed :
          Cell 01 - Address: AA:BB:CC:00:00:01
                    ESSID:"Home-Net"
                    Mode:Master
                    Channel:1
                    Frequency:2.412 GHz (Channel 1)
                    Quality=86/100  Signal level:-39 dBm  Noise level=-83 dBm
                    Encryption key:on
                    IE: IEEE 802.11i/WPA2 Version 1
                        Group Cipher : CCMP
                        Pairwise Ciphers (1) : CCMP
                        Authentication Suites (1) : PSK
                    Extra: Last beacon: 843ms ago
          Cell 02 - Address: AA:BB:CC:00:00:02
                    ESSID:"Cafe Guest"
                    Mode:Master
                    Channel:6
                    Quality=40/100  Signal level:-70 dBm  Noise level=-91 dBm
                    Encryption key:off
          Cell 03 - Address: aa:bb:cc:00:00:03
                    ESSID:"Old-Router"
                    Channel:11
                    Quality=30/100  Signal level:-75 dBm  Noise level=-91 dBm
                    Encryption key:on
                    IE: WPA Version 1
                        Group Cipher : TKIP
                        Authentication Suites (1) : PSK
          Cell 04 - Address: AA:BB:CC:00:00:04
                    ESSID:"WEP-Relic"
                    Channel:11
                    Quality=20/100  Signal level:-80 dBm  Noise level=-91 dBm
                    Encryption key:on
          Cell 05 - Address: AA:BB:CC:00:00:05
                    ESSID:"Campus"
                    Channel:36
                    Quality=50/100  Signal level:-65 dBm  Noise level=-91 dBm
                    Encryption key:on
                    IE: IEEE 802.11i/WPA2 Version 1
                        Authentication Suites (1) : 802.1x
          Cell 06 - Address: AA:BB:CC:00:00:06
                    ESSID:""
                    Channel:6
                    Quality=45/100  Signal level:-68 dBm  Noise level=-91 dBm
                    Encryption key:on
                    IE: IEEE 802.11i/WPA2 Version 1
                        Authentication Suites (1) : PSK
                    IE: WPA Version 1
'''

GCONF = ''' /system/osso/connectivity/IAP/11111111-aaaa-bbbb-cccc-000000000001:
  ipv4_type = AUTO
  wlan_ssid = [72,111,109,101,45,78,101,116]
  wlan_hidden = false
  type = WLAN_INFRA
  wlan_security = WPA_PSK
  name = Home-Net
 /system/osso/connectivity/IAP/Mobile@32@Data:
  ipv4_type = AUTO
  name = Mobile data
  type = GPRS
 /system/osso/connectivity/IAP/11111111-aaaa-bbbb-cccc-000000000002:
  wlan_ssid = [72,105,100,100,101,110]
  wlan_hidden = true
  type = WLAN_INFRA
  wlan_security = NONE
'''


class ScanTest(unittest.TestCase):
    def setUp(self):
        self.nets = wifi.parse_scan(SCAN)

    def test_parses_every_cell(self):
        self.assertEqual([n["ssid"] for n in self.nets], ["Home-Net", "Cafe Guest", "Old-Router", "WEP-Relic", "Campus", ""])
        n = self.nets[0]
        self.assertEqual((n["bssid"], n["channel"], n["signal"], n["quality"]), ("AA:BB:CC:00:00:01", 1, -39, 86))
        self.assertEqual(self.nets[2]["bssid"], "AA:BB:CC:00:00:03")            # upper-cased

    def test_security_classes(self):
        self.assertEqual([n["security"] for n in self.nets], ["WPA2", "OPEN", "WPA", "WEP", "WPA2 EAP", "WPA/WPA2"])

    def test_hidden_network(self):
        self.assertTrue(self.nets[5]["hidden"])
        self.assertFalse(self.nets[0]["hidden"])
        self.assertTrue(wifi.parse_scan(SCAN.replace('ESSID:""', 'ESSID:"\\x00\\x00\\x00"'))[5]["hidden"])

    def test_empty_and_garbage_input(self):
        self.assertEqual(wifi.parse_scan(""), [])
        self.assertEqual(wifi.parse_scan("wlan0     No scan results\n"), [])
        self.assertEqual(wifi.parse_scan("Cell 01 - Address: nonsense\n"), [])

    def test_a_missing_signal_does_not_break(self):
        nets = wifi.parse_scan("  Cell 01 - Address: AA:BB:CC:00:00:09\n   ESSID:\"x\"\n   Channel:3\n   Encryption key:off\n")
        self.assertEqual((nets[0]["signal"], nets[0]["quality"]), (None, None))
        self.assertEqual(wifi.sort_by_signal(nets + self.nets)[-1]["bssid"], "AA:BB:CC:00:00:09")

    def test_sort_and_bars(self):
        s = wifi.sort_by_signal(self.nets)
        self.assertEqual(s[0]["ssid"], "Home-Net")
        self.assertEqual(s[-1]["ssid"], "WEP-Relic")
        self.assertEqual([wifi.bar(x) for x in (-30, -50, -70, -90, -100, None)], [4, 4, 2, 0, 0, 0])


class StatsTest(unittest.TestCase):
    def setUp(self):
        self.nets = wifi.parse_scan(SCAN)

    def test_channel_usage_counts_only_the_24_ghz_band(self):
        self.assertEqual(wifi.channel_usage(self.nets), {1: 1, 6: 2, 11: 2})

    def test_summary(self):
        s = wifi.summary(self.nets)
        self.assertEqual((s["count"], s["hidden"], s["open"], s["strongest"]), (6, 1, 1, -39))
        self.assertEqual(s["security"]["WPA2"], 1)

    def test_best_channel_avoids_the_crowd(self):
        best = wifi.best_channel(self.nets)
        self.assertNotIn(best, wifi.channel_usage(self.nets))                    # never a channel that carries a network here
        self.assertEqual(best, 13)                                              # far from the strong network on 1 and the pair on 11
        self.assertEqual(wifi.best_channel([]), 1)
        crowded = [{"channel": c, "signal": -40} for c in (1, 1, 1, 2, 3, 4, 5, 6, 7, 11)]
        self.assertIn(wifi.best_channel(crowded), (9, 10, 12, 13))

    def test_merge_keeps_the_best_sample_and_reports_new_ones(self):
        known = {}
        self.assertEqual(len(wifi.merge(known, self.nets)), 6)
        better = [dict(self.nets[1], signal=-50)]
        worse = [dict(self.nets[0], signal=-80)]
        self.assertEqual(wifi.merge(known, better + worse), [])
        self.assertEqual(known["AA:BB:CC:00:00:02"]["signal"], -50)
        self.assertEqual(known["AA:BB:CC:00:00:01"]["signal"], -39)
        self.assertEqual(self.nets[1]["signal"], -70)                         # the caller's data are not changed


class ScanRunTest(unittest.TestCase):
    def test_scan_with_a_fake_tool(self):
        self.assertEqual(len(wifi.scan(run=lambda: SCAN)), 6)

    def test_a_failing_tool_gives_an_empty_list(self):
        def boom():
            raise OSError("no iwlist")
        self.assertEqual(wifi.scan(run=boom), [])


class FallbackTest(unittest.TestCase):
    """scan() without a runner: sudo first (a fresh scan), then the plain tool (the cache of the last scan)."""

    def fake(self, outputs):
        calls = []

        def runner(cmd, **kw):
            calls.append(cmd)
            out = outputs.pop(0)
            if isinstance(out, Exception):
                raise out
            return type("P", (), {"stdout": out})()
        return calls, runner

    def test_sudo_is_used_first(self):
        calls, runner = self.fake([SCAN])
        self.assertEqual(len(wifi.parse_scan(wifi._iwlist(True, runner))), 6)
        self.assertEqual(calls[0][:2], ["sudo", "iwlist"])

    def test_the_command_is_exactly_the_one_of_the_sudo_rule(self):
        calls, runner = self.fake(["", ""])
        wifi._iwlist(True, runner)
        wifi._iwlist(False, runner)
        self.assertEqual(calls, [["sudo", "iwlist", "wlan0", "scan"], ["iwlist", "wlan0", "scan"]])

    def test_scan_falls_back_when_sudo_gives_nothing(self):
        calls, runner = self.fake(["sudo: no tty present", SCAN])
        orig = wifi._iwlist
        wifi._iwlist = lambda sudo, runner=runner: orig(sudo, runner)
        try:
            self.assertEqual(len(wifi.scan()), 6)
            self.assertEqual([c[0] for c in calls], ["sudo", "iwlist"])
        finally:
            wifi._iwlist = orig

    def test_scan_survives_missing_tools(self):
        calls, runner = self.fake([OSError("no sudo"), OSError("no iwlist")])
        orig = wifi._iwlist
        wifi._iwlist = lambda sudo, runner=runner: orig(sudo, runner)
        try:
            self.assertEqual(wifi.scan(), [])
        finally:
            wifi._iwlist = orig


class SavedTest(unittest.TestCase):
    def test_decode_ssid(self):
        self.assertEqual(wifi.decode_ssid("[72,111,109,101]"), "Home")
        self.assertEqual(wifi.decode_ssid("[196,141,97]"), "ča")                 # UTF-8
        self.assertEqual(wifi.decode_ssid(""), "")

    def test_saved_networks_skip_mobile_data(self):
        s = wifi.saved_networks(GCONF)
        self.assertEqual([n["ssid"] for n in s], ["Home-Net", "Hidden"])
        self.assertEqual(s[0]["name"], "Home-Net")
        self.assertEqual(s[0]["id"], "11111111-aaaa-bbbb-cccc-000000000001")
        self.assertEqual((s[0]["security"], s[0]["hidden"]), ("WPA_PSK", False))
        self.assertTrue(s[1]["hidden"])
        self.assertEqual(s[1]["name"], "Hidden")                               # no name: the SSID is used

    def test_nothing_saved(self):
        self.assertEqual(wifi.saved_networks(""), [])


if __name__ == "__main__":
    unittest.main()
