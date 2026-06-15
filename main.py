#!/usr/bin/env python3
"""
tv_control.py - Contrôle TV via réseau local (fonctionne sur iSH)
"""

import socket
import json
import sys

class TVController:
    def __init__(self, tv_ip):
        self.tv_ip = tv_ip
        
    def wake_on_lan(self, mac_address):
        """Envoie un paquet magique pour allumer la TV"""
        mac_bytes = bytes.fromhex(mac_address.replace(':', ''))
        magic_packet = b'\xff' * 6 + mac_bytes * 16
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(magic_packet, ('<broadcast>', 9))
        sock.close()
        print("✅ Paquet magique envoyé")
    
    def send_http_command(self, endpoint, payload=None):
        """Envoie une commande HTTP à la TV"""
        # Exemple pour LG WebOS
        import urllib.request
        import base64
        
        url = f"http://{self.tv_ip}:8080/{endpoint}"
        req = urllib.request.Request(url)
        
        if payload:
            req.add_header('Content-Type', 'application/json')
            data = json.dumps(payload).encode()
            response = urllib.request.urlopen(req, data=data)
        else:
            response = urllib.request.urlopen(req)
        
        return response.read()
    
    def power_off(self):
        """Éteint la TV via réseau"""
        try:
            # Exemple commande LG WebOS
            self.send_http_command("roap/api/command/system/volume_up")
            print("✅ Commande envoyée")
        except:
            print("❌ Non supporté par cette TV")

# Utilisation
tv = TVController("192.168.1.100")  # IP de ta TV
tv.wake_on_lan("AA:BB:CC:DD:EE:FF")