#!/usr/bin/env python3
"""
Xiaomi Watch 5 Active Controller - Détection automatique IP
Nécessite: pip install adb-shell prompt_toolkit netifaces
"""

import asyncio
import sys
import socket
import struct
import subprocess
import re
from pathlib import Path

try:
    from adb_shell.adb_device import AdbDeviceTcp
    from adb_shell.auth.sign_pythonrsa import PythonRSASigner
    from adb_shell.auth.keygen import keygen
except ImportError:
    print("❌ Erreur: 'adb-shell' non installé.")
    print("👉 pip install adb-shell")
    sys.exit(1)

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.shortcuts import message_dialog
except ImportError:
    print("❌ Erreur: 'prompt_toolkit' non installé.")
    print("👉 pip install prompt_toolkit")
    sys.exit(1)

try:
    import netifaces
except ImportError:
    print("⚠️  netifaces non installé, scan réseau limité")
    print("👉 pip install netifaces (optionnel mais recommandé)")


class XiaomiWatchAutoDiscovery:
    """Détection automatique de la Xiaomi Watch sans IP manuelle"""
    
    # Signatures réseau des appareils Xiaomi Watch
    XIAOMI_MAC_PREFIXES = [
        "4c:21:5a",  # Xiaomi Watch S1
        "68:db:54",  # Xiaomi Watch S3  
        "b4:0f:3b",  # Xiaomi Mi Watch
        "a4:c1:38",  # Xiaomi Redmi Watch
        "f4:6e:d7",  # Xiaomi Watch 2 Pro
        "d4:5a:fb",  # Xiaomi Watch Color
    ]
    
    def __init__(self):
        self.watch_ip = None
        self.device = None
        self.signer = None
        self.session = PromptSession()
        self._load_keys()
    
    def _load_keys(self):
        """Charge ou génère la clé ADB"""
        key_path = Path.home() / ".android" / "adbkey"
        key_path.parent.mkdir(exist_ok=True)
        
        if not key_path.exists():
            print("🔑 Génération de la clé ADB...")
            keygen(str(key_path))
        
        with open(key_path, "r") as f:
            priv = f.read()
        with open(f"{key_path}.pub", "r") as f:
            pub = f.read()
        
        self.signer = PythonRSASigner(pub, priv)
    
    def get_local_network(self):
        """Récupère le réseau local automatiquement"""
        interfaces = netifaces.interfaces() if 'netifaces' in sys.modules else []
        
        for iface in interfaces:
            addrs = netifaces.ifaddresses(iface)
            if netifaces.AF_INET in addrs:
                for addr in addrs[netifaces.AF_INET]:
                    ip = addr['addr']
                    if ip.startswith('192.168.') or ip.startswith('10.') or ip.startswith('172.'):
                        netmask = addr.get('netmask', '255.255.255.0')
                        return ip, netmask
        
        # Fallback: récupérer l'IP via socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip, "255.255.255.0"
        except:
            return "192.168.1.1", "255.255.255.0"
    
    async def scan_arp_table(self):
        """Scan la table ARP du système (rapide)"""
        print("📡 Scan ARP (détection rapide)...")
        
        devices = []
        
        try:
            # Linux / Mac
            result = subprocess.run(['arp', '-n'], capture_output=True, text=True, timeout=5)
            for line in result.stdout.split('\n'):
                for prefix in self.XIAOMI_MAC_PREFIXES:
                    if prefix.lower() in line.lower():
                        parts = line.split()
                        ip = parts[0] if parts else None
                        if ip and ip not in devices:
                            devices.append(ip)
                            print(f"✅ Xiaomi Watch trouvée: {ip}")
        except:
            pass
        
        try:
            # Windows
            result = subprocess.run(['arp', '-a'], capture_output=True, text=True, timeout=5)
            for line in result.stdout.split('\n'):
                for prefix in self.XIAOMI_MAC_PREFIXES:
                    if prefix.lower() in line.lower():
                        parts = line.split()
                        ip = parts[0] if parts else None
                        if ip and ip not in devices:
                            devices.append(ip)
                            print(f"✅ Xiaomi Watch trouvée: {ip}")
        except:
            pass
        
        return devices
    
    async def scan_network_ping(self):
        """Scan le réseau par ping (complet mais plus lent)"""
        print("📡 Scan réseau (recherche en cours)...")
        
        ip, netmask = self.get_local_network()
        # Calcul du range IP (simplifié)
        base_ip = ".".join(ip.split(".")[:-1])
        
        found_devices = []
        for i in range(1, 255):
            test_ip = f"{base_ip}.{i}"
            if test_ip == ip:
                continue
            
            # Ping rapide
            try:
                if sys.platform == "win32":
                    cmd = ['ping', '-n', '1', '-w', '100', test_ip]
                else:
                    cmd = ['ping', '-c', '1', '-W', '0.1', test_ip]
                
                result = subprocess.run(cmd, capture_output=True, timeout=1)
                
                if result.returncode == 0:
                    # Test rapide du port ADB
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(0.2)
                    if sock.connect_ex((test_ip, 5555)) == 0:
                        found_devices.append(test_ip)
                        print(f"✅ Appareil ADB trouvé: {test_ip}")
                    sock.close()
            except:
                continue
            
            # Afficher la progression
            if i % 20 == 0:
                print(f"   Scan: {i}/254...", end="\r")
        
        print()  # Nouvelle ligne
        return found_devices
    
    async def auto_discover(self):
        """Détection automatique de la montre"""
        print("\n🔍 RECHERCHE AUTOMATIQUE DE LA MONTRE")
        print("="*40)
        
        # Méthode 1: Scan ARP (ultra rapide)
        devices = await self.scan_arp_table()
        
        # Méthode 2: Scan réseau complet (si ARP n'a rien trouvé)
        if not devices:
            devices = await self.scan_network_ping()
        
        if not devices:
            print("\n❌ Aucune Xiaomi Watch trouvée.")
            print("\n💡 Vérifications :")
            print("   1. La montre est allumée")
            print("   2. Le WiFi est activé sur la montre")
            print("   3. Le débogage ADB est actif dans Paramètres > Options développeur")
            print("   4. La montre et l'ordinateur sont sur le même réseau")
            return None
        
        if len(devices) == 1:
            self.watch_ip = devices[0]
            print(f"\n🎯 Montre trouvée: {self.watch_ip}")
            return self.watch_ip
        
        # Plusieurs appareils trouvés
        print(f"\n📱 {len(devices)} appareils trouvés:")
        for i, ip in enumerate(devices, 1):
            print(f"   {i}. {ip}")
        
        choice = self.session.prompt("\n👉 Choisissez (1-{}): ".format(len(devices)))
        try:
            self.watch_ip = devices[int(choice)-1]
            return self.watch_ip
        except:
            return None
    
    async def connect(self):
        """Connexion automatique à la montre"""
        if not self.watch_ip:
            if not await self.auto_discover():
                return False
        
        print(f"\n🔌 Connexion à {self.watch_ip}...")
        
        self.device = AdbDeviceTcp(self.watch_ip, 5555, key_spinner=False)
        
        try:
            await self.device.connect(rsa_keys=[self.signer], auth_timeout_s=10)
            
            # Test de connexion
            result = await self.device.shell("echo 'ok'")
            if "ok" in result:
                print("✅ Montre connectée avec succès!")
                
                # Récupérer le nom de la montre
                name = await self.device.shell("getprop ro.product.model")
                if name:
                    print(f"📱 Modèle: {name.strip()}")
                
                return True
            else:
                print("❌ Échec de connexion")
                return False
                
        except Exception as e:
            print(f"❌ Erreur: {e}")
            print("\n💡 Acceptez la demande d'autorisation sur l'écran de la montre!")
            return False
    
    async def send_command(self, cmd):
        """Envoie une commande shell"""
        if not self.device:
            return None
        try:
            return (await self.device.shell(cmd)).strip()
        except Exception as e:
            print(f"❌ Erreur: {e}")
            return None
    
    async def get_battery(self):
        """Batterie"""
        result = await self.send_command("dumpsys battery | grep level")
        if result:
            level = result.split(":")[-1].strip()
            print(f"🔋 Batterie: {level}%")
    
    async def toggle_screen(self):
        """Allumer/Éteindre l'écran"""
        print("\n1. Allumer")
        print("2. Éteindre")
        choice = self.session.prompt("👉 Choix: ")
        
        if choice == "1":
            await self.send_command("input keyevent KEYCODE_WAKEUP")
            print("✅ Écran allumé")
        elif choice == "2":
            await self.send_command("input keyevent KEYCODE_SLEEP")
            print("✅ Écran éteint")
    
    async def simulate_tap(self):
        """Simuler un tap"""
        print("\nPosition X Y (ex: 200 200):")
        try:
            xy = self.session.prompt("👉 ")
            x, y = xy.split()
            await self.send_command(f"input tap {x} {y}")
            print(f"✅ Tap à ({x}, {y})")
        except:
            print("❌ Format invalide")
    
    async def swipe(self):
        """Swipe"""
        print("Format: X1 Y1 X2 Y2 (ex: 200 300 200 100)")
        try:
            coords = self.session.prompt("👉 ")
            await self.send_command(f"input swipe {coords}")
            print("✅ Swipe effectué")
        except:
            print("❌ Format invalide")
    
    async def launch_app(self):
        """Lancer une app"""
        print("\nApplications connues:")
        print("1. Sport/Workout")
        print("2. Santé")
        print("3. Musique")
        print("4. Commande personnalisée")
        
        choice = self.session.prompt("👉 Choix: ")
        
        apps = {
            "1": "com.xiaomi.hm.health/.activity.WorkoutActivity",
            "2": "com.xiaomi.hm.health",
            "3": "com.google.android.music",
        }
        
        if choice in apps:
            await self.send_command(f"am start -n {apps[choice]}")
            print("✅ App lancée")
        elif choice == "4":
            pkg = self.session.prompt("Package name: ")
            if pkg:
                await self.send_command(f"monkey -p {pkg} 1")
    
    async def run(self):
        """Menu principal"""
        print("\n" + "="*50)
        print("⌚ XIAOMI WATCH 5 ACTIVE - DÉTECTION AUTO")
        print("="*50)
        
        if not await self.connect():
            print("\n❌ Échec de connexion")
            message_dialog(
                title="💡 Conseil",
                text="Activez le débogage ADB dans:\n"
                     "Paramètres → Options développeur\n"
                     "et acceptez l'autorisation sur la montre.",
                ok_text="OK"
            ).run()
            return
        
        while True:
            print("\n" + "="*40)
            print("🏠 MENU PRINCIPAL")
            print("="*40)
            print("1. 🔋 Batterie")
            print("2. 🖥️  Allumer/Éteindre l'écran")
            print("3. 👆 Tap à une position")
            print("4. 👇 Swipe")
            print("5. 🚀 Lancer une app")
            print("6. 💻 Commande shell libre")
            print("7. 🔌 Reconnecter")
            print("8. 🚪 Quitter")
            
            choice = self.session.prompt("\n👉 Votre choix: ")
            
            if choice == "1":
                await self.get_battery()
            elif choice == "2":
                await self.toggle_screen()
            elif choice == "3":
                await self.simulate_tap()
            elif choice == "4":
                await self.swipe()
            elif choice == "5":
                await self.launch_app()
            elif choice == "6":
                cmd = self.session.prompt("💻 Commande: ")
                if cmd:
                    result = await self.send_command(cmd)
                    if result:
                        print(f"\n📤 {result}")
            elif choice == "7":
                await self.device.close()
                self.watch_ip = None
                if await self.connect():
                    print("✅ Reconnecté")
            elif choice == "8":
                if self.device:
                    await self.device.close()
                print("\n👋 Au revoir!")
                break


async def main():
    try:
        controller = XiaomiWatchAutoDiscovery()
        await controller.run()
    except KeyboardInterrupt:
        print("\n\n👋 Interrompu")
    except Exception as e:
        print(f"\n❌ Erreur: {e}")


if __name__ == "__main__":
    asyncio.run(main())