#!/usr/bin/env python3
import gi
import subprocess
import os
from datetime import datetime

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

class CloneApp(Gtk.Window):
    def __init__(self):
        super().__init__(title="LinuxCNC Drive Cloner")
        self.set_default_size(600, 400)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_border_width(10)
        self.set_name("MainWindow")

        self.set_dark_theme()

        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        self.add(grid)

        # Source and target
        self.source_combo = Gtk.ComboBoxText()
        self.target_combo = Gtk.ComboBoxText()
        self.refresh_drives()

        # Folder chooser
        self.folder_button = Gtk.FileChooserButton("Select Backup Folder", Gtk.FileChooserAction.SELECT_FOLDER)

        # File selector for restore
        self.restore_file_button = Gtk.FileChooserButton("Select Backup Image", Gtk.FileChooserAction.OPEN)

        # Buttons
        clone_button = Gtk.Button(label="🡒 Clone to Image")
        restore_button = Gtk.Button(label="🡐 Restore to Drive")
        refresh_button = Gtk.Button(label="↻ Refresh Drives")

        clone_button.connect("clicked", self.clone_drive)
        restore_button.connect("clicked", self.restore_image)
        refresh_button.connect("clicked", self.refresh_drives)

        # Output and progress
        self.progress = Gtk.ProgressBar()
        self.output = Gtk.TextView(editable=False)
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.add(self.output)

        # Layout
        grid.attach(Gtk.Label(label="Source Drive:"), 0, 0, 1, 1)
        grid.attach(self.source_combo, 1, 0, 2, 1)

        grid.attach(Gtk.Label(label="Backup Folder:"), 0, 1, 1, 1)
        grid.attach(self.folder_button, 1, 1, 2, 1)

        grid.attach(clone_button, 1, 2, 1, 1)

        grid.attach(Gtk.Label(label="Backup Image:"), 0, 3, 1, 1)
        grid.attach(self.restore_file_button, 1, 3, 2, 1)

        grid.attach(Gtk.Label(label="Target Drive:"), 0, 4, 1, 1)
        grid.attach(self.target_combo, 1, 4, 2, 1)

        grid.attach(restore_button, 1, 5, 1, 1)
        grid.attach(refresh_button, 2, 5, 1, 1)

        grid.attach(self.progress, 0, 6, 3, 1)
        grid.attach(scroll, 0, 7, 3, 1)

    def set_dark_theme(self):
        screen = Gdk.Screen.get_default()
        provider = Gtk.CssProvider()
        provider.load_from_data(b"""
            #MainWindow {
                background-color: #2e2e2e;
                color: white;
            }
            * {
                background-color: #2e2e2e;
                color: white;
            }
            entry, combobox, button {
                background-color: #3c3c3c;
                color: white;
            }
        """)
        Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def refresh_drives(self, *_):
        self.source_combo.remove_all()
        self.target_combo.remove_all()
        result = subprocess.run(['lsblk', '-dpno', 'NAME,SIZE,TYPE'], stdout=subprocess.PIPE)
        for line in result.stdout.decode().splitlines():
            if 'disk' in line:
                path = line.split()[0]
                self.source_combo.append_text(path)
                self.target_combo.append_text(path)

    def append_output(self, text):
        buffer = self.output.get_buffer()
        end = buffer.get_end_iter()
        buffer.insert(end, text + "\n")
        while Gtk.events_pending():
            Gtk.main_iteration()

    def update_progress(self, fraction, text=None):
        GLib.idle_add(self.progress.set_fraction, fraction)
        if text:
            GLib.idle_add(self.progress.set_text, text)

    def clone_drive(self, _):
        source = self.source_combo.get_active_text()
        folder = self.folder_button.get_filename()
        if not source or not folder:
            self.append_output("❗ Select a source drive and backup folder.")
            return
        date_str = datetime.now().strftime("%Y-%m-%d-%H%M")
        filename = os.path.join(folder, f"linuxcnc-{date_str}.img.gz")
        command = ['sudo', 'partclone.ext4', '-c', '-s', source]
        gzip_cmd = ['gzip']

        self.append_output(f"📀 Backing up {source} → {filename}")
        self.run_with_progress(command, gzip_cmd, filename)

    def restore_image(self, _):
        image = self.restore_file_button.get_filename()
        target = self.target_combo.get_active_text()
        if not image or not target:
            self.append_output("❗ Select an image and a target drive.")
            return

        if image.endswith('.gz'):
            gunzip_cmd = ['gunzip', '-c', image]
            partclone_cmd = ['sudo', 'partclone.ext4', '-r', '-s', '-', '-o', target]
            self.append_output(f"📦 Restoring {image} → {target}")
            self.run_with_progress(gunzip_cmd, partclone_cmd)
        else:
            command = ['sudo', 'partclone.ext4', '-r', '-s', image, '-o', target]
            self.append_output(f"📦 Restoring {image} → {target}")
            self.run_with_progress(command)

    def run_with_progress(self, *commands_and_output):
        self.progress.set_fraction(0.0)
        self.progress.set_text("Starting...")
        output_file = None

        if len(commands_and_output) == 3:
            cmd1, cmd2, output_file = commands_and_output
            with open(output_file, 'wb') as outfile:
                p1 = subprocess.Popen(cmd1, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                p2 = subprocess.Popen(cmd2, stdin=p1.stdout, stdout=outfile)
                p1.stdout.close()
                self.monitor_output(p1)
                p2.wait()
        else:
            cmd = commands_and_output[0]
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            self.monitor_output(p)

    def monitor_output(self, process):
        buffer = self.output.get_buffer()
        for line in process.stdout:
            line = line.strip()
            self.append_output(line)
            percent = self.extract_progress(line)
            if percent is not None:
                self.update_progress(percent / 100.0, f"{percent:.0f}%")
        process.wait()
        self.update_progress(1.0, "✔ Done")

    def extract_progress(self, line):
        # Extract 'xx%' from partclone output
        if "%" in line:
            try:
                percent = int(line.split('%')[0].split()[-1])
                return percent
            except:
                return None
        return None

if __name__ == "__main__":
    app = CloneApp()
    app.connect("destroy", Gtk.main_quit)
    app.show_all()
    Gtk.main()
