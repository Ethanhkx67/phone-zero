cat > /mnt/user-data/outputs/hue_controller.py << 'ENDOFFILE'
#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════╗
║          💡  Philips Hue Controller  💡              ║
║   Détection · Connexion · Contrôle des ampoules      ║
╚══════════════════════════════════════════════════════╝

Prérequis :
  pip install requests colorama zeroconf

Premier lancement :
  → Appuyez sur le bouton du Hue Bridge quand demandé
  → Config sauvegardée automatiquement (une seule fois)
"""

import sys
import json
import time
import threading
import socket
import os
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

CONFIG_FILE = "hue_config.json"
APP_NAME    = "hue_python_controller"

# ── Helpers visuels ───────────────────────────────────────────────────────────
def banner():
    print(Fore.YELLOW + Style.BRIGHT + """
╔══════════════════════════════════════════════════════╗
║          💡  Philips Hue Controller  💡              ║
║   Détection · Connexion · Contrôle des ampoules      ║
╚══════════════════════════════════════════════════════╝""")
    print(Fore.WHITE + Style.DIM + "  Utilisez 'aide' pour voir toutes les commandes\n")

def ok(msg):   print(Fore.GREEN  + "  ✔ " + str(msg))
def err(msg):  print(Fore.RED    + "  ✖ " + str(msg))
def info(msg): print(Fore.CYAN   + "  ℹ " + str(msg))
def warn(msg): print(Fore.YELLOW + "  ⚠ " + str(msg))

def sep(title=""):
    if title:
        pad = (52 - len(title) - 2) // 2
        print(Fore.YELLOW + "─" * pad + f" {title} " + "─" * pad)
    else:
        print(Fore.YELLOW + "─" * 54)

def spinner(stop_event, msg="En cours"):
    frames = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
    i = 0
    while not stop_event.is_set():
        print(f"\r{Fore.YELLOW}  {frames[i%len(frames)]} {msg}...", end="", flush=True)
        time.sleep(0.1)
        i += 1
    print("\r" + " " * (len(msg)+10) + "\r", end="")

# ── Config persistante ────────────────────────────────────────────────────────
def save_config(ip, token):
    with open(CONFIG_FILE, "w") as f:
        json.dump({"ip": ip, "token": token}, f, indent=2)
    ok(f"Config sauvegardée dans {CONFIG_FILE}")

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return None, None
    try:
        with open(CONFIG_FILE) as f:
            data = json.load(f)
        return data.get("ip"), data.get("token")
    except Exception:
        return None, None

# ── Détection du Bridge ───────────────────────────────────────────────────────
def discover_bridge_cloud():
    """Utilise le service de découverte Philips (nécessite internet)."""
    try:
        r = requests.get("https://discovery.meethue.com/", timeout=5)
        devices = r.json()
        if devices:
            return devices[0].get("internalipaddress")
    except Exception:
        pass
    return None

def discover_bridge_mdns():
    """Découverte mDNS locale (_hue._tcp)."""
    if not HAS_ZEROCONF:
        return None
    found = []

    class HueListener:
        def add_service(self, zc, type_, name):
            nfo = zc.get_service_info(type_, name)
            if nfo and nfo.addresses:
                ip = socket.inet_ntoa(nfo.addresses[0])
                found.append(ip)
        def remove_service(self, *_): pass
        def update_service(self, *_): pass

    zc = Zeroconf()
    ServiceBrowser(zc, "_hue._tcp.local.", HueListener())
    time.sleep(3)
    zc.close()
    return found[0] if found else None

def discover_bridge_scan(local_ip):
    """Scan TCP sur le port 80 en cherchant le bridge Hue."""
    found = []
    lock  = threading.Lock()

    def try_host(ip):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.4)
            if s.connect_ex((ip, 80)) == 0:
                try:
                    r = requests.get(f"http://{ip}/api/config", timeout=1)
                    data = r.json()
                    if "bridgeid" in data or "name" in data:
                        with lock:
                            found.append(ip)
                except Exception:
                    pass
            s.close()
        except Exception:
            pass

    parts   = local_ip.rsplit(".", 1)
    threads = [threading.Thread(target=try_host,
               args=(f"{parts[0]}.{i}",), daemon=True) for i in range(1, 255)]
    for t in threads: t.start()
    for t in threads: t.join(timeout=1)
    return found[0] if found else None

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None

# ── Classe Bridge Hue ─────────────────────────────────────────────────────────
class HueBridge:
    def __init__(self, ip: str, token: str):
        self.ip    = ip
        self.token = token
        self.base  = f"http://{ip}/api/{token}"

    def _get(self, path):
        try:
            r = requests.get(f"{self.base}/{path}", timeout=5)
            return r.json()
        except Exception as e:
            err(f"Erreur réseau : {e}")
            return None

    def _put(self, path, data):
        try:
            r = requests.put(f"{self.base}/{path}", json=data, timeout=5)
            return r.json()
        except Exception as e:
            err(f"Erreur réseau : {e}")
            return None

    def get_lights(self):
        return self._get("lights") or {}

    def afficher_lampes(self):
        lights = self.get_lights()
        if not lights:
            warn("Aucune ampoule trouvée."); return
        sep("Ampoules")
        for lid, light in lights.items():
            state  = light["state"]
            on     = state.get("on", False)
            bri    = state.get("bri", 0)
            name   = light["name"]
            modele = light.get("modelid", "?")
            status = f"{Fore.GREEN}ON  bri={bri}/254{Style.RESET_ALL}" if on else f"{Fore.RED}OFF{Style.RESET_ALL}"
            print(f"  {Fore.CYAN}[{lid}]{Style.RESET_ALL} {name:<25} {status}  {Style.DIM}{modele}")

    def set_light(self, lid, **kwargs):
        return self._put(f"lights/{lid}/state", kwargs)

    def all_lights(self, **kwargs):
        lights = self.get_lights()
        for lid in lights:
            self.set_light(lid, **kwargs)

    # ── Actions ───────────────────────────────────────────────────────────────
    def eteindre_tout(self):
        self.all_lights(on=False)
        ok("Toutes les ampoules éteintes.")

    def allumer_tout(self):
        self.all_lights(on=True)
        ok("Toutes les ampoules allumées.")

    def eteindre_une(self, lid):
        self.set_light(lid, on=False)
        ok(f"Ampoule [{lid}] éteinte.")

    def allumer_une(self, lid):
        self.set_light(lid, on=True)
        ok(f"Ampoule [{lid}] allumée.")

    def luminosite(self, lid_ou_all, valeur: int):
        """Luminosité 0-100 → convertie en 0-254."""
        bri = max(1, min(254, int(valeur * 254 / 100)))
        if lid_ou_all == "all":
            self.all_lights(on=True, bri=bri)
            ok(f"Luminosité de toutes les ampoules → {valeur}%")
        else:
            self.set_light(lid_ou_all, on=True, bri=bri)
            ok(f"Ampoule [{lid_ou_all}] luminosité → {valeur}%")

    def couleur(self, lid_ou_all, teinte: int):
        """
        Teinte (hue) 0-360 degrés → convertie en 0-65535.
        Couleurs : 0=rouge 30=orange 60=jaune 120=vert 180=cyan 240=bleu 300=violet
        """
        hue = int(teinte * 65535 / 360)
        if lid_ou_all == "all":
            self.all_lights(on=True, hue=hue, sat=254)
            ok(f"Couleur de toutes les ampoules → {teinte}°")
        else:
            self.set_light(lid_ou_all, on=True, hue=hue, sat=254)
            ok(f"Ampoule [{lid_ou_all}] couleur → {teinte}°")

    def blanc(self, lid_ou_all, temperature=4000):
        """Blanc chaud/froid — température en Kelvin (2000=chaud, 6500=froid)."""
        ct = max(153, min(500, int(1_000_000 / temperature)))
        if lid_ou_all == "all":
            self.all_lights(on=True, ct=ct, sat=0)
            ok(f"Blanc {temperature}K sur toutes les ampoules.")
        else:
            self.set_light(lid_ou_all, on=True, ct=ct, sat=0)
            ok(f"Ampoule [{lid_ou_all}] blanc {temperature}K.")

    def alerte(self, lid_ou_all):
        """Effet clignotant (alerte)."""
        if lid_ou_all == "all":
            self.all_lights(alert="lselect")
            ok("Effet alerte sur toutes les ampoules (15s).")
        else:
            self.set_light(lid_ou_all, alert="lselect")
            ok(f"Ampoule [{lid_ou_all}] effet alerte.")

    def info_bridge(self):
        sep("Informations Bridge")
        try:
            r = requests.get(f"http://{self.ip}/api/config", timeout=5)
            data = r.json()
            champs = ["name", "bridgeid", "modelid", "swversion", "apiversion"]
            for c in champs:
                if c in data:
                    print(f"  {Fore.CYAN}{c:<15}{Fore.WHITE}{data[c]}")
        except Exception as e:
            err(str(e))

# ── Enregistrement (bouton bridge) ────────────────────────────────────────────
def register_app(bridge_ip) -> str | None:
    """Appuie sur le bouton du bridge et récupère un token."""
    print(f"\n  {Fore.YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  {Fore.WHITE}Appuyez sur le {Fore.YELLOW}bouton rond{Fore.WHITE} du Hue Bridge,")
    print(f"  {Fore.WHITE}puis appuyez sur {Fore.CYAN}Entrée{Fore.WHITE} ici.")
    print(f"  {Fore.YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
    input("  > ")

    stop = threading.Event()
    t = threading.Thread(target=spinner, args=(stop, "Enregistrement"))
    t.start()

    try:
        r = requests.post(
            f"http://{bridge_ip}/api",
            json={"devicetype": APP_NAME},
            timeout=10
        )
        stop.set(); t.join()
        data = r.json()
        if isinstance(data, list) and "success" in data[0]:
            token = data[0]["success"]["username"]
            ok(f"Token obtenu : {token[:8]}…")
            return token
        elif isinstance(data, list) and "error" in data[0]:
            code = data[0]["error"]["type"]
            if code == 101:
                err("Bouton non pressé (ou trop tard). Réessayez.")
            else:
                err(f"Erreur Hue {code} : {data[0]['error']['description']}")
    except Exception as e:
        stop.set(); t.join()
        err(str(e))
    return None

# ── Aide ──────────────────────────────────────────────────────────────────────
def afficher_aide():
    print(f"""
{Fore.YELLOW}{Style.BRIGHT}Commandes disponibles :

