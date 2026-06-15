#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════╗
║           🔥 Fire TV ADB Controller 🔥               ║
║     Détection, connexion et contrôle à distance      ║
╚══════════════════════════════════════════════════════╝

Prérequis :
  pip install pure-python-adb zeroconf colorama
  + adb installé sur votre machine (dans le PATH)

Sur le Fire TV Stick :
  Paramètres > Mon Fire TV > Options pour les développeurs
    ✔ Débogage ADB activé
    ✔ Débogage ADB réseau activé (Fire OS 7+)
"""

import subprocess
import socket
import threading
import time
import sys
import os
from typing import Optional

# ── Dépendances optionnelles ──────────────────────────────────────────────────
try:
    from colorama import init, Fore, Style, Back
    init(autoreset=True)
    HAS_COLOR = True
except ImportError:
    HAS_COLOR = False
    class Fore:
        RED = GREEN = YELLOW = CYAN = MAGENTA = WHITE = BLUE = ""
    class Style:
        BRIGHT = RESET_ALL = DIM = ""
    class Back:
        BLACK = ""

try:
    from zeroconf import ServiceBrowser, Zeroconf
    HAS_ZEROCONF = True
except ImportError:
    HAS_ZEROCONF = False

# ── Constantes ────────────────────────────────────────────────────────────────
ADB_PORT        = 5555
SCAN_TIMEOUT    = 5
CONNECT_TIMEOUT = 8

KEYCODES = {
    "home"       : "KEYCODE_HOME",
    "back"       : "KEYCODE_BACK",
    "menu"       : "KEYCODE_MENU",
    "up"         : "KEYCODE_DPAD_UP",
    "down"       : "KEYCODE_DPAD_DOWN",
    "left"       : "KEYCODE_DPAD_LEFT",
    "right"      : "KEYCODE_DPAD_RIGHT",
    "select"     : "KEYCODE_DPAD_CENTER",
    "play_pause" : "KEYCODE_MEDIA_PLAY_PAUSE",
    "play"       : "KEYCODE_MEDIA_PLAY",
    "pause"      : "KEYCODE_MEDIA_PAUSE",
    "stop"       : "KEYCODE_MEDIA_STOP",
    "next"       : "KEYCODE_MEDIA_NEXT",
    "prev"       : "KEYCODE_MEDIA_PREVIOUS",
    "rewind"     : "KEYCODE_MEDIA_REWIND",
    "forward"    : "KEYCODE_MEDIA_FAST_FORWARD",
    "vol_up"     : "KEYCODE_VOLUME_UP",
    "vol_down"   : "KEYCODE_VOLUME_DOWN",
    "mute"       : "KEYCODE_VOLUME_MUTE",
    "power"      : "KEYCODE_POWER",
    "sleep"      : "KEYCODE_SLEEP",
    "wake"       : "KEYCODE_WAKEUP",
}

# ── Helpers visuels ───────────────────────────────────────────────────────────
def banner():
    print(Fore.CYAN + Style.BRIGHT + """
