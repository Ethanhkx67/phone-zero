#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════╗
║        📺  Freebox Player Controller  📺             ║
║   Détection · Connexion · Contrôle à distance        ║
╚══════════════════════════════════════════════════════╝

Prérequis :
  pip install colorama requests zeroconf

Compatible : Freebox Delta Player Mini, Révolution (V6),
             Delta (V7), Pop, Mini 4K

Comment trouver votre code télécommande :
  Sur le Player → Paramètres → Système → Informations
  Freebox Player et Server → Code télécommande (8 chiffres)
"""

import sys
import time
import threading
import socket
import requests

try:
    from colorama import init, Fore, Style
    init(autoreset=True)
except ImportError:
    class Fore:
        RED = GREEN = YELLOW = CYAN = WHITE = MAGENTA = ""
    class Style:
        BRIGHT = RESET_ALL = DIM = ""

try:
    from zeroconf import ServiceBrowser, Zeroconf
    HAS_ZEROCONF = True
except ImportError:
    HAS_ZEROCONF = False

# ── Touches disponibles ───────────────────────────────────────────────────────
KEYS = {
    # Navigation
    "haut"       : "up",
    "bas"        : "down",
    "gauche"     : "left",
    "droite"     : "right",
    "ok"         : "select",
    "retour"     : "back",
    "menu"       : "menu",
    "accueil"    : "home",
    # Lecture
    "lecture"    : "play",
    "pause"      : "pause",
    "stop"       : "stop",
    "suivant"    : "fwd",
    "precedent"  : "rev",
    "avance"     : "fastforward",
    "recul"      : "rewind",
    "enreg"      : "rec",
    # Volume
    "vol+"       : "vol_inc",
    "vol-"       : "vol_dec",
    "mute"       : "mute",
    # Chaînes
    "ch+"        : "prgm_inc",
    "ch-"        : "prgm_dec",
    # Couleurs
    "rouge"      : "red",
    "vert"       : "green",
    "bleu"       : "blue",
    "jaune"      : "yellow",
    # Infos
    "info"       : "info",
    "epg"        : "epg",
    # Pouvoir
    "power"      : "power",
    "veille"     : "standby",
    # Chiffres
    "0":"0","1":"1","2":"2","3":"3","4":"4",
    "5":"5","6":"6","7":"7","8":"8","9":"9",
}

# ── Helpers visuels ───────────────────────────────────────────────────────────
def banner():
    print(Fore.CYAN + Style.BRIGHT + """
