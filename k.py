#!/usr/bin/env python3
"""
hue_http.py - Contrôle Philips Hue via API HTTP
Compatible a-Shell (iOS) - Pas besoin de phue
"""

import json
import time
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("❌ Installation requise: pip install requests")
    sys.exit(1)

class HueHTTP:
    CONFIG_FILE = Path.home() / ".hue_config.json"
    
    def __init__(self):
        self.bridge_ip = None
        self.username = None
        self.load_config()
    
    def load_config(self):
        """Charge la configuration sauvegardée"""
        if self.CONFIG_FILE.exists():
            try:
                with open(self.CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    self.bridge_ip = data.get('bridge_ip')
                    self.username = data.get('username')
            except:
                pass
    
    def save_config(self):
        """Sauvegarde la configuration"""
        with open(self.CONFIG_FILE, 'w') as f:
            json.dump({
                'bridge_ip': self.bridge_ip,
                'username': self.username
            }, f)
    
    def discover_bridge(self):
        """Découverte du pont via URL standard"""
        print("\n🔍 Recherche du pont Hue...")
        
        # Méthode 1: URL standard de découverte
        try:
            resp = requests.get("https://discovery.meethue.com/", timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                if data and len(data) > 0:
                    self.bridge_ip = data[0]['internalipaddress']
                    print(f"✅ Pont trouvé: {self.bridge_ip}")
                    return True
        except:
            pass
        
        # Méthode 2: Scan réseau simple (IPs courantes)
        print("   Scan réseau en cours...")
        common_ips = [
            "192.168.1.1", "192.168.1.2", "192.168.1.10",
            "192.168.0.1", "192.168.0.10", "10.0.0.1", "10.0.0.10"
        ]
        
        for ip in common_ips:
            try:
                resp = requests.get(f"http://{ip}/api/config", timeout=1)
                if resp.status_code == 200 and 'bridgeid' in resp.text:
                    self.bridge_ip = ip
                    print(f"✅ Pont trouvé: {self.bridge_ip}")
                    return True
            except:
                continue
        
        print("❌ Aucun pont trouvé")
        return False
    
    def register(self):
        """Enregistre l'application sur le pont (nécessite bouton)"""
        print("\n🔐 Appuie sur le BOUTON ROND du pont Hue")
        print("   Puis appuie sur Entrée...")
        input()
        
        # Tente de s'enregistrer
        try:
            resp = requests.post(
                f"http://{self.bridge_ip}/api",
                json={"devicetype": "hue_controller"}
            )
            
            if resp.status_code == 200:
                data = resp.json()
                if 'success' in data[0]:
                    self.username = data[0]['success']['username']
                    self.save_config()
                    print("✅ Enregistrement réussi!")
                    return True
                else:
                    print(f"❌ Erreur: {data}")
                    return False
        except Exception as e:
            print(f"❌ Erreur: {e}")
            return False
    
    def connect(self):
        """Connexion au pont"""
        if not self.bridge_ip:
            if not self.discover_bridge():
                return False
        
        # Si on a déjà un username, on teste
        if self.username:
            try:
                resp = requests.get(
                    f"http://{self.bridge_ip}/api/{self.username}/config"
                )
                if resp.status_code == 200:
                    print("✅ Connecté!")
                    return True
                else:
                    print("⚠️ Connexion perdue, ré-enregistrement nécessaire")
                    self.username = None
            except:
                self.username = None
        
        # Nouvel enregistrement
        return self.register()
    
    def get_lights(self):
        """Récupère toutes les lampes"""
        if not self.username:
            return {}
        
        try:
            resp = requests.get(
                f"http://{self.bridge_ip}/api/{self.username}/lights"
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            print(f"❌ Erreur: {e}")
        
        return {}
    
    def set_light_state(self, light_id, on=True):
        """Allume ou éteint une lampe"""
        try:
            resp = requests.put(
                f"http://{self.bridge_ip}/api/{self.username}/lights/{light_id}/state",
                json={"on": on}
            )
            return resp.status_code == 200
        except:
            return False
    
    def run(self):
        """Menu principal"""
        print("\n" + "="*50)
        print("💡 PHILIPS HUE CONTROLLER (HTTP)")
        print("="*50)
        
        if not self.connect():
            print("❌ Impossible de se connecter au pont")
            return
        
        while True:
            print("\n" + "="*40)
            print("1. 📋 Lister les lampes")
            print("2. 💡 Éteindre une lampe")
            print("3. 💡 Allumer une lampe")
            print("4. 🚪 Quitter")
            
            choice = input("\n👉 Choix: ")
            
            if choice == "1":
                lights = self.get_lights()
                if not lights:
                    print("❌ Aucune lampe trouvée")
                    continue
                
                print("\n📋 LAMPES:")
                for lid, info in lights.items():
                    name = info.get('name', '?')
                    state = info.get('state', {})
                    on = "🟢 ON" if state.get('on') else "🔴 OFF"
                    print(f"   {lid}. {name} - {on}")
            
            elif choice == "2":
                lid = input("🔢 ID de la lampe à éteindre: ")
                if self.set_light_state(lid, on=False):
                    print("✅ Lampe éteinte!")
                else:
                    print("❌ Erreur")
            
            elif choice == "3":
                lid = input("🔢 ID de la lampe à allumer: ")
                if self.set_light_state(lid, on=True):
                    print("✅ Lampe allumée!")
                else:
                    print("❌ Erreur")
            
            elif choice == "4":
                break


if __name__ == "__main__":
    try:
        HueHTTP().run()
    except KeyboardInterrupt:
        print("\n👋 Au revoir!")