╔══════════════════════════════════════════════════════╗
║           🔥  Fire TV ADB Controller  🔥             ║
║     Détection · Connexion · Contrôle à distance      ║
╚══════════════════════════════════════════════════════╝""")
    print(Fore.WHITE + Style.DIM + "  Utilisez 'aide' pour voir toutes les commandes\n")

def ok(msg):   print(Fore.GREEN  + "  ✔ " + msg)
def err(msg):  print(Fore.RED    + "  ✖ " + msg)
def info(msg): print(Fore.CYAN   + "  ℹ " + msg)
def warn(msg): print(Fore.YELLOW + "  ⚠ " + msg)

def separator(title=""):
    w = 54
    if title:
        pad = (w - len(title) - 2) // 2
        print(Fore.CYAN + "─" * pad + f" {title} " + "─" * pad)
    else:
        print(Fore.CYAN + "─" * w)

def spinner(stop_event, msg="En cours"):
    frames = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
    i = 0
    while not stop_event.is_set():
        print(f"\r{Fore.YELLOW}  {frames[i % len(frames)]} {msg}...", end="", flush=True)
        time.sleep(0.1)
        i += 1
    print("\r" + " " * (len(msg) + 10) + "\r", end="")

# ── ADB wrapper ───────────────────────────────────────────────────────────────
def adb(args: list, timeout=10):
    try:
        result = subprocess.run(
            ["adb"] + args,
            capture_output=True, text=True, timeout=timeout
        )
        out = (result.stdout + result.stderr).strip()
        return result.returncode == 0, out
    except FileNotFoundError:
        return False, "adb introuvable. Installez Android Platform Tools."
    except subprocess.TimeoutExpired:
        return False, "Timeout."
    except Exception as e:
        return False, str(e)

def adb_shell(device_ip: str, cmd: str, timeout=10):
    return adb(["-s", f"{device_ip}:{ADB_PORT}", "shell", cmd], timeout=timeout)

# ── Détection réseau ──────────────────────────────────────────────────────────
def scan_ip_range(base_ip: str, port=ADB_PORT, timeout=0.4):
    found = []
    lock  = threading.Lock()

    def try_host(ip):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            if s.connect_ex((ip, port)) == 0:
                with lock:
                    found.append(ip)
            s.close()
        except Exception:
            pass

    parts   = base_ip.rsplit(".", 1)
    threads = [threading.Thread(target=try_host, args=(f"{parts[0]}.{i}",), daemon=True)
               for i in range(1, 255)]
    for t in threads: t.start()
    for t in threads: t.join(timeout=timeout + 0.2)
    return found

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None

def discover_mdns():
    if not HAS_ZEROCONF:
        return []
    found_ips = []

    class ADBListener:
        def add_service(self, zc, type_, name):
            nfo = zc.get_service_info(type_, name)
            if nfo and nfo.addresses:
                ip = socket.inet_ntoa(nfo.addresses[0])
                if ip not in found_ips:
                    found_ips.append(ip)
        def remove_service(self, *_): pass
        def update_service(self, *_): pass

    zc = Zeroconf()
    listener = ADBListener()
    ServiceBrowser(zc, "_adb-tls-connect._tcp.local.", listener)
    ServiceBrowser(zc, "_androidtvremote2._tcp.local.", listener)
    time.sleep(3)
    zc.close()
    return found_ips

# ── Classe Fire TV ────────────────────────────────────────────────────────────
class FireTV:
    def __init__(self, ip: str):
        self.ip   = ip
        self.addr = f"{ip}:{ADB_PORT}"

    def connect(self) -> bool:
        stop = threading.Event()
        t = threading.Thread(target=spinner, args=(stop, "Connexion ADB"))
        t.start()
        ok_f, out = adb(["connect", self.addr], timeout=CONNECT_TIMEOUT)
        stop.set(); t.join()
        if "connected" in out.lower():
            ok(f"Connecté à {self.addr}")
            return True
        err(f"Échec : {out}")
        return False

    def disconnect(self):
        adb(["disconnect", self.addr])
        ok(f"Déconnecté de {self.addr}")

    def shell(self, cmd: str, silent=False) -> str:
        _, out = adb_shell(self.ip, cmd)
        if not silent and out:
            print(Fore.WHITE + "  " + out)
        return out

    def power_off(self):
        self.shell("input keyevent KEYCODE_SLEEP")
        ok("Signal d'extinction envoyé (veille).")

    def power_on(self):
        self.shell("input keyevent KEYCODE_WAKEUP")
        ok("Signal de réveil envoyé.")

    def reboot(self):
        warn("Redémarrage en cours…")
        self.shell("reboot")

    def keyevent(self, key: str):
        code = KEYCODES.get(key.lower(), key.upper())
        self.shell(f"input keyevent {code}", silent=True)
        ok(f"Touche envoyée : {code}")

    def launch_app(self, package: str):
        self.shell(f"monkey -p {package} -c android.intent.category.LAUNCHER 1", silent=True)
        ok(f"Application lancée : {package}")

    def list_packages(self):
        out  = self.shell("pm list packages", silent=True)
        pkgs = [l.replace("package:", "").strip() for l in out.splitlines() if l.startswith("package:")]
        for p in sorted(pkgs):
            print(Fore.WHITE + f"    {p}")
        info(f"{len(pkgs)} paquets trouvés.")

    def screenshot(self, local_path="screenshot.png"):
        stop = threading.Event()
        t = threading.Thread(target=spinner, args=(stop, "Capture d'écran"))
        t.start()
        self.shell("screencap -p /sdcard/screen.png", silent=True)
        s, out = adb(["-s", self.addr, "pull", "/sdcard/screen.png", local_path])
        stop.set(); t.join()
        if s:
            ok(f"Screenshot sauvegardé : {local_path}")
        else:
            err(f"Échec : {out}")

    def get_info(self):
        separator("Informations appareil")
        props = {
            "Modèle"      : "ro.product.model",
            "Fabricant"   : "ro.product.manufacturer",
            "Android"     : "ro.build.version.release",
            "Fire OS"     : "ro.build.display.id",
            "Numéro série": "ro.serialno",
        }
        for label, prop in props.items():
            val = self.shell(f"getprop {prop}", silent=True).strip()
            print(f"  {Fore.CYAN}{label:<15}{Fore.WHITE}{val or '—'}")

    def send_text(self, text: str):
        escaped = text.replace(" ", "%s").replace("'", "\\'")
        self.shell(f"input text '{escaped}'", silent=True)
        ok(f"Texte envoyé : {text}")

    def set_volume(self, level: int):
        for _ in range(15):
            self.shell("input keyevent KEYCODE_VOLUME_DOWN", silent=True)
        for _ in range(max(0, min(level, 15))):
            self.shell("input keyevent KEYCODE_VOLUME_UP", silent=True)
        ok(f"Volume réglé à {level}/15")

# ── Aide ──────────────────────────────────────────────────────────────────────
APPS_CONNUS = {
    "netflix" : "com.netflix.ninja",
    "prime"   : "com.amazon.avod.thirdpartyclient",
    "youtube" : "com.amazon.firetv.youtube",
    "disney"  : "com.disney.disneyplus",
    "twitch"  : "tv.twitch.android.viewer",
    "plex"    : "com.plexapp.android",
    "kodi"    : "org.xbmc.kodi",
}

def afficher_aide():
    print(f"""
{Fore.CYAN}{Style.BRIGHT}Commandes disponibles :