╔══════════════════════════════════════════════════════╗
║        📺  Freebox Player Controller  📺             ║
║   Détection · Connexion · Contrôle à distance        ║
╚══════════════════════════════════════════════════════╝""")
    print(Fore.WHITE + Style.DIM + "  Utilisez 'aide' pour voir toutes les commandes\n")

def ok(msg):   print(Fore.GREEN  + "  ✔ " + str(msg))
def err(msg):  print(Fore.RED    + "  ✖ " + str(msg))
def info(msg): print(Fore.CYAN   + "  ℹ " + str(msg))
def warn(msg): print(Fore.YELLOW + "  ⚠ " + str(msg))

def sep(title=""):
    if title:
        pad = (52 - len(title) - 2) // 2
        print(Fore.CYAN + "─" * pad + f" {title} " + "─" * pad)
    else:
        print(Fore.CYAN + "─" * 54)

def spinner(stop_event, msg="En cours"):
    frames = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
    i = 0
    while not stop_event.is_set():
        print(f"\r{Fore.YELLOW}  {frames[i%len(frames)]} {msg}...", end="", flush=True)
        time.sleep(0.1)
        i += 1
    print("\r" + " " * (len(msg)+10) + "\r", end="")

# ── Détection réseau ──────────────────────────────────────────────────────────
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None

def scan_freebox_mdns():
    """Détecte le Player via mDNS (service _fbx-api._tcp)."""
    if not HAS_ZEROCONF:
        return []
    found = []

    class FreeboxListener:
        def add_service(self, zc, type_, name):
            nfo = zc.get_service_info(type_, name)
            if nfo and nfo.addresses:
                ip = socket.inet_ntoa(nfo.addresses[0])
                port = nfo.port
                if ip not in [f[0] for f in found]:
                    found.append((ip, port, name))
        def remove_service(self, *_): pass
        def update_service(self, *_): pass

    zc = Zeroconf()
    listener = FreeboxListener()
    # Service API Freebox OS
    ServiceBrowser(zc, "_fbx-api._tcp.local.", listener)
    # Service player classique
    ServiceBrowser(zc, "_hd._tcp.local.", listener)
    time.sleep(3)
    zc.close()
    return found

def scan_tcp_player(base_ip, port=80, timeout=0.5):
    """Scan TCP rapide pour trouver le player sur le réseau."""
    found = []
    lock  = threading.Lock()

    def try_host(ip):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            if s.connect_ex((ip, port)) == 0:
                # Vérifie que c'est bien une Freebox
                try:
                    r = requests.get(
                        f"http://{ip}/pub/remote_control?code=00000000&key=mute",
                        timeout=1
                    )
                    if r.status_code in (200, 403, 400):
                        with lock:
                            found.append(ip)
                except Exception:
                    pass
            s.close()
        except Exception:
            pass

    parts   = base_ip.rsplit(".", 1)
    threads = [threading.Thread(target=try_host,
               args=(f"{parts[0]}.{i}",), daemon=True) for i in range(1, 255)]
    for t in threads: t.start()
    for t in threads: t.join(timeout=timeout + 0.5)
    return found

def detect_via_mafreebox():
    """Essaie la résolution par mafreebox.freebox.fr (réseau local uniquement)."""
    try:
        r = requests.get("http://mafreebox.freebox.fr/api_version", timeout=3)
        if r.status_code == 200:
            data = r.json()
            return data.get("api_domain", None)
    except Exception:
        return None

# ── Classe Player ─────────────────────────────────────────────────────────────
class FreeboxPlayer:
    def __init__(self, ip: str, code: str):
        self.ip   = ip
        self.code = code
        self.base = f"http://{ip}/pub/remote_control"

    def send_key(self, key: str, long_press=False, repeat=1) -> bool:
        """Envoie une touche via l'API HTTP."""
        params = {
            "code"  : self.code,
            "key"   : key,
            "long"  : "true" if long_press else "false",
            "repeat": repeat,
        }
        try:
            r = requests.get(self.base, params=params, timeout=5)
            return r.status_code == 200
        except requests.exceptions.ConnectionError:
            err(f"Impossible de joindre le Player à {self.ip}")
            return False
        except Exception as e:
            err(str(e))
            return False

    def power_off(self):
        """Mise en veille du Player."""
        if self.send_key("standby"):
            ok("Signal de veille envoyé au Freebox Player.")
        else:
            warn("Essayez avec la touche 'power' à la place.")
            self.send_key("power")

    def power_toggle(self):
        """Toggle allumage/extinction."""
        if self.send_key("power"):
            ok("Signal power envoyé (toggle on/off).")

    def touche(self, nom: str, long_press=False):
        key = KEYS.get(nom.lower(), nom.lower())
        if self.send_key(key, long_press=long_press):
            ok(f"Touche envoyée : {nom} → {key}" + (" [long]" if long_press else ""))
        else:
            err(f"Échec envoi touche : {key}")

    def chaine(self, numero: int):
        """Zapper sur une chaîne en tapant les chiffres."""
        for ch in str(numero):
            self.send_key(ch)
            time.sleep(0.15)
        ok(f"Chaîne {numero} sélectionnée.")

    def volume(self, direction: str, fois=5):
        key = "vol_inc" if direction in ("+", "up") else "vol_dec"
        for _ in range(fois):
            self.send_key(key)
            time.sleep(0.05)
        sens = "+" if direction in ("+", "up") else "-"
        ok(f"Volume {sens}{fois}")

    def ping(self) -> bool:
        """Vérifie que le Player répond."""
        try:
            r = requests.get(f"http://{self.ip}/", timeout=3)
            return True
        except Exception:
            return False

