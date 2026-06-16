#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════╗
║           🦈  SharkX  —  TV Remote CLI           ║
║        Contrôle à distance Hitachi Smart TV      ║
╚══════════════════════════════════════════════════╝
Protocoles supportés : Android TV (ADB) + Wake-on-LAN
"""

import sys
import os
import socket
import struct
import time
import json
import argparse
import subprocess
from pathlib import Path

# ── Couleurs ANSI ──────────────────────────────────────────────────────────────
class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    BLUE   = "\033[94m"
    CYAN   = "\033[96m"
    WHITE  = "\033[97m"
    BG_DARK = "\033[48;5;234m"

# ── Config ─────────────────────────────────────────────────────────────────────
CONFIG_FILE = Path.home() / ".sharkx_config.json"
DEFAULT_CONFIG = {
    "tv_ip": "",
    "tv_port": 5555,
    "tv_mac": "",
    "adb_path": "adb",
    "connection_mode": "adb",   # "adb" ou "network"
}

# ── Keycodes Android TV (ADB) ──────────────────────────────────────────────────
ADB_KEYS = {
    # Alimentation
    "power":          "KEYCODE_POWER",
    "sleep":          "KEYCODE_SLEEP",
    "wakeup":         "KEYCODE_WAKEUP",
    # Volume
    "vol+":           "KEYCODE_VOLUME_UP",
    "vol-":           "KEYCODE_VOLUME_DOWN",
    "mute":           "KEYCODE_VOLUME_MUTE",
    # Navigation
    "up":             "KEYCODE_DPAD_UP",
    "down":           "KEYCODE_DPAD_DOWN",
    "left":           "KEYCODE_DPAD_LEFT",
    "right":          "KEYCODE_DPAD_RIGHT",
    "ok":             "KEYCODE_DPAD_CENTER",
    "back":           "KEYCODE_BACK",
    "home":           "KEYCODE_HOME",
    "menu":           "KEYCODE_MENU",
    # Lecture
    "play":           "KEYCODE_MEDIA_PLAY",
    "pause":          "KEYCODE_MEDIA_PAUSE",
    "playpause":      "KEYCODE_MEDIA_PLAY_PAUSE",
    "stop":           "KEYCODE_MEDIA_STOP",
    "next":           "KEYCODE_MEDIA_NEXT",
    "prev":           "KEYCODE_MEDIA_PREVIOUS",
    "rewind":         "KEYCODE_MEDIA_REWIND",
    "forward":        "KEYCODE_MEDIA_FAST_FORWARD",
    # Chaînes
    "ch+":            "KEYCODE_CHANNEL_UP",
    "ch-":            "KEYCODE_CHANNEL_DOWN",
    # Entrées
    "hdmi":           "KEYCODE_TV_INPUT_HDMI_1",
    "hdmi1":          "KEYCODE_TV_INPUT_HDMI_1",
    "hdmi2":          "KEYCODE_TV_INPUT_HDMI_2",
    "hdmi3":          "KEYCODE_TV_INPUT_HDMI_3",
    "input":          "KEYCODE_TV_INPUT",
    # Fonctions
    "info":           "KEYCODE_INFO",
    "guide":          "KEYCODE_GUIDE",
    "settings":       "KEYCODE_SETTINGS",
    "search":         "KEYCODE_SEARCH",
    # Couleurs (télétexte)
    "red":            "KEYCODE_PROG_RED",
    "green":          "KEYCODE_PROG_GREEN",
    "yellow":         "KEYCODE_PROG_YELLOW",
    "blue":           "KEYCODE_PROG_BLUE",
    # Apps
    "netflix":        None,   # lancé via intent
    "youtube":        None,
    "prime":          None,
}

# Intents Android pour lancer des apps
APP_INTENTS = {
    "netflix":  "com.netflix.ninja/.MainActivity",
    "youtube":  "com.google.android.youtube.tv/com.google.android.youtube.tv.MainActivity",
    "prime":    "com.amazon.amazonvideo.livingroom/.MainActivity",
    "disney":   "com.disney.disneyplus/.activity.SplashActivity",
}

# ── Bannière ───────────────────────────────────────────────────────────────────
BANNER = f"""
{C.CYAN}{C.BOLD}
  ███████╗██╗  ██╗ █████╗ ██████╗ ██╗  ██╗██╗  ██╗
  ██╔════╝██║  ██║██╔══██╗██╔══██╗██║ ██╔╝╚██╗██╔╝
  ███████╗███████║███████║██████╔╝█████╔╝  ╚███╔╝ 
  ╚════██║██╔══██║██╔══██║██╔══██╗██╔═██╗  ██╔██╗ 
  ███████║██║  ██║██║  ██║██║  ██║██║  ██╗██╔╝ ██╗
  ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝{C.RESET}
{C.DIM}        🦈  Contrôle Hitachi Smart TV à distance{C.RESET}
"""

# ── Helpers ────────────────────────────────────────────────────────────────────
def ok(msg):    print(f"  {C.GREEN}✔{C.RESET}  {msg}")
def err(msg):   print(f"  {C.RED}✘{C.RESET}  {msg}", file=sys.stderr)
def info(msg):  print(f"  {C.CYAN}ℹ{C.RESET}  {msg}")
def warn(msg):  print(f"  {C.YELLOW}⚠{C.RESET}  {msg}")
def sep():      print(f"  {C.DIM}{'─' * 48}{C.RESET}")

def load_config():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                cfg = json.load(f)
            return {**DEFAULT_CONFIG, **cfg}
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
    ok(f"Config sauvegardée dans {CONFIG_FILE}")

# ── Wake-on-LAN ────────────────────────────────────────────────────────────────
def send_wol(mac: str, broadcast: str = "255.255.255.255", port: int = 9):
    """Envoie un Magic Packet Wake-on-LAN."""
    mac_clean = mac.replace(":", "").replace("-", "").replace(".", "")
    if len(mac_clean) != 12:
        raise ValueError(f"Adresse MAC invalide : {mac!r}")
    mac_bytes = bytes.fromhex(mac_clean)
    packet = b"\xff" * 6 + mac_bytes * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(packet, (broadcast, port))
        s.sendto(packet, (broadcast, 7))   # port alternatif

# ── ADB ────────────────────────────────────────────────────────────────────────
class ADBRemote:
    def __init__(self, ip: str, port: int = 5555, adb_path: str = "adb"):
        self.ip = ip
        self.port = port
        self.adb = adb_path
        self.target = f"{ip}:{port}"

    def _run(self, *args, capture=True):
        cmd = [self.adb] + list(args)
        try:
            r = subprocess.run(
                cmd,
                capture_output=capture,
                text=True,
                timeout=10,
            )
            return r.returncode, r.stdout.strip(), r.stderr.strip()
        except FileNotFoundError:
            raise RuntimeError(
                f"Commande '{self.adb}' introuvable. "
                "Installez ADB : https://developer.android.com/tools/adb"
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("Délai d'attente ADB dépassé.")

    def connect(self):
        code, out, stderr = self._run("connect", self.target)
        if "connected" in out.lower() or "already connected" in out.lower():
            return True
        raise RuntimeError(f"Connexion ADB échouée : {out or stderr}")

    def disconnect(self):
        self._run("disconnect", self.target)

    def send_key(self, keycode: str):
        code, out, stderr = self._run(
            "-s", self.target, "shell",
            "input", "keyevent", keycode
        )
        if code != 0:
            raise RuntimeError(stderr or "Erreur keyevent")

    def launch_app(self, component: str):
        code, out, stderr = self._run(
            "-s", self.target, "shell",
            "am", "start", "-n", component
        )
        if code != 0:
            raise RuntimeError(stderr or "Erreur am start")

    def get_property(self, prop: str) -> str:
        _, out, _ = self._run("-s", self.target, "shell", "getprop", prop)
        return out

    def shell(self, *cmd):
        code, out, stderr = self._run("-s", self.target, "shell", *cmd)
        return out

    def is_screen_on(self) -> bool:
        out = self.shell("dumpsys", "power")
        return "mWakefulness=Awake" in out or "mHoldingWakeLockSuspendBlocker" in out

# ── Commandes de haut niveau ───────────────────────────────────────────────────
def cmd_config(args):
    """Configuration interactive."""
    print(BANNER)
    print(f"  {C.BOLD}⚙  Configuration SharkX{C.RESET}\n")
    cfg = load_config()

    fields = [
        ("tv_ip",   "Adresse IP de la télé",     cfg["tv_ip"]),
        ("tv_port", "Port ADB (défaut 5555)",      str(cfg["tv_port"])),
        ("tv_mac",  "Adresse MAC (pour allumer)", cfg["tv_mac"]),
        ("adb_path","Chemin vers adb",            cfg["adb_path"]),
    ]
    for key, label, default in fields:
        prompt = f"  {C.CYAN}{label}{C.RESET}"
        if default:
            prompt += f" {C.DIM}[{default}]{C.RESET}"
        prompt += " : "
        val = input(prompt).strip()
        if val:
            cfg[key] = int(val) if key == "tv_port" else val

    save_config(cfg)


def cmd_status(args):
    """Affiche l'état de connexion et les infos TV."""
    cfg = load_config()
    _require_ip(cfg)
    sep()
    print(f"  {C.BOLD}📺  État de la télé{C.RESET}")
    sep()
    info(f"IP    : {C.WHITE}{cfg['tv_ip']}:{cfg['tv_port']}{C.RESET}")
    info(f"MAC   : {C.WHITE}{cfg['tv_mac'] or 'non configurée'}{C.RESET}")

    remote = ADBRemote(cfg["tv_ip"], cfg["tv_port"], cfg["adb_path"])
    try:
        remote.connect()
        ok("ADB connecté")
        model   = remote.get_property("ro.product.model")
        android = remote.get_property("ro.build.version.release")
        screen  = "allumé" if remote.is_screen_on() else "éteint"
        info(f"Modèle  : {C.WHITE}{model}{C.RESET}")
        info(f"Android : {C.WHITE}{android}{C.RESET}")
        info(f"Écran   : {C.WHITE}{screen}{C.RESET}")
        remote.disconnect()
    except Exception as e:
        err(f"Impossible de se connecter : {e}")