{Fore.YELLOW}  [Détection & connexion]
{Fore.WHITE}  scanner           — Recherche des appareils sur le réseau local
  connecter <ip>    — Connexion ADB à une IP donnée
  deconnecter       — Déconnexion de l'appareil courant

{Fore.YELLOW}  [Contrôle]
{Fore.WHITE}  eteindre          — Met l'appareil en veille
  allumer           — Réveille l'appareil
  redemarrer        — Redémarre l'appareil
  touche <nom>      — Envoie une touche (home, back, play_pause…)
  volume <0-15>     — Règle le volume
  texte <...>       — Envoie du texte

{Fore.YELLOW}  [Applications]
{Fore.WHITE}  apps              — Liste les applications installées
  lancer <package>  — Lance une app (ou alias : netflix, prime…)

{Fore.YELLOW}  [Infos & debug]
{Fore.WHITE}  info              — Affiche les infos de l'appareil
  screenshot        — Capture l'écran → screenshot.png
  shell <cmd>       — Commande ADB shell directe

{Fore.YELLOW}  [Touches disponibles]
{Fore.WHITE}  home  back  menu  up  down  left  right  select
  play_pause  play  pause  stop  next  prev  rewind  forward
  vol_up  vol_down  mute  power  sleep  wake

{Fore.YELLOW}  [Général]
{Fore.WHITE}  aide / help       — Affiche ce message
  quitter           — Quitte le programme