# ── Aide ──────────────────────────────────────────────────────────────────────
def afficher_aide():
    print(f"""
{Fore.CYAN}{Style.BRIGHT}Commandes disponibles :

{Fore.YELLOW}  [Détection & configuration]
{Fore.WHITE}  scanner              — Recherche le Freebox Player sur le réseau
  connecter <ip> <code>— Connexion au Player (IP + code 8 chiffres)
  code <nouveau_code>  — Changer le code télécommande
  ping                 — Vérifie que le Player répond

{Fore.YELLOW}  [Alimentation]
{Fore.WHITE}  eteindre             — Met le Player en veille (standby)
  power                — Toggle allumage/extinction

{Fore.YELLOW}  [Navigation]
{Fore.WHITE}  touche <nom>         — Envoie une touche (voir liste ci-dessous)
  touche <nom> long    — Appui long sur une touche
  chaine <numero>      — Zapper sur un numéro de chaîne

{Fore.YELLOW}  [Volume]
{Fore.WHITE}  vol+ [n]             — Monte le volume (n fois, défaut 5)
  vol- [n]             — Baisse le volume (n fois, défaut 5)
  mute                 — Couper/rétablir le son

{Fore.YELLOW}  [Touches disponibles]
{Fore.WHITE}  haut  bas  gauche  droite  ok  retour  menu  accueil
  lecture  pause  stop  suivant  precedent  avance  recul
  vol+  vol-  mute  ch+  ch-  info  epg  enreg
  rouge  vert  bleu  jaune  power  veille  0-9

{Fore.YELLOW}  [Code télécommande — où le trouver sur le Player]
{Fore.WHITE}  Paramètres → Système → Informations Freebox Player et Server
  → "Code télécommande" (nombre à 8 chiffres)

{Fore.YELLOW}  [Général]
{Fore.WHITE}  aide / help          — Affiche ce message
  quitter              — Quitte le programme
""")

