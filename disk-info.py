#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script d'analyse SMART - Disques Linux
Application Tkinter avec interface graphique pour analyser les disques via smartctl
"""

import re
import subprocess
import os
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

class DiskInfoApp(tk.Tk):
    """
    Fenêtre principale de l'application d'analyse SMART
    """
    
    def __init__(self):
        super().__init__()
        
        # Configuration de la fenêtre principale
        self.title("Analyseur SMART - Disques Linux")
        self.geometry("900x600")
        self.minsize(700, 500)
        
        # Variable globale pour stocker le mot de passe sudo
        self.sudo_password = None
        
        # Chargement de l'icône disk-info.png dans le même répertoire que le script (sans Pillow)
        script_dir = os.path.dirname(os.path.realpath(__file__))
        icon_path = os.path.join(script_dir, "disk-info.png")
        if os.path.exists(icon_path):
            try:
                self.icon_image = tk.PhotoImage(file=icon_path)
                self.iconphoto(True, self.icon_image)
            except Exception as e:
                print(f"Impossible de charger l'icône : {e}")
        
        # Style ttk
        self.style = ttk.Style(self)
        self.style.theme_use('clam')
        
        # Configuration globale des polices
        self.style.configure('.', font=('Helvetica', 11))
        self.style.configure('TButton', font=('Helvetica', 11, 'bold'))
        self.style.configure('TLabel', font=('Helvetica', 11))
        self.style.configure('Labelframe.Label', font=('Helvetica', 11, 'bold'))
        
        # Dictionnaires pour stocker les éléments d'interface liés aux disques
        self.disk_map = {}
        self.summary_vars = {}
        
        # Initialisation de l'interface utilisateur
        self.init_ui()

    def ask_sudo_password(self):
        """Demande et mémorise le mot de passe sudo."""
        if self.sudo_password is None:
            self.sudo_password = simpledialog.askstring(
                "Mot de passe requis", 
                "Entrez votre mot de passe administrateur (sudo) :", 
                show='*'
            )
        return self.sudo_password

    def get_block_devices(self):
        """Récupère la liste des disques via lsblk."""
        try:
            result = subprocess.run(
                ["lsblk", "-d", "-n", "-o", "NAME,SIZE,MODEL"],
                capture_output=True,
                text=True,
                check=True
            )
            devices = []
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    parts = line.split(maxsplit=2)
                    dev_name = f"/dev/{parts[0]}"
                    details = " ".join(parts[1:]) if len(parts) > 1 else ""
                    devices.append((dev_name, f"{dev_name} ({details})"))
            return devices
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de lister les disques :\n{e}")
            return []

    def clean_temperature_value(self, raw_val):
        """Nettoie la chaîne de température pour ne garder que la valeur numérique."""
        cleaned = re.sub(r'(?i)\s*celsius', '', raw_val)
        cleaned = re.sub(r'\(.*?\)', '', cleaned)
        return cleaned.strip()

    def run_smartctl(self, event=None):
        """Exécute smartctl avec le protocole adapté (SATA / NVMe / USB) et gère les erreurs."""
        selected_display = self.combo_disks.get()
        if not selected_display or not self.disk_map or selected_display not in self.disk_map:
            return

        dev_path = self.disk_map[selected_display]

        # Effacement de la zone de texte brute
        self.text_output.config(state="normal")
        self.text_output.delete("1.0", tk.END)

        # Remise à zéro des indicateurs du résumé
        for attr_id in self.summary_vars:
            self.summary_vars[attr_id].config(text="N/A")

        pwd = self.ask_sudo_password()
        if not pwd:
            self.text_output.insert(tk.END, "Annulé : Mot de passe sudo requis.")
            self.text_output.config(state="disabled")
            return

        try:
            output = ""
            if "nvme" in dev_path.lower():
                cmds = [
                    f"echo {pwd} | sudo -S smartctl -d nvme -A {dev_path}",
                    f"echo {pwd} | sudo -S smartctl -d nvme -T permissive -A {dev_path}"
                ]
            else:
                cmds = [
                    f"echo {pwd} | sudo -S smartctl -d sat -A {dev_path}",
                    f"echo {pwd} | sudo -S smartctl -d nvme -A {dev_path}",
                    f"echo {pwd} | sudo -S smartctl -d nvme -T permissive -A {dev_path}",
                    f"echo {pwd} | sudo -S smartctl -A {dev_path}"
                ]

            for cmd in cmds:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                output = result.stdout if result.stdout else result.stderr
                if "Read Device Identity failed" not in output and "A mandatory SMART command failed" not in output and "No such device" not in output:
                    break

            if not output.strip():
                output = "Aucune donnée retournée par smartctl."

            self.text_output.insert(tk.END, output)

            # Analyse et extraction des indicateurs
            for line in output.split("\n"):
                line_lower = line.lower()
                
                # --- 1. Gestion des disques NVMe ---
                if "power on hours" in line_lower:
                    parts = line.split(":")
                    if len(parts) > 1:
                        self.summary_vars["9"].config(text=parts[1].strip())
                elif "power cycles" in line_lower:
                    parts = line.split(":")
                    if len(parts) > 1:
                        self.summary_vars["12"].config(text=parts[1].strip())
                elif line_lower.startswith("temperature:") or ("temperature:" in line_lower and "sensor" not in line_lower):
                    parts = line.split(":")
                    if len(parts) > 1:
                        temp_clean = self.clean_temperature_value(parts[1])
                        self.summary_vars["194"].config(text=temp_clean)
                elif "percentage used" in line_lower:
                    parts = line.split(":")
                    if len(parts) > 1:
                        val_str = parts[1].strip().replace("%", "")
                        try:
                            used_val = int(val_str)
                            health_val = max(0, 100 - used_val)
                            self.summary_vars["231"].config(text=str(health_val))
                        except ValueError:
                            self.summary_vars["231"].config(text=parts[1].strip().replace("%", ""))

                # --- 2. Gestion des disques SATA ---
                parts = line.split()
                if parts and parts[0].isdigit():
                    attr_id = parts[0]
                    if attr_id in self.summary_vars:
                        if attr_id == "9" and self.summary_vars["9"]["text"] == "N/A":
                            self.summary_vars["9"].config(text=parts[-1])
                        elif attr_id == "12" and self.summary_vars["12"]["text"] == "N/A":
                            self.summary_vars["12"].config(text=parts[-1])
                        elif attr_id == "194":
                            raw_val = " ".join(parts[9:]) if len(parts) >= 10 else parts[-1]
                            self.summary_vars["194"].config(text=self.clean_temperature_value(raw_val))
                        elif attr_id == "231" and self.summary_vars["231"]["text"] == "N/A":
                            self.summary_vars["231"].config(text=parts[-1].replace("%", ""))

        except Exception as e:
            self.text_output.insert(tk.END, f"Erreur lors de l'exécution de smartctl :\n{e}")

        self.text_output.config(state="disabled")

    def init_ui(self):
        """Initialise l'interface utilisateur"""
        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 1. Cadre supérieur pour la sélection du disque
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(top_frame, text="Disques :", font=("Helvetica", 11, "bold")).pack(side=tk.LEFT, padx=(0, 10))

        devices = self.get_block_devices()
        self.disk_map = {display: dev for dev, display in devices}
        disk_options = list(self.disk_map.keys())

        self.combo_disks = ttk.Combobox(top_frame, values=disk_options, state="readonly", width=50)
        self.combo_disks.pack(side=tk.LEFT, padx=5)
        self.combo_disks.bind("<<ComboboxSelected>>", self.run_smartctl)

        if disk_options:
            self.combo_disks.current(0)

        # 2. Cadre intermédiaire : Résumé horizontal épuré
        summary_frame = tk.LabelFrame(main_frame, text=" Indicateurs Clés ", font=("Helvetica", 11, "bold"), padx=10, pady=10)
        summary_frame.pack(fill=tk.X, pady=(0, 10))

        tracked_attributes = [
            ("9", "Durée de fonctionnement (heures)"),
            ("12", "Cycles d'alimentation"),
            ("194", "Température (°C)"),
            ("231", "Etat de santé (%)")
        ]

        for i, (attr_id, label_text) in enumerate(tracked_attributes):
            col_frame = tk.Frame(summary_frame, bd=1, relief=tk.GROOVE, padx=5, pady=5, bg="white")
            col_frame.grid(row=0, column=i, padx=4, sticky="nsew")
            summary_frame.grid_columnconfigure(i, weight=1)
            
            lbl_name = tk.Label(col_frame, text=label_text, font=("Helvetica", 9, "bold"), fg="#333", bg="white", justify="center")
            lbl_name.pack()
            
            lbl_val = tk.Label(col_frame, text="N/A", font=("Helvetica", 12, "bold"), fg="#1c733c", bg="white")
            lbl_val.pack(pady=(3, 0))
            
            self.summary_vars[attr_id] = lbl_val

        # 3. Cadre principal pour l'affichage de la sortie brute SMART
        frame_output = tk.LabelFrame(main_frame, text=" Informations SMART ", font=("Helvetica", 11, "bold"), padx=10, pady=10)
        frame_output.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        text_container = ttk.Frame(frame_output)
        text_container.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(text_container, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.text_output = tk.Text(
            text_container,
            wrap=tk.NONE,
            font=("Courier", 10),
            yscrollcommand=scrollbar.set,
            bg="#1e1e1e",
            fg="#00ff00",
            insertbackground="white"
        )
        self.text_output.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.text_output.yview)

        # Bouton fermer
        close_button = ttk.Button(main_frame, text="Fermer", command=self.destroy)
        close_button.pack(side=tk.RIGHT, anchor="e")

        # Lancer la première lecture si un disque est sélectionné
        if disk_options:
            self.run_smartctl()

if __name__ == "__main__":
    app = DiskInfoApp()
    app.mainloop()
