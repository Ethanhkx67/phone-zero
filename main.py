#!/usr/bin/env python3
"""
network_scanner.py - Scan réseau et identification des appareils
Fonctionne sur iSH (iOS)
"""

import socket
import subprocess
import threading
import time
import sys
from datetime import datetime

class NetworkScanner:
    def __init__(self):
        self.devices = []
        self.lock = threading.Lock()
        
    def get_local_ip(self):
        """Récupère l'IP locale d'iSH"""
        try:
            # Méthode 1: socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            # Méthode 2: hostname
            try:
                hostname = socket.gethostname()
                return socket.gethostbyname(hostname)
            except:
                return "192.168.1.1"  # Fallback par défaut
    
    def get_network_range(self):
        """Détermine le range IP à scanner"""
        local_ip = self.get_local_ip()
        # Extrait les 3 premiers octets
        parts = local_ip.split('.')
        if len(parts) == 4:
            network = f"{parts[0]}.{parts[1]}.{parts[2]}"
            return network, local_ip
        return "192.168.1", local_ip
    
    def ping_host(self, ip):
        """Ping une IP pour vérifier si elle répond"""
        try:
            # Ping avec timeout court (0.2s)
            cmd = ['ping', '-c', '1', '-W', '1', ip]
            result = subprocess.run(cmd, capture_output=True, timeout=2)
            return result.returncode == 0
        except:
            return False
    
    def get_hostname(self, ip):
        """Récupère le nom de l'appareil via DNS reverse"""
        try:
            hostname, _, _ = socket.gethostbyaddr(ip)
            return hostname.split('.')[0]
        except:
            return "Inconnu"
    
    def get_vendor_from_mac(self, mac):
        """Devine le fabricant à partir de la MAC (version simplifiée)"""
        if not mac or len(mac) < 8:
            return "?"
        
        prefix = mac[:8].upper()
        
        # Base de données des préfixes MAC courants
        vendors = {
            "00:11:22": "Apple",
            "3C:22:FB": "Intel",
            "D4:F5:EF": "Samsung",
            "B8:27:EB": "Raspberry Pi",
            "DC:A6:32": "Google",
            "00:1E:06": "LG",
            "C4:65:16": "Huawei",
            "F4:6E:D7": "Xiaomi",
            "04:FE:7F": "TP-Link",
            "00:24:A5": "Netgear",
            "E4:5F:01": "Philips",
            "AC:84:C6": "Amazon",
            "B0:79:94": "Sony",
            "34:E6:D7": "Microsoft",
            "A4:77:33": "Acer",
            "00:1B:44": "Dell",
            "00:26:2D": "HP",
            "00:1A:70": "Nintendo",
            "00:25:00": "Canon",
            "C8:E7:D8": "Xiaomi (Watch)",
            "68:DB:54": "Xiaomi (Watch)",
            "4C:21:5A": "Xiaomi (Watch)",
        }
        
        for pre, vendor in vendors.items():
            if prefix.startswith(pre):
                return vendor
        return "?"
    
    def get_arp_table(self):
        """Lit la table ARP pour obtenir les MAC"""
        arp_table = {}
        try:
            result = subprocess.run(['arp', '-n'], capture_output=True, text=True, timeout=3)
            lines = result.stdout.split('\n')
            for line in lines:
                if '?' in line or 'incomplete' in line.lower():
                    continue
                parts = line.split()
                if len(parts) >= 3:
                    ip = parts[0]
                    mac = parts[2] if len(parts) > 2 else None
                    if mac and ':' in mac and ip != 'Address':
                        arp_table[ip] = mac
        except:
            pass
        return arp_table
    
    def scan_device(self, ip, arp_table):
        """Scanne un appareil spécifique"""
        if self.ping_host(ip):
            hostname = self.get_hostname(ip)
            mac = arp_table.get(ip, "??:??:??:??:??:??")
            vendor = self.get_vendor_from_mac(mac)
            
            device = {
                'ip': ip,
                'hostname': hostname,
                'mac': mac,
                'vendor': vendor
            }
            return device
        return None
    
    def scan_network(self, progress_callback=None):
        """Scan le réseau en parallèle"""
        network, local_ip = self.get_network_range()
        print(f"\n🔍 Scan du réseau: {network}.0/24")
        print(f"📡 IP locale: {local_ip}")
        print(f"⏱️  Début: {datetime.now().strftime('%H:%M:%S')}\n")
        
        # Récupère la table ARP une fois
        arp_table = self.get_arp_table()
        
        threads = []
        devices_found = []
        
        for i in range(1, 255):
            ip = f"{network}.{i}"
            
            # Skip l'IP locale
            if ip == local_ip:
                continue
            
            thread = threading.Thread(target=lambda: self._scan_ip(ip, arp_table, devices_found))
            thread.start()
            threads.append(thread)
            
            # Affiche la progression
            if progress_callback:
                progress_callback(i, 254)
        
        # Attend la fin de tous les threads
        for thread in threads:
            thread.join()
        
        return devices_found
    
    def _scan_ip(self, ip, arp_table, devices_list):
        """Fonction interne pour le scan d'une IP"""
        device = self.scan_device(ip, arp_table)
        if device:
            with self.lock:
                devices_list.append(device)
    
    def display_devices(self, devices):
        """Affiche joliment les appareils trouvés"""
        if not devices:
            print("\n❌ Aucun appareil trouvé.")
            return
        
        # Trie par IP
        devices.sort(key=lambda x: [int(i) for i in x['ip'].split('.')])
        
        print("\n" + "="*70)
        print(f"📱 APPARELS TROUVÉS ({len(devices)})")
        print("="*70)
        print(f"{'IP':<18} {'NOM':<25} {'FABRICANT':<15} {'MAC':<18}")
        print("-"*70)
        
        for d in devices:
            print(f"{d['ip']:<18} {d['hostname']:<25} {d['vendor']:<15} {d['mac']:<18}")
        
        print("="*70)
        
        # Détection spéciale TV
        tvs = []
        for d in devices:
            if d['vendor'] in ['Samsung', 'LG', 'Sony', 'Philips']:
                tvs.append(d)
        
        if tvs:
            print("\n📺 TV POTENTIELLES:")
            for tv in tvs:
                print(f"   - {tv['hostname']} ({tv['ip']}) - {tv['vendor']}")
                
                # Teste si les ports HTTP sont ouverts
                for port in [8080, 8000, 8001, 5000]:
                    if self._check_port(tv['ip'], port):
                        print(f"      🔌 Port {port} ouvert (API possible)")
    
    def _check_port(self, ip, port):
        """Test si un port est ouvert"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex((ip, port))
            sock.close()
            return result == 0
        except:
            return False
    
    def save_to_file(self, devices, filename="scan_result.txt"):
        """Sauvegarde les résultats"""
        with open(filename, 'w') as f:
            f.write(f"Scan réseau - {datetime.now()}\n")
            f.write("="*50 + "\n")
            for d in devices:
                f.write(f"{d['ip']} | {d['hostname']} | {d['vendor']} | {d['mac']}\n")
        print(f"\n💾 Résultats sauvegardés dans {filename}")


def show_progress(current, total):
    """Affiche une barre de progression"""
    percent = (current / total) * 100
    bar = "█" * int(percent / 2) + "░" * (50 - int(percent / 2))
    sys.stdout.write(f"\r🔍 Scan: [{bar}] {current}/{total} IPs")
    sys.stdout.flush()


def main():
    print("\n" + "="*50)
    print("🌐 SCANNEUR RÉSEAU - iSH compatible")
    print("="*50)
    
    scanner = NetworkScanner()
    
    # Menu
    while True:
        print("\n📋 MENU:")
        print("1. Scan rapide (ping + ARP)")
        print("2. Scan complet (avec identification fabricant)")
        print("3. Scan ports ouverts (TV/objets connectés)")
        print("4. Quitter")
        
        choice = input("\n👉 Votre choix: ")
        
        if choice == "1":
            print("\n⚡ Scan rapide...")
            devices = scanner.scan_network(progress_callback=show_progress)
            scanner.display_devices(devices)
            
        elif choice == "2":
            print("\n🔍 Scan complet...")
            devices = scanner.scan_network(progress_callback=show_progress)
            scanner.display_devices(devices)
            scanner.save_to_file(devices)
            
        elif choice == "3":
            print("\n🔌 Scan ports TV...")
            devices = scanner.scan_network()
            tvs = [d for d in devices if d['vendor'] in ['Samsung', 'LG', 'Sony', 'Philips']]
            for tv in tvs:
                print(f"\n📺 {tv['hostname']} ({tv['ip']})")
                for port in [8080, 8000, 8001, 5000, 5555]:
                    if scanner._check_port(tv['ip'], port):
                        print(f"   ✅ Port {port} ouvert")
                    else:
                        print(f"   ❌ Port {port} fermé")
                        
        elif choice == "4":
            print("\n👋 Au revoir!")
            break
        else:
            print("❌ Option invalide")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Interrompu")
    except Exception as e:
        print(f"\n❌ Erreur: {e}")