def cmd_allumer(args):
    """Allume la télé via Wake-on-LAN puis ADB wakeup."""
    cfg = load_config()
    sep()
    print(f"  {C.BOLD}🟢  Allumer la télé{C.RESET}")
    sep()

    if cfg.get("tv_mac"):
        try:
            send_wol(cfg["tv_mac"])
            ok(f"Magic Packet WoL envoyé → {cfg['tv_mac']}")
            info("Attente du démarrage (15 s)…")
            time.sleep(15)
        except Exception as e:
            warn(f"WoL échoué : {e}")
    else:
        warn("Aucune adresse MAC configurée — WoL ignoré.")

    _require_ip(cfg)
    remote = ADBRemote(cfg["tv_ip"], cfg["tv_port"], cfg["adb_path"])
    try:
        remote.connect()
        remote.send_key("KEYCODE_WAKEUP")
        ok("Signal WAKEUP envoyé via ADB")
        remote.disconnect()
    except Exception as e:
        err(f"ADB wakeup échoué : {e}")


def cmd_eteindre(args):
    _send_simple_key("power", "🔴  Éteindre la télé")


def cmd_mute(args):
    _send_simple_key("mute", "🔇  Couper / rétablir le volume")


def cmd_vol_plus(args):
    n = getattr(args, "n", 1) or 1
    _repeat_key("vol+", n, f"🔊  Volume + ({n}x)")