# ── Boucle principale ─────────────────────────────────────────────────────────
def main():
    banner()

    # Vérification requests
    try:
        import requests as _r
    except ImportError:
        err("Module 'requests' manquant.")
        warn("Installez-le : pip install requests")
        sys.exit(1)

    player = None

    while True:
        try:
            prompt = (
                f"\n{Fore.GREEN}[{player.ip}]{Style.RESET_ALL} "
                if player else
                f"\n{Fore.YELLOW}[non connecté]{Style.RESET_ALL} "
            )
            raw = input(prompt + f"{Fore.CYAN}>{Style.RESET_ALL} ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            ok("Au revoir !")
            break

        if not raw:
            continue

        parts = raw.split()
        cmd   = parts[0].lower()
        args  = parts[1:]

        # ── Commandes globales ────────────────────────────────────────────────
        if cmd in ("aide", "help"):
            afficher_aide()

        elif cmd == "quitter":
            ok("Au revoir !")
            break

        elif cmd == "scanner":
            sep("Scan réseau")
            local_ip = get_local_ip()
            if local_ip:
                info(f"IP locale : {local_ip}")

            # 1) mafreebox.freebox.fr
            stop = threading.Event()
            t = threading.Thread(target=spinner, args=(stop, "Résolution mafreebox.freebox.fr"))
            t.start()
            domain = detect_via_mafreebox()
            stop.set(); t.join()
            if domain:
                ok(f"Freebox Server détecté : {domain}")

            # 2) mDNS
            mdns_found = []
            if HAS_ZEROCONF:
                stop = threading.Event()
                t = threading.Thread(target=spinner, args=(stop, "Découverte mDNS"))
                t.start()
                mdns_found = scan_freebox_mdns()
                stop.set(); t.join()
                for ip, port, name in mdns_found:
                    ok(f"mDNS : {ip}:{port}  ({name.split('.')[0]})")

            # 3) Scan TCP
            if local_ip:
                stop = threading.Event()
                t = threading.Thread(target=spinner,
                    args=(stop, f"Scan TCP {local_ip.rsplit('.',1)[0]}.x/24"))
                t.start()
                tcp_found = scan_tcp_player(local_ip)
                stop.set(); t.join()
                for ip in tcp_found:
                    if ip not in [f[0] for f in mdns_found]:
                        ok(f"TCP  : {ip}:80")

            all_ips = list({f[0] for f in mdns_found} | set(tcp_found if local_ip else []))
            if not all_ips:
                warn("Aucun Player détecté automatiquement.")
                info("Trouvez l'IP manuellement :")
                info("  Player → Paramètres → Système → Informations")
                info("  → Adresse IP du Player")
            else:
                print()
                info("Tapez :  connecter <ip> <code_8_chiffres>")

        elif cmd == "connecter":
            if len(args) < 2:
                ip   = (args[0] if args else input("  IP du Player : ").strip())
                code = input("  Code télécommande (8 chiffres) : ").strip()
            else:
                ip, code = args[0], args[1]

            if len(code) != 8 or not code.isdigit():
                warn("Le code doit être exactement 8 chiffres.")
                code = input("  Code (8 chiffres) : ").strip()

            stop = threading.Event()
            t = threading.Thread(target=spinner, args=(stop, f"Test connexion {ip}"))
            t.start()
            p = FreeboxPlayer(ip, code)
            reachable = p.ping()
            stop.set(); t.join()

            if reachable:
                ok(f"Player joignable à {ip}")
                player = p
                info("Tapez 'eteindre' pour mettre en veille.")
            else:
                err(f"Impossible de joindre {ip}:80")
                warn("Vérifiez l'IP et que le Player est allumé.")

        # ── Commandes nécessitant un Player ───────────────────────────────────
        elif cmd == "ping":
            if not player: warn("Aucun Player connecté."); continue
            if player.ping():
                ok(f"Player {player.ip} répond.")
            else:
                err(f"Player {player.ip} ne répond pas.")

        elif cmd == "code":
            if not player: warn("Aucun Player connecté."); continue
            nouveau = args[0] if args else input("  Nouveau code (8 chiffres) : ").strip()
            if len(nouveau) == 8 and nouveau.isdigit():
                player.code = nouveau
                ok(f"Code mis à jour : {nouveau}")
            else:
                err("Code invalide (8 chiffres requis).")

        elif cmd == "eteindre":
            if not player: warn("Aucun Player connecté."); continue
            player.power_off()

        elif cmd == "power":
            if not player: warn("Aucun Player connecté."); continue
            player.power_toggle()

        elif cmd == "touche":
            if not player: warn("Aucun Player connecté."); continue
            if not args: err("Touche manquante."); continue
            nom = args[0]
            long_press = len(args) > 1 and args[1].lower() == "long"
            player.touche(nom, long_press=long_press)

        elif cmd == "chaine":
            if not player: warn("Aucun Player connecté."); continue
            if not args or not args[0].isdigit():
                err("Numéro de chaîne requis."); continue
            player.chaine(int(args[0]))

        elif cmd in ("vol+", "volup"):
            if not player: warn("Aucun Player connecté."); continue
            fois = int(args[0]) if args and args[0].isdigit() else 5
            player.volume("+", fois)

        elif cmd in ("vol-", "voldown"):
            if not player: warn("Aucun Player connecté."); continue
            fois = int(args[0]) if args and args[0].isdigit() else 5
            player.volume("-", fois)

        elif cmd == "mute":
            if not player: warn("Aucun Player connecté."); continue
            player.touche("mute")

        else:
            warn(f"Commande inconnue : '{cmd}'. Tapez 'aide'.")

if __name__ == "__main__":
    main()
