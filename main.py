#!/usr/bin/env python3
# autoscan.py - Scan réseau avec mise à jour auto depuis GitHub

import subprocess, socket, os, sys

VERSION = "1.0"
REPO_URL = "https://raw.githubusercontent.com/TON_USER/TON_REPO/main/scan.py"

def check_update():
    """Vérifie si une nouvelle version existe"""
    try:
        import urllib.request
        print("🔍 Vérification des mises à jour...")
        req = urllib.request.Request(REPO_URL, method='HEAD')
        response = urllib.request.urlopen(req, timeout=3)
        return True
    except:
        return False

def update_script():
    """Met à jour le script"""
    try:
        import urllib.request
        print("📥 Mise à jour en cours...")
        response = urllib.request.urlopen(REPO_URL, timeout=5)
        new_content = response.read().decode()
        
        # Sauvegarde l'ancien
        if os.path.exists(__file__):
            os.rename(__file__, __file__ + ".old")
        
        # Écrit le nouveau
        with open(__file__, 'w') as f:
            f.write(new_content)
        
        print("✅ Mise à jour terminée. Relance le script.")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Erreur: {e}")

def scan():
    """Fonction de scan principale"""
    network = "192.168.1."
    print(f"\n🔍 Scan du réseau {network}0/24...")
    
    for i in range(1, 255):
        ip = f"{network}{i}"
        r = subprocess.run(["ping", "-c", "1", "-W", "1", ip], capture_output=True)
        if r.returncode == 0:
            try:
                name = socket.gethostbyaddr(ip)[0].split('.')[0]
            except:
                name = "?"
            print(f"✅ {ip} - {name}")
    
    print("\n✅ Scan terminé")

def menu():
    while True:
        print("\n" + "="*40)
        print(f"📡 SCAN RÉSEAU v{VERSION}")
        print("="*40)
        print("1. Scanner le réseau")
        print("2. Vérifier les mises à jour")
        print("3. Quitter")
        
        choice = input("\n👉 Choix: ")
        
        if choice == "1":
            scan()
        elif choice == "2":
            if check_update():
                update_script()
            else:
                print("✅ Déjà à jour")
        elif choice == "3":
            break

if __name__ == "__main__":
    menu()