def cmd_vol_moins(args):
    n = getattr(args, "n", 1) or 1
    _repeat_key("vol-", n, f"🔉  Volume − ({n}x)")


def cmd_chaine(args):
    if args.numero:
        _send_digits(args.numero)
    elif args.sens == "+":
        _send_simple_key("ch+", "📺  Chaîne suivante")
    else:
        _send_simple_key("ch-", "📺  Chaîne précédente")


def cmd_app(args):
    cfg = load_config()
    _require_ip(cfg)
    app = args.nom.lower()
    sep()
    print(f"  {C.BOLD}📱  Lancer {args.nom}{C.RESET}")
    sep()
    remote = ADBRemote(cfg["tv_ip"], cfg["tv_port"], cfg["adb_path"])
    try:
        remote.connect()
        if app in APP_INTENTS:
            remote.launch_app(APP_INTENTS[app])
            ok(f"{args.nom} lancé")
        else:
            err(f"Application '{app}' inconnue. Disponibles : {', '.join(APP_INTENTS)}")
        remote.disconnect()
    except Exception as e:
        err(str(e))


def cmd_nav(args):
    """Navigation directionnelle."""
    key_map = {
        "haut": "up", "bas": "down", "gauche": "left",
        "droite": "right", "ok": "ok", "retour": "back",
        "accueil": "home", "menu": "menu",
    }
    direction = args.direction.lower()
    key = key_map.get(direction, direction)
    _send_simple_key(key, f"🕹  Navigation : {args.direction}")