{Fore.CYAN}  [Découverte & connexion]
{Fore.WHITE}  scanner              — Recherche le Hue Bridge sur le réseau
  connecter <ip>       — Connexion manuelle à un Bridge
  info                 — Infos sur le Bridge connecté
  lampes               — Liste toutes les ampoules et leur état

{Fore.CYAN}  [Contrôle global — toutes les ampoules]
{Fore.WHITE}  eteindre             — Éteint toutes les ampoules
  allumer              — Allume toutes les ampoules
  bri <0-100>          — Luminosité globale (ex: bri 50)
  couleur <0-360>      — Teinte globale en degrés
                         0=rouge 60=jaune 120=vert 240=bleu 300=violet
  blanc [kelvin]       — Blanc chaud/froid (ex: blanc 2700)
  alerte               — Effet clignotant sur toutes

{Fore.CYAN}  [Contrôle d'une ampoule — remplacer 'all' par l'ID]
{Fore.WHITE}  eteindre <id>        — Éteint l'ampoule n°id
  allumer <id>         — Allume l'ampoule n°id
  bri <0-100> <id>     — Luminosité d'une ampoule
  couleur <0-360> <id> — Couleur d'une ampoule
  blanc [k] <id>       — Blanc sur une ampoule
  alerte <id>          — Clignotement sur une ampoule

