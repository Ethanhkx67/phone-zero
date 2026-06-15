#!/usr/bin/env python3
"""
hue_control.py - Contrôle Philips Hue avec scan réseau
Pour iSH / iPhone / Linux / Mac / Windows
"""

import sys
import time
from pathlib import Path

# Vérification de l'installation
try:
    from phue import Bridge
except ImportError:
    print("\n❌ Bibliothèque 'phue' non installée")
    print("👉 Tapez: pip install phue")
    print("👉 Puis relancez: python3 hue.py")
    sys.exit(1)

class HueController:
    def __init__(self):
        self.bridge = None
        self.bridge_ip = None
        self.lights = {}
        
    def scan_network(self):
        """Scanne le réseau pour trouver le pont Hue"""
        print("\n🔍 Recherche du pont Philips Hue sur le réseau...")
        
        # Méthode 1: Découverte automatique via phue
        try:
            from phue import PhueException
            # Tentative de découverte SSDP
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(3)
            
            msg = ('M-SEARCH * HTTP/1.1\r\n'
                   'HOST: 239.255.255.250:1900\r\n'
                   'MAN: "ssdp:discover"\r\n'
                   'MX: 3\r\n'
                   'ST: upnp:rootdevice\r\n'
                   '\r\n')
            
            sock.sendto(msg.encode(), ('239.255.255.250', 1900))
            
            found_ips = set()
            start = time.time()
            
            while time.time() - start < 5:
                try:
                    data, addr = sock.recvfrom(1024)
                    response = data.decode()
                    if 'philips' in response.lower() or 'hue' in response.lower():
                        found_ips.add(addr[0])
                        print(f"   → Pont trouvé: {addr[0]}")
                except socket.timeout:
                    break
            
            sock.close()
            
            if found_ips:
                self.bridge_ip = list(found_ips)[0]
                print(f"\n✅ Pont Hue trouvé à: {self.bridge_ip}")
                return True
                
        except Exception as e:
            print(f"   Scan SSDP: {e}")
        
        # Méthode 2: Scan réseau par ping (fallback)
        print("   Scan alternatif en cours...")
        local_ip = self._get_local_ip()
        if local_ip:
            network = ".".join(local_ip.split(".")[:-1])
            for i in range(1, 255):
                ip = f"{network}.{i}"
                # Test rapide du port 80 (interface web Hue)
                if self._check_port(ip, 80):
                    try:
                        # Vérifie si c'est bien un pont Hue
                        import urllib.request
                        urllib.request.urlopen(f"http://{ip}/description.xml", timeout=1)
                        self.bridge_ip = ip
                        print(f"✅ Pont Hue trouvé: {self.bridge_ip}")
                        return True
                    except:
                        pass
                
                # Affichage progression
                if i % 20 == 0:
                    print(f"   Scan: {i}/254...", end="\r")
        
        print("\n❌ Aucun pont Hue trouvé sur le réseau")
        print("\n💡 Vérifications:")
        print("   1. Le pont est branché et allumé")
        print("   2. Tu es sur le même réseau WiFi")
        print("   3. La led du pont est bleue fixe")
        return False
    
    def _get_local_ip(self):
        """Récupère l'IP locale"""
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return None
    
    def _check_port(self, ip, port):
        """Test si un port est ouvert"""
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.3)
            result = sock.connect_ex((ip, port))
            sock.close()
            return result == 0
        except:
            return False
    
    def connect(self):
        """Connexion au pont Hue"""
        if not self.bridge_ip:
            if not self.scan_network():
                return False
        
        print(f"\n🔌 Connexion au pont {self.bridge_ip}...")
        
        try:
            # Essaie de se connecter avec une clé existante
            self.bridge = Bridge(self.bridge_ip)
            
            # Vérifie si déjà appairé
            try:
                self.bridge.get_api()
                print("✅ Connecté (clé existante)")
                return True
            except:
                print("\n🔐 PREMIÈRE CONNEXION REQUISE")
                print("   Appuie sur le BOUTON ROND du pont Philips Hue")
                print("   Puis appuie sur Entrée...")
                input()
                
                self.bridge.connect()
                print("✅ Connecté et appairé!")
                return True
                
        except Exception as e:
            print(f"❌ Erreur: {e}")
            return False
    
    def get_lights(self):
        """Récupère toutes les lampes"""
        try:
            lights_data = self.bridge.get_light_objects('name')
            self.lights = {}
            for name, light in lights_data.items():
                self.lights[name] = {
                    'object': light,
                    'id': light.light_id,
                    'on': light.on,
                    'brightness': getattr(light, 'brightness', 0)
                }
            return self.lights
        except Exception as e:
            print(f"❌ Erreur: {e}")
            return {}
    
    def display_lights(self):
        """Affiche la liste des lampes"""
        if not self.lights:
            self.get_lights()
        
        if not self.lights:
            print("\n❌ Aucune lampe trouvée")
            return False
        
        print("\n" + "="*60)
        print("📋 LAMPES PHILIPS HUE DÉTECTÉES")
        print("="*60)
        print(f"{'N°':<4} {'NOM':<25} {'STATUT':<10} {'LUMINOSITÉ':<10}")
        print("-"*60)
        
        items = list(self.lights.items())
        for idx, (name, info) in enumerate(items, 1):
            status = "🟢 ALLUMÉ" if info['on'] else "🔴 ÉTEINT"
            brightness = f"{info['brightness']}%" if info['brightness'] else "—"
            print(f"{idx:<4} {name:<25} {status:<10} {brightness:<10}")
        
        print("="*60)
        return items
    
    def turn_off_light(self, light_obj):
        """Éteint une lampe"""
        try:
            light_obj.on = False
            print("✅ Lampe éteinte!")
            return True
        except Exception as e:
            print(f"❌ Erreur: {e}")
            return False
    
    def turn_on_light(self, light_obj):
        """Allume une lampe"""
        try:
            light_obj.on = True
            print("✅ Lampe allumée!")
            return True
        except Exception as e:
            print(f"❌ Erreur: {e}")
            return False
    
    def set_brightness(self, light_obj, level):
        """Règle la luminosité (0-100)"""
        try:
            light_obj.brightness = level
            print(f"✅ Luminosité réglée à {level}%")
            return True
        except Exception as e:
            print(f"❌ Erreur: {e}")
            return False
    
    def run(self):
        """Menu principal"""
        print("\n" + "="*50)
        print("💡 PHILIPS HUE CONTROLLER")
        print("="*50)
        
        # Connexion
        if not self.connect():
            print("\n❌ Impossible de se connecter au pont")
            return
        
        # Récupère les lampes
        self.get_lights()
        
        while True:
            print("\n" + "="*40)
            print("🏠 MENU PRINCIPAL")
            print("="*40)
            print(f"🔌 Pont: {self.bridge_ip}")
            print(f"💡 Lampes: {len(self.lights)}")
            print("-"*40)
            print("1. 📋 Lister toutes les lampes")
            print("2. 💡 Sélectionner une lampe à éteindre")
            print("3. 🔄 Rafraîchir la liste")
            print("4. 🚪 Quitter")
            print("="*40)
            
            choice = input("\n👉 Votre choix: ")
            
            if choice == "1":
                self.display_lights()
                
            elif choice == "2":
                items = self.display_lights()
                if not items:
                    continue
                
                try:
                    num = int(input("\n🔢 Numéro de la lampe à éteindre: "))
                    if 1 <= num <= len(items):
                        name, info = items[num-1]
                        print(f"\n💡 Lampe sélectionnée: {name}")
                        print(f"   État actuel: {'ALLUMÉE' if info['on'] else 'ÉTEINTE'}")
                        
                        print("\n1. 🔴 Éteindre")
                        print("2. 🟢 Allumer")
                        print("3. ⭐ Changer luminosité")
                        print("4. ↩️ Retour")
                        
                        subchoice = input("\n👉 Action: ")
                        
                        if subchoice == "1":
                            self.turn_off_light(info['object'])
                        elif subchoice == "2":
                            self.turn_on_light(info['object'])
                        elif subchoice == "3":
                            try:
                                bri = int(input("Luminosité (0-100): "))
                                bri = max(0, min(100, bri))
                                self.set_brightness(info['object'], bri)
                            except:
                                print("❌ Entrez un nombre")
                        else:
                            continue
                    else:
                        print("❌ Numéro invalide")
                except ValueError:
                    print("❌ Entrez un nombre valide")
                    
            elif choice == "3":
                self.get_lights()
                print(f"✅ {len(self.lights)} lampes trouvées")
                
            elif choice == "4":
                print("\n👋 Au revoir!")
                break
            else:
                print("❌ Option invalide")


def main():
    try:
        controller = HueController()
        controller.run()
    except KeyboardInterrupt:
        print("\n\n👋 Interrompu")
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        print("\n💡 Conseil: Vérifie que le pont Hue est allumé")


if __name__ == "__main__":
    main()