def cmd_media(args):
    """Commandes de lecture média."""
    label_map = {
        "play": "▶  Lecture",
        "pause": "⏸  Pause",
        "playpause": "⏯  Lecture/Pause",
        "stop": "⏹  Stop",
        "next": "⏭  Suivant",
        "prev": "⏮  Précédent",
        "rewind": "⏪  Retour rapide",
        "forward": "⏩  Avance rapide",
    }
    action = args.action.lower()
    _send_simple_key(action, label_map.get(action, action))


def cmd_entree(args):
    """Change la source d'entrée."""
    key_map = {
        "hdmi1": "hdmi1",
        "hdmi2": "hdmi2",
        "hdmi3": "hdmi3",
        "hdmi":  "hdmi",
        "input": "input",
    }
    src = args.source.lower()
    key = key_map.get(src, "input")
    _send_simple_key(key, f"🔌  Entrée : {args.source}")


def cmd_shell(args):
    """Exécute une commande ADB shell brute."""
    cfg = load_config()
    _require_ip(cfg)
    remote = ADBRemote(cfg["tv_ip"], cfg["tv_port"], cfg["adb_path"])
    try:
        remote.connect()
        out = remote.shell(*args.commande)
        if out:
            print(f"\n{C.DIM}{out}{C.RESET}\n")
        remote.disconnect()
    except Exception as e:
        err(str(e))


def cmd_liste(args):
    """Affiche toutes les commandes disponibles."""
    print(BANNER)
    sep()
    print(f"  {C.BOLD}📋  Commandes disponibles{C.RESET}")
    sep()

    sections = {
        "⚡ Alimentation": [
            ("allumer",        "Allume la télé (WoL + ADB)"),
            ("eteindre",       "Éteint la télé"),
            ("status",         "Affiche l'état et les infos TV"),
        ],
        "🔊 Volume": [
            ("mute",           "Coupe / rétablit le son"),
            ("vol+ [N]",       "Monte le volume (N fois)"),
            ("vol- [N]",       "Baisse le volume (N fois)"),
        ],
        "📺 Chaînes": [
            ("chaine +",       "Chaîne suivante"),
            ("chaine -",       "Chaîne précédente"),
            ("chaine 42",      "Va directement à la chaîne 42"),
        ],
        "🕹 Navigation": [
            ("nav haut/bas/gauche/droite", "Déplacer le curseur"),
            ("nav ok",         "Valider"),
            ("nav retour",     "Retour arrière"),
            ("nav accueil",    "Écran d'accueil"),
            ("nav menu",       "Ouvrir le menu"),
        ],
        "⏯ Média": [
            ("media play",     "Lecture"),
            ("media pause",    "Pause"),
            ("media playpause","Basculer lecture/pause"),
            ("media stop",     "Stop"),
            ("media next/prev","Suivant / précédent"),
            ("media rewind/forward", "Rembobinage / avance"),
        ],
        "🔌 Entrées": [
            ("entree hdmi1",   "Passer en HDMI 1"),
            ("entree hdmi2",   "Passer en HDMI 2"),
            ("entree hdmi3",   "Passer en HDMI 3"),
            ("entree input",   "Sélection d'entrée"),
        ],
        "📱 Applications": [
            ("app netflix",    "Lancer Netflix"),
            ("app youtube",    "Lancer YouTube"),
            ("app prime",      "Lancer Prime Video"),
            ("app disney",     "Lancer Disney+"),
        ],
        "⚙ Outils": [
            ("config",         "Configurer l'IP, MAC, etc."),
            ("shell CMD",      "Commande ADB shell libre"),
            ("liste",          "Afficher cette aide"),
        ],
    }

    for section, cmds in sections.items():
        print(f"\n  {C.YELLOW}{section}{C.RESET}")
        for cmd, desc in cmds:
            print(f"    {C.WHITE}{cmd:<32}{C.RESET}{C.DIM}{desc}{C.RESET}")
    print()


