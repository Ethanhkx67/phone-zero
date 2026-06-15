#!/usr/bin/env python3
"""
ble_hue.py - Contrôle lampe Philips Hue Bluetooth (sans pont)
Scan BLE, liste les lampes, et permet d'éteindre/allumer
"""

import asyncio
import sys
from datetime import datetime

try:
    from bleak import BleakScanner, BleakClient
except ImportError:
    print("❌ Installation requise: pip install bleak")
    sys.exit(1)

class HueBleController:
    # Services et caractéristiques Philips Hue (Bluetooth)
    HUE_SERVICE = "932c32bd-0000-47a2-835a-a8d455b859dd"
    HUE_STATE_CHAR = "932c32bd-0002-47a2-835a-a8d455b859dd"  # On/Off
    HUE_BRIGHTNESS_CHAR = "932c32bd-0003-47a2-835a-a8d455b859dd"  # Luminosité
    HUE_COLOR_CHAR = "932c32bd-0005-47a2-835a-a8d455b859dd"  # Couleur
    
    # Préfixes d'adresses MAC Philips Hue Bluetooth
    HUE_MAC_PREFIXES = ["5C:C5:A4", "CC:22:3B", "00:17:88"]
    
    def __init__(self):
        self.devices = []
        self.selected_device = None
        self.client = None
    
    def is_hue_device(self, name, address):
        """Détecte si c'est une lampe Hue BLE"""
        if not name:
            return False
        
        name_lower = name.lower()
        # Noms typiques des lampes Hue Bluetooth
        hue_names = ["hue", "philips", "lamp", "light", "bloom", "go", "play"]
        
        for hue_name in hue_names:
            if hue_name in name_lower:
                return True
        
        # Vérifie par préfixe MAC
        for prefix in self.HUE_MAC_PREFIXES:
            if address.upper().startswith(prefix):
                return True
        
        return False
    
    async def scan_devices(self, timeout=8):
        """Scan les appareils BLE à proximité"""
        print(f"\n🔍 Scan BLE - Recherche de lampes Philips Hue...")
        print(f"   (appuyez sur Ctrl+C pour arrêter)\n")
        
        devices_found = []
        
        def detection_callback(device, advertisement_data):
            if device.name and self.is_hue_device(device.name, device.address):
                if device.address not in [d['address'] for d in devices_found]:
                    devices_found.append({
                        'name': device.name,
                        'address': device.address,
                        'rssi': advertisement_data.rssi
                    })
                    print(f"   ✅ Lampe trouvée: {device.name} ({device.address})")
        
        scanner = BleakScanner(detection_callback)
        await scanner.start()
        await asyncio.sleep(timeout)
        await scanner.stop()
        
        self.devices = devices_found
        return devices_found
    
    async def connect_to_device(self, address):
        """Se connecte à la lampe"""
        print(f"\n🔌 Connexion à {address}...")
        try:
            self.client = BleakClient(address)
            await self.client.connect()
            print("✅ Connecté!")
            return True
        except Exception as e:
            print(f"❌ Erreur: {e}")
            return False
    
    async def send_command(self, char_uuid, data):
        """Envoie une commande à la lampe"""
        if not self.client or not self.client.is_connected:
            print("❌ Non connecté")
            return False
        
        try:
            await self.client.write_gatt_char(char_uuid, data)
            return True
        except Exception as e:
            print(f"❌ Erreur envoi: {e}")
            return False
    
    async def turn_off(self):
        """Éteint la lampe"""
        # Commande OFF pour Hue BLE (généralement b'\x00')
        result = await self.send_command(self.HUE_STATE_CHAR, b'\x00')
        if result:
            print("✅ Lampe éteinte!")
        return result
    
    async def turn_on(self):
        """Allume la lampe"""
        result = await self.send_command(self.HUE_STATE_CHAR, b'\x01')
        if result:
            print("✅ Lampe allumée!")
        return result
    
    async def set_brightness(self, level):
        """Règle la luminosité (0-254)"""
        # level: 0 = éteint, 254 = max
        data = bytes([level])
        result = await self.send_command(self.HUE_BRIGHTNESS_CHAR, data)
        if result:
            print(f"✅ Luminosité réglée à {int(level/2.54)}%")
        return result
    
    async def set_color(self, red, green, blue):
        """Règle la couleur (RGB)"""
        # Format: bytes [R, G, B]
        data = bytes([red, green, blue])
        result = await self.send_command(self.HUE_COLOR_CHAR, data)
        if result:
            print(f"✅ Couleur réglée: RGB({red},{green},{blue})")
        return result
    
    async def display_menu(self):
        """Affiche le menu pour une lampe sélectionnée"""
        if not self.selected_device:
            print("❌ Aucune lampe sélectionnée")
            return
        
        print(f"\n" + "="*50)
        print(f"💡 CONTRÔLE: {self.selected_device['name']}")
        print("="*50)
        print("1. 🔴 Éteindre")
        print("2. 🟢 Allumer")
        print("3. ⭐ Changer luminosité")
        print("4. 🎨 Changer couleur (RGB)")
        print("5. 🔄 Se reconnecter")
        print("6. ↩️ Retour au scan")
        
        choice = input("\n👉 Votre choix: ")
        
        if choice == "1":
            await self.turn_off()
        elif choice == "2":
            await self.turn_on()
        elif choice == "3":
            try:
                level = int(input("Luminosité (0-100): "))
                level = max(0, min(100, level))
                await self.set_brightness(int(level * 2.54))  # Convert 0-100 -> 0-254
            except:
                print("❌ Entrez un nombre")
        elif choice == "4":
            try:
                print("🎨 Valeurs RGB (0-255)")
                r = int(input("Rouge: "))
                g = int(input("Vert: "))
                b = int(input("Bleu: "))
                await self.set_color(r, g, b)
            except:
                print("❌ Entrez des nombres valides")
        elif choice == "5":
            await self.client.disconnect() if self.client else None
            await self.connect_to_device(self.selected_device['address'])
        elif choice == "6":
            self.selected_device = None
            if self.client:
                await self.client.disconnect()
            return
        else:
            print("❌ Option invalide")
        
        # Petit délai avant de revenir au menu
        await asyncio.sleep(0.5)
        await self.display_menu()
    
    async def run(self):
        """Boucle principale"""
        print("\n" + "="*50)
        print("💡 PHILIPS HUE BLUETOOTH CONTROLLER")
        print("="*50)
        
        while True:
            # Étape 1: Scan
            await self.scan_devices(timeout=5)
            
            if not self.devices:
                print("\n❌ Aucune lampe Hue Bluetooth trouvée.")
                print("   Vérifie que ta lampe est allumée et à proximité")
                retry = input("\n🔍 Relancer le scan? (o/n): ")
                if retry.lower() != 'o':
                    break
                continue
            
            # Étape 2: Sélection
            print("\n" + "="*40)
            print("📋 LAMPES TROUVÉES:")
            for i, dev in enumerate(self.devices, 1):
                print(f"   {i}. {dev['name']} ({dev['address']})")
            print("="*40)
            
            try:
                choice = input("\n👉 Choisis une lampe (1-{}): ".format(len(self.devices)))
                idx = int(choice) - 1
                if 0 <= idx < len(self.devices):
                    self.selected_device = self.devices[idx]
                    
                    # Connexion
                    if await self.connect_to_device(self.selected_device['address']):
                        await self.display_menu()
                    else:
                        print("❌ Connexion échouée")
            except ValueError:
                print("❌ Numéro invalide")


async def main():
    controller = HueBleController()
    await controller.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Au revoir!")