{Fore.CYAN}  [Général]
{Fore.WHITE}  aide / help          — Affiche ce message
  quitter              — Quitte le programme

{Fore.CYAN}  [Exemples]
{Fore.WHITE}  bri 30               → toutes les ampoules à 30%
  couleur 240          → toutes en bleu
  blanc 2700           → blanc chaud ambiance soirée
  eteindre 2           → éteint uniquement l'ampoule n°2
  couleur 120 3        → ampoule n°3 en vert
""")

# ── Boucle principale ─────────────────────────────────────────────────────────
def main():
    banner()

    bridge = None

    # Chargement config existante
    ip, token = load_config()
    if ip and token:
        stop = threading.Event()
        t = threading.Thread(target=spinner, args=(stop, f"Reconnexion à {ip}"))
        t.start()
        try:
            r = requests.get(f"http://{ip}/api/{token}/lights", timeout=4)
            data = r.json()
            stop.set(); t.join()
            if isinstance(data, dict) and not (isinstance(data, list) and "error" in data[0]):
                bridge = HueBridge(ip, token)
                nb = len(data)
                ok(f"Bridge connecté : {ip} — {nb} ampoule(s) trouvée(s)")
                info("Tapez 'lampes' pour les voir, 'aide' pour les commandes.")
            else:
                stop.set(); t.join()
                warn("Token expiré ou invalide — reconnexion nécessaire.")
        except Exception:
            stop.set(); t.join()
            warn(f"Bridge {ip} injoignable — vérifiez votre réseau.")

    while True:
        try:
            prompt = (
                f"\n{Fore.GREEN}[{bridge.ip}]{Style.RESET_ALL} "
                if bridge else
                f"\n{Fore.YELLOW}[non connecté]{Style.RESET_ALL} "
            )
            raw = input(prompt + f"{Fore.YELLOW}>{Style.RESET_ALL} ").strip()
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
            sep("Recherche du Hue Bridge")
            found_ip = None

            # 1) Service cloud Philips
            stop = threading.Event()
            t = threading.Thread(target=spinner, args=(stop, "Service découverte Philips"))
            t.start()
            found_ip = discover_bridge_cloud()
            stop.set(); t.join()
            if found_ip:
                ok(f"Bridge trouvé via Philips Cloud : {found_ip}")

            # 2) mDNS local
            if not found_ip and HAS_ZEROCONF:
                stop = threading.Event()
                t = threading.Thread(target=spinner, args=(stop, "Découverte mDNS locale"))
                t.start()
                found_ip = discover_bridge_mdns()
                stop.set(); t.join()
                if found_ip:
                    ok(f"Bridge trouvé via mDNS : {found_ip}")

            # 3) Scan TCP
            if not found_ip:
                local_ip = get_local_ip()
                if local_ip:
                    stop = threading.Event()
                    t = threading.Thread(target=spinner,
                        args=(stop, f"Scan réseau {local_ip.rsplit('.',1)[0]}.x/24"))
                    t.start()
                    found_ip = discover_bridge_scan(local_ip)
                    stop.set(); t.join()
                    if found_ip:
                        ok(f"Bridge trouvé via scan TCP : {found_ip}")

            if not found_ip:
                err("Aucun Bridge Hue détecté.")
                info("Vérifiez que le Bridge est allumé et branché à votre box.")
                info("Ou tapez :  connecter <ip>  si vous connaissez l'IP.")
            else:
                print()
                # Essai avec token existant
                if token:
                    try:
                        r = requests.get(f"http://{found_ip}/api/{token}/lights", timeout=3)
                        if isinstance(r.json(), dict):
                            bridge = HueBridge(found_ip, token)
                            save_config(found_ip, token)
                            ok(f"Reconnecté avec le token existant !")
                            continue
                    except Exception:
                        pass

                # Sinon → enregistrement
                info(f"Bridge trouvé à {found_ip} — enregistrement nécessaire.")
                new_token = register_app(found_ip)
                if new_token:
                    bridge = HueBridge(found_ip, new_token)
                    save_config(found_ip, new_token)
                    bridge.afficher_lampes()

        elif cmd == "connecter":
            ip_arg = args[0] if args else input("  IP du Bridge : ").strip()
            # Token existant ?
            saved_ip, saved_token = load_config()
            if saved_token:
                try:
                    r = requests.get(f"http://{ip_arg}/api/{saved_token}/lights", timeout=3)
                    if isinstance(r.json(), dict):
                        bridge = HueBridge(ip_arg, saved_token)
                        ok(f"Connecté à {ip_arg} avec le token sauvegardé.")
                        continue
                except Exception:
                    pass
            # Nouvel enregistrement
            new_token = register_app(ip_arg)
            if new_token:
                bridge = HueBridge(ip_arg, new_token)
                save_config(ip_arg, new_token)
                bridge.afficher_lampes()

        # ── Commandes nécessitant un bridge ───────────────────────────────────
        elif cmd == "lampes":
            if not bridge: warn("Aucun Bridge connecté."); continue
            bridge.afficher_lampes()

        elif cmd == "info":
            if not bridge: warn("Aucun Bridge connecté."); continue
            bridge.info_bridge()

        elif cmd == "eteindre":
            if not bridge: warn("Aucun Bridge connecté."); continue
            if args:
                bridge.eteindre_une(args[0])
            else:
                bridge.eteindre_tout()

        elif cmd == "allumer":
            if not bridge: warn("Aucun Bridge connecté."); continue
            if args:
                bridge.allumer_une(args[0])
            else:
                bridge.allumer_tout()

        elif cmd == "bri":
            if not bridge: warn("Aucun Bridge connecté."); continue
            if not args or not args[0].isdigit():
                err("Usage : bri <0-100> [id_ampoule]"); continue
            valeur = int(args[0])
            cible  = args[1] if len(args) > 1 else "all"
            bridge.luminosite(cible, valeur)

        elif cmd == "couleur":
            if not bridge: warn("Aucun Bridge connecté."); continue
            if not args or not args[0].isdigit():
                err("Usage : couleur <0-360> [id_ampoule]"); continue
            teinte = int(args[0])
            cible  = args[1] if len(args) > 1 else "all"
            bridge.couleur(cible, teinte)

        elif cmd == "blanc":
            if not bridge: warn("Aucun Bridge connecté."); continue
            kelvin = int(args[0]) if args and args[0].isdigit() else 4000
            cible  = args[1] if len(args) > 1 else "all"
            bridge.blanc(cible, kelvin)

        elif cmd == "alerte":
            if not bridge: warn("Aucun Bridge connecté."); continue
            cible = args[0] if args else "all"
            bridge.alerte(cible)

        else:
            warn(f"Commande inconnue : '{cmd}'. Tapez 'aide'.")

if __name__ == "__main__":
    main()