# ── Helpers internes ───────────────────────────────────────────────────────────
def _require_ip(cfg):
    if not cfg.get("tv_ip"):
        err("Adresse IP non configurée. Lancez d'abord : sharkx config")
        sys.exit(1)

def _send_simple_key(key_alias: str, label: str):
    cfg = load_config()
    _require_ip(cfg)
    sep()
    print(f"  {C.BOLD}{label}{C.RESET}")
    sep()
    remote = ADBRemote(cfg["tv_ip"], cfg["tv_port"], cfg["adb_path"])
    try:
        remote.connect()
        keycode = ADB_KEYS.get(key_alias, key_alias.upper())
        remote.send_key(keycode)
        ok(f"Commande envoyée : {keycode}")
        remote.disconnect()
    except Exception as e:
        err(str(e))

def _repeat_key(key_alias: str, n: int, label: str):
    cfg = load_config()
    _require_ip(cfg)
    sep()
    print(f"  {C.BOLD}{label}{C.RESET}")
    sep()
    remote = ADBRemote(cfg["tv_ip"], cfg["tv_port"], cfg["adb_path"])
    try:
        remote.connect()
        keycode = ADB_KEYS[key_alias]
        for _ in range(n):
            remote.send_key(keycode)
            time.sleep(0.15)
        ok(f"{keycode} envoyé {n}x")
        remote.disconnect()
    except Exception as e:
        err(str(e))

def _send_digits(numero: str):
    cfg = load_config()
    _require_ip(cfg)
    sep()
    print(f"  {C.BOLD}📺  Chaîne → {numero}{C.RESET}")
    sep()
    digit_keys = {
        "0": "KEYCODE_0", "1": "KEYCODE_1", "2": "KEYCODE_2",
        "3": "KEYCODE_3", "4": "KEYCODE_4", "5": "KEYCODE_5",
        "6": "KEYCODE_6", "7": "KEYCODE_7", "8": "KEYCODE_8",
        "9": "KEYCODE_9",
    }
    remote = ADBRemote(cfg["tv_ip"], cfg["tv_port"], cfg["adb_path"])
    try:
        remote.connect()
        for d in str(numero):
            if d in digit_keys:
                remote.send_key(digit_keys[d])
                time.sleep(0.3)
        ok(f"Chaîne {numero} saisie")
        remote.disconnect()
    except Exception as e:
        err(str(e))