""")

# ── Boucle principale ─────────────────────────────────────────────────────────
def main():
    banner()

    ok_f, out = adb(["version"])
    if not ok_f:
        err(out)
        warn("Installez Android Platform Tools :")
        warn("https://developer.android.com/tools/releases/platform-tools")
        sys.exit(1)
    info(out.splitlines()[0])

    device: Optional[FireTV] = None

    while True:
        try:
            prompt = (f"\n{Fore.GREEN}[{device.ip}]{Style.RESET_ALL} "
                      if device else f"\n{Fore.YELLOW}[non connecté]{Style.RESET_ALL} ")
            raw = input(prompt + f"{Fore.CYAN}>{Style.RESET_ALL} ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            ok("Au revoir !")
            break

        if not raw:
            continue

        parts = raw.split(maxsplit=1)
        cmd   = parts[0].lower()
        arg   = parts[1] if len(parts) > 1 else ""

        if cmd in ("aide", "help"):
            afficher_aide()

        elif cmd == "quitter":
            if device: device.disconnect()
            ok("Au revoir !")
            break

        elif cmd == "scanner":
            separator("Scan réseau")
            local_ip = get_local_ip()
            if not local_ip:
                err("Impossible de déterminer votre IP locale."); continue
            info(f"IP locale : {local_ip}")

            mdns_ips = []
            if HAS_ZEROCONF:
                stop = threading.Event()
                t    = threading.Thread(target=spinner, args=(stop, "Découverte mDNS"))
                t.start()
                mdns_ips = discover_mdns()
                stop.set(); t.join()

            stop = threading.Event()
            t    = threading.Thread(target=spinner, args=(stop, f"Scan TCP {local_ip.rsplit('.',1)[0]}.x/24"))
            t.start()
            tcp_ips = scan_ip_range(local_ip)
            stop.set(); t.join()

            all_ips = list(dict.fromkeys(mdns_ips + tcp_ips))
            if all_ips:
                ok(f"{len(all_ips)} appareil(s) ADB trouvé(s) :")
                for i, ip in enumerate(all_ips, 1):
                    print(f"  {Fore.CYAN}{i}.{Fore.WHITE} {ip}:{ADB_PORT}")
                info("Tapez  connecter <ip>  pour vous connecter.")
            else:
                warn("Aucun appareil ADB détecté.")
                info("Activez le débogage ADB réseau dans les paramètres du Fire TV.")

        elif cmd == "connecter":
            ip = arg.strip() or input("  IP de l'appareil : ").strip()
            if not ip:
                err("IP requise."); continue
            tv = FireTV(ip)
            if tv.connect():
                device = tv
            else:
                warn("Acceptez la demande de débogage sur l'écran du Fire TV.")

        elif cmd == "deconnecter":
            if not device: warn("Aucun appareil connecté."); continue
            device.disconnect(); device = None

        elif cmd == "eteindre":
            if not device: warn("Aucun appareil connecté."); continue
            device.power_off()

        elif cmd == "allumer":
            if not device: warn("Aucun appareil connecté."); continue
            device.power_on()

        elif cmd == "redemarrer":
            if not device: warn("Aucun appareil connecté."); continue
            c = input(f"  {Fore.YELLOW}Confirmer le redémarrage ? (o/n) : {Style.RESET_ALL}").strip().lower()
            if c == "o": device.reboot()
            else: info("Annulé.")

        elif cmd == "touche":
            if not device: warn("Aucun appareil connecté."); continue
            key = arg or input("  Nom de la touche : ").strip()
            device.keyevent(key)

        elif cmd == "volume":
            if not device: warn("Aucun appareil connecté."); continue
            try: device.set_volume(int(arg))
            except ValueError: err("Valeur entre 0 et 15.")

        elif cmd == "texte":
            if not device: warn("Aucun appareil connecté."); continue
            device.send_text(arg or input("  Texte : ").strip())

        elif cmd == "apps":
            if not device: warn("Aucun appareil connecté."); continue
            device.list_packages()

        elif cmd == "lancer":
            if not device: warn("Aucun appareil connecté."); continue
            pkg = APPS_CONNUS.get(arg.lower(), arg)
            if not pkg:
                separator("Apps connues")
                for alias, package in APPS_CONNUS.items():
                    print(f"  {Fore.CYAN}{alias:<12}{Fore.WHITE}{package}")
                raw_pkg = input("  Package ou alias : ").strip()
                pkg = APPS_CONNUS.get(raw_pkg.lower(), raw_pkg)
            device.launch_app(pkg)

        elif cmd == "info":
            if not device: warn("Aucun appareil connecté."); continue
            device.get_info()

        elif cmd == "screenshot":
            if not device: warn("Aucun appareil connecté."); continue
            device.screenshot(arg or "screenshot.png")

        elif cmd == "shell":
            if not device: warn("Aucun appareil connecté."); continue
            if not arg: err("Commande requise."); continue
            device.shell(arg)

        else:
            warn(f"Commande inconnue : '{cmd}'. Tapez 'aide'.")

if __name__ == "__main__":
    main()