# ── Point d'entrée ─────────────────────────────────────────────────────────────
def build_parser():
    parser = argparse.ArgumentParser(
        prog="sharkx",
        description=f"{C.CYAN}SharkX{C.RESET} — Télécommande CLI pour Hitachi Smart TV",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"  Exemple : {C.WHITE}sharkx mute{C.RESET}  |  "
               f"{C.WHITE}sharkx vol+ 5{C.RESET}  |  "
               f"{C.WHITE}sharkx app netflix{C.RESET}",
    )
    sub = parser.add_subparsers(dest="cmd", metavar="COMMANDE")

    # Alimentation
    sub.add_parser("allumer",  help="Allume la télé (WoL + ADB)")
    sub.add_parser("eteindre", help="Éteint la télé")
    sub.add_parser("status",   help="Affiche l'état de la télé")

    # Volume
    sub.add_parser("mute", help="Coupe / rétablit le son")

    p_vp = sub.add_parser("vol+", help="Monte le volume")
    p_vp.add_argument("n", nargs="?", type=int, default=1, metavar="N",
                      help="Nombre d'incréments (défaut 1)")

    p_vm = sub.add_parser("vol-", help="Baisse le volume")
    p_vm.add_argument("n", nargs="?", type=int, default=1, metavar="N",
                      help="Nombre d'incréments (défaut 1)")

    # Chaînes
    p_ch = sub.add_parser("chaine", help="Changer de chaîne")
    p_ch.add_argument("numero", nargs="?", metavar="+/-/N",
                      help="'+', '-' ou numéro direct")
    p_ch.add_argument("sens", nargs="?", choices=["+", "-"], default="+")

    # Navigation
    p_nav = sub.add_parser("nav", help="Navigation directionnelle")
    p_nav.add_argument("direction",
                       choices=["haut","bas","gauche","droite",
                                "ok","retour","accueil","menu"],
                       metavar="DIRECTION")

    # Média
    p_med = sub.add_parser("media", help="Contrôles de lecture")
    p_med.add_argument("action",
                       choices=["play","pause","playpause","stop",
                                "next","prev","rewind","forward"],
                       metavar="ACTION")

    # Entrées
    p_ent = sub.add_parser("entree", help="Changer la source d'entrée")
    p_ent.add_argument("source",
                       choices=["hdmi1","hdmi2","hdmi3","hdmi","input"],
                       metavar="SOURCE")

    # Apps
    p_app = sub.add_parser("app", help="Lancer une application")
    p_app.add_argument("nom",
                       choices=list(APP_INTENTS.keys()),
                       metavar="NOM")

    # Config & outils
    sub.add_parser("config", help="Configurer l'adresse IP, MAC…")

    p_sh = sub.add_parser("shell", help="Commande ADB shell libre")
    p_sh.add_argument("commande", nargs="+", metavar="CMD")

    sub.add_parser("liste", help="Afficher toutes les commandes")

    return parser


def main():
    parser = build_parser()

    # Alias commodes (sans sous-commande)
    aliases = {
        "on":      "allumer",
        "off":     "eteindre",
        "silence": "mute",
    }

    if len(sys.argv) == 1:
        print(BANNER)
        parser.print_help()
        sys.exit(0)

    # Traiter les alias
    if sys.argv[1] in aliases:
        sys.argv[1] = aliases[sys.argv[1]]

    # Cas spécial : chaine +  ou  chaine -
    if len(sys.argv) >= 3 and sys.argv[1] == "chaine" and sys.argv[2] in ("+", "-"):
        args = argparse.Namespace(cmd="chaine", numero=None, sens=sys.argv[2])
        cmd_chaine(args)
        return

    args = parser.parse_args()

    dispatch = {
        "allumer":  cmd_allumer,
        "eteindre": cmd_eteindre,
        "status":   cmd_status,
        "mute":     cmd_mute,
        "vol+":     cmd_vol_plus,
        "vol-":     cmd_vol_moins,
        "chaine":   cmd_chaine,
        "nav":      cmd_nav,
        "media":    cmd_media,
        "entree":   cmd_entree,
        "app":      cmd_app,
        "config":   cmd_config,
        "shell":    cmd_shell,
        "liste":    cmd_liste,
    }

    fn = dispatch.get(args.cmd)
    if fn:
        fn(args)
    else:
        print(BANNER)
        parser.print_help()


if __name__ == "__main__":
    main()
